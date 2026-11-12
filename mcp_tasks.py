from __future__ import annotations

import hashlib
import html
import hmac
import json
import secrets
import time
from fnmatch import fnmatchcase
from typing import Any
from urllib.parse import parse_qs, urlsplit

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request
from mcp.server import MCPServer
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import HTMLResponse, JSONResponse

from mcp_oauth import DatabaseTokenVerifier, user_from_mcp_headers

DELETE_CONFIRMATION_LIFETIME = 5 * 60
DELETE_APPROVAL_FORM_LIMIT = 8 * 1024
TASK_SNAPSHOT_FIELDS = (
    "id",
    "title",
    "status",
    "priority",
    "category",
    "deadline",
    "user_id",
    "author_username",
)


def _confirmation_hash(token):
    if not isinstance(token, str) or not token or len(token) > 512:
        return ""
    try:
        return hashlib.sha256(token.encode("ascii")).hexdigest()
    except UnicodeEncodeError:
        return ""


def _delete_approval_row(conn, approval_hash):
    return conn.execute(
        """
        SELECT a.confirmation_hash, a.csrf_token_hash, a.status AS approval_status,
            a.expires_at AS approval_expires_at, c.task_id,
            c.user_id AS confirmation_user_id, c.task_snapshot_hash,
            c.expires_at AS confirmation_expires_at, c.consumed_at,
            t.id, t.title, t.status, t.priority, t.category, t.deadline,
            t.user_id, t.author_username, u.username AS confirmation_username
        FROM mcp_task_delete_approvals a
        JOIN mcp_task_delete_confirmations c
            ON c.confirmation_hash = a.confirmation_hash
        JOIN tasks t ON t.id = c.task_id
        JOIN users u ON u.id = c.user_id
        WHERE a.approval_hash = ?
        """,
        (approval_hash,),
    ).fetchone()


def _valid_delete_approval(row, now):
    return bool(
        row
        and row["approval_expires_at"] > now
        and row["confirmation_expires_at"] > now
        and row["consumed_at"] is None
        and row["user_id"] == row["confirmation_user_id"]
        and hmac.compare_digest(
            row["task_snapshot_hash"], _task_snapshot_hash(row)
        )
    )


async def _approval_form_payload(request):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/x-www-form-urlencoded":
        return None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > DELETE_APPROVAL_FORM_LIMIT:
            return None
    try:
        parsed = parse_qs(
            body.decode("utf-8"), keep_blank_values=True, max_num_fields=8
        )
    except (UnicodeDecodeError, ValueError):
        return None
    if any(len(values) != 1 for values in parsed.values()):
        return None
    return {key: values[0] for key, values in parsed.items()}


def _approval_html(content, status_code=200):
    response = HTMLResponse(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>TaskStack task deletion</title></head><body>"
        f"{content}</body></html>",
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; form-action 'self'; base-uri 'none'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _approval_error(message, status_code=400):
    return _approval_html(
        f"<h1>Deletion confirmation unavailable</h1><p>{html.escape(message)}</p>",
        status_code,
    )


def _delete_task_preview(task):
    fields = (
        ("Task ID", task["id"]),
        ("Title", task["title"]),
        ("Status", task["status"]),
        ("Priority", task["priority"]),
        ("Category", task["category"]),
        ("Deadline", task["deadline"]),
    )
    return "".join(
        f"<p>{label}: <strong>{html.escape(str(value))}</strong></p>"
        for label, value in fields
    )


def _delete_login_form(approval_reference, csrf_token, task, error=""):
    escaped_reference = html.escape(approval_reference, quote=True)
    escaped_username = html.escape(str(task["confirmation_username"]))
    escaped_error = f"<p role=\"alert\">{html.escape(error)}</p>" if error else ""
    return _approval_html(
        "<h1>Review task deletion</h1>"
        f"{_delete_task_preview(task)}"
        f"<p>Sign in as <strong>{escaped_username}</strong> to continue.</p>"
        f"{escaped_error}"
        f"<form method=\"post\" action=\"/mcp/delete-confirmation/{escaped_reference}/login\">"
        f"<input type=\"hidden\" name=\"csrf_token\" value=\"{html.escape(csrf_token, quote=True)}\">"
        "<label>Username <input name=\"username\" autocomplete=\"username\" required></label>"
        "<label>Password <input type=\"password\" name=\"password\" autocomplete=\"current-password\" required></label>"
        "<button type=\"submit\">Continue</button></form>"
    )


def _delete_approval_form(approval_reference, csrf_token, task):
    escaped_reference = html.escape(approval_reference, quote=True)
    escaped_username = html.escape(str(task["confirmation_username"]))
    return _approval_html(
        "<h1>Confirm task deletion</h1>"
        f"<p>Signed in as <strong>{escaped_username}</strong>.</p>"
        "<p>Delete this task permanently?</p>"
        f"{_delete_task_preview(task)}"
        f"<form method=\"post\" action=\"/mcp/delete-confirmation/{escaped_reference}/approve\">"
        f"<input type=\"hidden\" name=\"csrf_token\" value=\"{html.escape(csrf_token, quote=True)}\">"
        "<button type=\"submit\" name=\"decision\" value=\"approve\">Approve deletion</button>"
        "<button type=\"submit\" name=\"decision\" value=\"deny\">Cancel</button>"
        "</form>"
    )


def create_delete_confirmation_router(connect_db, authenticate_user):
    router = APIRouter()

    @router.get(
        "/mcp/delete-confirmation/{approval_reference}",
        response_class=HTMLResponse,
    )
    def show_delete_confirmation(approval_reference: str):
        approval_hash = _confirmation_hash(approval_reference)
        if not approval_hash:
            return _approval_error("This link is invalid or expired.", 404)
        now = int(time.time())
        csrf_token = secrets.token_urlsafe(32)
        with connect_db() as conn:
            row = _delete_approval_row(conn, approval_hash)
            if not _valid_delete_approval(row, now):
                return _approval_error("This link is invalid or expired.", 404)
            if row["approval_status"] == "approved":
                return _approval_html(
                    "<h1>Deletion approved</h1>"
                    "<p>Return to your AI client to complete the requested deletion.</p>"
                )
            if row["approval_status"] not in {
                "pending",
                "awaiting_login",
                "awaiting_confirmation",
            }:
                return _approval_error("This link is invalid or expired.", 404)
            updated = conn.execute(
                """
                UPDATE mcp_task_delete_approvals
                SET status = 'awaiting_login', csrf_token_hash = ?
                WHERE approval_hash = ? AND expires_at > ?
                    AND status IN ('pending', 'awaiting_login', 'awaiting_confirmation')
                """,
                (_confirmation_hash(csrf_token), approval_hash, now),
            )
            if updated.rowcount != 1:
                return _approval_error("This link is invalid or expired.", 404)
            row = _delete_approval_row(conn, approval_hash)
            return _delete_login_form(approval_reference, csrf_token, row)

    @router.post(
        "/mcp/delete-confirmation/{approval_reference}/login",
        response_class=HTMLResponse,
    )
    async def verify_delete_confirmation_user(
        approval_reference: str, request: Request
    ):
        form = await _approval_form_payload(request)
        approval_hash = _confirmation_hash(approval_reference)
        csrf_hash = _confirmation_hash(form.get("csrf_token")) if form else ""
        if not form or not approval_hash or not csrf_hash:
            return _approval_error("The request is invalid or expired.", 400)
        now = int(time.time())
        with connect_db() as conn:
            row = _delete_approval_row(conn, approval_hash)
            if (
                not _valid_delete_approval(row, now)
                or row["approval_status"] != "awaiting_login"
                or not hmac.compare_digest(row["csrf_token_hash"], csrf_hash)
            ):
                return _approval_error("The request is invalid or expired.", 400)

        user = await to_thread.run_sync(
            authenticate_user,
            form.get("username", ""),
            form.get("password", ""),
        )
        next_csrf_token = secrets.token_urlsafe(32)
        now = int(time.time())
        with connect_db() as conn:
            row = _delete_approval_row(conn, approval_hash)
            if (
                not _valid_delete_approval(row, now)
                or row["approval_status"] != "awaiting_login"
                or not hmac.compare_digest(row["csrf_token_hash"], csrf_hash)
            ):
                return _approval_error("The request is invalid or expired.", 400)
            if user is None or user["id"] != row["confirmation_user_id"]:
                rotated = conn.execute(
                    """
                    UPDATE mcp_task_delete_approvals
                    SET csrf_token_hash = ?
                    WHERE approval_hash = ? AND status = 'awaiting_login'
                        AND csrf_token_hash = ?
                    """,
                    (
                        _confirmation_hash(next_csrf_token),
                        approval_hash,
                        csrf_hash,
                    ),
                )
                if rotated.rowcount != 1:
                    return _approval_error(
                        "The request is invalid or expired.", 400
                    )
                return _delete_login_form(
                    approval_reference,
                    next_csrf_token,
                    row,
                    "Unable to verify this TaskStack account.",
                )
            updated = conn.execute(
                """
                UPDATE mcp_task_delete_approvals
                SET status = 'awaiting_confirmation', csrf_token_hash = ?
                WHERE approval_hash = ? AND status = 'awaiting_login'
                    AND csrf_token_hash = ?
                """,
                (_confirmation_hash(next_csrf_token), approval_hash, csrf_hash),
            )
            if updated.rowcount != 1:
                return _approval_error("The request is invalid or expired.", 400)
            row = _delete_approval_row(conn, approval_hash)
            return _delete_approval_form(
                approval_reference, next_csrf_token, row
            )

    @router.post(
        "/mcp/delete-confirmation/{approval_reference}/approve",
        response_class=HTMLResponse,
    )
    async def approve_delete_confirmation(
        approval_reference: str, request: Request
    ):
        form = await _approval_form_payload(request)
        approval_hash = _confirmation_hash(approval_reference)
        csrf_hash = _confirmation_hash(form.get("csrf_token")) if form else ""
        if (
            not form
            or not approval_hash
            or not csrf_hash
            or form.get("decision") not in {"approve", "deny"}
        ):
            return _approval_error("The request is invalid or expired.", 400)
        now = int(time.time())
        with connect_db() as conn:
            row = _delete_approval_row(conn, approval_hash)
            if (
                not _valid_delete_approval(row, now)
                or row["approval_status"] != "awaiting_confirmation"
                or not hmac.compare_digest(row["csrf_token_hash"], csrf_hash)
            ):
                return _approval_error("The request is invalid or expired.", 400)
            if form["decision"] == "deny":
                denied = conn.execute(
                    """
                    UPDATE mcp_task_delete_approvals
                    SET status = 'denied', csrf_token_hash = ''
                    WHERE approval_hash = ? AND status = 'awaiting_confirmation'
                        AND csrf_token_hash = ?
                    """,
                    (approval_hash, csrf_hash),
                )
                if denied.rowcount != 1:
                    return _approval_error(
                        "The request is invalid or expired.", 400
                    )
                consumed = conn.execute(
                    """
                    UPDATE mcp_task_delete_confirmations SET consumed_at = ?
                    WHERE confirmation_hash = ? AND consumed_at IS NULL
                    """,
                    (now, row["confirmation_hash"]),
                )
                if consumed.rowcount != 1:
                    return _approval_error(
                        "The request is invalid or expired.", 400
                    )
                return _approval_html(
                    "<h1>Deletion cancelled</h1>"
                    "<p>The task was not deleted.</p>"
                )
            updated = conn.execute(
                """
                UPDATE mcp_task_delete_approvals
                SET status = 'approved', csrf_token_hash = '', approved_at = ?
                WHERE approval_hash = ? AND status = 'awaiting_confirmation'
                    AND csrf_token_hash = ?
                """,
                (now, approval_hash, csrf_hash),
            )
            if updated.rowcount != 1:
                return _approval_error("The request is invalid or expired.", 400)
            return _approval_html(
                "<h1>Deletion approved</h1>"
                "<p>Return to your AI client to complete the requested deletion.</p>"
            )

    return router


def _task_snapshot_hash(task):
    snapshot = {field: task[field] for field in TASK_SNAPSHOT_FIELDS}
    encoded = json.dumps(
        snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class MCPTransportSecurityGuard:
    def __init__(self, app, settings):
        self.app = app
        self.allowed_hosts = settings.allowed_hosts
        self.allowed_origins = settings.allowed_origins

    @staticmethod
    def _matches(value, patterns):
        return any(fnmatchcase(value.lower(), pattern.lower()) for pattern in patterns)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            headers = {}
            for key, value in scope.get("headers", []):
                headers.setdefault(key.lower(), []).append(
                    value.decode("latin-1")
                )
            hosts = headers.get(b"host", [])
            origins = headers.get(b"origin", [])
            if (
                len(hosts) != 1
                or not self._matches(hosts[0], self.allowed_hosts)
                or len(origins) > 1
                or (
                    origins
                    and not self._matches(origins[0], self.allowed_origins)
                )
            ):
                response = JSONResponse(
                    {"detail": "Invalid MCP Host or Origin header."},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_mcp_server(
    connect_db,
    get_tasks,
    add_task,
    update_task_fields,
    delete_owned_task,
    task_model,
    issuer,
):
    resource_url = f"{issuer}/mcp"

    mcp = MCPServer(
        name="TaskStack",
        instructions=(
            "Manage the authenticated user's TaskStack tasks. Task dates are kept "
            "as user-provided text; do not invent timezone or date conversions."
        ),
        token_verifier=DatabaseTokenVerifier(connect_db),
        auth=AuthSettings(
            issuer_url=issuer,
            resource_server_url=resource_url,
            validate_token_resource=True,
        ),
    )

    async def authenticated_user(ctx: Context, scope: str):
        try:
            return await to_thread.run_sync(
                user_from_mcp_headers,
                ctx.headers,
                scope,
                connect_db,
                resource_url,
            )
        except PermissionError as error:
            raise ToolError(str(error)) from error

    @mcp.tool(
        description=(
            "List all tasks currently accessible to the authenticated TaskStack "
            "user, including tasks shared with them."
        ),
        annotations=ToolAnnotations(
            title="List accessible tasks",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def list_tasks(ctx: Context) -> list[dict[str, Any]]:
        user = await authenticated_user(ctx, "tasks:read")
        return await to_thread.run_sync(get_tasks, user["id"], user)

    @mcp.tool(
        description=(
            "Read one task that is currently accessible to the authenticated "
            "TaskStack user. Shared tasks are readable under the same rules as "
            "the TaskStack task list."
        ),
        annotations=ToolAnnotations(
            title="Get accessible task",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def get_task(ctx: Context, task_id: int) -> dict[str, Any]:
        user = await authenticated_user(ctx, "tasks:read")
        tasks = await to_thread.run_sync(get_tasks, user["id"], user)
        task = next((item for item in tasks if item["id"] == task_id), None)
        if task is None:
            raise ToolError("Task is not accessible or does not exist.")
        return task

    @mcp.tool(
        description=(
            "Update a task accessible to the authenticated user. Shared users "
            "may change status only; only the task owner may change its title, "
            "priority, category, or deadline."
        ),
        annotations=ToolAnnotations(
            title="Update task",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def update_task(
        ctx: Context,
        task_id: int,
        title: str | None = None,
        status: int | None = None,
        priority: str | None = None,
        category: str | None = None,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        user = await authenticated_user(ctx, "tasks:write")
        try:
            await to_thread.run_sync(
                update_task_fields,
                task_id,
                {
                    "title": title,
                    "status": status,
                    "priority": priority,
                    "category": category,
                    "deadline": deadline,
                },
                user,
            )
        except HTTPException as error:
            raise ToolError(str(error.detail)) from error
        tasks = await to_thread.run_sync(get_tasks, user["id"], user)
        task = next((item for item in tasks if item["id"] == task_id), None)
        if task is None:
            raise ToolError("Task is not accessible or does not exist.")
        return task

    @mcp.tool(
        description=(
            "Prepare, but do not perform, deletion of a task owned by the "
            "authenticated user. Show the returned task preview and "
            "confirmation_url. The user must open the link, sign in to TaskStack, "
            "and explicitly approve that task before confirm_task_delete."
        ),
        annotations=ToolAnnotations(
            title="Preview task deletion",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def prepare_task_delete(ctx: Context, task_id: int) -> dict[str, Any]:
        user = await authenticated_user(ctx, "tasks:delete")
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        confirmation_hash = _confirmation_hash(token)
        approval_reference = secrets.token_urlsafe(32)
        with connect_db() as conn:
            conn.execute(
                """
                DELETE FROM mcp_task_delete_approvals
                WHERE expires_at <= ? OR status IN ('consumed', 'denied')
                """,
                (now,),
            )
            conn.execute(
                """
                DELETE FROM mcp_task_delete_confirmations
                WHERE expires_at <= ? OR consumed_at IS NOT NULL
                """,
                (now,),
            )
            task = conn.execute(
                """
                SELECT id, title, status, priority, category, deadline, user_id,
                    author_username
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is None or task["user_id"] != user["id"]:
                raise ToolError("Task is not owned by the authenticated user.")
            conn.execute(
                """
                INSERT INTO mcp_task_delete_confirmations
                    (confirmation_hash, task_id, user_id, task_snapshot_hash,
                     expires_at, consumed_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    confirmation_hash,
                    task_id,
                    user["id"],
                    _task_snapshot_hash(task),
                    now + DELETE_CONFIRMATION_LIFETIME,
                ),
            )
            conn.execute(
                """
                INSERT INTO mcp_task_delete_approvals
                    (approval_hash, confirmation_hash, csrf_token_hash, status,
                     expires_at, approved_at)
                VALUES (?, ?, '', 'pending', ?, NULL)
                """,
                (
                    _confirmation_hash(approval_reference),
                    confirmation_hash,
                    now + DELETE_CONFIRMATION_LIFETIME,
                ),
            )
        return {
            "confirmation_token": token,
            "confirmation_url": (
                f"{issuer}/mcp/delete-confirmation/{approval_reference}"
            ),
            "expires_in": DELETE_CONFIRMATION_LIFETIME,
            "task": {
                "id": task["id"],
                "title": task["title"],
                "status": task["status"],
                "priority": task["priority"],
                "category": task["category"],
                "deadline": task["deadline"],
            },
            "confirmation_required": True,
        }

    @mcp.tool(
        description=(
            "Delete a task only after the user has opened the preview's "
            "confirmation_url, signed in to TaskStack, and explicitly approved "
            "that exact task. Then provide the preview's confirmation token and "
            "confirm=true. Never call automatically or without verified approval."
        ),
        annotations=ToolAnnotations(
            title="Confirm task deletion",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def confirm_task_delete(
        ctx: Context,
        task_id: int,
        confirmation_token: str,
        confirm: bool,
    ) -> dict[str, Any]:
        user = await authenticated_user(ctx, "tasks:delete")
        if confirm is not True:
            raise ToolError("Deletion not performed; explicit confirm=true is required.")
        token_hash = _confirmation_hash(confirmation_token)
        if not token_hash:
            raise ToolError("A valid deletion confirmation token is required.")
        now = int(time.time())
        with connect_db() as conn:
            approval = conn.execute(
                """
                SELECT 1 FROM mcp_task_delete_approvals
                WHERE confirmation_hash = ? AND status = 'approved'
                    AND approved_at IS NOT NULL AND expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            if approval is None:
                raise ToolError(
                    "TaskStack user approval through the confirmation page is required."
                )
            approval_consumed = conn.execute(
                """
                UPDATE mcp_task_delete_approvals
                SET status = 'consumed'
                WHERE confirmation_hash = ? AND status = 'approved'
                    AND approved_at IS NOT NULL AND expires_at > ?
                """,
                (token_hash, now),
            )
            if approval_consumed.rowcount != 1:
                raise ToolError(
                    "TaskStack user approval is invalid, expired, or already used."
                )
            consumed = conn.execute(
                """
                UPDATE mcp_task_delete_confirmations
                SET consumed_at = ?
                WHERE confirmation_hash = ? AND task_id = ? AND user_id = ?
                    AND consumed_at IS NULL AND expires_at > ?
                """,
                (now, token_hash, task_id, user["id"], now),
            )
            if consumed.rowcount != 1:
                raise ToolError("Deletion confirmation is invalid or expired.")
            confirmation = conn.execute(
                """
                SELECT task_snapshot_hash FROM mcp_task_delete_confirmations
                WHERE confirmation_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            task = conn.execute(
                """
                SELECT id, title, status, priority, category, deadline, user_id,
                    author_username
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if (
                task is None
                or task["user_id"] != user["id"]
                or not hmac.compare_digest(
                    confirmation["task_snapshot_hash"], _task_snapshot_hash(task)
                )
            ):
                raise ToolError(
                    "Task changed after preview; prepare a new deletion confirmation."
                )
            try:
                delete_owned_task(
                    conn,
                    task_id,
                    user["id"],
                    expected_snapshot=task,
                )
            except HTTPException as error:
                raise ToolError(str(error.detail)) from error
        return {"deleted": True, "task_id": task_id}

    @mcp.tool(
        description=(
            "Create a task for the authenticated TaskStack user. Keep deadline "
            "wording exactly as provided; do not infer a timezone or change a "
            "relative date such as 'next Friday'."
        ),
        annotations=ToolAnnotations(
            title="Create task",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def create_task(
        ctx: Context,
        title: str,
        priority: str = "⚡ Средний",
        category: str = "💻 Разработка",
        deadline: str = "",
        status: int = 0,
    ) -> dict[str, Any]:
        user = await authenticated_user(ctx, "tasks:write")
        clean_title = title.strip()
        if not clean_title:
            raise ToolError("A task title is required.")
        if status not in (0, 1):
            raise ToolError("Task status must be 0 (open) or 1 (complete).")
        model = task_model(
            title=clean_title,
            priority=priority,
            category=category,
            deadline=deadline,
            status=status,
            user_id=user["id"],
            author_username=user["username"],
            shared_with_ids=[],
            shared_with_group_ids=[],
        )
        created = await to_thread.run_sync(add_task, model, user)
        return {
            "id": created["id"],
            "title": clean_title,
            "status": status,
            "priority": priority,
            "category": category,
            "deadline": deadline,
        }

    return mcp


def create_transport_security(issuer):
    parsed_issuer = urlsplit(issuer)
    if parsed_issuer.hostname in {"localhost", "127.0.0.1", "::1"}:
        return TransportSecuritySettings(
            allowed_hosts=[
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
                "[::1]",
                "[::1]:*",
            ],
            allowed_origins=[
                issuer,
                "http://localhost",
                "http://localhost:*",
                "http://127.0.0.1",
                "http://127.0.0.1:*",
                "http://[::1]:*",
            ],
        )
    return TransportSecuritySettings(
        allowed_hosts=[parsed_issuer.netloc],
        allowed_origins=[issuer],
    )
