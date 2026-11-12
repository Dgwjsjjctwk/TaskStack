import base64
from contextlib import asynccontextmanager, contextmanager
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from mcp_oauth import create_oauth_router, public_issuer

DATABASE_PATH = os.environ.get("TASKSTACK_DB_PATH", "server_tasks.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
PASSWORD_HASH_ITERATIONS = 600_000
SESSION_LIFETIME_SECONDS = 30 * 24 * 60 * 60
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="Task Manager Server")


def _postgres_sql(statement: str) -> str:
    sql = statement.strip()
    ignore_conflicts = sql.upper().startswith("INSERT OR IGNORE INTO ")
    if ignore_conflicts:
        sql = re.sub(r"^INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.IGNORECASE)

    sql = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"\bINTEGER\b", "BIGINT", sql, flags=re.IGNORECASE)
    sql = sql.replace("?", "%s")

    if ignore_conflicts:
        sql += " ON CONFLICT DO NOTHING"
    elif re.match(
        r"INSERT\s+INTO\s+(users|groups|tasks|mcp_oauth_grants)\b",
        sql,
        flags=re.IGNORECASE,
    ):
        sql += " RETURNING id"
    return sql


class _PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._inserted_id = None

    def execute(self, statement, parameters=()):
        self._cursor.execute(_postgres_sql(statement), parameters)
        return self

    def executemany(self, statement, parameter_sets):
        self._cursor.executemany(_postgres_sql(statement), parameter_sets)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        if self._inserted_id is None:
            row = self.fetchone()
            if row is not None:
                self._inserted_id = row["id"]
        return self._inserted_id


class _PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        return _PostgresCursor(self._connection.cursor()).execute(statement, parameters)

    def executemany(self, statement, parameter_sets):
        return _PostgresCursor(self._connection.cursor()).executemany(
            statement, parameter_sets
        )

    def cursor(self):
        return _PostgresCursor(self._connection.cursor())

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def _open_db():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        return _PostgresConnection(
            psycopg.connect(DATABASE_URL, row_factory=dict_row)
        )

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _integrity_errors():
    if DATABASE_URL:
        import psycopg

        return (psycopg.IntegrityError,)
    return (sqlite3.IntegrityError,)


def validate_database_config(database_url=None, require_database_url=None):
    if database_url is None:
        database_url = DATABASE_URL
    if require_database_url is None:
        require_database_url = (
            os.environ.get("TASKSTACK_REQUIRE_DATABASE_URL", "").lower() == "true"
        )
    if require_database_url and not database_url:
        raise RuntimeError(
            "DATABASE_URL is required for this deployment; refusing ephemeral SQLite storage"
        )


@contextmanager
def connect_db():
    conn = _open_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status INTEGER DEFAULT 0,
                priority TEXT,
                category TEXT,
                deadline TEXT,
                user_id INTEGER,
                author_username TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_shares (
                task_id INTEGER,
                user_id INTEGER,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(task_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                creator_id INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                user_id INTEGER,
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(group_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_group_shares (
                task_id INTEGER,
                group_id INTEGER,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
                UNIQUE(task_id, group_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_clients (
                client_id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                redirect_uris TEXT NOT NULL,
                grant_types TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_authorization_requests (
                request_id_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                state TEXT NOT NULL,
                resource TEXT NOT NULL,
                scopes TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                csrf_token_hash TEXT NOT NULL,
                user_id INTEGER,
                status TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(client_id) REFERENCES mcp_oauth_clients(client_id)
                    ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_grants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                resource TEXT NOT NULL,
                scopes TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                revoked_at INTEGER,
                FOREIGN KEY(client_id) REFERENCES mcp_oauth_clients(client_id)
                    ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_codes (
                code_hash TEXT PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                resource TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER,
                FOREIGN KEY(grant_id) REFERENCES mcp_oauth_grants(id)
                    ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_access_tokens (
                token_hash TEXT PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                FOREIGN KEY(grant_id) REFERENCES mcp_oauth_grants(id)
                    ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_oauth_refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                grant_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER,
                revoked_at INTEGER,
                FOREIGN KEY(grant_id) REFERENCES mcp_oauth_grants(id)
                    ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_task_delete_confirmations (
                confirmation_hash TEXT PRIMARY KEY,
                task_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                task_snapshot_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                consumed_at INTEGER,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_task_delete_approvals (
                approval_hash TEXT PRIMARY KEY,
                confirmation_hash TEXT NOT NULL UNIQUE,
                csrf_token_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                approved_at INTEGER,
                FOREIGN KEY(confirmation_hash)
                REFERENCES mcp_task_delete_confirmations(confirmation_hash)
                ON DELETE CASCADE
            )
        """)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    derived_text = base64.urlsafe_b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_text}${derived_text}"


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return whether the password matches and whether its hash needs upgrading."""
    if not stored_hash.startswith("pbkdf2_sha256$"):
        legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash), True

    try:
        algorithm, iterations_text, salt_text, expected_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False, False
        iterations = int(iterations_text)
        if iterations < 1 or iterations > PASSWORD_HASH_ITERATIONS:
            return False, False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(actual, expected), iterations < PASSWORD_HASH_ITERATIONS
    except (ValueError, TypeError):
        return False, False


def _authenticate_user_credentials(conn, username: str, password: str):
    row = conn.execute(
        "SELECT id, username, password FROM users WHERE username = ?",
        (username.strip(),),
    ).fetchone()
    if row is None:
        return None

    valid, needs_upgrade = verify_password(password, row["password"])
    if not valid:
        return None
    if needs_upgrade:
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(password), row["id"]),
        )
    return {"id": row["id"], "username": row["username"]}


def authenticate_mcp_user(username: str, password: str):
    with connect_db() as conn:
        return _authenticate_user_credentials(conn, username, password)


def issue_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, int(time.time()) + SESSION_LIFETIME_SECONDS),
    )
    return token


def unauthorized():
    raise HTTPException(
        status_code=401,
        detail="Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        unauthorized()

    try:
        token = credentials.credentials.encode("ascii")
    except UnicodeEncodeError:
        unauthorized()
    token_hash = hashlib.sha256(token).hexdigest()
    now = int(time.time())
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT users.id, users.username
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
    if row is None:
        unauthorized()
    return {"id": row["id"], "username": row["username"]}


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_self(requested_user_id: int, current_user: dict):
    if requested_user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Недостаточно прав")


def can_access_task(cursor, task_id: int, user_id: int) -> bool:
    row = cursor.execute(
        """
        SELECT 1
        FROM tasks t
        WHERE t.id = ? AND (
            t.user_id = ?
            OR EXISTS (
                SELECT 1 FROM task_shares s
                WHERE s.task_id = t.id AND s.user_id = ?
            )
            OR EXISTS (
                SELECT 1
                FROM task_group_shares gs
                JOIN groups g ON g.id = gs.group_id
                LEFT JOIN group_members gm ON gm.group_id = g.id
                WHERE gs.task_id = ? AND (g.creator_id = ? OR gm.user_id = ?)
            )
        )
        """,
        (task_id, user_id, user_id, task_id, user_id, user_id),
    ).fetchone()
    return row is not None


validate_database_config()
init_db()


class UserRegisterModel(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class GroupModel(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    creator_id: int
    member_ids: list[int] = Field(default_factory=list)


class TaskModel(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    status: int = 0
    priority: str = "⚡ Средний"
    category: str = "💻 Разработка"
    deadline: str = ""
    user_id: int
    author_username: str = ""
    shared_with_ids: list[int] = Field(default_factory=list)
    shared_with_group_ids: list[int] = Field(default_factory=list)


class TaskUpdateModel(BaseModel):
    status: int = Field(ge=0, le=1)


@app.get("/health")
def health_check():
    with connect_db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "database": "postgresql" if DATABASE_URL else "sqlite",
    }


@app.post("/register")
def register_user(user: UserRegisterModel):
    username = user.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Имя пользователя обязательно")
    if len(user.password) < 8:
        raise HTTPException(status_code=400, detail="Пароль должен содержать не менее 8 символов")

    with connect_db() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hash_password(user.password)),
            )
            user_id = cursor.lastrowid
        except _integrity_errors():
            raise HTTPException(
                status_code=400, detail="Пользователь с таким именем уже существует"
            )
    return {"id": user_id, "message": "Регистрация успешна!"}


@app.post("/login")
def login_user(user: UserRegisterModel):
    with connect_db() as conn:
        authenticated_user = _authenticate_user_credentials(
            conn, user.username, user.password
        )
        if authenticated_user is None:
            raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")
        token = issue_session(conn, authenticated_user["id"])
        username = authenticated_user["username"]
        user_id = authenticated_user["id"]

    return {
        "id": user_id,
        "username": username,
        "access_token": token,
        "token_type": "bearer",
        "message": "Успешный вход!",
    }


@app.get("/users")
def get_users(current_user: CurrentUser, exclude_id: int | None = None):
    if exclude_id is not None:
        require_self(exclude_id, current_user)
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT id, username FROM users WHERE id != ?",
            (current_user["id"],),
        ).fetchall()
    return [{"id": row["id"], "username": row["username"]} for row in rows]


@app.get("/groups")
def get_groups(user_id: int, current_user: CurrentUser):
    require_self(user_id, current_user)
    with connect_db() as conn:
        groups_rows = conn.execute(
            """
            SELECT DISTINCT g.id, g.name, g.creator_id
            FROM groups g
            LEFT JOIN group_members gm ON g.id = gm.group_id
            WHERE g.creator_id = ? OR gm.user_id = ?
            """,
            (current_user["id"], current_user["id"]),
        ).fetchall()

        groups = []
        for group in groups_rows:
            members = conn.execute(
                "SELECT user_id FROM group_members WHERE group_id = ?",
                (group["id"],),
            ).fetchall()
            groups.append({
                "id": group["id"],
                "name": group["name"],
                "creator_id": group["creator_id"],
                "member_ids": [member["user_id"] for member in members],
            })
    return groups


@app.post("/groups")
def create_group(group: GroupModel, current_user: CurrentUser):
    require_self(group.creator_id, current_user)
    name = group.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название группы обязательно")
    with connect_db() as conn:
        try:
            for member_id in set(group.member_ids):
                if conn.execute(
                    "SELECT 1 FROM users WHERE id = ?", (member_id,)
                ).fetchone() is None:
                    raise HTTPException(status_code=400, detail="Участник не найден")
            cursor = conn.execute(
                "INSERT INTO groups (name, creator_id) VALUES (?, ?)",
                (name, current_user["id"]),
            )
            group_id = cursor.lastrowid
            conn.executemany(
                "INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)",
                [(group_id, member_id) for member_id in set(group.member_ids)],
            )
        except _integrity_errors():
            raise HTTPException(status_code=400, detail="Группа с таким названием уже существует")
    return {"id": group_id, "message": "Группа создана!"}


@app.get("/tasks")
def get_tasks(user_id: int, current_user: CurrentUser):
    require_self(user_id, current_user)
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT t.id, t.title, t.status, t.priority, t.category,
                t.deadline, t.user_id, t.author_username
            FROM tasks t
            LEFT JOIN task_shares s ON t.id = s.task_id
            LEFT JOIN task_group_shares gs ON t.id = gs.task_id
            LEFT JOIN group_members gm ON gs.group_id = gm.group_id
            LEFT JOIN groups g ON gs.group_id = g.id
            WHERE t.user_id = ? OR s.user_id = ? OR gm.user_id = ? OR g.creator_id = ?
            """,
            (current_user["id"],) * 4,
        ).fetchall()

        tasks = []
        for row in rows:
            shares = conn.execute(
                "SELECT user_id FROM task_shares WHERE task_id = ?", (row["id"],)
            ).fetchall()
            group_shares = conn.execute(
                "SELECT group_id FROM task_group_shares WHERE task_id = ?",
                (row["id"],),
            ).fetchall()
            tasks.append({
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "priority": row["priority"],
                "category": row["category"],
                "deadline": row["deadline"],
                "user_id": row["user_id"],
                "author_username": row["author_username"],
                "shared_with_ids": [share["user_id"] for share in shares],
                "shared_with_group_ids": [share["group_id"] for share in group_shares],
            })
    return tasks


@app.post("/tasks")
def add_task(task: TaskModel, current_user: CurrentUser):
    require_self(task.user_id, current_user)
    with connect_db() as conn:
        for user_id in set(task.shared_with_ids):
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise HTTPException(status_code=400, detail="Получатель не найден")
        for group_id in set(task.shared_with_group_ids):
            group_access = conn.execute(
                """
                SELECT 1 FROM groups g
                LEFT JOIN group_members gm ON gm.group_id = g.id
                WHERE g.id = ? AND (g.creator_id = ? OR gm.user_id = ?)
                """,
                (group_id, current_user["id"], current_user["id"]),
            ).fetchone()
            if group_access is None:
                raise HTTPException(status_code=403, detail="Нет доступа к группе")

        cursor = conn.execute(
            """
            INSERT INTO tasks
                (title, status, priority, category, deadline, user_id, author_username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.title.strip(),
                task.status,
                task.priority,
                task.category,
                task.deadline,
                current_user["id"],
                current_user["username"],
            ),
        )
        task_id = cursor.lastrowid
        conn.executemany(
            "INSERT OR IGNORE INTO task_shares (task_id, user_id) VALUES (?, ?)",
            [(task_id, user_id) for user_id in set(task.shared_with_ids)],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO task_group_shares (task_id, group_id) VALUES (?, ?)",
            [(task_id, group_id) for group_id in set(task.shared_with_group_ids)],
        )
    return {"id": task_id, "message": "Задача добавлена и расшарена!"}


def update_task_fields(task_id: int, updates: dict, current_user: dict):
    allowed_fields = {"title", "status", "priority", "category", "deadline"}
    fields = {key: value for key, value in updates.items() if value is not None}
    if not fields or set(fields) - allowed_fields:
        raise HTTPException(status_code=400, detail="No valid task fields to update")
    if "title" in fields:
        if not isinstance(fields["title"], str) or not fields["title"].strip():
            raise HTTPException(status_code=400, detail="Task title cannot be empty")
        fields["title"] = fields["title"].strip()
    if "status" in fields and fields["status"] not in (0, 1):
        raise HTTPException(status_code=400, detail="Task status must be 0 or 1")
    for field in ("priority", "category", "deadline"):
        if field in fields and not isinstance(fields[field], str):
            raise HTTPException(status_code=400, detail=f"{field} must be text")

    with connect_db() as conn:
        row = conn.execute(
            "SELECT user_id FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None or not can_access_task(
            conn.cursor(), task_id, current_user["id"]
        ):
            raise HTTPException(status_code=404, detail="Задача не найдена")
        if row["user_id"] != current_user["id"] and set(fields) != {"status"}:
            raise HTTPException(
                status_code=403,
                detail="Only the task owner can update task details",
            )
        assignments = ", ".join(f"{field} = ?" for field in fields)
        conn.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ?",
            (*fields.values(), task_id),
        )


@app.put("/tasks/{task_id}/status")
def update_task_status(task_id: int, task_update: TaskUpdateModel, current_user: CurrentUser):
    update_task_fields(task_id, {"status": task_update.status}, current_user)
    return {"message": "Статус обновлен"}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, current_user: CurrentUser):
    with connect_db() as conn:
        delete_owned_task(conn, task_id, current_user["id"])
    return {"message": "Задача удалена"}


def delete_owned_task(
    conn, task_id: int, user_id: int, expected_snapshot=None
):
    if expected_snapshot is not None:
        snapshot_fields = (
            "title",
            "status",
            "priority",
            "category",
            "deadline",
            "author_username",
        )
        null_safe_operator = "IS NOT DISTINCT FROM" if DATABASE_URL else "IS"
        predicates = ["id = ?", "user_id = ?"]
        parameters = [task_id, user_id]
        for field in snapshot_fields:
            predicates.append(f"{field} {null_safe_operator} ?")
            parameters.append(expected_snapshot[field])
        deleted = conn.execute(
            f"DELETE FROM tasks WHERE {' AND '.join(predicates)}",
            parameters,
        )
        if deleted.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="Task changed after preview; prepare a new deletion confirmation.",
            )
        conn.execute("DELETE FROM task_shares WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_group_shares WHERE task_id = ?", (task_id,))
        return

    row = conn.execute(
        "SELECT user_id FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    conn.execute("DELETE FROM task_shares WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM task_group_shares WHERE task_id = ?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


app.include_router(
    create_oauth_router(connect_db, authenticate_mcp_user, get_current_user)
)

from mcp_tasks import (
    MCPTransportSecurityGuard,
    create_delete_confirmation_router,
    create_mcp_server,
    create_transport_security,
)

_mcp_issuer = public_issuer()
app.include_router(
    create_delete_confirmation_router(connect_db, authenticate_mcp_user)
)
_mcp_transport_security = create_transport_security(_mcp_issuer)
mcp_server = create_mcp_server(
    connect_db,
    get_tasks,
    add_task,
    update_task_fields,
    delete_owned_task,
    TaskModel,
    _mcp_issuer,
)
mcp_http_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    transport_security=_mcp_transport_security,
    host="0.0.0.0",
)
mcp_http_app = MCPTransportSecurityGuard(mcp_http_app, _mcp_transport_security)
_existing_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _app_lifespan(application):
    async with _existing_lifespan(application):
        async with mcp_server.session_manager.run():
            yield


app.router.lifespan_context = _app_lifespan
app.mount("/", mcp_http_app)
