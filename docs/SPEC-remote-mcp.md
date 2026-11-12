# Spec: TaskStack Remote MCP (1.3 feature)

## Objective

Add a remote MCP endpoint to the existing TaskStack FastAPI API so a user can authorize an MCP-capable AI client with their existing TaskStack account and a distinct, revocable consent grant. The MCP server exposes task create, list/read, update, and safely confirmed delete operations while preserving TaskStack's per-user visibility and sharing rules.

The implementation starts from released v1.2.0. Version, changelog, tags, release assets, and production deployment are explicitly out of scope until the user requests release preparation.

## Capability map

See [remote MCP capability map](remote-mcp-capability-map.md). The stable module ids and dependency order are `mcp-remote-auth` → `mcp-task-tools` → `mcp-hosting-interop`.

## Tech Stack

- Python 3.11+; FastAPI / Starlette ASGI application; Pydantic models.
- Existing SQLite development and PostgreSQL Render database via `server.py`.
- Official Model Context Protocol Python SDK for Streamable HTTP and protocol handling, subject to pinning and compatibility tests.
- OAuth 2.1 authorization code with PKCE S256, RFC 8414 authorization-server metadata, RFC 9728 protected-resource metadata, RFC 7591 dynamic client registration, RFC 8707 resource indicator, and RFC 7009 token revocation as applicable.
- Existing Render web service and `render.yaml`; HTTPS is supplied by the existing host.

## Commands

- Focused and complete test suite: `python -m unittest discover -s tests -p "test_*.py"`
- Local API: `python -m pip install -r requirements-server.txt` then `python -m uvicorn server:app --host 127.0.0.1 --port 8000`
- Deployment remains the existing Render service; do not deploy this branch.

## Project Structure

- `server.py` — current account/task API, database initialization, and shared authorization helpers.
- `tests/` — `unittest` API/authentication tests; MCP/OAuth integration tests follow the same convention.
- `docs/remote-mcp-capability-map.md` — stable module boundaries and build order.
- `docs/SPEC-remote-mcp.md` — requirements and acceptance contract.
- `README.md` — user-facing setup and compatibility documentation.

## Code Style

Follow current `server.py` conventions: FastAPI route decorators, Pydantic request models, parameterized SQL, explicit `HTTPException` status codes, and `unittest` assertions. Keep caller identity server-derived:

```python
@app.get("/tasks")
def get_tasks(user_id: int, current_user: CurrentUser):
    require_self(user_id, current_user)
    ...
```

MCP tools must derive identity from the validated OAuth access token; no tool argument may select a TaskStack user.

## Contract

### OAuth and account access

- MCP is served at `/mcp` over Streamable HTTP on the existing FastAPI process.
- Use an authorization-code flow with PKCE S256 and standard OAuth discovery. The MCP client receives only short-lived MCP-specific tokens; do not reuse or accept the existing account-wide TaskStack bearer token as an MCP token.
- The user authenticates on a TaskStack-hosted HTTPS page using their existing account, sees the client name, exact redirect URI, and requested scopes, and explicitly approves or denies access.
- Each approval creates a separate per-user/per-client grant. Grants and tokens are scoped to the canonical MCP resource URI and least-privilege task scopes; tokens are opaque, expiring, stored hashed, and revocable.
- Validate OAuth `state`, exact registered redirect URI, client identity, resource/audience, PKCE verifier/challenge, scope, token expiry, and revocation. Never log passwords, authorization codes, access/refresh tokens, or authorization headers.
- Public-client redirect URIs are exact-match HTTPS or loopback HTTP URIs; do not accept wildcard redirects or open redirect behavior.
- Validate Streamable HTTP `Origin` when present and use an explicit host/origin policy suitable for the Render URL and local development.

### Task tools and authorization

- Expose create, list/read, update, and delete-preview/confirm tools only.
- List returns the tasks visible to the authenticated user under the current API rules: ownership, direct share, or membership in a group with which the task is shared.
- Create always assigns ownership to the authenticated user. It does not accept a caller-supplied `user_id`, `author_username`, or shares as authority.
- Update preserves current mutation semantics: a user with access may change status; only the owner may change title, priority, category, or deadline.
- Delete is owner-only. The first call creates a short-lived, single-use confirmation bound to the authenticated user, task, and task snapshot and makes no mutation. It returns a separate approval URL. The user must open that TaskStack page, reauthenticate as the owning account, and explicitly approve the exact task. A second MCP call requires both the opaque confirmation token and `confirm=true`; the server checks and atomically consumes the browser-recorded approval, rechecks ownership and task snapshot, then deletes. Stale, expired, reused, cross-user, or altered-task confirmations fail without deleting.
- Tool descriptions must tell the client to show the preview and approval URL, wait for the user's explicit approval on the TaskStack page, and only then call the confirm tool. Tool annotations are advisory; the server-side approval record is the enforcement mechanism. A client that cannot present or complete this interaction must not invoke the confirm tool.
- Accept ordinary natural-language date text in the task's existing `deadline` field (for example, `next Friday`); do not silently infer or persist additional fields unsupported by the current task schema.

### Hosting and compatibility

- Extend the existing FastAPI/Render service; no second service, separate database, calendar integration, client-specific API, or Claude skill.
- Use one shared issuer for OAuth discovery and MCP audience validation: prefer `TASKSTACK_PUBLIC_URL`, then Render's `RENDER_EXTERNAL_URL`, then the local default `http://127.0.0.1:8000`. Set the override to the exact public origin when using a different local host/port or custom production domain. The existing Render manifest needs no additional service or secret.
- Do not configure production secrets, perform a Render deployment, merge, or release in this task.
- Document connection setup for Claude, ChatGPT, DeepSeek, and other clients only where remote MCP and OAuth are supported. Distinguish clients tested against the implementation from those only expected to interoperate; do not claim client support without verification.

#### Client compatibility status

| Client or harness | Status | Evidence and limits |
|---|---|---|
| MCP Python SDK 2.3.0 with FastAPI `TestClient` | Tested at protocol level | Exercises OAuth against this server, Streamable HTTP initialization, tool discovery, and tool calls; this is not a test of a third-party desktop or hosted client. |
| Claude Code | Expected, not tested | Anthropic documents remote HTTP MCP servers and OAuth sign-in. No specific Claude Code version has been tested against this endpoint. |
| OpenAI Responses API | Protocol expected; OAuth handoff unverified | OpenAI documents remote MCP over Streamable HTTP. Its API request flow expects the calling application to provide an authorization token; user-specific browser consent/token handoff has not been verified. This does not establish support in the ChatGPT consumer app. |
| DeepSeek API | Direct native MCP support not verified | DeepSeek's documented API capability is function calling, not a native remote MCP client. DeepSeek may be usable behind a separate MCP-capable host, but that combination is not tested here. |
| Other MCP clients | Expected only when standards match | Must support Streamable HTTP and the MCP OAuth discovery/authorization flow, including PKCE and resource indicators. Client-specific configuration and consent UX may differ. |

## Testing Strategy

- Use the repository's `unittest` suite and FastAPI `TestClient` with the local SQLite database.
- Test OAuth metadata and registration validation; PKCE, state, exact redirect/resource/scope validation; login/consent/deny; token expiry, refresh/revocation, and cross-client/user isolation.
- Test MCP Streamable HTTP handshake/tool discovery and calls; task natural-language payload creation; accessible task listing; owner/shared/group authorization; owner-only field mutation and deletion.
- Test delete preview has no side effect; reject MCP confirmation until the owning user signs in and approves on the TaskStack page; then allow confirmation once. Reject wrong-account approval, CSRF replay, absent/false confirmation, expired/reused/cross-user tokens, and stale task snapshots.
- Run all existing tests and the added protocol/API tests. Do not connect to or mutate production data.

## Boundaries

- **Always:** Keep changes in this isolated worktree; derive authorization from server state; hash opaque tokens; validate all external input; use parameterized SQL; include the versioned schema additions in existing DB initialization; preserve old API behavior; test SQLite and verify PostgreSQL-compatible SQL.
- **Ask first:** Production deployment or data changes; adding a new external service; changing account login behavior; changing release metadata; changing existing task-sharing policy.
- **Never:** Merge or tag/release v1.3; put credentials/tokens in client configuration or logs; accept a TaskStack bearer token as MCP authorization; accept `user_id` from a model as identity; delete on the first MCP call; modify the primary checkout; add calendar APIs or Claude skill.

## Success Criteria

1. Existing TaskStack API authentication, task visibility, sharing, and owner-only delete tests still pass.
2. OAuth discovery conforms to MCP remote authorization requirements; PKCE S256 and `resource` are enforced, user consent is per client and revocable, and MCP tokens cannot authenticate to ordinary TaskStack API routes.
3. Standard Streamable HTTP clients can initialize, list tools, and call tools with the OAuth bearer token.
4. MCP operations pass isolation and sharing tests, and natural-language date strings are preserved.
5. Delete cannot mutate on preview or an MCP-only `confirm=true`; the owning user must explicitly approve through the protected TaskStack page, and the approval is user/task/snapshot-bound, short-lived, and single-use.
6. Existing Render service remains the only service; no deployment, production mutation, release metadata change, or release occurs.
7. Documentation separates tested clients from expected interoperability.

## Verified protocol sources

- MCP Streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP authorization and OAuth discovery/resource requirements: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- MCP tools and annotations: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- MCP Python SDK and ASGI integration: https://py.sdk.modelcontextprotocol.io/run/asgi/
- MCP Python SDK tools/context: https://py.sdk.modelcontextprotocol.io/servers/tools/ and https://py.sdk.modelcontextprotocol.io/handlers/context/
- OAuth 2.0 Security Best Current Practice: https://datatracker.ietf.org/doc/html/rfc9700
- Claude Code MCP server configuration and OAuth: https://docs.anthropic.com/en/docs/claude-code/mcp
- OpenAI Responses API remote MCP tools: https://platform.openai.com/docs/guides/tools-remote-mcp
- DeepSeek API function calling: https://api-docs.deepseek.com/guides/function_calling

## Open Questions

No implementation-blocking questions remain. Compatibility statements remain limited to the protocol evidence above; actual third-party client interoperability requires separate end-to-end testing.
