# Getting Started

## Prerequisites

- Python 3.11+
- Azure CLI — `az login` with access to the `rg-langchain-dev` subscription
- ngrok account — for tunneling the local MCP server to Azure
- Access to `foundryagentdevkmmebr` (Azure AI Services) in `rg-langchain-dev`

---

## Install

```bash
git clone <repo>
cd azure-ai-foundry

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your values (see table below)
```

---

## Start the local MCP server

The agent needs to reach your local file system and shell. FastMCP exposes those tools over HTTP on port 8765, and ngrok creates a stable HTTPS tunnel Azure can call.

```bash
# Terminal 1 — start MCP server
python -m local_mcp.server
# Output: Running on http://127.0.0.1:8765

# Terminal 2 — create ngrok tunnel
ngrok http 8765
# Copy the Forwarding URL, e.g. https://eggnog-choking-accent.ngrok-free.dev
```

Set in `.env`:
```
LOCAL_MCP_URL=https://<your-ngrok-url>/mcp
```

> **Pitfall:** If you get 421 Misdirected Request errors from the agent, the MCP server's DNS rebinding protection is rejecting the ngrok Host header (which includes the port). The server already has `enable_dns_rebinding_protection=False` to handle this — make sure you haven't reverted that setting. See [`pitfalls.md — Bug 1`](pitfalls.md#bug-1-fastmcp-421-misdirected-request-from-ngrok).

---

## Environment variable reference

| Variable                          | Required | Default              | Description                                                                        |
| -----------------------------------| ----------| ----------------------| ------------------------------------------------------------------------------------|
| `AZURE_FOUNDRY_ENDPOINT`          | Yes      | —                    | Project API base: `https://<account>.services.ai.azure.com/api/projects/<project>` |
| `AZURE_OPENAI_ENDPOINT`           | Yes      | —                    | OpenAI endpoint: `https://<account>.services.ai.azure.com/openai/v1`               |
| `AZURE_OPENAI_API_KEY`            | Yes      | —                    | API key for the OpenAI client                                                      |
| `AZURE_OPENAI_API_VERSION`        | No       | `2025-04-01-preview` | API version                                                                        |
| `AZURE_CHAT_MODEL_DEPLOYMENT`     | No       | `gpt-5.4-mini`       | Model deployment name as shown in Foundry → Deployments                            |
| `AGENT_NAME`                      | No       | `foundry-harness`    | Agent name in Foundry                                                              |
| `TOOLBOX_NAME`                    | No       | `harness-toolbox`    | Toolbox name in Foundry                                                            |
| `SKILLS_DIR`                      | No       | `skills`             | Relative path to skill directories                                                 |
| `LOCAL_MCP_URL`                   | Yes      | —                    | ngrok HTTPS URL + `/mcp`                                                           |
| `MCP_CONNECTIONS`                 | No       | `{}`                 | JSON dict of external MCP servers (see below)                                      |
| `MCP_REQUIRE_APPROVAL`            | No       | `false`              | If `true`, prompts interactively before each MCP tool call                         |
| `OTEL_EXPORTER_OTLP_ENDPOINT`     | No       | —                    | Collector base URL — leave blank to disable all telemetry                          |
| `OTEL_EXPORTER_OTLP_BEARER_TOKEN` | No       | —                    | Bearer token for collector auth                                                    |
| `OTEL_SERVICE_NAME`               | No       | `foundry-harness`    | Service name tag in traces and logs                                                |
| `OTEL_CAPTURE_CONTENT`            | No       | `false`              | Include prompts/completions in spans — PII risk, enable deliberately               |
| `OTEL_LOG_LEVEL`                  | No       | `INFO`               | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`                                |

### MCP_CONNECTIONS format

Register external MCP servers that the agent can call through the toolbox. Each entry needs a connection registered in the Azure AI Foundry portal first.

```json
{
  "github": {
    "server_url": "https://api.githubcopilot.com/mcp",
    "connection_id": "my-github-connection",
    "require_approval": "always"
  }
}
```

---

## First run

After filling in `.env` and starting the MCP server:

```bash
# Deploy the agent (one-time setup)
python scripts/deploy_agent.py
# Creates .agent_ref with the deployed agent:version

# Send a message
python scripts/run.py "List files in this directory"
# Response:
#   <agent answer>
#   Conversation: conv_0b4daf43...

# Continue the same conversation
python scripts/run.py --conversation conv_0b4daf43... "Now summarize the Python files"
```

---

## Authentication

The harness uses `DefaultAzureCredential` for the `AIProjectClient` (Skills, Toolbox, Agent APIs). For a local dev machine, `az login` satisfies this. No API key is needed for the project client.

The OpenAI client (`AZURE_OPENAI_API_KEY`) is separate — it's used for the Responses API and needs an explicit key because `DefaultAzureCredential` is not supported on that path in this SDK version.

---

## Running Evaluations & Tests

The harness uses [promptfoo](https://github.com/promptfoo/promptfoo) for end-to-end evaluation, verification, and safety (red-team) testing of the agent.

For a detailed explanation of the tests, refer to [Agent Testing with Promptfoo](file:///Users/immanuelnowpert/Personal/azure-ai-foundry/tests/README.md).

### 1. Install Promptfoo
Ensure you have Node.js (≥ 18) installed, then install the Promptfoo CLI globally:
```bash
npm install -g promptfoo
```

### 2. Run Evaluations
The test suites expect your `.env` variables to be fully configured. Ensure the local MCP server is running if testing tool-use cases.

```bash
# Run all evaluation suites (smoke, skills, tool_use, multi_turn)
npx promptfoo eval -c tests/promptfoo.yaml

# Run a single suite (e.g. smoke tests)
npx promptfoo eval -c tests/suites/smoke.yaml
```

### 3. View Results in Browser
After running an evaluation, open the interactive web viewer to review agent responses, assertions, and metrics:
```bash
npx promptfoo view
```

### 4. Run Red-Teaming (Safety Probing)
To probe the agent for safety, alignment, and jailbreak vulnerabilities:
```bash
npx promptfoo redteam run -c tests/suites/redteam.yaml
```

---

## Next steps

- [Deployment guide](deployment.md) — sync skills, create toolbox, redeploy agent
- [Observability guide](observability.md) — configure OTEL collector, understand traces and logs
- [Architecture](architecture.md) — how the components fit together
- [Agent Testing Guide](file:///Users/immanuelnowpert/Personal/azure-ai-foundry/tests/README.md) — comprehensive testing docs

