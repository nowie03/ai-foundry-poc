# Architecture

## What this is

A Python harness that deploys a hosted AI agent on Azure AI Foundry, gives it local file system and shell tool access via the Model Context Protocol (MCP), and instruments the whole thing with OpenTelemetry tracing and structured logging.

The key design challenge: Azure's hosted agent runtime runs in Microsoft's cloud, but local developer tools (files, shell) run on your machine. MCP + ngrok bridges that gap. OpenTelemetry makes both sides observable in one trace.

---

## Why Azure AI Foundry

| Capability | What it provides |
|---|---|
| **Skills API** | Reusable prompt skills defined as Markdown files, versioned and hosted in Foundry. The agent discovers and loads them via MCP at runtime. |
| **Toolbox API** | Composable tool bundles (web search + MCP integrations + skill references) exposed as a single MCP endpoint. Useful for Foundry Playground agents. |
| **Hosted agent runtime** | Conversations API + Responses API manage multi-turn state server-side; no local loop required. |
| **Built-in OTEL instrumentation** | `AIProjectInstrumentor` auto-instruments both the Agents API and the Responses API with GenAI semantic convention spans. |

---

## System diagram

```
Developer Machine                       Azure AI Foundry (eastus)
─────────────────────                   ──────────────────────────
local_mcp/server.py ←──── ngrok ──────► Agent Runtime
  read_file                               Conversations API  (/v1/conversations)
  write_file                              Responses API      (/v1/responses)
  list_files                              Skills API         (/v1/skills)
  run_shell                               Toolbox API        (/v1/toolboxes)

        │ OTLP/HTTP /v1/traces                   │ OTLP/HTTP /v1/traces
        │ OTLP/HTTP /v1/logs                     │
        └──────────────────────┬─────────────────┘
                               ▼
              ┌─────────────────────────────────────┐
              │  ca-collector-dev  (OTEL Collector)  │
              │  Authorization: Bearer <token>        │
              │                                       │
              │  ├─► debug exporter (stdout)          │
              │  │     └─► Container App log stream   │
              │  │           └─► law-agent-dev (LA)   │
              │  │                                     │
              │  ├─► azuremonitor exporter             │
              │  │     └─► ai-agent-dev (App Insights) │
              │  │                                     │
              │  └─► otlphttp/observe exporter         │
              │        └─► Observe Inc (long-term)     │
              └─────────────────────────────────────────┘
```

---

## Component table

| Module | Role | Key SDK / framework |
|---|---|---|
| `harness/config.py` | Loads all env vars into `HarnessConfig` dataclass | `python-dotenv` |
| `harness/client.py` | Factory for `AIProjectClient` and OpenAI client | `azure-ai-projects`, `openai` |
| `harness/telemetry.py` | OTEL bootstrap (traces + logs) | `opentelemetry-sdk`, `azure-core-tracing-opentelemetry` |
| `harness/runner/runner.py` | Agent deploy, conversation lifecycle, MCP approval loop | `azure-ai-projects`, `openai` |
| `harness/skills/manager.py` | Parse `SKILL.md` files, sync to Foundry Skills API | `azure-ai-projects` beta |
| `harness/toolbox/builder.py` | Assemble toolbox versions with tools + skill references | `azure-ai-projects` beta |
| `local_mcp/server.py` | FastMCP HTTP server exposing 4 file/shell tools | `mcp` (FastMCP), `uvicorn` |
| `scripts/` | CLI entry points (run, deploy, sync, delete) | — |
| `skills/*/SKILL.md` | Reusable prompt skills (YAML front matter + body) | — |

---

## Key design decisions

These are the non-obvious choices made during the build. Each one has a corresponding entry in [`pitfalls.md`](pitfalls.md) with the full bug story.

### `project.get_openai_client()` — not `build_openai_client()`
The conversations endpoint (`/v1/conversations`) lives under the project-scoped base URL: `https://<account>.services.ai.azure.com/api/projects/<project>/openai/v1/`. The `build_openai_client()` helper points at the global `/openai/v1` endpoint which does not host conversations. Use `self._project.get_openai_client()` in `AgentRunner.run()` exclusively.

### `WebSearchTool()` directly on the agent, not via toolbox MCPTool
The toolbox exposes its tools as MCP at `/toolboxes/{name}/mcp`. For a hosted agent to call it, the runtime must authenticate to that endpoint using a `project_connection_id` registered in the Foundry portal. If that field is absent, Azure returns a 424 `external_connector_error`. Solution: attach `WebSearchTool()` directly to the `PromptAgentDefinition` — it requires no connection registration. The toolbox is still useful in the Foundry Playground UI.

### `enable_dns_rebinding_protection=False` on FastMCP
`TransportSecuritySettings(allowed_hosts=[...])` implicitly enables DNS rebinding protection. When ngrok routes requests to localhost, the `Host` header contains the port (e.g. `127.0.0.1:8765`), which failed the host validation check and caused 421 Misdirected Request errors. Disabling rebinding protection entirely is safe here because ngrok handles TLS termination and authentication.

### `azure-core-tracing-opentelemetry` as a required bridge
`AIProjectInstrumentor().instrument()` internally calls `azure-core`'s `settings.tracing_implementation` to route spans to the active tracer. Without `azure-core-tracing-opentelemetry`, that call is a no-op and no spans are emitted — even if the OTEL SDK is fully installed. This package is not listed as a dependency of `azure-ai-projects`. See [`pitfalls.md — Bug 4`](pitfalls.md#bug-4-aiprojectinstrumentor-emits-no-spans).

### `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` must precede `instrument()`
The Azure SDK reads this env var at `instrument()` call time. Setting it afterward misses the gate. `harness/telemetry.py:_apply()` sets it via `os.environ` as the very first action before any import.

### Dual OTEL pipelines, independent failure
The trace pipeline and log pipeline are set up in separate `try/except` blocks. If the log pipeline fails (e.g. wrong log exporter URL), traces still flow. This prevents a misconfigured logging endpoint from taking down observability entirely.
