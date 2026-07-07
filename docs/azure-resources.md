# Azure Resources: rg-immanuelnowpertt-6876

**Resource group:** `rg-immanuelnowpertt-6876`
**Region:** East US 2
**Subscription:** `a44445b7-a72e-4bf2-b891-83c0fa5d6a33`
**Tags (Bicep-managed resources only):** `application: langchain-agent`, `environment: dev`, `managedBy: bicep`

> **History:** The observability + collector stack originally lived in `rg-langchain-dev`
> (East US), alongside a full AI Hub/Project/Foundry-account deployment. That stack was torn
> down; only two orphaned resources (`cae-agent-dev`, `aihubdevkmmebr`) were left behind, and
> `rg-langchain-dev` itself was deleted after this redeploy. The Bicep templates in `infra/`
> were updated to deploy into this existing resource group instead of creating their own, and
> no longer provision an AI Hub/Project/Foundry account/Storage/Key Vault — those are covered
> by the resource below that already lived here.

This resource group contains two independent things:
1. **`immanuelnowpertt-6876-resource`** — the Azure AI Foundry account/project (portal-created,
   **not** managed by this repo's Bicep). `.env`'s `AZURE_FOUNDRY_ENDPOINT` /
   `AZURE_OPENAI_ENDPOINT` point here.
2. **The observability + collector stack** — Log Analytics, Application Insights, ACR,
   Container Apps Environment, and the OTel Collector Container App. Provisioned by
   `infra/main.bicep` + `infra/resources.bicep` (indicated by the `managedBy: bicep` tag).

---

## Resource map

```
rg-immanuelnowpertt-6876
├── immanuelnowpertt-6876-resource  (Azure AI Foundry account — pre-existing, not Bicep-managed)
│     └── immanuelnowpertt-6876-re-project  (Foundry project)
│
├── ai-agent-dev  (Application Insights — monitoring)
│     └── law-agent-dev  (Log Analytics Workspace)
│           └── cae-agent-dev  (Container Apps Environment)
│                 └── ca-collector-dev  (OTEL Collector container app)
└── cragentdevooploqbrbm2cy  (ACR — otel-collector image)
```

---

## Summary table

| Resource name | Type | SKU / Tier | Purpose |
|---|---|---|---|
| `immanuelnowpertt-6876-resource` | Cognitive Services account (AIServices) | S0 | Azure AI Foundry account backing `AZURE_FOUNDRY_ENDPOINT` / `AZURE_OPENAI_ENDPOINT` — not Bicep-managed |
| `cae-agent-dev` | Container Apps Environment | — | Runtime host for container apps; routes logs to `law-agent-dev` |
| `ca-collector-dev` | Container App | 0.25 CPU / 0.5 GB | OpenTelemetry Collector; HTTPS port 4318; Bearer token auth |
| `cragentdevooploqbrbm2cy` | Azure Container Registry | Basic | Image: `otel-collector` |
| `law-agent-dev` | Log Analytics Workspace | PerGB2018, 30-day retention | Central log store for CAE and Application Insights |
| `ai-agent-dev` | Application Insights | Web | App monitoring; linked to `law-agent-dev` |

---

## Per-resource detail

### Container Apps Environment: `cae-agent-dev`

The runtime host for all container apps in this environment.

| Property | Value |
|---|---|
| Default domain | `kindsky-8e345864.eastus2.azurecontainerapps.io` |
| Static IP | `57.166.162.148` |
| mTLS | Disabled |
| App logs | → `law-agent-dev` (Log Analytics) |

---

### Container App: `ca-collector-dev`

The OpenTelemetry Collector that receives traces and logs from the harness and fans them out to three backends.

| Property | Value |
|---|---|
| FQDN | `ca-collector-dev.kindsky-8e345864.eastus2.azurecontainerapps.io` |
| Target port | 4318 (HTTPS, external) |
| Image | `cragentdevooploqbrbm2cy.azurecr.io/otel-collector:latest` |
| Container name | `otel-collector` |
| CPU | 0.25 cores |
| Memory | 0.5 GB |
| Startup args | `--config=/etc/otelcol/collector-config.dev.yaml` |
| Min/max replicas | 1 / 1 |
| Identity | System-assigned (Principal ID: `1eb59b7b-f516-45b1-9b7e-62c57f82ba59`) |

**Environment variables (via secrets):**

| Env var | Secret name | Used by |
|---|---|---|
| `COLLECTOR_AUTH_TOKEN` | `collector-auth-token` | OTLP receiver auth |
| `AZURE_APPINSIGHTS_CONNECTION_STRING` | `appinsights-connection-string` | azuremonitor exporter |
| `OBSERVE_CUSTOMER_ID` | `observe-customer-id` | Observe Inc exporter URL (`${env:OBSERVE_CUSTOMER_ID}.collect.observeinc.com`) |
| `OBSERVE_DATASTREAM_TOKEN` | `observe-datastream-token` | Observe Inc bearer auth |

All four secrets are now set as part of the initial Bicep deploy (see
[`pitfalls.md — Bug 6`](pitfalls.md#bug-6-observe-inc-exporter--no-such-host-dns-error) for the
DNS failure this avoids).

**Registry credentials:**

| Property | Value |
|---|---|
| Registry server | `cragentdevooploqbrbm2cy.azurecr.io` |
| Auth | Via `registry-password` secret |

---

### Azure Container Registry: `cragentdevooploqbrbm2cy`

| Property | Value |
|---|---|
| Login server | `cragentdevooploqbrbm2cy.azurecr.io` |
| Admin user | Enabled |
| SKU | Basic |
| Public network access | Enabled |

**Repositories:**

| Repository | Tags | Purpose |
|---|---|---|
| `otel-collector` | `latest` | Custom OTEL Collector with `collector-config.dev.yaml` baked in; built via `az acr build` |

---

### Log Analytics Workspace: `law-agent-dev`

Central log aggregation for the observability stack.

| Property | Value |
|---|---|
| Customer ID | `0d795a93-d11b-411d-aece-8d5e06ecc9b9` |
| SKU | PerGB2018 (pay-as-you-go) |
| Retention | 30 days |

Receives: Container App logs (via CAE), Application Insights data, OTEL debug exporter output (via `ca-collector-dev` stdout).

---

### Application Insights: `ai-agent-dev`

| Property | Value |
|---|---|
| Application type | Web |
| Instrumentation key | `90bba248-ec43-4f9e-91b8-0bd58c1c4d78` |
| Application ID | `6d7076a9-a816-4381-bd97-e23aa14dffec` |
| Ingestion mode | LogAnalytics (integrated with `law-agent-dev`) |
| Public ingestion | Enabled |

Connection string is stored only as the `appinsights-connection-string` Container App secret —
not committed anywhere in this repo.

---

### Azure AI Foundry account: `immanuelnowpertt-6876-resource`

Pre-existing, portal-created — **not** managed by `infra/`. This is the resource behind
`AZURE_FOUNDRY_ENDPOINT` and `AZURE_OPENAI_ENDPOINT` in `.env`:
```
https://immanuelnowpertt-6876-resource.services.ai.azure.com/api/projects/immanuelnowpertt-6876
```

---

## Adding resources to the environment

All observability/collector resources are managed by Bicep. To add or modify:
1. Update the Bicep templates in `infra/`
2. Re-run the Bicep deployment targeting `rg-immanuelnowpertt-6876` (see `infra/README.md`)
3. For secrets in `ca-collector-dev`, add them via CLI then reference via `secretref:` in env vars

To add a secret to `ca-collector-dev`:
```bash
# 1. Add the secret
az containerapp secret set \
  --name ca-collector-dev \
  --resource-group rg-immanuelnowpertt-6876 \
  --secrets "my-secret=<value>"

# 2. Wire it to an env var
az containerapp update \
  --name ca-collector-dev \
  --resource-group rg-immanuelnowpertt-6876 \
  --set-env-vars "MY_VAR=secretref:my-secret"
# This creates a new revision automatically
```

To rebuild and redeploy the collector image after changing `collector/`:
```bash
az acr build --registry cragentdevooploqbrbm2cy --image otel-collector:latest --file collector/Dockerfile collector/
az containerapp update --name ca-collector-dev --resource-group rg-immanuelnowpertt-6876 --image cragentdevooploqbrbm2cy.azurecr.io/otel-collector:latest
```
