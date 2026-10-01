# Agent Bricks CLI (`agentbricks`) Command Reference

Comprehensive reference of all subcommands, options, and behaviors in `agentbricks`.

---

## Global Options
- `--profile, -p <profile>`: Specify the `~/.databrickscfg` profile to authenticate with.
  **Position matters:** this is a global option and must come *before* the subcommand
  (`agentbricks --profile <p> tools list`, `agentbricks --profile <p> dev`). Only `init` also accepts it after the
  subcommand; `deploy`, `dev`, `tools`, `memory`, `sessions` and `tracing` do not (verified with `--help`) (`agentbricks tools list --profile <p>` fails with
  "No such option '--profile'").
- `--output, -o <text|json>`: Output format (default: `text`).
- `--version`: Display version information.
- `--help, -h`: Show command help.

---

## 1. Project Initialization: `agentbricks init`

Scaffold a local agent project from bundled templates.

```bash
agentbricks init [DIRECTORY] [OPTIONS]
```

### Options:
- `--framework <langgraph|openai>`: Agent framework to scaffold (default: `langgraph`).
- `--server <agentbricks|custom>`: Invocation server type (default: `agentbricks`).
- `--profile <profile>`: Seed local `.env` with `DATABRICKS_CONFIG_PROFILE=<profile>`.
- `--disable-chat-app`: Scaffold API-only backend without the browser chat UI.
- `--memory-store <name>`: Custom display name for the declared Lakebase memory store.
- `--session-store <name>`: Custom display name for the declared Lakebase session store.
- `--existing`: Prepare a migration bundle for an existing LangGraph/OpenAI project.

---

## 2. Local Development: `agentbricks dev`

Run the agent locally wrapping `databricks apps run-local`.

```bash
agentbricks dev [OPTIONS]
```

### Options:
- `--source <path>`: Path to agent project directory containing `app.yaml` (default: `.`).
- `--app-port <port>`: Port to run local app on (default: `8000`). **Always pass a free port.** If
  something else already listens on the default port, the dev proxy (printed `localhost:8001`) forwards to
  that stale process. `dev` runs `uv run start-server`, building `<project>/.venv` and ignoring
  `UV_PROJECT_ENVIRONMENT`.
- `--prepare-environment / --no-prepare-environment`: Force re-building virtual environment via `uv`.

---

## 3. Tool Management: `agentbricks tools`

Discover, bind, and unbind tools in `agent.toml`.

### Subcommands:
- **`agentbricks tools add uc-function <tool_id> --function <catalog.schema.func>`**
  - `--auth <app|user>`: Auth mode (`app` uses App SP, `user` uses user On-Behalf-Of).
- **`agentbricks tools add sandbox <tool_id>`**
  - `--downscope <kind:resource:permission>`: Limit access (e.g. `table:cat.sch.tbl:read_only`, `volume:cat.sch.vol:read_write`, `workspace:/Workspace/dir:read_only`).
- **`agentbricks tools add mcp <tool_id> --service <mcp_service_name>`**
  - Bind a managed Model Context Protocol service.
- **`agentbricks tools add genie <tool_id> --space-id <genie_space_id>`**
  - Bind a Databricks Genie analytics space.
- **`agentbricks tools list`**
  - List available tools, UC functions, and MCP services.
  - `--kind <mcp|...>`: Filter tool types.
  - `--schema <catalog.schema>`: Discover tools in a specific UC schema.
- **`agentbricks tools remove <tool_id>`**
  - Remove a tool binding from `agent.toml`.

---

## 4. State & Memory Management: `agentbricks memory` / `sessions`

### Memory (Cross-session Long-Term Memory):
- `agentbricks memory bind <store_name>`: Bind a Lakebase Memory Store.
- `agentbricks memory unbind`: Unbind memory store.
- `agentbricks memory list`: List accessible memory stores.

### Sessions (Per-conversation Session State):
- `agentbricks sessions bind <store_name>`: Bind a Lakebase Session Store.
- `agentbricks sessions unbind`: Unbind session store.
- `agentbricks sessions list`: List accessible session stores.

---

## 5. Tracing: `agentbricks tracing`

- `agentbricks tracing bind <experiment_name>`: Bind an MLflow workspace experiment path for Unity Catalog tracing (e.g. `/Users/you@company.com/agent-traces`).
- `agentbricks tracing unbind`: Disable tracing in deployed agent.

---

## 6. Deployment: `agentbricks deploy`

Provisions resources and rolls out to Databricks Apps.

```bash
agentbricks deploy [NAME] [OPTIONS]
```

### Options:
- `--source <path>`: Local source directory (default: `.`).
- `--instances <N>`: Set fixed compute instances with sticky routing.
- `--allow-user-scope-update`: Grant required OBO OAuth scopes for tools with `auth = "user"`.
- (no `--profile` here) Use the global form: `agentbricks --profile <profile> deploy ...`.

---

## 7. Deployment Lifecycle: `agentbricks deployments`

- `agentbricks deployments list`: List all Agent Bricks apps.
- `agentbricks deployments get <name>`: Get compute status and public URL.
- `agentbricks deployments logs <name> [--follow]`: View container logs.
- `agentbricks deployments start <name>`: Start stopped deployment.
- `agentbricks deployments stop <name>`: Stop active deployment.
- `agentbricks deployments delete <name> [--yes]`: Tear down deployment.

---

## 8. Endpoint Invocation: `agentbricks endpoint`

- `agentbricks endpoint invoke <path> --data '<json>'`: Send request payload to agent.
- `agentbricks endpoint get <path>`: Send GET request to agent endpoint.
