# Observability

The harness ships with full OpenTelemetry integration: distributed traces covering both the Azure agent runtime and the local MCP server, plus structured log records at configurable severity levels — all exported to the same OTLP/HTTP collector.

---

## Overview

Two independent pipelines are set up in `harness/telemetry.py:_apply()`. Each is wrapped in its own `try/except` so a failure in one does not take down the other.

```
Python process
  │
  ├── Trace pipeline
  │     AIProjectInstrumentor (auto-spans) + custom MCP spans
  │     → TracerProvider → BatchSpanProcessor
  │     → OTLPSpanExporter → {endpoint}/v1/traces
  │
  └── Log pipeline
        stdlib logging → LoggingHandler (OTEL bridge)
        → LoggerProvider → BatchLogRecordProcessor
        → OTLPLogExporter → {endpoint}/v1/logs
```

If `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, both pipelines are skipped entirely — zero overhead, no imports, no errors. Developers without a collector are unaffected.

---

## How `harness/telemetry.py` works

`setup_telemetry(config)` is called at the top of every script, before any client construction. It delegates to `_apply()`:

1. **Early exit** — if `endpoint` is blank, return immediately
2. **Set env gates** — `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` must be set before any instrumentation import reads it. If `OTEL_CAPTURE_CONTENT=true`, also sets `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`
3. **Shared resource** — `Resource({"service.name": service_name})` labels all spans and log records
4. **Endpoint normalization** — constructs explicit `{base}/v1/traces` and `{base}/v1/logs` URLs (the OTLP exporter does NOT auto-append the path — see [Bug 3](pitfalls.md#bug-3-otlpspanexporter-404-on-v1traces))
5. **Trace pipeline** — `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter`
6. **azure-core bridge** — `settings.tracing_implementation.set_value(OpenTelemetrySpan)` — required for `AIProjectInstrumentor` to emit anything (see [Bug 4](pitfalls.md#bug-4-aiprojectinstrumentor-emits-no-spans))
7. **Instrumentation** — `AIProjectInstrumentor().instrument(enable_content_recording=...)` — covers Agents API + Responses API automatically
8. **Log pipeline** — `LoggerProvider` + `BatchLogRecordProcessor` + `OTLPLogExporter`
9. **Root logger hook** — `LoggingHandler` added to `logging.getLogger()` at the configured level
10. **Shutdown hooks** — `atexit.register(lambda: (provider.force_flush(), provider.shutdown()))` for both pipelines

For the local MCP server (a separate process), `setup_telemetry_from_env(service_name="local-mcp")` is called instead — it reads env vars directly and uses `"local-mcp"` as the service name regardless of what `OTEL_SERVICE_NAME` is set to in `.env`.

---

## Trace pipeline

### Auto-instrumented spans

`AIProjectInstrumentor` produces these spans automatically:

| Span name | Triggered by | Key attributes |
|---|---|---|
| `invoke_agent` | `AgentRunner.run()` start | `gen_ai.agent.name`, `gen_ai.provider.name`, `az.namespace` |
| `create_response` | Each `responses.create()` call | `gen_ai.conversation.id`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |

If `OTEL_CAPTURE_CONTENT=true`, span events include the full prompt and completion text. This is useful for debugging but captures user content — enable deliberately.

> **Why the env var must be set before `instrument()`:**
> The Azure SDK checks `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` at call time when `instrument()` runs. Setting it afterward is a no-op. `_apply()` sets it via `os.environ` as the very first step. See [Bug 5](pitfalls.md#bug-5-azure_experimental_enable_genai_tracing-must-be-set-before-instrument).

### Local MCP spans

`local_mcp/server.py` wraps each tool in a manual span using `tracer.start_as_current_span(...)`. These appear as child spans under the `create_response` span when the agent calls an MCP tool.

| Span | Always-set attributes | Content-gated attributes |
|---|---|---|
| `mcp.read_file` | `rpc.method` | `mcp.tool.argument.path` |
| `mcp.write_file` | `rpc.method`, `mcp.tool.argument.content_length` | `mcp.tool.argument.path` |
| `mcp.list_files` | `rpc.method`, `mcp.tool.result.file_count` | `mcp.tool.argument.directory`, `mcp.tool.argument.glob_pattern` |
| `mcp.run_shell` | `rpc.method`, `process.exit_code` | `process.command_line`, `process.working_directory` |

Non-zero exit codes on `run_shell` set `StatusCode.ERROR`. All exceptions set `StatusCode.ERROR` with the exception message.

---

## Log pipeline

Every `logging.getLogger(name)` call in the harness emits a structured log record to `/v1/logs` when at or above `OTEL_LOG_LEVEL`.

### What each module logs

| Logger name | Level | Events |
|---|---|---|
| `harness.telemetry` | INFO | OTEL pipeline startup confirmation |
| `harness.telemetry` | WARNING | Missing package (ImportError), pipeline failure |
| `harness.runner.runner` | INFO | Conversation created, response complete (with char count) |
| `harness.runner.runner` | DEBUG | Message send (with char count), MCP auto-approve decisions |
| `harness.runner.runner` | WARNING | MCP approval required (interactive mode) |
| `harness.skills.manager` | INFO | Skill synced (name + version) |
| `harness.skills.manager` | DEBUG | Skill parse steps |
| `harness.toolbox.builder` | INFO | Toolbox version created |

### Log level guide

| `OTEL_LOG_LEVEL` | What you get |
|---|---|
| `DEBUG` | Everything, including per-message sends and MCP auto-approvals. **Warning:** also captures urllib3 HTTP debug logs, which creates significant noise (see [Gotcha: DEBUG feedback loop](pitfalls.md#gotcha-debug-log-level-causes-feedback-loop)) |
| `INFO` | Conversation lifecycle events. Good default for production. |
| `WARNING` | MCP approval prompts and pipeline errors only. |
| `ERROR` | Only exceptions and failures. |
| `CRITICAL` | Silent for most harness events. |

> **DEBUG feedback loop:** At `OTEL_LOG_LEVEL=DEBUG`, the `LoggingHandler` is attached to the root logger, which captures urllib3's HTTP connection-pool debug messages — including the OTEL exporter's own POST to `/v1/logs`. This gets exported, triggering another HTTP request, another debug log, and so on. Keep `DEBUG` for short verification sessions only. See [Gotcha](pitfalls.md#gotcha-debug-log-level-causes-feedback-loop).

---

## The collector: `ca-collector-dev`

The collector runs as a Container App in `rg-immanuelnowpertt-6876` (East US 2), alongside the Azure AI Foundry account this repo talks to. It receives OTLP/HTTP on port 4318 (HTTPS, publicly reachable) and fans out to three exporters.

### Endpoints

| Signal | URL |
|---|---|
| Traces | `https://ca-collector-dev.kindsky-8e345864.eastus2.azurecontainerapps.io/v1/traces` |
| Logs | `https://ca-collector-dev.kindsky-8e345864.eastus2.azurecontainerapps.io/v1/logs` |

Authentication: `Authorization: Bearer <COLLECTOR_AUTH_TOKEN>` on every request.

### Exporters

| Exporter | Destination | Use |
|---|---|---|
| `debug` | Container App stdout → Log Analytics (`law-agent-dev`) | Live tail, debugging |
| `azuremonitor` | Application Insights (`ai-agent-dev`) | Dashboards, alerts, 90-day retention |
| `otlphttp/observe` | Observe Inc (`https://<customer_id>.collect.observeinc.com/v2/otel`) | Long-term storage, advanced queries |

### Collector configuration

The config file is baked into the container image at `/etc/otelcol/collector-config.dev.yaml`. The container is launched with `--config=/etc/otelcol/collector-config.dev.yaml`.

The Observe Inc exporter URL uses environment variable substitution: `${env:OBSERVE_CUSTOMER_ID}`. If that env var is missing from the Container App, the URL becomes `https://.collect.observeinc.com/...` — a malformed hostname that fails DNS resolution silently.

> **Critical:** All four env vars below must be set in the Container App for all exporters to work. They are stored as secrets and injected via `secretref:`, and are now provisioned as part of the initial Bicep deploy. See [Bug 6](pitfalls.md#bug-6-observe-inc-exporter--no-such-host-dns-error) for the original incident that motivated this.

### Required Container App secrets and env vars

| Secret name | Env var (via secretref) | Used by |
|---|---|---|
| `collector-auth-token` | `COLLECTOR_AUTH_TOKEN` | Receiver auth |
| `appinsights-connection-string` | `AZURE_APPINSIGHTS_CONNECTION_STRING` | azuremonitor exporter |
| `observe-customer-id` | `OBSERVE_CUSTOMER_ID` | Observe Inc exporter URL |
| `observe-datastream-token` | `OBSERVE_DATASTREAM_TOKEN` | Observe Inc bearer auth |

### Adding a new collector revision

Any change to secrets or env vars creates a new Container App revision automatically. To force a new revision after adding secrets:
```bash
az containerapp update \
  --name ca-collector-dev \
  --resource-group rg-immanuelnowpertt-6876 \
  --set-env-vars "NEW_VAR=secretref:new-secret-name"
```

---

## Verifying the pipeline

### Check traces reach the collector
```bash
az containerapp logs show \
  --name ca-collector-dev \
  --resource-group rg-immanuelnowpertt-6876 \
  --tail 50
# Look for: invoke_agent, create_response spans in debug exporter output
```

### Check log records reach the collector
```bash
# Run agent with explicit flush
python -c "
from harness.config import load_config
from harness.telemetry import setup_telemetry
from opentelemetry import trace
from opentelemetry._logs import get_logger_provider
import logging

cfg = load_config()
setup_telemetry(cfg)
logging.getLogger('test').info('pipeline check')
trace.get_tracer_provider().force_flush(8000)
get_logger_provider().force_flush(8000)
"
# Check collector logs for SeverityText: INFO
```

### Verify Observe Inc receives data
```bash
curl -X POST https://<customer_id>.collect.observeinc.com/v1/http \
  -H "Authorization: Bearer <datastream_token>" \
  -H "Content-Type: application/json" \
  -d '{"test": "ping"}'
# 200 = endpoint reachable
```
