# `agent.toml` Manifest Specification

`agent.toml` is the declarative, framework-neutral manifest governing an Agent Bricks agent. It specifies dependencies, tool bindings, memory/session stores, and tracing configuration.

---

## Minimal Example

```toml
schema_version = 1

[agent]
framework = "langgraph"       # "langgraph" or "openai"
server = "agentbricks"        # "agentbricks" or "custom"
deployment_name = "sales-copilot"

[memory_store]
name = "sales-copilot-memory"

[session_store]
name = "sales-copilot-sessions"

[tracing]
experiment_name = "/Users/dev@company.com/sales-copilot-traces"
```

---

## Schema Sections

### 1. `[agent]` Table (Required)
- `framework` (string, required): Either `"langgraph"` or `"openai"`.
- `server` (string, required): `"agentbricks"` (managed durable runtime) or `"custom"` (standalone FastAPI).
- `deployment_name` (string, optional): Base name for Databricks Apps deployment (will be prefixed with `agent-bricks-`).

### 2. `[[tools]]` Array of Tables (Optional)
Defines tool integrations.

#### Unity Catalog Function:
```toml
[[tools]]
id = "get_stock_quote"
auth = "app" # or "user"
source = { kind = "uc-function", function = "finance.market_data.get_latest_price" }
```

#### Secure Python Data Sandbox:
```toml
[[tools]]
id = "data_interpreter"
source = { kind = "sandbox" }
policy = { downscope = [
  { resource = "table:analytics.crm.customers", permission = "read_only" },
  { resource = "volume:analytics.crm.reports", permission = "read_write" },
  { resource = "workspace:/Workspace/Shared/Queries", permission = "read_only" }
] }
```

#### Managed MCP Service:
```toml
[[tools]]
id = "github_tool"
source = { kind = "mcp", service = "system.ai.github" }
auth = "user" # user-delegated auth requires --allow-user-scope-update on deploy
```

#### Databricks Genie Space:
```toml
[[tools]]
id = "bi_genie"
source = { kind = "genie", space_id = "01ef87a4..." }
```

---

### 3. `[memory_store]` Table (Optional)
Declares the Lakebase-backed long-term memory store.
```toml
[memory_store]
name = "my-agent-memory"
# id = "store_id_uuid" (provisioned automatically at deployment)
```

### 4. `[session_store]` Table (Optional)
Declares the Lakebase-backed session store for conversation thread persistence.
```toml
[session_store]
name = "my-agent-sessions"
```

### 5. `[tracing]` Table (Optional)
Declares the target MLflow workspace experiment for Unity Catalog tracing.
```toml
[tracing]
experiment_name = "/Users/user@company.com/agent-traces"
```
