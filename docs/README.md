# Azure AI Foundry Harness — Documentation

A Python harness that deploys a hosted AI agent on Azure AI Foundry with local tool access via MCP and full OpenTelemetry observability.

---

## Contents

| Doc | What's in it |
|---|---|
| [Architecture](architecture.md) | System diagram, component table, key design decisions |
| [Getting Started](getting-started.md) | Prerequisites, install, env vars reference, first run |
| [Deployment](deployment.md) | Skills → Toolbox → Agent lifecycle, script reference, re-deploy checklist |
| [Observability](observability.md) | OTEL trace + log pipelines, collector setup, Observe Inc, verification |
| [Azure Resources](azure-resources.md) | All resources in `rg-langchain-dev` with config details |
| [Pitfalls](pitfalls.md) | Every bug and gotcha hit during the build — symptoms, root causes, fixes |

---

## Quick reference

```bash
# Setup (one-time)
pip install -r requirements.txt
cp .env.example .env   # fill in values

# Start local MCP server + ngrok
python -m local_mcp.server &
ngrok http 8765         # copy HTTPS URL → LOCAL_MCP_URL in .env

# Deploy (order matters)
python scripts/sync_skills.py       # upload SKILL.md files to Foundry
python scripts/deploy_toolbox.py    # create toolbox version
python scripts/deploy_agent.py      # create agent, saves .agent_ref

# Run
python scripts/run.py "What files are in this directory?"
python scripts/run.py --conversation <conv_id> "Now summarize them"
```

---

## Stack

| Layer | Technology |
|---|---|
| Agent hosting | Azure AI Foundry (Skills API, Toolbox API, Conversations + Responses API) |
| Model | `gpt-5.4-mini` on `foundryagentdevkmmebr` (Azure AI Services S0) |
| Local tools | FastMCP over HTTP, tunneled via ngrok |
| Tracing + logging | OpenTelemetry → `ca-collector-dev` → Application Insights + Observe Inc |
| Infrastructure | `rg-langchain-dev` (East US), provisioned via Bicep |
