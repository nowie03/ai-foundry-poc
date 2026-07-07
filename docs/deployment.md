# Deployment Guide

## Deployment order

Skills → Toolbox → Agent

Skills must exist in Foundry before the toolbox can reference them. The toolbox should exist before the agent is deployed, though the agent doesn't strictly depend on it (the harness runner uses tools directly, not through the toolbox MCP endpoint).

---

## 1. Sync Skills

```bash
python scripts/sync_skills.py
```

Walks `skills/*/SKILL.md`, parses each file, and upserts it to the Foundry Skills API. Each skill is created as a new version and immediately promoted to default.

### SKILL.md format

```markdown
---
name: code-review
description: Perform a thorough code review of provided files
---

# Code Review Skill

You are an expert code reviewer...
(full instructions follow)
```

The front matter (`---...---`) is required. `name` and `description` are the only mandatory fields. The body (everything after the closing `---`) is the skill's instruction content.

### Bundled skills

| Skill | Description |
|---|---|
| `code-review` | Reads files, analyzes bugs/security/performance, writes findings to `code_review_output.md` |
| `research` | Searches 3–5 sources, cross-references claims, writes report to `research_output.md` |
| `summarize` | Reads files or text, produces TL;DR + key points, stays under 300 words |

### Adding a new skill

1. Create `skills/<name>/SKILL.md` with the front matter + instructions
2. Run `python scripts/sync_skills.py` — it will pick up all directories automatically

---

## 2. Deploy Toolbox

```bash
python scripts/deploy_toolbox.py
```

Creates a new toolbox version containing:
- `WebSearchTool` — Bing web search
- `ToolboxSearchPreviewTool` — search across toolbox contents
- `ToolboxSkillReference` — one entry per skill in `skills/`
- `MCPTool` entries — one per connection in `MCP_CONNECTIONS`

The toolbox MCP endpoint is printed after creation:
```
https://<foundry-endpoint>/toolboxes/harness-toolbox/mcp?api-version=v1
```

This endpoint is what AI Foundry Playground agents use to access tools and skills. The harness runner (`AgentRunner`) does not call through it — it attaches tools directly to the agent definition.

### External MCP connections

To add an external MCP server (e.g. GitHub, Jira) to the toolbox:
1. Register the connection in the Azure AI Foundry portal under **Connections**
2. Add it to `MCP_CONNECTIONS` in `.env`:
   ```json
   {"github": {"server_url": "https://api.githubcopilot.com/mcp", "connection_id": "my-conn", "require_approval": "always"}}
   ```
3. Re-run `deploy_toolbox.py` to create a new toolbox version

---

## 3. Deploy Agent

```bash
python scripts/deploy_agent.py
```

Creates a `PromptAgentDefinition` with:
- `WebSearchTool()` — Bing web search attached directly to the agent
- `MCPTool(server_label="local-tools", server_url=LOCAL_MCP_URL, require_approval="never")` — the local file/shell MCP server

The agent name and version are saved to `.agent_ref`:
```
foundry-harness:1
```

The runner reads this file at conversation time to identify which agent to invoke. You don't need to pass the version anywhere — it's resolved automatically.

> **Why `WebSearchTool()` directly instead of through the toolbox?**
> The toolbox exposes its tools at `/toolboxes/{name}/mcp`. For a hosted agent to call that endpoint, it needs a `project_connection_id` registered in the Foundry portal. If that field is absent, the Azure runtime returns a 424 `external_connector_error`. Attaching `WebSearchTool()` directly bypasses this auth constraint entirely. See [`pitfalls.md — Bug 2`](pitfalls.md#bug-2-toolbox-mcptool-424-external_connector_error).

### Base instructions

The agent is given these system instructions:

> You are an agentic assistant with access to web search, external integrations via MCP, file system tools, shell execution, and reusable skills. Skills are available as MCP resources on the toolbox endpoint — discover and load them when the user's request matches a skill's description. Use tools proactively to complete tasks.

---

## 4. Run conversations

```bash
# New conversation
python scripts/run.py "What files are in this directory?"

# Continue an existing conversation
python scripts/run.py --conversation conv_0b4daf43... "Now run the tests"
```

The runner:
1. Reads `.agent_ref` to get the deployed agent name
2. Creates a new conversation (or uses the provided ID)
3. Sends the message via the Responses API
4. Loops on MCP approval requests if `MCP_REQUIRE_APPROVAL=true`
5. Returns the response text and conversation ID

### MCP approval flow

When `MCP_REQUIRE_APPROVAL=true`, the runner pauses before each MCP tool call:
```
[MCP approval] server=local-tools tool=run_shell
Approve? (y/N):
```

When `false` (default), all MCP calls are auto-approved. The agent can still see approval requests in the span data.

---

## 5. Delete agent

```bash
python scripts/delete_agent.py
```

Reads `.agent_ref`, calls `delete_version()` on the Foundry API, and removes the `.agent_ref` file. Run this before redeploying if you want to clean up old versions.

---

## Re-deployment checklist

When updating the agent after changes:

| Changed | Action needed |
|---|---|
| `skills/*/SKILL.md` | `sync_skills.py` |
| `MCP_CONNECTIONS` or new external MCP | `deploy_toolbox.py` |
| `BASE_INSTRUCTIONS` or tool list | `delete_agent.py` → `deploy_agent.py` |
| `LOCAL_MCP_URL` (new ngrok URL) | `deploy_agent.py` (new agent version with updated URL) |
| `local_mcp/server.py` tool logic | Restart `python -m local_mcp.server` — no Foundry redeploy needed |
