import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import desktop_net  # noqa: E402
from desktop_net import (  # noqa: E402
    ApiError,
    NetworkError,
    ServerProbe,
    clear_completed,
    describe_error,
    parse_ai_answer,
)
try:
    from tests.test_mobile_api import FakeTaskStack  # noqa: E402
except ImportError:  # run with `discover -s tests`
    from test_mobile_api import FakeTaskStack  # noqa: E402


class ScriptedApi:
    """Stands in for the client: each call pops the next scripted outcome."""

    def __init__(self, ping=(), health=()):
        self.outcomes = {"ping": list(ping), "health": list(health)}
        self.calls = []

    def _answer(self, name, timeout):
        self.calls.append((name, timeout))
        outcome = self.outcomes[name].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def ping(self, timeout=None):
        return self._answer("ping", timeout)

    def health(self, timeout=None):
        return self._answer("health", timeout)


class ServerProbeTests(unittest.TestCase):
    def test_online_uses_ping_only(self):
        api = ScriptedApi(ping=[{"status": "ok"}])
        self.assertTrue(ServerProbe(api, timeout=1.5)())
        self.assertEqual(api.calls, [("ping", 1.5)])

    def test_unreachable_server_is_offline_without_trying_health(self):
        api = ScriptedApi(ping=[NetworkError("down")])
        self.assertFalse(ServerProbe(api)())
        self.assertEqual([name for name, _t in api.calls], ["ping"])

    def test_old_server_without_ping_falls_back_to_health_and_remembers(self):
        api = ScriptedApi(
            ping=[ApiError(404, "Not Found")],
            health=[{"status": "ok"}, {"status": "ok"}],
        )
        probe = ServerProbe(api)
        self.assertTrue(probe())
        self.assertTrue(probe())
        self.assertEqual(
            [name for name, _t in api.calls], ["ping", "health", "health"]
        )

    def test_server_error_while_waking_up_does_not_disable_ping(self):
        api = ScriptedApi(ping=[ApiError(502, "Bad Gateway"), {"status": "ok"}])
        probe = ServerProbe(api)
        self.assertFalse(probe())
        self.assertTrue(probe())
        self.assertTrue(probe.ping_supported)

    def test_health_failure_after_missing_ping_is_offline(self):
        api = ScriptedApi(ping=[ApiError(405, "")], health=[NetworkError("down")])
        self.assertFalse(ServerProbe(api)())


class HelperTests(unittest.TestCase):
    def test_describe_error(self):
        self.assertEqual(describe_error(ApiError(400, "Слишком короткий пароль")), "Слишком короткий пароль")
        self.assertEqual(describe_error(NetworkError("timed out")), "timed out")
        self.assertEqual(describe_error(ValueError()), "ValueError")

    def test_parse_ai_answer_accepts_plain_and_fenced_json(self):
        self.assertEqual(parse_ai_answer(' {"title": "a"} '), {"title": "a"})
        self.assertEqual(parse_ai_answer('```json\n{"title": "b"}\n```'), {"title": "b"})
        self.assertEqual(parse_ai_answer('```\n{"title": "c"}\n```'), {"title": "c"})
        with self.assertRaises(ValueError):
            parse_ai_answer("not json")

    def test_clear_completed_reports_each_failure_separately(self):
        class Api:
            def delete_task(self, task_id):
                if task_id == 2:
                    raise ApiError(404, "gone")
                if task_id == 3:
                    raise NetworkError("down")

        self.assertEqual(clear_completed(Api(), [1, 2, 3, 4]), ([1, 4], [2, 3]))

    def test_shared_client_is_the_android_one(self):
        self.assertIs(desktop_net.TaskStackClient.__module__, "taskstack_api")
        self.assertEqual(desktop_net.client.timeout, desktop_net.SERVER_WAKE_TIMEOUT)


class DesktopAgainstFakeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeTaskStack)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_probe_and_clear_against_http(self):
        api = desktop_net.TaskStackClient(self.url, timeout=3)
        self.assertTrue(ServerProbe(api)())
        api.login("ilya", "correct-password")
        self.assertEqual(clear_completed(api, [5, 6]), ([5, 6], []))
        api.token = "expired"
        self.assertEqual(clear_completed(api, [5]), ([], [5]))


if __name__ == "__main__":
    unittest.main()
