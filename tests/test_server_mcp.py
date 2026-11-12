import base64
import hashlib
import html
import json
import re
import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient

_test_directory = tempfile.TemporaryDirectory()
TEST_ISSUER = "http://127.0.0.1:8000"
os.environ.pop("DATABASE_URL", None)
os.environ["TASKSTACK_DB_PATH"] = os.path.join(
    _test_directory.name, "test-mcp.sqlite"
)
os.environ["TASKSTACK_PUBLIC_URL"] = TEST_ISSUER

import server
import mcp_oauth


class McpDiscoveryTests(unittest.TestCase):
    def setUp(self):
        server.init_db()
        self.client = TestClient(
            server.app, base_url=TEST_ISSUER, follow_redirects=False
        )

    def tearDown(self):
        self.client.close()

    def test_protected_resource_metadata_discloses_authorization_server(self):
        response = self.client.get("/.well-known/oauth-protected-resource/mcp")

        self.assertEqual(response.status_code, 200)
        metadata = response.json()
        self.assertEqual(metadata["resource"], f"{TEST_ISSUER}/mcp")
        self.assertEqual(
            metadata["authorization_servers"], [TEST_ISSUER]
        )
        self.assertEqual(
            metadata["scopes_supported"],
            ["tasks:read", "tasks:write", "tasks:delete"],
        )

    def test_authorization_server_metadata_advertises_pkce_and_registration(self):
        response = self.client.get("/.well-known/oauth-authorization-server")

        self.assertEqual(response.status_code, 200)
        metadata = response.json()
        self.assertEqual(metadata["issuer"], TEST_ISSUER)
        self.assertEqual(
            metadata["authorization_endpoint"],
            f"{TEST_ISSUER}/oauth/authorize",
        )
        self.assertEqual(
            metadata["token_endpoint"], f"{TEST_ISSUER}/oauth/token"
        )
        self.assertEqual(
            metadata["registration_endpoint"],
            f"{TEST_ISSUER}/oauth/register",
        )
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])

    def test_authorization_server_uses_render_public_url_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "TASKSTACK_PUBLIC_URL": "",
                "RENDER_EXTERNAL_URL": "https://taskstack.example.onrender.com",
            },
        ):
            response = self.client.get("/.well-known/oauth-authorization-server")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["issuer"], "https://taskstack.example.onrender.com"
        )

    def test_local_default_issuer_is_shared_by_oauth_and_mcp(self):
        with patch.dict(
            os.environ,
            {"TASKSTACK_PUBLIC_URL": "", "RENDER_EXTERNAL_URL": ""},
        ):
            issuer = mcp_oauth.public_issuer()

        self.assertEqual(issuer, TEST_ISSUER)
        self.assertEqual(server._mcp_issuer, TEST_ISSUER)

    def test_public_client_registration_returns_client_id_and_exact_redirects(self):
        response = self.client.post(
            "/oauth/register",
            json={
                "client_name": "TaskStack integration test",
                "redirect_uris": ["http://127.0.0.1:49152/oauth/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )

        self.assertEqual(response.status_code, 201)
        registration = response.json()
        self.assertTrue(registration["client_id"])
        self.assertEqual(
            registration["redirect_uris"],
            ["http://127.0.0.1:49152/oauth/callback"],
        )
        self.assertNotIn("client_secret", registration)

    def test_public_client_registration_rejects_non_loopback_http_redirect(self):
        response = self.client.post(
            "/oauth/register",
            json={
                "client_name": "Untrusted redirect test",
                "redirect_uris": ["http://attacker.example/callback"],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client_metadata")


class McpOAuthFlowTests(unittest.TestCase):
    def setUp(self):
        server.init_db()
        with server.connect_db() as conn:
            existing_tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in (
                "mcp_oauth_codes",
                "mcp_oauth_refresh_tokens",
                "mcp_oauth_access_tokens",
                "mcp_oauth_grants",
                "mcp_oauth_authorization_requests",
                "mcp_oauth_clients",
                "mcp_task_delete_confirmations",
                "sessions",
                "tasks",
                "users",
            ):
                if table in existing_tables:
                    conn.execute(f"DELETE FROM {table}")
        self.client = TestClient(
            server.app, base_url=TEST_ISSUER, follow_redirects=False
        )

    def tearDown(self):
        self.client.close()

    def register_client(self):
        response = self.client.post(
            "/oauth/register",
            json={
                "client_name": "TaskStack OAuth integration test",
                "redirect_uris": ["http://127.0.0.1:49152/oauth/callback"],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["client_id"]

    @staticmethod
    def hidden_fields(page):
        return {
            "request_id": re.search(
                r'name="request_id" value="([^"]+)"', page
            ).group(1),
            "csrf_token": re.search(
                r'name="csrf_token" value="([^"]+)"', page
            ).group(1),
        }

    def begin_authorization(self, client_id, verifier):
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        response = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "state": "opaque-client-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "tasks:read tasks:write tasks:delete",
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        self.assertEqual(response.status_code, 200)
        return self.hidden_fields(response.text)

    def test_authorization_code_requires_login_consent_and_pkce(self):
        client_id = self.register_client()
        verifier = "A" * 43
        pending = self.begin_authorization(client_id, verifier)

        with server.connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("mcp-user", server.hash_password("correct horse battery staple")),
            )

        login = self.client.post(
            "/oauth/authorize/login",
            data={
                **pending,
                "username": "mcp-user",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("TaskStack OAuth integration test", login.text)
        self.assertIn("http://127.0.0.1:49152/oauth/callback", login.text)
        consent = self.hidden_fields(login.text)

        approved = self.client.post(
            "/oauth/authorize/consent",
            data={**consent, "decision": "approve"},
        )
        self.assertEqual(approved.status_code, 302)
        self.assertIn("no-store", approved.headers["cache-control"].lower())
        self.assertEqual(approved.headers["pragma"].lower(), "no-cache")
        callback = urlsplit(approved.headers["location"])
        callback_query = parse_qs(callback.query)
        self.assertEqual(callback.netloc, "127.0.0.1:49152")
        self.assertEqual(callback_query["state"], ["opaque-client-state"])
        code = callback_query["code"][0]

        token = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "code": code,
                "code_verifier": verifier,
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        self.assertEqual(token.status_code, 200)
        self.assertIn("no-store", token.headers["cache-control"].lower())
        self.assertEqual(token.headers["pragma"].lower(), "no-cache")
        tokens = token.json()
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertEqual(tokens["expires_in"], 3600)
        self.assertTrue(tokens["access_token"])
        self.assertTrue(tokens["refresh_token"])

        api_response = self.client.get(
            "/tasks",
            params={"user_id": 1},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        self.assertEqual(api_response.status_code, 401)
        with server.connect_db() as conn:
            conn.execute(
                "UPDATE mcp_oauth_access_tokens SET expires_at = 0 WHERE token_hash = ?",
                (hashlib.sha256(tokens["access_token"].encode("ascii")).hexdigest(),),
            )
        self.assertIsNone(
            mcp_oauth.DatabaseTokenVerifier(server.connect_db)._verify_token(
                tokens["access_token"]
            )
        )

    def test_authorization_rejects_missing_pkce_and_wrong_resource(self):
        client_id = self.register_client()
        missing_pkce = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "state": "state",
                "code_challenge": "",
                "code_challenge_method": "S256",
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        wrong_resource = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "state": "state",
                "code_challenge": "A" * 43,
                "code_challenge_method": "S256",
                "resource": "https://other.example/mcp",
            },
        )

        self.assertEqual(missing_pkce.status_code, 400)
        self.assertEqual(wrong_resource.status_code, 400)

    def test_denial_and_csrf_replay_do_not_create_a_grant(self):
        client_id = self.register_client()
        pending = self.begin_authorization(client_id, "D" * 43)
        with server.connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("mcp-denial-user", server.hash_password("correct horse battery staple")),
            )
        login = self.client.post(
            "/oauth/authorize/login",
            data={
                **pending,
                "username": "mcp-denial-user",
                "password": "correct horse battery staple",
            },
        )
        consent = self.hidden_fields(login.text)
        invalid_csrf = self.client.post(
            "/oauth/authorize/consent",
            data={**consent, "csrf_token": "Z" * 43, "decision": "approve"},
        )
        denied = self.client.post(
            "/oauth/authorize/consent",
            data={**consent, "decision": "deny"},
        )
        replay = self.client.post(
            "/oauth/authorize/consent",
            data={**consent, "decision": "approve"},
        )

        self.assertEqual(invalid_csrf.status_code, 400)
        self.assertEqual(denied.status_code, 302)
        callback_query = parse_qs(urlsplit(denied.headers["location"]).query)
        self.assertEqual(callback_query["error"], ["access_denied"])
        self.assertEqual(callback_query["state"], ["opaque-client-state"])
        self.assertIn("no-store", denied.headers["cache-control"].lower())
        self.assertEqual(replay.status_code, 400)
        with server.connect_db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS count FROM mcp_oauth_grants")
                .fetchone()["count"],
                0,
            )

    def test_refresh_tokens_rotate_and_revocation_invalidates_access(self):
        client_id = self.register_client()
        verifier = "B" * 43
        pending = self.begin_authorization(client_id, verifier)
        with server.connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("mcp-user", server.hash_password("correct horse battery staple")),
            )
        login = self.client.post(
            "/oauth/authorize/login",
            data={
                **pending,
                "username": "mcp-user",
                "password": "correct horse battery staple",
            },
        )
        consent = self.hidden_fields(login.text)
        approved = self.client.post(
            "/oauth/authorize/consent",
            data={**consent, "decision": "approve"},
        )
        code = parse_qs(urlsplit(approved.headers["location"]).query)["code"][0]
        initial = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "code": code,
                "code_verifier": verifier,
                "resource": f"{TEST_ISSUER}/mcp",
            },
        ).json()

        refreshed = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": initial["refresh_token"],
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        replay = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": initial["refresh_token"],
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("no-store", refreshed.headers["cache-control"].lower())
        self.assertEqual(refreshed.headers["pragma"].lower(), "no-cache")
        self.assertNotEqual(
            refreshed.json()["refresh_token"], initial["refresh_token"]
        )
        self.assertEqual(replay.status_code, 400)

        revoked = self.client.post(
            "/oauth/revoke",
            data={
                "client_id": client_id,
                "token": refreshed.json()["refresh_token"],
                "token_type_hint": "refresh_token",
            },
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertIn("no-store", revoked.headers["cache-control"].lower())
        after_revoke = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refreshed.json()["refresh_token"],
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        self.assertEqual(after_revoke.status_code, 400)


class McpTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        cls.client = TestClient(
            server.app, base_url=TEST_ISSUER, follow_redirects=False
        )
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.next_request_id = 2
        with server.connect_db() as conn:
            existing_tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in (
                "mcp_oauth_codes",
                "mcp_oauth_refresh_tokens",
                "mcp_oauth_access_tokens",
                "mcp_oauth_grants",
                "mcp_oauth_authorization_requests",
                "mcp_oauth_clients",
                "mcp_task_delete_approvals",
                "mcp_task_delete_confirmations",
                "task_group_shares",
                "group_members",
                "groups",
                "sessions",
                "tasks",
                "users",
            ):
                if table in existing_tables:
                    conn.execute(f"DELETE FROM {table}")

    @staticmethod
    def hidden_fields(page):
        return {
            "request_id": re.search(
                r'name="request_id" value="([^"]+)"', page
            ).group(1),
            "csrf_token": re.search(
                r'name="csrf_token" value="([^"]+)"', page
            ).group(1),
        }

    def issue_access_token(
        self, username="mcp-transport-user",
        scopes="tasks:read tasks:write tasks:delete",
    ):
        password = "correct horse battery staple"
        with server.connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, server.hash_password(password)),
            )
        registration = self.client.post(
            "/oauth/register",
            json={
                "client_name": "MCP transport test",
                "redirect_uris": ["http://127.0.0.1:49152/oauth/callback"],
            },
        )
        client_id = registration.json()["client_id"]
        verifier = "C" * 43
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        authorization = self.client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "state": "transport-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": scopes,
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        login = self.client.post(
            "/oauth/authorize/login",
            data={
                **self.hidden_fields(authorization.text),
                "username": username,
                "password": password,
            },
        )
        consent = self.client.post(
            "/oauth/authorize/consent",
            data={
                **self.hidden_fields(login.text),
                "decision": "approve",
            },
        )
        code = parse_qs(urlsplit(consent.headers["location"]).query)["code"][0]
        token = self.client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:49152/oauth/callback",
                "code": code,
                "code_verifier": verifier,
                "resource": f"{TEST_ISSUER}/mcp",
            },
        )
        self.assertEqual(token.status_code, 200)
        return token.json()["access_token"]

    def open_mcp_session(self, access_token):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
        }
        initialized = self.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )
        self.assertEqual(initialized.status_code, 200, initialized.text)
        headers["MCP-Session-Id"] = initialized.headers["mcp-session-id"]
        headers["MCP-Protocol-Version"] = initialized.json()["result"][
            "protocolVersion"
        ]
        ready = self.client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        self.assertEqual(ready.status_code, 202, ready.text)
        return headers

    def call_tool(self, headers, name, arguments, request_id=None):
        if request_id is None:
            request_id = self.next_request_id
            self.next_request_id += 1
        response = self.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    @staticmethod
    def csrf_field(page):
        return re.search(
            r'name="csrf_token" value="([^"]+)"', page
        ).group(1)

    def login_for_delete_preview(self, preview, username, password):
        confirmation_path = urlsplit(preview["confirmation_url"]).path
        page = self.client.get(confirmation_path)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn(f"Task ID: <strong>{preview['task']['id']}</strong>", page.text)
        self.assertIn(html.escape(preview["task"]["title"]), page.text)
        csrf_token = self.csrf_field(page.text)

        login = self.client.post(
            f"{confirmation_path}/login",
            data={
                "csrf_token": csrf_token,
                "username": username,
                "password": password,
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        return confirmation_path, login

    def approve_delete_preview(self, preview, username, password):
        confirmation_path, login = self.login_for_delete_preview(
            preview, username, password
        )
        self.assertIn("Approve deletion", login.text)
        approval = self.client.post(
            f"{confirmation_path}/approve",
            data={
                "csrf_token": self.csrf_field(login.text),
                "decision": "approve",
            },
        )
        self.assertEqual(approval.status_code, 200, approval.text)
        self.assertIn("approved", approval.text.lower())

    def test_browser_denial_prevents_mcp_delete(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-delete-deny"))
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Keep the task unless the user approves"},
        )["structuredContent"]
        preview = self.call_tool(
            owner, "prepare_task_delete", {"task_id": created["id"]}
        )["structuredContent"]
        confirmation_path, login = self.login_for_delete_preview(
            preview, "mcp-delete-deny", "correct horse battery staple"
        )
        denied = self.client.post(
            f"{confirmation_path}/approve",
            data={
                "csrf_token": self.csrf_field(login.text),
                "decision": "deny",
            },
        )
        attempted_delete = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": True,
            },
        )

        self.assertIn("Deletion cancelled", denied.text)
        self.assertTrue(attempted_delete["isError"])
        with server.connect_db() as conn:
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM tasks WHERE id = ?", (created["id"],)
                ).fetchone()
            )

    def test_mcp_streamable_http_requires_an_oauth_access_token(self):
        response = self.client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn(
            "resource_metadata",
            response.headers.get("www-authenticate", ""),
        )

    def test_mcp_streamable_http_rejects_untrusted_origin(self):
        response = self.client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "Origin": "https://untrusted.example",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "untrusted-client", "version": "1.0"},
                },
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_oauth_client_can_initialize_and_list_mcp_tools(self):
        access_token = self.issue_access_token()
        session_headers = self.open_mcp_session(access_token)
        tools = self.client.post(
            "/mcp",
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )

        self.assertEqual(tools.status_code, 200, tools.text)
        self.assertIn(
            "list_tasks",
            [tool["name"] for tool in tools.json()["result"]["tools"]],
        )

    def test_create_task_preserves_natural_language_deadline(self):
        session = self.open_mcp_session(self.issue_access_token())
        result = self.call_tool(
            session,
            "create_task",
            {
                "title": "Prepare the renewal summary before Friday's review",
                "deadline": "next Friday before the 3 pm review",
                "priority": "high",
                "category": "Planning",
            },
        )

        self.assertFalse(result.get("isError"))
        task = result["structuredContent"]
        self.assertEqual(
            task["title"], "Prepare the renewal summary before Friday's review"
        )
        self.assertEqual(task["deadline"], "next Friday before the 3 pm review")
        self.assertEqual(task["priority"], "high")
        self.assertEqual(task["category"], "Planning")
        self.assertNotIn("user_id", task)

    def test_scoped_consent_allows_read_but_denies_task_creation(self):
        session = self.open_mcp_session(
            self.issue_access_token("mcp-read-only", scopes="tasks:read")
        )
        listed = self.call_tool(session, "list_tasks", {})
        created = self.call_tool(
            session,
            "create_task",
            {"title": "This write must be denied"},
        )

        self.assertFalse(listed.get("isError"))
        self.assertEqual(listed["structuredContent"]["result"], [])
        self.assertTrue(created["isError"])

    def test_shared_tasks_are_visible_only_to_users_with_access(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-owner"))
        recipient = self.open_mcp_session(
            self.issue_access_token("mcp-recipient")
        )
        outsider = self.open_mcp_session(self.issue_access_token("mcp-outsider"))
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Coordinate the release handoff"},
        )["structuredContent"]
        with server.connect_db() as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-owner",)
            ).fetchone()["id"]
            recipient_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-recipient",)
            ).fetchone()["id"]
            self.assertEqual(created["id"], conn.execute(
                "SELECT id FROM tasks WHERE user_id = ?", (owner_id,)
            ).fetchone()["id"])
            conn.execute(
                "INSERT INTO task_shares (task_id, user_id) VALUES (?, ?)",
                (created["id"], recipient_id),
            )

        recipient_tasks = self.call_tool(recipient, "list_tasks", {})[
            "structuredContent"
        ]["result"]
        outsider_tasks = self.call_tool(outsider, "list_tasks", {})[
            "structuredContent"
        ]["result"]
        recipient_task = self.call_tool(
            recipient, "get_task", {"task_id": created["id"]}
        )
        outsider_task = self.call_tool(
            outsider, "get_task", {"task_id": created["id"]}
        )

        self.assertIn(created["id"], [task["id"] for task in recipient_tasks])
        self.assertEqual(outsider_tasks, [])
        self.assertEqual(recipient_task["structuredContent"]["id"], created["id"])
        self.assertTrue(outsider_task["isError"])

    def test_group_shared_tasks_are_visible_to_members_only(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-group-owner"))
        member = self.open_mcp_session(
            self.issue_access_token("mcp-group-member")
        )
        outsider = self.open_mcp_session(
            self.issue_access_token("mcp-group-outsider")
        )
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Coordinate the shared group handoff"},
        )["structuredContent"]

        with server.connect_db() as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("mcp-group-owner",),
            ).fetchone()["id"]
            member_id = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("mcp-group-member",),
            ).fetchone()["id"]
            group_id = conn.execute(
                "INSERT INTO groups (name, creator_id) VALUES (?, ?)",
                ("MCP test group", owner_id),
            ).lastrowid
            conn.execute(
                "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                (group_id, member_id),
            )
            conn.execute(
                "INSERT INTO task_group_shares (task_id, group_id) VALUES (?, ?)",
                (created["id"], group_id),
            )

        member_tasks = self.call_tool(member, "list_tasks", {})[
            "structuredContent"
        ]["result"]
        outsider_tasks = self.call_tool(outsider, "list_tasks", {})[
            "structuredContent"
        ]["result"]
        member_task = self.call_tool(
            member, "get_task", {"task_id": created["id"]}
        )
        outsider_task = self.call_tool(
            outsider, "get_task", {"task_id": created["id"]}
        )

        self.assertIn(created["id"], [task["id"] for task in member_tasks])
        self.assertEqual(outsider_tasks, [])
        self.assertEqual(member_task["structuredContent"]["id"], created["id"])
        self.assertTrue(outsider_task["isError"])

    def test_shared_user_can_change_status_but_only_owner_edits_task_fields(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-owner"))
        recipient = self.open_mcp_session(
            self.issue_access_token("mcp-recipient")
        )
        created = self.call_tool(
            owner,
            "create_task",
            {
                "title": "Confirm the shipment",
                "deadline": "before the end of the month",
            },
        )["structuredContent"]
        with server.connect_db() as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-owner",)
            ).fetchone()["id"]
            recipient_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-recipient",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO task_shares (task_id, user_id) VALUES (?, ?)",
                (created["id"], recipient_id),
            )

        status_update = self.call_tool(
            recipient, "update_task", {"task_id": created["id"], "status": 1}
        )
        forbidden_edit = self.call_tool(
            recipient,
            "update_task",
            {"task_id": created["id"], "title": "Change by recipient"},
        )
        owner_edit = self.call_tool(
            owner,
            "update_task",
            {
                "task_id": created["id"],
                "title": "Confirm the international shipment",
                "deadline": "before month-end, local office time",
            },
        )

        self.assertFalse(status_update.get("isError"))
        self.assertEqual(status_update["structuredContent"]["status"], 1)
        self.assertTrue(forbidden_edit["isError"])
        self.assertFalse(owner_edit.get("isError"))
        self.assertEqual(
            owner_edit["structuredContent"]["title"],
            "Confirm the international shipment",
        )
        with server.connect_db() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (created["id"],)
            ).fetchone()
            self.assertEqual(task["user_id"], owner_id)
            self.assertEqual(task["status"], 1)
            self.assertEqual(
                task["title"], "Confirm the international shipment"
            )
            self.assertEqual(
                task["deadline"], "before month-end, local office time"
            )

    def test_delete_requires_owner_bound_explicit_single_use_confirmation(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-owner"))
        recipient = self.open_mcp_session(
            self.issue_access_token("mcp-recipient")
        )
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Archive <script>alert(1)</script> the signed agreement"},
        )["structuredContent"]
        with server.connect_db() as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-owner",)
            ).fetchone()["id"]
            recipient_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("mcp-recipient",)
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO task_shares (task_id, user_id) VALUES (?, ?)",
                (created["id"], recipient_id),
            )

        prepared = self.call_tool(
            owner, "prepare_task_delete", {"task_id": created["id"]}
        )
        preview = prepared["structuredContent"]
        confirmation_path = urlsplit(preview["confirmation_url"]).path
        initial_page = self.client.get(confirmation_path)
        initial_csrf = self.csrf_field(initial_page.text)
        wrong_account = self.client.post(
            f"{confirmation_path}/login",
            data={
                "csrf_token": initial_csrf,
                "username": "mcp-recipient",
                "password": "correct horse battery staple",
            },
        )
        replayed_csrf = self.client.post(
            f"{confirmation_path}/login",
            data={
                "csrf_token": initial_csrf,
                "username": "mcp-owner",
                "password": "correct horse battery staple",
            },
        )
        unapproved = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": True,
            },
        )
        with server.connect_db() as conn:
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM tasks WHERE id = ?", (created["id"],)
                ).fetchone()
            )
        self.approve_delete_preview(
            preview, "mcp-owner", "correct horse battery staple"
        )
        wrong_user = self.call_tool(
            recipient,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": True,
            },
        )
        declined = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": False,
            },
        )
        confirmed = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": True,
            },
        )
        replay = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": preview["confirmation_token"],
                "confirm": True,
            },
        )

        self.assertIn("Archive <script>", preview["task"]["title"])
        self.assertIn("&lt;script&gt;", initial_page.text)
        self.assertNotIn("<script>", initial_page.text)
        self.assertEqual(preview["task"]["id"], created["id"])
        self.assertIn("Unable to verify this TaskStack account", wrong_account.text)
        self.assertEqual(replayed_csrf.status_code, 400)
        self.assertTrue(unapproved["isError"])
        self.assertTrue(wrong_user["isError"])
        self.assertTrue(declined["isError"])
        self.assertFalse(confirmed.get("isError"))
        self.assertTrue(replay["isError"])
        with server.connect_db() as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM tasks WHERE id = ?", (created["id"],)
                ).fetchone()
            )

    def test_delete_confirmation_expires_and_rejects_changed_task_snapshot(self):
        owner = self.open_mcp_session(self.issue_access_token("mcp-owner"))
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Review the contract draft"},
        )["structuredContent"]
        stale = self.call_tool(
            owner, "prepare_task_delete", {"task_id": created["id"]}
        )["structuredContent"]
        self.approve_delete_preview(
            stale, "mcp-owner", "correct horse battery staple"
        )
        changed = self.call_tool(
            owner,
            "update_task",
            {"task_id": created["id"], "title": "Review the revised contract"},
        )
        stale_confirmation = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": stale["confirmation_token"],
                "confirm": True,
            },
        )
        expired = self.call_tool(
            owner, "prepare_task_delete", {"task_id": created["id"]}
        )["structuredContent"]
        self.approve_delete_preview(
            expired, "mcp-owner", "correct horse battery staple"
        )
        with server.connect_db() as conn:
            conn.execute(
                """
                UPDATE mcp_task_delete_confirmations SET expires_at = 0
                WHERE confirmation_hash = ?
                """,
                (
                    hashlib.sha256(
                        expired["confirmation_token"].encode("ascii")
                    ).hexdigest(),
                ),
            )
        expired_confirmation = self.call_tool(
            owner,
            "confirm_task_delete",
            {
                "task_id": created["id"],
                "confirmation_token": expired["confirmation_token"],
                "confirm": True,
            },
        )

        self.assertFalse(changed.get("isError"))
        self.assertTrue(stale_confirmation["isError"])
        self.assertTrue(expired_confirmation["isError"])
        with server.connect_db() as conn:
            task = conn.execute(
                "SELECT title FROM tasks WHERE id = ?", (created["id"],)
            ).fetchone()
            self.assertEqual(task["title"], "Review the revised contract")

    def test_delete_rechecks_task_snapshot_in_atomic_delete(self):
        owner = self.open_mcp_session(
            self.issue_access_token("mcp-atomic-delete")
        )
        created = self.call_tool(
            owner,
            "create_task",
            {"title": "Task approved before a concurrent update"},
        )["structuredContent"]
        with server.connect_db() as conn:
            owner_id = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                ("mcp-atomic-delete",),
            ).fetchone()["id"]
            snapshot = dict(
                conn.execute(
                    """
                    SELECT id, title, status, priority, category, deadline,
                        user_id, author_username
                    FROM tasks WHERE id = ?
                    """,
                    (created["id"],),
                ).fetchone()
            )
            conn.execute(
                "UPDATE tasks SET title = ? WHERE id = ?",
                ("Task after a concurrent update", created["id"]),
            )

            with self.assertRaises(server.HTTPException):
                server.delete_owned_task(
                    conn,
                    created["id"],
                    owner_id,
                    expected_snapshot=snapshot,
                )

            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM tasks WHERE id = ?", (created["id"],)
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
