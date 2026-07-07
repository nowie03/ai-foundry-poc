# Pitfalls & Lessons Learned

Every non-obvious bug, gotcha, and constraint hit during the build. Format: **symptom → root cause → fix → affected file**.

Cross-references to the specific doc where context applies are included at the end of each entry.

---

## Bug 1: FastMCP 421 Misdirected Request from ngrok

**Symptom:**
```
openai.BadRequestError: Error code: 400
Server returned 421: Misdirected Request
```
The agent runtime called the local MCP server's `ListTools` endpoint and got 421 back. The MCP server logs showed the request arriving but being rejected.

**Root cause:**
`TransportSecuritySettings(allowed_hosts=["localhost", "127.0.0.1"])` does two things: it sets an allowlist *and* it implicitly enables DNS rebinding protection. ngrok routes requests to localhost, but the `Host` header it sends contains the port (`127.0.0.1:8765`). The host validation strips the port before matching, but the rebinding protection code checked the header as-is — so `127.0.0.1:8765` did not match `127.0.0.1` and the request was rejected.

**Fix:**
```python
# local_mcp/server.py
mcp = FastMCP(
    ...,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
```
Removing host validation entirely is safe here — ngrok handles TLS termination and the tunnel itself is authenticated. No local process can spoof an ngrok URL.

**Files:** `local_mcp/server.py`
**See also:** [Architecture — TransportSecuritySettings decision](architecture.md#enable_dns_rebinding_protectionfalse-on-fastmcp)

---

## Bug 2: Toolbox MCPTool 424 external_connector_error

**Symptom:**
```
openai.BadRequestError: Error code: 400
{'error': {'message': 'Server returned 424: None', 'code': 'external_connector_error'}}
```
Appeared on agent calls that used `MCPTool` pointing at the toolbox MCP endpoint (`/toolboxes/{name}/mcp`).

**Root cause:**
The toolbox MCP endpoint requires the Azure hosted agent runtime to authenticate against it. That auth path uses a `project_connection_id` — a connection registered in the Azure AI Foundry portal under **Connections**. When `project_connection_id` is absent (or not matching a real registered connection), the runtime cannot obtain a token for the toolbox endpoint and returns 424.

This is not documented prominently. The `MCPTool` model accepts `project_connection_id` as an optional field, but for hosted runtime use it is effectively required.

**Fix:**
Remove the toolbox `MCPTool` from the agent definition entirely. Attach tools directly:
```python
# harness/runner/runner.py — deploy()
definition = PromptAgentDefinition(
    model=...,
    instructions=BASE_INSTRUCTIONS,
    tools=[
        WebSearchTool(),        # direct — no connection_id needed
        MCPTool(
            server_label="local-tools",
            server_url=config.local_mcp_url,
            require_approval="never",
        ),
    ],
)
```
The toolbox is still created and synced (`deploy_toolbox.py`) for use with AI Foundry Playground UI agents, but the harness runner bypasses it.

**Files:** `harness/runner/runner.py`, `harness/toolbox/builder.py`
**See also:** [Deployment — why WebSearchTool is used directly](deployment.md#3-deploy-agent)

---

## Bug 3: OTLPSpanExporter 404 on /v1/traces

**Symptom:**
Spans not reaching the collector. Manually curling the collector base URL returned 404. The exporter logs showed HTTP 404 on POST.

**Root cause:**
`OTLPSpanExporter(endpoint="https://host")` uses the URL exactly as given — it does NOT auto-append `/v1/traces`. The OTEL collector only exposes `/v1/traces` and `/v1/logs`, so a POST to the bare root returned 404.

This is a common misconception: `OTLPSpanExporter` will auto-append the path only if the endpoint does not already include a path. When the URL is the root (`https://host`), it POSTs to `https://host` (no path), which is not a valid OTLP endpoint.

**Fix:**
Normalize the endpoint explicitly in `harness/telemetry.py:_apply()`:
```python
base = endpoint.rstrip("/")
if base.endswith("/v1/traces"):
    base = base.removesuffix("/v1/traces")
traces_endpoint = f"{base}/v1/traces"
logs_endpoint = f"{base}/v1/logs"
```
This handles all three input forms: bare host, host + `/v1/traces`, and host + any other path.

**Files:** `harness/telemetry.py`
**See also:** [Observability — trace pipeline](observability.md#trace-pipeline)

---

## Bug 4: AIProjectInstrumentor emits no spans

**Symptom:**
OTEL SDK installed and configured, `AIProjectInstrumentor().instrument()` called, no spans appeared in the collector or console.

**Root cause:**
`AIProjectInstrumentor` routes its spans through `azure-core`'s internal tracing abstraction (`azure.core.settings.settings.tracing_implementation`). By default this is a no-op. It only emits real spans when `settings.tracing_implementation` is set to an OTEL-backed implementation.

The bridge package `azure-core-tracing-opentelemetry` provides `OpenTelemetrySpan`, which connects `azure-core`'s tracing calls to the OTEL `TracerProvider`. Without it, even a fully configured OTEL SDK is invisible to the Azure SDK.

This package is not listed as a dependency of `azure-ai-projects`. It must be installed and wired separately.

**Fix:**
```python
# requirements.txt
azure-core-tracing-opentelemetry>=1.0.0b11

# harness/telemetry.py — in _apply(), after setting up the TracerProvider
from azure.core.settings import settings
from azure.core.tracing.ext.opentelemetry_span import OpenTelemetrySpan
settings.tracing_implementation.set_value(OpenTelemetrySpan)
```

**Files:** `requirements.txt`, `harness/telemetry.py`
**See also:** [Architecture — azure-core-tracing-opentelemetry](architecture.md#azure-core-tracing-opentelemetry-as-a-required-bridge)

---

## Bug 5: AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING must be set before instrument()

**Symptom:**
Spans appeared (Bug 4 fixed) but were missing GenAI semantic convention attributes: no `gen_ai.agent.name`, no `gen_ai.usage.input_tokens`, no `gen_ai.conversation.id`.

**Root cause:**
The Azure AI Projects SDK checks `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` when `AIProjectInstrumentor().instrument()` is called. The env var is read at that exact moment — not lazily, not at span creation time. Setting it afterward (e.g. after imports or after `instrument()`) has no effect.

**Fix:**
Set the env var programmatically as the first action in `_apply()`, before any imports:
```python
def _apply(endpoint, ...):
    if not endpoint:
        return
    # Must be set BEFORE any instrumentation import reads it
    os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
    if content_recording:
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
    # ... imports and setup follow
    AIProjectInstrumentor().instrument(enable_content_recording=content_recording)
```

**Files:** `harness/telemetry.py`
**See also:** [Observability — trace pipeline](observability.md#trace-pipeline)

---

## Bug 6: Observe Inc exporter — "no such host" DNS error

**Symptom:**
OTEL traces flowing to the collector (confirmed via debug exporter stdout), but nothing reaching Observe Inc after 15+ minutes. Collector logs (when checked via `az containerapp logs show`) showed DNS resolution errors:
```
dial tcp: lookup .collect.observeinc.com: no such host
```
Note the leading dot in the hostname.

**Root cause:**
The collector config (`/etc/otelcol/collector-config.dev.yaml`, baked into the image) uses environment variable substitution for the Observe Inc URL:
```yaml
endpoint: "https://${env:OBSERVE_CUSTOMER_ID}.collect.observeinc.com/v2/otel"
```
The Container App was missing `OBSERVE_CUSTOMER_ID` as an environment variable. When the OTEL collector started, `${env:OBSERVE_CUSTOMER_ID}` resolved to an empty string, producing `https://.collect.observeinc.com/v2/otel` — a syntactically valid but unresolvable hostname.

**Timeline:** The collector Docker image was updated at 13:44 UTC (June 29) — 7 minutes after the current Container App revision was created (13:37 UTC). The new image added the Observe Inc exporter with `${env:OBSERVE_CUSTOMER_ID}` substitution, but the Container App revision was already running with the old image and env vars. The env vars were never added.

**Fix:**
Add secrets and env vars to the Container App:
```bash
az containerapp secret set \
  --name ca-collector-dev \
  --resource-group rg-langchain-dev \
  --secrets "observe-customer-id=<id>" "observe-datastream-token=<token>"

az containerapp update \
  --name ca-collector-dev \
  --resource-group rg-langchain-dev \
  --set-env-vars \
    "OBSERVE_CUSTOMER_ID=secretref:observe-customer-id" \
    "OBSERVE_DATASTREAM_TOKEN=secretref:observe-datastream-token"
```
A new revision (`ca-collector-dev--0000001`) was created automatically.

**Investigation technique:** The collector config was embedded in the image, not mounted as a volume. To read it without running the container, we used:
```bash
id=$(az acr run --registry cragentdevkmmebrrah74ma --cmd \
  "docker create cragentdevkmmebrrah74ma.azurecr.io/otel-collector:latest" /dev/null 2>&1 | tail -1)
docker cp $id:/etc/otelcol/collector-config.dev.yaml /tmp/
```

**Files:** `ca-collector-dev` Container App (Azure resource)
**See also:** [Observability — collector secrets](observability.md#required-container-app-secrets-and-env-vars), [Azure Resources — ca-collector-dev](azure-resources.md#container-app-ca-collector-dev)

---

## Bug 7: `project.get_openai_client()` required for conversations

**Symptom:**
```
openai.NotFoundError: The model 'conversations' does not exist
```
or similar errors when calling `openai_client.conversations.create()`.

**Root cause:**
The Azure AI Foundry conversations endpoint lives at the project-scoped URL:
```
https://<account>.services.ai.azure.com/api/projects/<project>/openai/v1/conversations
```

`build_openai_client()` in `harness/client.py` uses `AZURE_OPENAI_ENDPOINT` which points at the global Azure OpenAI path:
```
https://<account>.services.ai.azure.com/openai/v1/
```

That path does not expose the conversations or responses APIs — those are project-scoped features of the Azure AI Foundry runtime, not the global Azure OpenAI service.

**Fix:**
In `AgentRunner.run()`, always use `self._project.get_openai_client()`, which configures the correct project-scoped base URL automatically.

**Files:** `harness/runner/runner.py`
**See also:** [Architecture — `project.get_openai_client()` decision](architecture.md#projectget_openai_client--not-build_openai_client)

---

## Gotcha: DEBUG log level causes a feedback loop

**Symptom:**
At `OTEL_LOG_LEVEL=DEBUG`, the collector receives an exponentially growing stream of log records containing HTTP POST metadata — things like:
```
https://ca-collector-dev... "POST /v1/logs HTTP/1.1" 200 2
```

**Root cause:**
`LoggingHandler` is added to the root `logging.Logger`. At DEBUG level, this captures urllib3's connection-pool debug messages, which include logs of every HTTP request made. When the OTEL log exporter POSTs to `/v1/logs`, urllib3 logs that request at DEBUG level. That log record is exported, triggering another POST, which triggers another debug log, and so on. The batch processor buffers entries so it doesn't spin infinitely, but the noise is significant.

**Fix:**
Keep `OTEL_LOG_LEVEL=INFO` in production. The harness loggers (`harness.*`) emit meaningful records at INFO and above. Only set DEBUG for short manual pipeline verification sessions.

**Files:** `.env` (`OTEL_LOG_LEVEL`), `harness/telemetry.py`
**See also:** [Observability — log level guide](observability.md#log-level-guide)

---

## Gotcha: `setup_telemetry_from_env` ignores `OTEL_SERVICE_NAME`

**Why this is intentional:**
`local_mcp/server.py` is a separate process with its own OTEL identity: `service.name=local-mcp`. If `setup_telemetry_from_env` read `OTEL_SERVICE_NAME` from the environment, it would inherit `foundry-harness` from `.env` (shared with the main harness), and the MCP spans would appear under the wrong service in traces.

**Design:**
`setup_telemetry_from_env(service_name=...)` takes `service_name` as a mandatory keyword argument and ignores `OTEL_SERVICE_NAME` entirely. This way `local_mcp/server.py` always gets:
```python
setup_telemetry_from_env(service_name="local-mcp")
```
regardless of what `.env` has configured.

**Files:** `harness/telemetry.py`, `local_mcp/server.py`
