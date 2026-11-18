import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mobile"))

from taskstack_api import (  # noqa: E402
    DEFAULT_SERVER_URL,
    build_ssl_context,
    ApiError,
    NetworkError,
    TaskStackClient,
    normalize_server_url,
)


class FakeTaskStack(BaseHTTPRequestHandler):
    """Mimics the contract of server.py closely enough to test the client."""

    requests = []
    tasks = []

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else None

    def _authorized(self):
        return self.headers.get("Authorization") == "Bearer good-token"

    def _handle(self, method):
        parsed = urlparse(self.path)
        body = self._body()
        FakeTaskStack.requests.append(
            (method, self.path, body, self.headers.get("Authorization"))
        )
        path = parsed.path
        if path == "/health":
            return self._send(200, {"status": "ok"})
        if path == "/login" and method == "POST":
            if body["password"] != "correct-password":
                return self._send(401, {"detail": "Неверное имя пользователя или пароль"})
            return self._send(
                200,
                {"id": 7, "username": body["username"], "access_token": "good-token"},
            )
        if path == "/register" and method == "POST":
            if len(body["password"]) < 8:
                return self._send(400, {"detail": "Пароль должен содержать не менее 8 символов"})
            return self._send(200, {"id": 8, "message": "ok"})
        if path == "/bad-json":
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"???")
            return
        if path == "/validation":
            return self._send(422, {"detail": [{"msg": "field required"}]})
        if not self._authorized():
            return self._send(401, {"detail": "Требуется авторизация"})
        if path == "/tasks" and method == "GET":
            return self._send(200, FakeTaskStack.tasks)
        if path == "/tasks" and method == "POST":
            FakeTaskStack.tasks.append({"id": 100, **body})
            return self._send(200, {"id": 100, "message": "ok"})
        if path.startswith("/tasks/") and path.endswith("/status") and method == "PUT":
            return self._send(200, {"message": "ok"})
        if path.startswith("/tasks/") and method == "DELETE":
            return self._send(200, {"message": "ok"})
        if path == "/users":
            return self._send(200, [{"id": 2, "username": "anna"}])
        if path == "/groups" and method == "GET":
            return self._send(200, [{"id": 1, "name": "team", "member_ids": [7, 2]}])
        if path == "/groups" and method == "POST":
            return self._send(200, {"id": 5, "message": "ok"})
        return self._send(404, {"detail": "not found"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


class TaskStackClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTaskStack)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeTaskStack.requests.clear()
        FakeTaskStack.tasks = []
        self.client = TaskStackClient(self.url, timeout=3)

    def logged_in(self):
        self.client.login("ilya", "correct-password")
        return self.client

    def test_normalize_server_url(self):
        self.assertEqual(normalize_server_url(""), DEFAULT_SERVER_URL)
        self.assertEqual(normalize_server_url("  "), DEFAULT_SERVER_URL)
        self.assertEqual(normalize_server_url("tasks.example.com/"), "https://tasks.example.com")
        self.assertEqual(normalize_server_url("http://10.0.2.2:8000/"), "http://10.0.2.2:8000")

    def test_ssl_context_survives_missing_android_certificate_dirs(self):
        context, count = build_ssl_context(("/no/such/dir", "/also/missing"))
        self.assertEqual(count, 0)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_ssl_context_loads_certificates_whatever_the_file_names(self):
        bundle = None
        for candidate in (
            ssl.get_default_verify_paths().cafile,
            "/etc/ssl/certs/ca-certificates.crt",
        ):
            if candidate and os.path.exists(candidate):
                bundle = candidate
                break
        if bundle is None:
            self.skipTest("no system CA bundle to take sample certificates from")
        pems = re.findall(
            r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----",
            open(bundle, encoding="ascii", errors="ignore").read(),
            re.DOTALL,
        )
        self.assertGreaterEqual(len(pems), 3)
        with tempfile.TemporaryDirectory() as directory:
            # Android style: hash-like names plus trailing text after the PEM.
            for index, pem in enumerate(pems[:3]):
                with open(os.path.join(directory, f"{index:08x}.0"), "w") as handle:
                    handle.write(pem + "\nCertificate:\n    Data:\n")
            with open(os.path.join(directory, "duplicate.0"), "w") as handle:
                handle.write(pems[0])
            with open(os.path.join(directory, "notes.txt"), "w") as handle:
                handle.write("not a certificate")
            context, count = build_ssl_context((directory,))
        self.assertEqual(count, 3)
        self.assertGreaterEqual(len(context.get_ca_certs()), 3)

    @unittest.skipUnless(shutil.which("openssl"), "openssl command line tool needed")
    def test_https_verifies_against_certificates_with_android_style_names(self):
        with tempfile.TemporaryDirectory() as work:
            def run(*args):
                subprocess.run(["openssl", *args], cwd=work, check=True, capture_output=True)

            run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key",
                "-out", "ca.pem", "-days", "2", "-subj", "/CN=Test Android CA",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign")
            run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key",
                "-out", "srv.csr", "-subj", "/CN=localhost")
            with open(os.path.join(work, "ext.cnf"), "w") as handle:
                handle.write(
                    "subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\n"
                    "keyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
                )
            run("x509", "-req", "-in", "srv.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
                "-CAcreateserial", "-out", "srv.pem", "-days", "2", "-extfile", "ext.cnf")
            cadir = os.path.join(work, "cacerts")
            os.mkdir(cadir)
            # Not the name OpenSSL's capath lookup expects: the Android situation.
            shutil.copy(os.path.join(work, "ca.pem"), os.path.join(cadir, "deadbeef.0"))

            class Hello(BaseHTTPRequestHandler):
                def do_GET(self):
                    body = b'{"status": "ok"}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *args):
                    pass

            server = HTTPServer(("127.0.0.1", 0), Hello)
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(
                os.path.join(work, "srv.pem"), os.path.join(work, "srv.key")
            )
            server.socket = server_context.wrap_socket(server.socket, server_side=True)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            url = f"https://localhost:{server.server_port}"

            untrusting = TaskStackClient(url, timeout=5)
            with self.assertRaises(NetworkError) as caught:
                untrusting._request("GET", "/health")
            self.assertIn("CERTIFICATE_VERIFY_FAILED", str(caught.exception))
            self.assertIn("system CA certificates loaded", str(caught.exception))

            # The new client reads the files directly and trusts the test CA.
            trusting = TaskStackClient(url, timeout=5)
            context, count = build_ssl_context((cadir,))
            self.assertEqual(count, 1)
            trusting._ssl_context = context
            self.assertEqual(trusting.health(), {"status": "ok"})

    def test_health(self):
        self.assertEqual(self.client.health()["status"], "ok")

    def test_login_stores_token_and_identity(self):
        data = self.client.login("ilya", "correct-password")
        self.assertEqual(data["id"], 7)
        self.assertEqual(self.client.token, "good-token")
        self.assertEqual(self.client.user_id, 7)
        self.assertEqual(self.client.username, "ilya")

    def test_login_failure_reports_server_message(self):
        with self.assertRaises(ApiError) as caught:
            self.client.login("ilya", "wrong")
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(caught.exception.detail, "Неверное имя пользователя или пароль")
        self.assertIsNone(self.client.token)

    def test_register_validation_error_message(self):
        with self.assertRaises(ApiError) as caught:
            self.client.register("ilya", "short")
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("8", caught.exception.detail)

    def test_fastapi_validation_detail_list_is_flattened(self):
        with self.assertRaises(ApiError) as caught:
            self.client._request("GET", "/validation")
        self.assertEqual(caught.exception.detail, "field required")

    def test_authenticated_calls_send_bearer_token(self):
        client = self.logged_in()
        client.list_tasks()
        method, path, _body, auth = FakeTaskStack.requests[-1]
        self.assertEqual((method, path), ("GET", "/tasks?user_id=7"))
        self.assertEqual(auth, "Bearer good-token")

    def test_unauthorized_is_flagged(self):
        self.client.restore_session("expired", 7, "ilya")
        with self.assertRaises(ApiError) as caught:
            self.client.list_tasks()
        self.assertTrue(caught.exception.is_unauthorized)

    def test_add_task_payload_matches_server_model(self):
        client = self.logged_in()
        result = client.add_task(
            "Купить молоко",
            "🔥 Высокий",
            "🏠 Личное",
            "2026-12-01 18:00",
            shared_with_ids=[2],
            shared_with_group_ids=[1],
        )
        self.assertEqual(result["id"], 100)
        _method, path, body, _auth = FakeTaskStack.requests[-1]
        self.assertEqual(path, "/tasks")
        self.assertEqual(
            body,
            {
                "title": "Купить молоко",
                "status": 0,
                "priority": "🔥 Высокий",
                "category": "🏠 Личное",
                "deadline": "2026-12-01 18:00",
                "user_id": 7,
                "author_username": "ilya",
                "shared_with_ids": [2],
                "shared_with_group_ids": [1],
            },
        )

    def test_status_and_delete_routes(self):
        client = self.logged_in()
        client.set_task_status(42, True)
        self.assertEqual(
            FakeTaskStack.requests[-1][:3], ("PUT", "/tasks/42/status", {"status": 1})
        )
        client.set_task_status(42, False)
        self.assertEqual(FakeTaskStack.requests[-1][2], {"status": 0})
        client.delete_task(42)
        self.assertEqual(FakeTaskStack.requests[-1][:2], ("DELETE", "/tasks/42"))

    def test_users_and_groups(self):
        client = self.logged_in()
        self.assertEqual(client.list_users(), [{"id": 2, "username": "anna"}])
        self.assertEqual(FakeTaskStack.requests[-1][1], "/users?exclude_id=7")
        self.assertEqual(client.list_groups()[0]["name"], "team")
        self.assertEqual(FakeTaskStack.requests[-1][1], "/groups?user_id=7")
        self.assertEqual(client.create_group("new", [2])["id"], 5)
        self.assertEqual(
            FakeTaskStack.requests[-1][2],
            {"name": "new", "creator_id": 7, "member_ids": [2]},
        )

    def test_logout_clears_session(self):
        client = self.logged_in()
        client.logout()
        self.assertIsNone(client.token)
        self.assertIsNone(client.user_id)

    def test_default_timeout_outlasts_a_sleeping_free_host(self):
        # The first request after the server slept can take close to a minute.
        self.assertGreaterEqual(TaskStackClient().timeout, 45)

    def test_unreachable_server_raises_network_error(self):
        client = TaskStackClient("http://127.0.0.1:1", timeout=2)
        with self.assertRaises(NetworkError):
            client.health()

    def test_unreadable_body_raises_network_error(self):
        with self.assertRaises(NetworkError):
            self.client._request("GET", "/bad-json")


if __name__ == "__main__":
    unittest.main()
