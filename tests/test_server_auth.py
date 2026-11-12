import os
import hashlib
import re
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

_test_directory = tempfile.TemporaryDirectory()
os.environ.pop("DATABASE_URL", None)
os.environ["TASKSTACK_DB_PATH"] = os.path.join(_test_directory.name, "test.sqlite")
os.environ["TASKSTACK_PUBLIC_URL"] = "http://127.0.0.1:8000"

import server


class ServerAuthenticationTests(unittest.TestCase):
    def setUp(self):
        server.init_db()
        with server.connect_db() as conn:
            for table in (
                "sessions",
                "task_shares",
                "task_group_shares",
                "group_members",
                "tasks",
                "groups",
                "users",
            ):
                conn.execute(f"DELETE FROM {table}")

    def test_password_hashing_and_legacy_upgrade(self):
        first_hash = server.hash_password("correct horse battery staple")
        second_hash = server.hash_password("correct horse battery staple")

        self.assertTrue(first_hash.startswith("pbkdf2_sha256$"))
        self.assertNotEqual(first_hash, second_hash)
        self.assertEqual(
            server.verify_password("correct horse battery staple", first_hash),
            (True, False),
        )
        self.assertFalse(server.verify_password("wrong password", first_hash)[0])

        legacy_hash = hashlib.sha256(b"legacy-password").hexdigest()
        self.assertEqual(
            server.verify_password("legacy-password", legacy_hash),
            (True, True),
        )

    def test_login_upgrades_legacy_hash_and_creates_hashed_session(self):
        legacy_hash = hashlib.sha256(b"legacy-password").hexdigest()
        with server.connect_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("legacy", legacy_hash),
            )

        result = server.login_user(
            server.UserRegisterModel(username="legacy", password="legacy-password")
        )
        with server.connect_db() as conn:
            stored_password = conn.execute(
                "SELECT password FROM users WHERE username = ?", ("legacy",)
            ).fetchone()["password"]
            session_count = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()["count"]
            token_hash = conn.execute(
                "SELECT token_hash FROM sessions"
            ).fetchone()["token_hash"]

        self.assertTrue(stored_password.startswith("pbkdf2_sha256$"))
        self.assertEqual(session_count, 1)
        self.assertEqual(token_hash, hashlib.sha256(result["access_token"].encode()).hexdigest())
        self.assertNotEqual(token_hash, result["access_token"])
        user = server.get_current_user(
            HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=result["access_token"]
            )
        )
        self.assertEqual(user["username"], "legacy")

    def test_protected_routes_require_bearer_dependency(self):
        protected_paths = {
            "/users",
            "/groups",
            "/tasks",
            "/tasks/{task_id}/status",
            "/tasks/{task_id}",
        }
        protected_routes = [
            route
            for route in server.app.routes
            if getattr(route, "path", None) in protected_paths
        ]

        self.assertEqual({route.path for route in protected_routes}, protected_paths)
        for route in protected_routes:
            self.assertTrue(
                any(
                    dependency.call is server.get_current_user
                    for dependency in route.dependant.dependencies
                ),
                f"{route.path} is missing the current-user dependency",
            )

    def test_users_cannot_impersonate_or_access_unshared_tasks(self):
        owner = server.register_user(
            server.UserRegisterModel(username="owner", password="password-owner")
        )
        stranger = server.register_user(
            server.UserRegisterModel(username="stranger", password="password-stranger")
        )
        with server.connect_db() as conn:
            owner_row = conn.execute(
                "SELECT username FROM users WHERE id = ?", (owner["id"],)
            ).fetchone()
        owner_user = {"id": owner["id"], "username": owner_row["username"]}

        task = server.add_task(
            server.TaskModel(user_id=owner["id"], title="private task"),
            owner_user,
        )
        with server.connect_db() as conn:
            cursor = conn.cursor()
            self.assertTrue(server.can_access_task(cursor, task["id"], owner["id"]))
            self.assertFalse(server.can_access_task(cursor, task["id"], stranger["id"]))

        with self.assertRaises(HTTPException) as error:
            server.get_tasks(stranger["id"], owner_user)
        self.assertEqual(error.exception.status_code, 403)

    def test_only_task_owner_can_delete(self):
        owner = server.register_user(
            server.UserRegisterModel(username="owner", password="password-owner")
        )
        recipient = server.register_user(
            server.UserRegisterModel(username="recipient", password="password-recipient")
        )
        with server.connect_db() as conn:
            owner_name = conn.execute(
                "SELECT username FROM users WHERE id = ?", (owner["id"],)
            ).fetchone()["username"]
            recipient_name = conn.execute(
                "SELECT username FROM users WHERE id = ?", (recipient["id"],)
            ).fetchone()["username"]
        owner_user = {"id": owner["id"], "username": owner_name}
        recipient_user = {"id": recipient["id"], "username": recipient_name}
        task = server.add_task(
            server.TaskModel(user_id=owner["id"], title="owned task"),
            owner_user,
        )

        with self.assertRaises(HTTPException) as error:
            server.delete_task(task["id"], recipient_user)
        self.assertEqual(error.exception.status_code, 404)

        self.assertEqual(
            server.delete_task(task["id"], owner_user),
            {"message": "Задача удалена"},
        )

    def test_postgres_sql_translation(self):
        create = server._postgres_sql(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER)"
        )
        self.assertIn("id BIGSERIAL PRIMARY KEY", create)
        self.assertIn("user_id BIGINT", create)

        insert = server._postgres_sql(
            "INSERT OR IGNORE INTO task_shares (task_id, user_id) VALUES (?, ?)"
        )
        self.assertEqual(
            insert,
            "INSERT INTO task_shares (task_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        )

        insert_with_id = server._postgres_sql(
            "INSERT INTO tasks (title) VALUES (?)"
        )
        self.assertEqual(
            insert_with_id, "INSERT INTO tasks (title) VALUES (%s) RETURNING id"
        )

    def test_render_configuration_refuses_missing_database_url(self):
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
            server.validate_database_config(
                database_url=None, require_database_url=True
            )
        server.validate_database_config(
            database_url="postgresql://configured", require_database_url=True
        )

    def test_health_checks_database_and_reports_backend(self):
        result = server.health_check()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["database"], "sqlite")

    def test_postgres_cursor_lastrowid_reads_returning_id(self):
        cursor = Mock()
        cursor.fetchone.return_value = {"id": 27}
        wrapped = server._PostgresCursor(cursor)

        wrapped.execute("INSERT INTO tasks (title) VALUES (?)", ("demo",))

        self.assertEqual(wrapped.lastrowid, 27)
        cursor.execute.assert_called_once_with(
            "INSERT INTO tasks (title) VALUES (%s) RETURNING id", ("demo",)
        )

    def test_client_endpoint_paths_exist_in_api(self):
        source = (Path(__file__).parents[1] / "main_window.py").read_text(
            encoding="utf-8"
        )
        client_paths = {
            re.sub(r"\{(?:self\.)?(?:user_id|current_user_id|task_id|widget\.task_id)\}", "{task_id}", path.split("?", 1)[0])
            for path in re.findall(r'f"\{SERVER_URL\}([^"]+)"', source)
        }
        client_paths.discard("{endpoint}")
        client_paths.update({"/register", "/login"})
        api_paths = {
            route.path for route in server.app.routes if getattr(route, "path", None)
        }

        self.assertTrue(client_paths)
        self.assertEqual(client_paths - api_paths, set())


if __name__ == "__main__":
    unittest.main()
