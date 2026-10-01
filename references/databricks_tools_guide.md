# Databricks Tools & Security Integration Guide

This guide details how to integrate and secure Databricks-native tools (Unity Catalog Functions, Managed MCP, Python Sandbox, and Genie) within Agent Bricks.

---

## 1. Tool Categories and Use Cases

| Tool Kind | Source / Provider | Best For | Security / Isolation |
| :--- | :--- | :--- | :--- |
| **`uc-function`** | Unity Catalog SQL/Python Functions | Pre-defined SQL queries, domain algorithms, DB lookups | Governed by UC ACLs |
| **`sandbox`** | Databricks Isolated Python Sandbox | Dynamic code generation, plotting, statistical analysis | Fine-grained **downscoping** per table/volume |
| **`mcp`** | Managed Model Context Protocol | External API connectors (Slack, Jira, GitHub, custom MCPs) | Managed OAuth / Token delegation |
| **`genie`** | Databricks Genie Analytics Spaces | Natural language BI questions against lakehouse metrics | Genie space governance |
| **Local Tools** | Local Python in `agent/tools/` | In-process logic, custom data formatting, utility helpers | Process-local |

---

## 2. Binding Tools via Agent Bricks CLI

### Unity Catalog Functions
```bash
# Add a UC function with App Service Principal identity
agentbricks tools add uc-function get_customer --function sales.crm.get_customer_by_id

# Add with end-user identity (On-Behalf-Of)
agentbricks tools add uc-function get_salary --function hr.payroll.get_salary --auth user
```

### Secure Python Data Sandbox with Downscoping
The sandbox tool provides a secure Python REPL. Protect your lakehouse data by explicitly granting read-only or read-write access to specific resources:
```bash
agentbricks tools add sandbox data_analyst \
  --downscope table:analytics.finance.revenue:read_only \
  --downscope table:analytics.finance.expenses:read_only \
  --downscope volume:analytics.finance.exports:read_write \
  --downscope workspace:/Workspace/Shared/Reports:read_only
```

### Managed MCP (Model Context Protocol) Services
```bash
# Discover available MCP services in workspace
agentbricks tools list --kind mcp

# Bind an MCP service
agentbricks tools add mcp github_tool --service system.ai.github
```

---

## 3. How the Runtime Loads Bound Tools

Agent Bricks passes tool definitions from `agent.toml` directly into the agent runtime via `databricks_agentkit`.

### In LangGraph (`agent/agent.py`):
```python
from databricks_agentkit.langgraph import mcp_tools, memory_tools
from agent.tools import local_tools # discovered in agent/tools/__init__.py

def get_tools(actor: str):
    # mcp_tools loads UC functions, Sandbox, and MCP services defined in agent.toml
    managed = mcp_tools()
    
    # memory_tools provides actor-scoped get/set memory tools if bound in agent.toml
    mem = memory_tools(actor=actor)
    
    return [*local_tools, *managed, *mem]
```

### In OpenAI Agents SDK (`agent/agent.py`):
```python
from databricks_agentkit.openai import mcp_tools, memory_tools
from agent.tools import local_tools

def build_agent(actor: str):
    tools = [*local_tools, *mcp_tools(), *memory_tools(actor=actor)]
    return Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
        tools=tools,
    )
```

---

## 4. Authentication Modes: `app` vs `user` (OBO)

- **`auth = "app"` (Default)**:
  - The tool executes using the credentials and permissions of the Databricks App's Service Principal.
  - Ideal for general-purpose background agents or system automations where users share identical access rights.
- **`auth = "user"` (On-Behalf-Of delegation)**:
  - The tool executes using the calling user's OAuth access token.
  - Respects fine-grained Unity Catalog row/column-level security per individual user.
  - When deploying an app with `auth = "user"`, use the `--allow-user-scope-update` flag:
    ```bash
    agentbricks deploy <app_name> --allow-user-scope-update
    ```
