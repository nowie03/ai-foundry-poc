# Azure Infrastructure — Bicep Templates

## Overview

These templates provision the Azure observability stack for the harness agent
into an **existing** resource group (`rg-immanuelnowpertt-6876` by default —
the same resource group as the live Azure AI Foundry account/project):

```
rg-immanuelnowpertt-6876 (existing)
├── law-agent-{env}                  ← Log Analytics workspace
│     └── (Sentinel can be onboarded here — see Milestone 5)
├── ai-agent-{env}                   ← Application Insights (workspace-based)
├── cragent{env}<suffix>             ← Container Registry
├── cae-agent-{env}                  ← Container Apps Environment
└── ca-collector-{env}               ← OTel Collector Container App
```

Two environments: `dev` and `prod`. Deploy each separately with the same template.
The Azure AI Foundry account/project itself is **not** managed by this template —
it already exists in the target resource group.

---

## Prerequisites

1. **Azure CLI** installed and authenticated:
   ```bash
   az login
   az account show        # confirm the correct subscription is active
   az account set --subscription "<your-subscription-id>"
   ```

2. **Bicep CLI** (bundled with Azure CLI ≥ 2.20):
   ```bash
   az bicep version       # should print something like 0.x.x
   az bicep upgrade       # if outdated
   ```

---

## Deploy

Secrets (`collectorAuthToken`, `observeCustomerId`, `observeDatastreamToken`) are passed
inline on the CLI — never stored in `main.bicepparam` or committed to git.

### Dev environment

```bash
# Dry-run first (what-if)
az deployment sub what-if \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters collectorAuthToken="$(openssl rand -hex 32)" \
               observeCustomerId="<observe-customer-id>" \
               observeDatastreamToken="<observe-datastream-token>"

# Apply
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters collectorAuthToken="<same-token-as-above>" \
               observeCustomerId="<observe-customer-id>" \
               observeDatastreamToken="<observe-datastream-token>"
```

### Prod environment

Copy `main.bicepparam` to `main.prod.bicepparam`, set `environment = 'prod'`, then:

```bash
az deployment sub what-if \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.prod.bicepparam \
  --parameters collectorAuthToken="<token>" observeCustomerId="<id>" observeDatastreamToken="<token>"

az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters infra/main.prod.bicepparam \
  --parameters collectorAuthToken="<token>" observeCustomerId="<id>" observeDatastreamToken="<token>"
```

The collector container image itself must be built and pushed to the newly created ACR
before the collector Container App can start (see `collector/README.md`).

---

## Retrieve the connection string (after deploy)

The App Insights connection string and collector endpoint are **secure/output** values.
Retrieve them explicitly and place in your `.env` (locally) or your secrets manager (CI/CD):

```bash
# Dev
az deployment sub show \
  --name langchain-resources-dev \
  --query 'properties.outputs.appInsightsConnectionString.value' \
  --output tsv

az deployment group show \
  --resource-group rg-immanuelnowpertt-6876 \
  --name langchain-resources-dev \
  --query 'properties.outputs.collectorEndpoint.value' \
  --output tsv
```

Store the value in your `.env` as:
```
AZURE_APPINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=...
OTEL_EXPORTER_OTLP_ENDPOINT=<collectorEndpoint>
```

> ⚠️ **Never commit the real connection string to git.**  
> The placeholder in `.env` is safe to commit. Replace it locally only.

---

## Sentinel onboarding (Milestone 5)

Microsoft Sentinel is deployed on top of a Log Analytics workspace.
After the workspace exists:

```bash
az sentinel workspace-manager-configuration create \
  --resource-group rg-immanuelnowpertt-6876 \
  --workspace-name law-agent-prod
```

Or enable it in the Azure Portal: **Microsoft Sentinel → Add → select `law-agent-prod`**.

---

## Files

| File | Purpose |
|------|---------|
| `main.bicep` | Subscription-scoped entry point; deploys the resources module into an existing RG |
| `resources.bicep` | RG-scoped module; Log Analytics workspace, App Insights, ACR, Container Apps Environment, OTel Collector Container App |
| `main.bicepparam` | Example dev parameters file (no secrets) |
