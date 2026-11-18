"""Network layer of the desktop app, free of Qt so it can be unit-tested.

The HTTP client is the same module the Android app uses (``mobile/taskstack_api.py``),
so both apps speak to the server through one implementation. Every call is
synchronous; ``qt_async.run_async`` runs it off the UI thread.
"""

import json
import os
import sys
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.abspath(__file__))
_MOBILE = os.path.join(_ROOT, "mobile")
# From source the client lives in mobile/; in a PyInstaller build it is bundled
# (TaskManager.spec adds mobile/ to pathex), so this path simply does not exist.
if os.path.isdir(_MOBILE) and _MOBILE not in sys.path:
    sys.path.append(_MOBILE)  # appended: never shadows a desktop module

from taskstack_api import ApiError, NetworkError, TaskStackClient  # noqa: E402

from config import SERVER_URL  # noqa: E402

# A free hosting plan puts the server to sleep when it is idle, and the first
# request after that can take up to about a minute while it starts again.
# Requests run on worker threads, so waiting never freezes the window.
SERVER_WAKE_TIMEOUT = 60
# How long the network indicator waits for one answer before showing red.
PROBE_TIMEOUT = 1.5

client = TaskStackClient(SERVER_URL, timeout=SERVER_WAKE_TIMEOUT)


def describe_error(error):
    """Short human-readable text for an exception raised by a request."""
    if isinstance(error, ApiError):
        return error.detail
    return str(error) or error.__class__.__name__


class ServerProbe:
    """Liveness check for the network indicator; returns True or False.

    Asks /ping, which does not touch the database (asking /health would keep
    the database and the free host awake for as long as a client is open). A
    server older than /ping answers 404 or 405; the probe then uses /health.
    """

    def __init__(self, api, timeout=PROBE_TIMEOUT):
        self.api = api
        self.timeout = timeout
        self.ping_supported = True

    def __call__(self):
        if self.ping_supported:
            try:
                self.api.ping(timeout=self.timeout)
                return True
            except ApiError as error:
                if error.status in (404, 405):
                    self.ping_supported = False
                else:
                    return False
            except NetworkError:
                return False
        try:
            self.api.health(timeout=self.timeout)
            return True
        except (ApiError, NetworkError):
            return False


def clear_completed(api, task_ids):
    """Delete the given tasks one by one; return (deleted ids, failed ids)."""
    deleted, failed = [], []
    for task_id in task_ids:
        try:
            api.delete_task(task_id)
            deleted.append(task_id)
        except (ApiError, NetworkError):
            failed.append(task_id)
    return deleted, failed


def parse_ai_answer(raw):
    """Turn the model's text into a task dict; tolerates a ```json fence."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def request_ai_task(url, model, prompt, api_key="", timeout=15):
    """Ask the AI endpoint (Ollama format) to turn text into a task dict."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_ai_answer(result.get("response", ""))
