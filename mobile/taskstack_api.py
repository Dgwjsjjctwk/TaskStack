"""HTTP client for the TaskStack API.

Pure standard library, no Qt imports: the same module works on desktop,
on Android and in tests. Every call is synchronous; callers are responsible
for running it off the UI thread.
"""

import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.request

DEFAULT_SERVER_URL = "https://taskstack-o9vw.onrender.com"

# A free hosting plan puts the server to sleep when it is idle, and the first
# request after that can take up to about a minute while it starts again.
# Requests run on worker threads, so a long wait never freezes the screen.
DEFAULT_TIMEOUT = 60.0


# CPython built for Android has no default CA bundle, so HTTPS fails with
# CERTIFICATE_VERIFY_FAILED unless the system certificate store is loaded.
ANDROID_CA_DIRS = (
    "/apex/com.android.conscrypt/cacerts",  # Android 14 and newer
    "/system/etc/security/cacerts",
)

_PEM_CERTIFICATE = re.compile(
    r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL
)


def build_ssl_context(ca_dirs=ANDROID_CA_DIRS):
    """Return (context, number of system CA certificates loaded).

    Android names the files in its certificate directories with the old
    OpenSSL subject hash, which a ``capath`` lookup does not find, so every file
    is read and handed to OpenSSL directly.
    """
    context = ssl.create_default_context()
    loaded = set()
    for directory in ca_dirs:
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            try:
                with open(
                    os.path.join(directory, name), "r", encoding="ascii", errors="ignore"
                ) as handle:
                    text = handle.read()
            except OSError:
                continue
            for pem in _PEM_CERTIFICATE.findall(text):
                if pem in loaded:
                    continue
                try:
                    context.load_verify_locations(cadata=pem)
                except ssl.SSLError:
                    continue
                loaded.add(pem)
    return context, len(loaded)


class ApiError(Exception):
    """The server answered with an HTTP error status."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail

    @property
    def is_unauthorized(self):
        return self.status == 401


class NetworkError(Exception):
    """The server could not be reached or sent an unreadable answer."""


def normalize_server_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return DEFAULT_SERVER_URL
    if "://" not in url:
        url = "https://" + url
    return url


def _error_detail(error):
    try:
        body = json.loads(error.read().decode("utf-8"))
        detail = body.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        if isinstance(detail, list) and detail:
            # FastAPI validation errors: [{"msg": "...", ...}]
            first = detail[0]
            if isinstance(first, dict) and first.get("msg"):
                return str(first["msg"])
    except Exception:
        pass
    return f"HTTP {error.code}"


class TaskStackClient:
    def __init__(self, base_url=DEFAULT_SERVER_URL, token=None, timeout=DEFAULT_TIMEOUT):
        self.base_url = normalize_server_url(base_url)
        self.token = token
        self.timeout = timeout
        self.user_id = None
        self.username = None
        self._ssl_context = None
        self._system_ca_count = 0

    # -- transport ---------------------------------------------------------

    def _request(self, method, path, payload=None, timeout=None):
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        if self._ssl_context is None:
            self._ssl_context, self._system_ca_count = build_ssl_context()
        try:
            with urllib.request.urlopen(
                request, timeout=timeout or self.timeout, context=self._ssl_context
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise ApiError(error.code, _error_detail(error)) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            message = str(reason)
            if isinstance(reason, ssl.SSLCertVerificationError):
                message += f" ({self._system_ca_count} system CA certificates loaded)"
            raise NetworkError(message) from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise NetworkError("Unreadable response from server") from None

    # -- account -----------------------------------------------------------

    def health(self, timeout=None):
        return self._request("GET", "/health", timeout=timeout)

    def ping(self, timeout=None):
        """Cheap liveness check that does not touch the server's database."""
        return self._request("GET", "/ping", timeout=timeout)

    def register(self, username, password):
        return self._request(
            "POST", "/register", {"username": username, "password": password}
        )

    def login(self, username, password):
        data = self._request(
            "POST", "/login", {"username": username, "password": password}
        )
        token = (data or {}).get("access_token")
        if not token:
            raise NetworkError("Server did not return an access token")
        self.token = token
        self.user_id = data.get("id")
        self.username = data.get("username")
        return data

    def restore_session(self, token, user_id, username):
        self.token = token
        self.user_id = user_id
        self.username = username

    def logout(self):
        self.token = None
        self.user_id = None
        self.username = None

    # -- tasks -------------------------------------------------------------

    def list_tasks(self):
        return self._request("GET", f"/tasks?user_id={int(self.user_id)}")

    def add_task(
        self,
        title,
        priority,
        category,
        deadline="",
        shared_with_ids=(),
        shared_with_group_ids=(),
    ):
        payload = {
            "title": title,
            "status": 0,
            "priority": priority,
            "category": category,
            "deadline": deadline,
            "user_id": int(self.user_id),
            "author_username": self.username or "",
            "shared_with_ids": list(shared_with_ids),
            "shared_with_group_ids": list(shared_with_group_ids),
        }
        return self._request("POST", "/tasks", payload)

    def set_task_status(self, task_id, completed):
        return self._request(
            "PUT", f"/tasks/{int(task_id)}/status", {"status": 1 if completed else 0}
        )

    def delete_task(self, task_id):
        return self._request("DELETE", f"/tasks/{int(task_id)}")

    # -- sharing -----------------------------------------------------------

    def list_users(self):
        return self._request("GET", f"/users?exclude_id={int(self.user_id)}")

    def list_groups(self):
        return self._request("GET", f"/groups?user_id={int(self.user_id)}")

    def create_group(self, name, member_ids):
        return self._request(
            "POST",
            "/groups",
            {
                "name": name,
                "creator_id": int(self.user_id),
                "member_ids": list(member_ids),
            },
        )
