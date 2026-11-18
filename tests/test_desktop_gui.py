"""Headless smoke tests of the desktop window against a fake server.

They check what a refactor of the networking can break without anyone noticing:
the window must stay responsive while the server is slow, and every action
(load, add, tick, delete, clear, sign in) must still reach the server and
update the list.
"""
import os
import sys
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    if os.environ.get("CI"):
        raise  # in CI a missing Qt library must fail, not hide these tests
    QApplication = None

try:
    from tests.test_mobile_api import FakeTaskStack
except ImportError:  # run with `discover -s tests`
    from test_mobile_api import FakeTaskStack

DELAY = 0.6


class SlowTaskStack(FakeTaskStack):
    def _handle(self, method):
        if self.path.startswith("/tasks") and method == "GET":
            time.sleep(DELAY)
        super()._handle(method)


def task(task_id, title, status=0, owner=7):
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "priority": "⚡ Средний",
        "category": "💻 Разработка",
        "deadline": "2030-01-01 10:00",
        "user_id": owner,
        "author_username": "ilya" if owner == 7 else "anna",
    }


@unittest.skipIf(QApplication is None, "PyQt6 is not installed")
class DesktopWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.server = HTTPServer(("127.0.0.1", 0), SlowTaskStack)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        import desktop_net
        import main_window

        self.main_window = main_window
        self.client = desktop_net.client
        saved = (self.client.base_url, self.client.token, self.client.timeout)
        self.addCleanup(
            lambda: setattr(self.client, "base_url", saved[0])
            or setattr(self.client, "token", saved[1])
            or setattr(self.client, "timeout", saved[2])
        )
        self.client.base_url = self.url
        self.client.token = "good-token"
        self.client.timeout = 5
        FakeTaskStack.requests.clear()
        FakeTaskStack.tasks = [
            task(1, "first"),
            task(2, "done", status=1),
            task(3, "shared with me", status=1, owner=2),
        ]
        patches = [
            patch.object(main_window.QMessageBox, "question",
                         return_value=main_window.QMessageBox.StandardButton.Yes),
            patch.object(main_window.QMessageBox, "warning"),
            patch.object(main_window.QMessageBox, "critical"),
            patch.object(main_window.QMessageBox, "information"),
        ]
        self.boxes = {
            name: p.start()
            for name, p in zip(("question", "warning", "critical", "information"), patches)
        }
        for p in patches:
            self.addCleanup(p.stop)

    def wait_for(self, condition, timeout=8.0):
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.01)
        self.fail("timed out waiting for the window to update")

    def open_window(self):
        window = self.main_window.MainWindow(user_id=7, username="ilya")
        self.addCleanup(window.deleteLater)
        return window

    def seen(self, method, prefix):
        return [r for r in FakeTaskStack.requests if r[0] == method and r[1].startswith(prefix)]

    def titles(self, window):
        return sorted(
            window.task_list.itemWidget(window.task_list.item(i)).get_text()
            for i in range(window.task_list.count())
        )

    def test_window_stays_responsive_while_the_server_is_slow(self):
        started = time.time()
        window = self.open_window()
        elapsed = time.time() - started

        self.assertLess(elapsed, DELAY * 0.8, "constructing the window waited for the server")
        self.assertEqual(window.task_list.count(), 0)
        self.wait_for(lambda: window.task_list.count() == 3)
        self.assertEqual(self.titles(window), ["done", "first", "shared with me"])

    def test_adding_a_task_posts_it_and_shows_it(self):
        window = self.open_window()
        self.wait_for(lambda: window.task_list.count() == 3)

        window.task_input.setText("buy milk")
        window.add_task()
        self.wait_for(lambda: window.task_list.count() == 4)

        post = self.seen("POST", "/tasks")[-1]
        self.assertEqual(post[2]["title"], "buy milk")
        self.assertEqual(post[2]["user_id"], 7)
        self.assertEqual(post[3], "Bearer good-token")
        self.assertIn("buy milk", self.titles(window))

    def test_ticking_a_task_sends_the_status(self):
        window = self.open_window()
        self.wait_for(lambda: window.task_list.count() == 3)

        window.update_task_status_on_server(1, 1)
        self.wait_for(lambda: self.seen("PUT", "/tasks/1/status"))
        self.assertEqual(self.seen("PUT", "/tasks/1/status")[-1][2], {"status": 1})

    def test_failed_status_update_reloads_the_list(self):
        window = self.open_window()
        self.wait_for(lambda: window.task_list.count() == 3)
        FakeTaskStack.requests.clear()

        self.client.token = "expired"
        window.update_task_status_on_server(1, 1)
        self.wait_for(lambda: len(self.seen("GET", "/tasks")) >= 1)
        self.boxes["critical"].assert_not_called()  # the reload is quiet

    def test_deleting_the_selected_task(self):
        window = self.open_window()
        self.wait_for(lambda: window.task_list.count() == 3)
        row = window._find_row(1)
        window.task_list.setCurrentRow(row)

        window.delete_task()
        self.wait_for(lambda: window.task_list.count() == 2)

        self.assertTrue(self.seen("DELETE", "/tasks/1"))
        self.assertNotIn("first", self.titles(window))

    def test_clear_removes_only_my_completed_tasks(self):
        window = self.open_window()
        self.wait_for(lambda: window.task_list.count() == 3)

        window.clear_tasks()
        self.wait_for(lambda: window.task_list.count() == 2)

        self.assertEqual(self.titles(window), ["first", "shared with me"])
        self.assertEqual([r[1] for r in self.seen("DELETE", "/tasks/")], ["/tasks/2"])

    def test_unreachable_server_shows_an_error_instead_of_crashing(self):
        self.client.base_url = "http://127.0.0.1:9"  # nothing listens here
        window = self.open_window()
        self.wait_for(lambda: self.boxes["critical"].called)
        self.assertEqual(window.task_list.count(), 0)

    def test_expired_session_asks_to_sign_in_again(self):
        self.client.token = "expired"
        self.open_window()
        self.wait_for(lambda: self.boxes["warning"].called)
        self.assertIn("Сессия", self.boxes["warning"].call_args.args[1])

    def test_connection_indicator_turns_green(self):
        window = self.open_window()
        window.show()
        self.addCleanup(window.hide)
        window.check_server_connection()
        self.wait_for(lambda: window.net_status_label.text() == "🟢")

    def test_sign_in_dialog(self):
        dialog = self.main_window.AuthDialog()
        dialog.username_input.setText("ilya")
        dialog.password_input.setText("correct-password")
        dialog.handle_submit()
        self.assertFalse(dialog.submit_btn.isEnabled())
        self.wait_for(lambda: dialog.user_id == 7)
        self.assertEqual(dialog.access_token, "good-token")
        self.assertEqual(self.client.token, "good-token")

    def test_sign_in_with_wrong_password_reports_the_server_message(self):
        dialog = self.main_window.AuthDialog()
        dialog.username_input.setText("ilya")
        dialog.password_input.setText("wrong-password")
        dialog.handle_submit()
        self.wait_for(lambda: self.boxes["critical"].called)
        self.assertIn("Неверное", self.boxes["critical"].call_args.args[2])
        self.assertTrue(dialog.submit_btn.isEnabled())
        self.assertEqual(dialog.submit_btn.text(), "Войти")

    def test_share_dialog_loads_users_and_groups_in_the_background(self):
        dialog = self.main_window.ShareDialog(7)
        self.wait_for(lambda: dialog.groups_list.count() == 1)
        self.assertIn("anna", dialog.users_list.item(0).text())


if __name__ == "__main__":
    unittest.main()
