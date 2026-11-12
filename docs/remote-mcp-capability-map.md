# TaskStack Remote MCP Capability Map

Baseline: released GitHub `main` v1.2.0. The v1.3 feature and release metadata are prepared; production deployment remains separate.

| Module id | Responsibility | Depends on |
|---|---|---|
| `mcp-remote-auth` | OAuth 2.1 authorization-code + PKCE, client registration, explicit per-client consent, scoped tokens, and revocation using existing TaskStack accounts | Existing account/session and database layer |
| `mcp-task-tools` | Streamable HTTP MCP task tools; enforce existing task visibility and mutation rules, plus explicit two-step delete confirmation | `mcp-remote-auth` |
| `mcp-hosting-interop` | Mount MCP in the existing FastAPI/Render service, publish protocol discovery, document client setup and tested/expected compatibility | `mcp-remote-auth`, `mcp-task-tools` |

Build order: `mcp-remote-auth` → `mcp-task-tools` → `mcp-hosting-interop`.

All modules share the existing FastAPI process and database. No calendar API, client-specific API, Claude skill, or second service is in scope.
