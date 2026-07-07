# OTel Collector — Local Usage

## Files

| File | Purpose |
|------|---------|
| `collector-config.debug.yaml` | Local Milestone 1 testing — OTLP receiver → stdout only |
| `collector-config.dev.yaml`   | Dev environment — 100% sampling, debug + Azure Monitor exporters |
| `collector-config.prod.yaml`  | Prod environment — 20% sampling, Azure Monitor exporter only |

---

## Quick Start (local dev)

### 1. Debug mode (no Azure required)

```bash
docker run -d --rm \
  -p 4317:4317 -p 4318:4318 \
  --name otel-debug \
  -v $(pwd)/collector/collector-config.debug.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector-contrib:latest

docker logs -f otel-debug   # watch spans arrive
```

### 2. Dev mode (with Azure App Insights + Observe Inc)

`collector-config.dev.yaml` requires bearer-token auth on the OTLP receivers plus
credentials for both the Azure Monitor and Observe Inc exporters:

```bash
export AZURE_APPINSIGHTS_CONNECTION_STRING="InstrumentationKey=<dev-key>;..."
export COLLECTOR_AUTH_TOKEN="$(openssl rand -hex 32)"
export OBSERVE_CUSTOMER_ID="<observe-customer-id>"
export OBSERVE_DATASTREAM_TOKEN="<observe-datastream-token>"
```

Then start the collector:

```bash
docker run -d --rm \
  -p 4317:4317 -p 4318:4318 \
  --name otel-dev \
  -e AZURE_APPINSIGHTS_CONNECTION_STRING \
  -e COLLECTOR_AUTH_TOKEN \
  -e OBSERVE_CUSTOMER_ID \
  -e OBSERVE_DATASTREAM_TOKEN \
  -v $(pwd)/collector/collector-config.dev.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector-contrib:latest
```

Run the app:

```bash
APP_ENV=dev \
OTEL_SERVICE_NAME=langchain-agent \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
.venv/bin/python local-agent.py
```

### 3. Prod mode (with Azure App Insights)

Swap in the prod connection string and prod config:

```bash
export AZURE_APPINSIGHTS_CONNECTION_STRING="InstrumentationKey=<prod-key>;..."
export COLLECTOR_AUTH_TOKEN="$(openssl rand -hex 32)"

docker run -d --rm \
  -p 4317:4317 -p 4318:4318 \
  --name otel-prod \
  -e AZURE_APPINSIGHTS_CONNECTION_STRING \
  -e COLLECTOR_AUTH_TOKEN \
  -v $(pwd)/collector/collector-config.prod.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector-contrib:latest

APP_ENV=prod \
OTEL_SERVICE_NAME=langchain-agent \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
.venv/bin/python local-agent.py
```

> **Note:** Zero application code changes between dev and prod runs.  
> The only differences are the `APP_ENV` env var and which collector config is mounted.

---

## Switching environments

The entire environment switch is:
1. Change `APP_ENV` from `dev` → `prod`
2. Change `AZURE_APPINSIGHTS_CONNECTION_STRING` to the prod connection string
3. Mount `collector-config.prod.yaml` instead of `collector-config.dev.yaml`

No source code changes. No image rebuilds.

---

## Cloud deployment (Azure Container Apps)

The collector runs as its own Container App (`ca-collector-{env}`) provisioned by
`infra/main.bicep` into `rg-immanuelnowpertt-6876`. After the Bicep deployment creates the
Container Registry, build and push this image with ACR Tasks (no local Docker needed):

```bash
az acr build \
  --registry <acr-login-server-without-.azurecr.io> \
  --image otel-collector:latest \
  --file collector/Dockerfile \
  collector/
```

Then force the Container App to pull the new image:

```bash
az containerapp update \
  --name ca-collector-dev \
  --resource-group rg-immanuelnowpertt-6876 \
  --image <acr-login-server>/otel-collector:latest
```

See `infra/README.md` for the full Bicep deploy sequence and secrets handling.
