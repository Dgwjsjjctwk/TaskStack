import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from html import escape
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from anyio import to_thread
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from mcp.server.auth.provider import AccessToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError


TASK_SCOPES = ["tasks:read", "tasks:write", "tasks:delete"]
MAX_REGISTRATION_BODY_BYTES = 16 * 1024
AUTHORIZATION_REQUEST_LIFETIME = 10 * 60
AUTHORIZATION_CODE_LIFETIME = 5 * 60
ACCESS_TOKEN_LIFETIME = 60 * 60
REFRESH_TOKEN_LIFETIME = 30 * 24 * 60 * 60
CSRF_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
CODE_CHALLENGE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
CODE_VERIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
DEFAULT_TASKSTACK_ISSUER = "http://127.0.0.1:8000"


class OAuthClientRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(min_length=1, max_length=120)
    redirect_uris: list[str] = Field(min_length=1, max_length=20)
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"]
    )
    response_types: list[str] = Field(default_factory=lambda: ["code"])
    token_endpoint_auth_method: str = "none"


def _is_loopback_http(uri):
    try:
        address = ipaddress.ip_address(uri.hostname)
        return uri.scheme == "http" and address.is_loopback
    except ValueError:
        return uri.scheme == "http" and uri.hostname == "localhost"


def validate_redirect_uri(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    try:
        uri = urlsplit(value)
        if not uri.hostname or uri.username or uri.password or uri.fragment:
            return False
        _ = uri.port
        if uri.scheme == "https":
            return True
        return _is_loopback_http(uri)
    except ValueError:
        return False


def public_issuer(request=None):
    configured = os.environ.get("TASKSTACK_PUBLIC_URL") or os.environ.get(
        "RENDER_EXTERNAL_URL"
    )
    issuer = (
        configured.rstrip("/") if configured else DEFAULT_TASKSTACK_ISSUER
    )
    try:
        parsed = urlsplit(issuer)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError
        if parsed.scheme != "https" and not _is_loopback_http(parsed):
            raise ValueError
    except ValueError:
        raise RuntimeError("TASKSTACK_PUBLIC_URL must be an HTTPS origin")
    return issuer


async def _read_limited_body(request, max_bytes):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return None
        except ValueError:
            return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            return None
    return bytes(body)


async def _json_payload(request, max_bytes=MAX_REGISTRATION_BODY_BYTES):
    body = await _read_limited_body(request, max_bytes)
    if body is None:
        return None
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


async def _form_payload(request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/x-www-form-urlencoded":
        return None
    body = await _read_limited_body(request, MAX_REGISTRATION_BODY_BYTES)
    if body is None:
        return None
    try:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    except UnicodeDecodeError:
        return None
    if any(len(values) != 1 for values in parsed.values()):
        return None
    return {key: values[0] for key, values in parsed.items()}


def _token_hash(token):
    try:
        token_bytes = token.encode("ascii")
    except (AttributeError, UnicodeEncodeError):
        return ""
    return hashlib.sha256(token_bytes).hexdigest()


def _json_no_store(payload, status_code=200):
    response = JSONResponse(payload, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _error(code, status_code=400):
    return _json_no_store({"error": code}, status_code=status_code)


def _safe_html(content, status_code=200):
    response = HTMLResponse(content, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; form-action 'self'; base-uri 'none'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _authorization_redirect(uri):
    response = RedirectResponse(uri, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _authorization_form(request_id, csrf_token, error_message=""):
    escaped_error = (
        f"<p role=\"alert\">{escape(error_message)}</p>" if error_message else ""
    )
    return _safe_html(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>TaskStack authorization</title></head><body>"
        "<h1>Sign in to TaskStack</h1>"
        f"{escaped_error}"
        "<form method=\"post\" action=\"/oauth/authorize/login\">"
        f"<input type=\"hidden\" name=\"request_id\" value=\"{escape(request_id)}\">"
        f"<input type=\"hidden\" name=\"csrf_token\" value=\"{escape(csrf_token)}\">"
        "<label>Username <input name=\"username\" autocomplete=\"username\" required></label>"
        "<label>Password <input type=\"password\" name=\"password\" "
        "autocomplete=\"current-password\" required></label>"
        "<button type=\"submit\">Continue</button></form></body></html>"
    )


def _consent_form(request_id, csrf_token, client_name, redirect_uri, scopes):
    scope_items = "".join(f"<li>{escape(scope)}</li>" for scope in scopes)
    return _safe_html(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>TaskStack authorization</title></head><body>"
        "<h1>Authorize an AI client</h1>"
        f"<p><strong>{escape(client_name)}</strong> is requesting access.</p>"
        f"<p>Registered redirect URI: <code>{escape(redirect_uri)}</code></p>"
        f"<ul>{scope_items}</ul>"
        "<p>Only approve if you recognize this client and redirect address.</p>"
        "<form method=\"post\" action=\"/oauth/authorize/consent\">"
        f"<input type=\"hidden\" name=\"request_id\" value=\"{escape(request_id)}\">"
        f"<input type=\"hidden\" name=\"csrf_token\" value=\"{escape(csrf_token)}\">"
        "<button name=\"decision\" value=\"approve\" type=\"submit\">Allow</button>"
        "<button name=\"decision\" value=\"deny\" type=\"submit\">Deny</button>"
        "</form></body></html>"
    )


def _append_query(uri, parameters):
    parsed = urlsplit(uri)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(parameters.items())
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _valid_pending_request(conn, request_id, csrf_token, status):
    if (
        not request_id
        or not csrf_token
        or not CSRF_TOKEN_PATTERN.fullmatch(csrf_token)
    ):
        return None
    row = conn.execute(
        """
        SELECT request_id_hash, client_id, redirect_uri, state, resource, scopes,
            code_challenge, csrf_token_hash, user_id, status, expires_at
        FROM mcp_oauth_authorization_requests
        WHERE request_id_hash = ?
        """,
        (_token_hash(request_id),),
    ).fetchone()
    if (
        row is None
        or row["status"] != status
        or row["expires_at"] <= int(time.time())
        or not hmac.compare_digest(row["csrf_token_hash"], _token_hash(csrf_token))
    ):
        return None
    return row


def _issued_tokens(conn, client, grant, now):
    access_token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO mcp_oauth_access_tokens
            (token_hash, grant_id, expires_at, revoked_at)
        VALUES (?, ?, ?, NULL)
        """,
        (_token_hash(access_token), grant["id"], now + ACCESS_TOKEN_LIFETIME),
    )
    result = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_LIFETIME,
        "scope": " ".join(json.loads(grant["scopes"])),
    }
    if "refresh_token" in json.loads(client["grant_types"]):
        refresh_token = secrets.token_urlsafe(32)
        conn.execute(
            """
            INSERT INTO mcp_oauth_refresh_tokens
                (token_hash, grant_id, expires_at, consumed_at, revoked_at)
            VALUES (?, ?, ?, NULL, NULL)
            """,
            (_token_hash(refresh_token), grant["id"], now + REFRESH_TOKEN_LIFETIME),
        )
        result["refresh_token"] = refresh_token
    return result


class DatabaseTokenVerifier:
    def __init__(self, connect_db):
        self.connect_db = connect_db

    async def verify_token(self, token):
        return await to_thread.run_sync(self._verify_token, token)

    def _verify_token(self, token):
        token_hash = _token_hash(token)
        if not token_hash:
            return None
        now = int(time.time())
        with self.connect_db() as conn:
            row = conn.execute(
                """
                SELECT t.expires_at, t.revoked_at, g.client_id, g.user_id,
                    g.resource, g.scopes, g.revoked_at AS grant_revoked_at
                FROM mcp_oauth_access_tokens t
                JOIN mcp_oauth_grants g ON g.id = t.grant_id
                WHERE t.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if (
            row is None
            or row["expires_at"] <= now
            or row["revoked_at"] is not None
            or row["grant_revoked_at"] is not None
        ):
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes"]),
            expires_at=row["expires_at"],
            resource=row["resource"],
            subject=str(row["user_id"]),
        )


def user_from_mcp_headers(headers, required_scope, connect_db, resource_url):
    authorization = None
    for key, value in (headers or {}).items():
        if key.lower() == "authorization":
            authorization = value
            break
    if not authorization:
        raise PermissionError("A valid MCP access token is required.")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token or " " in token:
        raise PermissionError("A valid MCP access token is required.")
    token_hash = _token_hash(token)
    if not token_hash:
        raise PermissionError("A valid MCP access token is required.")

    now = int(time.time())
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, t.expires_at, t.revoked_at,
                g.resource, g.scopes, g.revoked_at AS grant_revoked_at
            FROM mcp_oauth_access_tokens t
            JOIN mcp_oauth_grants g ON g.id = t.grant_id
            JOIN users u ON u.id = g.user_id
            WHERE t.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
    if (
        row is None
        or row["expires_at"] <= now
        or row["revoked_at"] is not None
        or row["grant_revoked_at"] is not None
        or row["resource"] != resource_url
    ):
        raise PermissionError("A valid MCP access token is required.")
    if required_scope not in json.loads(row["scopes"]):
        raise PermissionError(f"The MCP access token requires {required_scope}.")
    return {"id": row["id"], "username": row["username"]}


def create_oauth_router(
    connect_db, authenticate_user_credentials, current_user_dependency
):
    router = APIRouter()

    @router.get("/.well-known/oauth-protected-resource")
    @router.get("/.well-known/oauth-protected-resource/mcp")
    def protected_resource_metadata(request: Request):
        issuer = public_issuer(request)
        return {
            "resource": f"{issuer}/mcp",
            "authorization_servers": [issuer],
            "bearer_methods_supported": ["header"],
            "scopes_supported": TASK_SCOPES,
        }

    @router.get("/.well-known/oauth-authorization-server")
    def authorization_server_metadata(request: Request):
        issuer = public_issuer(request)
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "registration_endpoint": f"{issuer}/oauth/register",
            "revocation_endpoint": f"{issuer}/oauth/revoke",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "revocation_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": TASK_SCOPES,
        }

    @router.post("/oauth/register", status_code=201)
    async def register_client(request: Request):
        payload = await _json_payload(request)
        if not isinstance(payload, dict):
            return JSONResponse(
                {"error": "invalid_client_metadata"},
                status_code=400,
            )
        try:
            registration = OAuthClientRegistration.model_validate(payload)
        except ValidationError:
            return JSONResponse(
                {"error": "invalid_client_metadata"},
                status_code=400,
            )

        redirect_uris = list(dict.fromkeys(registration.redirect_uris))
        client_name = registration.client_name.strip()
        grant_types = set(registration.grant_types)
        if (
            registration.token_endpoint_auth_method != "none"
            or "authorization_code" not in grant_types
            or grant_types - {"authorization_code", "refresh_token"}
            or len(grant_types) != len(registration.grant_types)
            or registration.response_types != ["code"]
            or not client_name
            or len(redirect_uris) != len(registration.redirect_uris)
            or any(not validate_redirect_uri(uri) for uri in redirect_uris)
        ):
            return JSONResponse(
                {"error": "invalid_client_metadata"},
                status_code=400,
            )

        client_id = secrets.token_urlsafe(24)
        with connect_db() as conn:
            conn.execute(
                """
                INSERT INTO mcp_oauth_clients
                    (client_id, client_name, redirect_uris, grant_types, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    client_name,
                    json.dumps(redirect_uris),
                    json.dumps(sorted(grant_types)),
                    int(time.time()),
                ),
            )

        return {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": sorted(grant_types),
            "response_types": registration.response_types,
            "token_endpoint_auth_method": "none",
        }

    @router.get("/oauth/authorize")
    def authorize(
        request: Request,
        response_type: str,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        resource: str,
        scope: str = "",
    ):
        issuer = public_issuer(request)
        requested_scopes = scope.split() if scope else TASK_SCOPES
        if (
            response_type != "code"
            or not state
            or len(state) > 512
            or code_challenge_method != "S256"
            or not CODE_CHALLENGE_PATTERN.fullmatch(code_challenge)
            or resource != f"{issuer}/mcp"
            or not requested_scopes
            or len(set(requested_scopes)) != len(requested_scopes)
            or any(item not in TASK_SCOPES for item in requested_scopes)
        ):
            return _error("invalid_request")

        with connect_db() as conn:
            client = conn.execute(
                """
                SELECT redirect_uris, grant_types
                FROM mcp_oauth_clients WHERE client_id = ?
                """,
                (client_id,),
            ).fetchone()
            if (
                client is None
                or "authorization_code" not in json.loads(client["grant_types"])
                or redirect_uri not in json.loads(client["redirect_uris"])
            ):
                return _error("invalid_request")

            request_id = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            conn.execute(
                """
                INSERT INTO mcp_oauth_authorization_requests
                    (request_id_hash, client_id, redirect_uri, state, resource,
                     scopes, code_challenge, csrf_token_hash, user_id, status,
                     expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'awaiting_login', ?, ?)
                """,
                (
                    _token_hash(request_id),
                    client_id,
                    redirect_uri,
                    state,
                    resource,
                    json.dumps(requested_scopes),
                    code_challenge,
                    _token_hash(csrf_token),
                    int(time.time()) + AUTHORIZATION_REQUEST_LIFETIME,
                    int(time.time()),
                ),
            )
        return _authorization_form(request_id, csrf_token)

    @router.post("/oauth/authorize/login")
    async def authorize_login(request: Request):
        form = await _form_payload(request)
        if form is None:
            return _error("invalid_request")
        with connect_db() as conn:
            pending = _valid_pending_request(
                conn,
                form.get("request_id"),
                form.get("csrf_token"),
                "awaiting_login",
            )
        if pending is None:
            return _error("invalid_request", status_code=400)

        user = await to_thread.run_sync(
            authenticate_user_credentials,
            form.get("username", ""), form.get("password", "")
        )
        if user is None:
            return _authorization_form(
                form["request_id"],
                form["csrf_token"],
                "Invalid username or password.",
            )

        csrf_token = secrets.token_urlsafe(32)
        now = int(time.time())
        with connect_db() as conn:
            updated = conn.execute(
                """
                UPDATE mcp_oauth_authorization_requests
                SET user_id = ?, status = 'awaiting_consent', csrf_token_hash = ?
                WHERE request_id_hash = ? AND status = 'awaiting_login'
                    AND expires_at > ?
                """,
                (
                    user["id"],
                    _token_hash(csrf_token),
                    pending["request_id_hash"],
                    now,
                ),
            )
            if updated.rowcount != 1:
                return _error("invalid_request")
            client = conn.execute(
                "SELECT client_name FROM mcp_oauth_clients WHERE client_id = ?",
                (pending["client_id"],),
            ).fetchone()
        if client is None:
            return _error("invalid_request")
        return _consent_form(
            form["request_id"],
            csrf_token,
            client["client_name"],
            pending["redirect_uri"],
            json.loads(pending["scopes"]),
        )

    @router.post("/oauth/authorize/consent")
    async def authorize_consent(request: Request):
        form = await _form_payload(request)
        if form is None or form.get("decision") not in {"approve", "deny"}:
            return _error("invalid_request")
        now = int(time.time())
        with connect_db() as conn:
            pending = _valid_pending_request(
                conn,
                form.get("request_id"),
                form.get("csrf_token"),
                "awaiting_consent",
            )
            if pending is None:
                return _error("invalid_request")
            updated = conn.execute(
                """
                UPDATE mcp_oauth_authorization_requests
                SET status = ?
                WHERE request_id_hash = ? AND status = 'awaiting_consent'
                    AND expires_at > ?
                """,
                (
                    "approved" if form["decision"] == "approve" else "denied",
                    pending["request_id_hash"],
                    now,
                ),
            )
            if updated.rowcount != 1:
                return _error("invalid_request")

            if form["decision"] == "deny":
                redirect = _append_query(
                    pending["redirect_uri"],
                    {
                        "error": "access_denied",
                        "state": pending["state"],
                        "iss": public_issuer(request),
                    },
                )
            else:
                grant_cursor = conn.execute(
                    """
                    INSERT INTO mcp_oauth_grants
                        (client_id, user_id, resource, scopes, created_at, revoked_at)
                    VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        pending["client_id"],
                        pending["user_id"],
                        pending["resource"],
                        pending["scopes"],
                        now,
                    ),
                )
                grant_id = grant_cursor.lastrowid
                code = secrets.token_urlsafe(32)
                conn.execute(
                    """
                    INSERT INTO mcp_oauth_codes
                        (code_hash, grant_id, client_id, redirect_uri, resource,
                         code_challenge, expires_at, consumed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        _token_hash(code),
                        grant_id,
                        pending["client_id"],
                        pending["redirect_uri"],
                        pending["resource"],
                        pending["code_challenge"],
                        now + AUTHORIZATION_CODE_LIFETIME,
                    ),
                )
                redirect = _append_query(
                    pending["redirect_uri"],
                    {"code": code, "state": pending["state"], "iss": public_issuer(request)},
                )
        return _authorization_redirect(redirect)

    @router.post("/oauth/token")
    async def token(request: Request):
        form = await _form_payload(request)
        if form is None:
            return _error("invalid_request")
        now = int(time.time())
        with connect_db() as conn:
            client = conn.execute(
                """
                SELECT client_id, grant_types FROM mcp_oauth_clients
                WHERE client_id = ?
                """,
                (form.get("client_id", ""),),
            ).fetchone()
            if client is None or form.get("resource") != f"{public_issuer(request)}/mcp":
                return _error("invalid_grant")

            if form.get("grant_type") == "authorization_code":
                verifier = form.get("code_verifier", "")
                if (
                    not CODE_VERIFIER_PATTERN.fullmatch(verifier)
                    or "authorization_code" not in json.loads(client["grant_types"])
                ):
                    return _error("invalid_grant")
                challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode("ascii")).digest()
                ).rstrip(b"=").decode("ascii")
                code = form.get("code", "")
                code_record = conn.execute(
                    """
                    SELECT c.code_hash, c.grant_id, c.client_id, c.redirect_uri,
                        c.resource, c.code_challenge, c.expires_at, c.consumed_at,
                        g.scopes, g.revoked_at
                    FROM mcp_oauth_codes c
                    JOIN mcp_oauth_grants g ON g.id = c.grant_id
                    WHERE c.code_hash = ?
                    """,
                    (_token_hash(code),),
                ).fetchone()
                if (
                    code_record is None
                    or code_record["client_id"] != client["client_id"]
                    or code_record["redirect_uri"] != form.get("redirect_uri")
                    or code_record["resource"] != form.get("resource")
                    or code_record["expires_at"] <= now
                    or code_record["consumed_at"] is not None
                    or code_record["revoked_at"] is not None
                    or not hmac.compare_digest(
                        code_record["code_challenge"], challenge
                    )
                ):
                    return _error("invalid_grant")
                consumed = conn.execute(
                    """
                    UPDATE mcp_oauth_codes SET consumed_at = ?
                    WHERE code_hash = ? AND consumed_at IS NULL AND expires_at > ?
                    """,
                    (now, code_record["code_hash"], now),
                )
                if consumed.rowcount != 1:
                    return _error("invalid_grant")
                grant = {
                    "id": code_record["grant_id"],
                    "scopes": code_record["scopes"],
                }
                return _json_no_store(_issued_tokens(conn, client, grant, now))

            if form.get("grant_type") == "refresh_token":
                if "refresh_token" not in json.loads(client["grant_types"]):
                    return _error("invalid_grant")
                refresh_hash = _token_hash(form.get("refresh_token", ""))
                refresh = conn.execute(
                    """
                    SELECT r.token_hash, r.grant_id, r.expires_at, r.consumed_at,
                        r.revoked_at AS token_revoked_at, g.client_id, g.resource,
                        g.scopes, g.revoked_at AS grant_revoked_at
                    FROM mcp_oauth_refresh_tokens r
                    JOIN mcp_oauth_grants g ON g.id = r.grant_id
                    WHERE r.token_hash = ?
                    """,
                    (refresh_hash,),
                ).fetchone()
                if (
                    refresh is None
                    or refresh["client_id"] != client["client_id"]
                    or refresh["resource"] != form.get("resource")
                    or refresh["expires_at"] <= now
                    or refresh["token_revoked_at"] is not None
                    or refresh["grant_revoked_at"] is not None
                ):
                    return _error("invalid_grant")
                if refresh["consumed_at"] is not None:
                    conn.execute(
                        "UPDATE mcp_oauth_grants SET revoked_at = ? WHERE id = ?",
                        (now, refresh["grant_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE mcp_oauth_refresh_tokens SET revoked_at = ?
                        WHERE grant_id = ?
                        """,
                        (now, refresh["grant_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE mcp_oauth_access_tokens SET revoked_at = ?
                        WHERE grant_id = ?
                        """,
                        (now, refresh["grant_id"]),
                    )
                    return _error("invalid_grant")
                consumed = conn.execute(
                    """
                    UPDATE mcp_oauth_refresh_tokens SET consumed_at = ?
                    WHERE token_hash = ? AND consumed_at IS NULL
                        AND revoked_at IS NULL AND expires_at > ?
                    """,
                    (now, refresh_hash, now),
                )
                if consumed.rowcount != 1:
                    return _error("invalid_grant")
                grant = {
                    "id": refresh["grant_id"],
                    "scopes": refresh["scopes"],
                }
                return _json_no_store(_issued_tokens(conn, client, grant, now))

        return _error("unsupported_grant_type")

    @router.post("/oauth/revoke")
    async def revoke_token(request: Request):
        form = await _form_payload(request)
        if form is None:
            return _error("invalid_request")
        now = int(time.time())
        token = form.get("token", "")
        token_hash = _token_hash(token) if token.isascii() else ""
        with connect_db() as conn:
            client = conn.execute(
                "SELECT client_id FROM mcp_oauth_clients WHERE client_id = ?",
                (form.get("client_id", ""),),
            ).fetchone()
            if client is not None:
                refresh = conn.execute(
                    """
                    SELECT r.grant_id FROM mcp_oauth_refresh_tokens r
                    JOIN mcp_oauth_grants g ON g.id = r.grant_id
                    WHERE r.token_hash = ? AND g.client_id = ?
                    """,
                    (token_hash, client["client_id"]),
                ).fetchone()
                if refresh is not None:
                    conn.execute(
                        "UPDATE mcp_oauth_grants SET revoked_at = ? WHERE id = ?",
                        (now, refresh["grant_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE mcp_oauth_refresh_tokens SET revoked_at = ?
                        WHERE grant_id = ?
                        """,
                        (now, refresh["grant_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE mcp_oauth_access_tokens SET revoked_at = ?
                        WHERE grant_id = ?
                        """,
                        (now, refresh["grant_id"]),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE mcp_oauth_access_tokens SET revoked_at = ?
                        WHERE token_hash = ? AND grant_id IN (
                            SELECT id FROM mcp_oauth_grants WHERE client_id = ?
                        )
                        """,
                        (now, token_hash, client["client_id"]),
                    )
        response = Response(status_code=200)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    @router.get("/oauth/grants")
    def list_grants(current_user=Depends(current_user_dependency)):
        with connect_db() as conn:
            rows = conn.execute(
                """
                SELECT g.id, c.client_name, g.scopes, g.created_at, g.revoked_at
                FROM mcp_oauth_grants g
                JOIN mcp_oauth_clients c ON c.client_id = g.client_id
                WHERE g.user_id = ? ORDER BY g.created_at DESC
                """,
                (current_user["id"],),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "client_name": row["client_name"],
                "scopes": json.loads(row["scopes"]),
                "created_at": row["created_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]

    @router.delete("/oauth/grants/{grant_id}")
    def revoke_grant(grant_id: int, current_user=Depends(current_user_dependency)):
        now = int(time.time())
        with connect_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM mcp_oauth_grants WHERE id = ?", (grant_id,)
            ).fetchone()
            if row is None or row["user_id"] != current_user["id"]:
                return JSONResponse({"detail": "Grant not found"}, status_code=404)
            conn.execute(
                "UPDATE mcp_oauth_grants SET revoked_at = ? WHERE id = ?",
                (now, grant_id),
            )
            conn.execute(
                "UPDATE mcp_oauth_refresh_tokens SET revoked_at = ? WHERE grant_id = ?",
                (now, grant_id),
            )
            conn.execute(
                "UPDATE mcp_oauth_access_tokens SET revoked_at = ? WHERE grant_id = ?",
                (now, grant_id),
            )
        return {"message": "MCP grant revoked"}

    return router
