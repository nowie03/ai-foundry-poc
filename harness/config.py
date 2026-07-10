from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class MCPConnectionConfig:
    server_url: str
    connection_id: str | None = None
    require_approval: str = "never"


@dataclass
class HarnessConfig:
    endpoint: str
    model_deployment: str
    embedding_model_deployment:str
    agent_name: str
    toolbox_name: str
    skills_dir: str
    local_mcp_url: str
    enable_local_tools: bool = True
    api_key: str | None = None          # Azure OpenAI / AI Foundry API key (optional; falls back to DefaultAzureCredential)
    azure_openai_endpoint: str | None = None  # e.g. https://foundryagentdevkmmebr.openai.azure.com/
    api_version: str = "2024-12-01-preview"
    mcp_connections: dict[str, MCPConnectionConfig] = field(default_factory=dict)
    require_mcp_approval: bool = False
    otel_endpoint: str | None = None
    otel_service_name: str = "foundry-harness"
    otel_content_recording: bool = False
    otel_bearer_token: str | None = None
    otel_log_level: str = "INFO"


def _env(key: str, default: str = "") -> str:
    """os.environ.get(key, default), but also falls back to default when the
    var is set to an empty/whitespace string — e.g. an unset GitHub Actions
    repo variable referenced via ${{ vars.X }} comes through as "", not absent."""
    value = os.environ.get(key, "").strip()
    return value or default


def load_config() -> HarnessConfig:
    endpoint = _env("AZURE_FOUNDRY_ENDPOINT")
    if not endpoint:
        conn_str = _env("AZURE_FOUNDRY_CONNECTION_STRING")
        if not conn_str:
            raise ValueError(
                "Set AZURE_FOUNDRY_ENDPOINT or AZURE_FOUNDRY_CONNECTION_STRING"
            )
        host, sub, rg, proj = conn_str.split(";")
        endpoint = (
            f"https://{host}/agents/v1.0/subscriptions/{sub}"
            f"/resourceGroups/{rg}/providers"
            f"/Microsoft.MachineLearningServices/workspaces/{proj}"
        )

    return HarnessConfig(
        endpoint=endpoint,
        model_deployment=_env("AZURE_CHAT_MODEL_DEPLOYMENT", "gpt-5.4-mini"),
        embedding_model_deployment=_env("AZURE_EMBEDDING_MODEL_DEPLOYMENT", "text-embedding-3-small"),
        api_key=_env("AZURE_OPENAI_API_KEY") or None,
        azure_openai_endpoint=_env("AZURE_OPENAI_ENDPOINT") or None,
        api_version=_env("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        agent_name=_env("AGENT_NAME", "foundry-harness"),
        toolbox_name=_env("TOOLBOX_NAME", "harness-toolbox"),
        skills_dir=_env("SKILLS_DIR", "skills"),
        local_mcp_url=_env("LOCAL_MCP_URL", "http://127.0.0.1:8765"),
        enable_local_tools=_env("ENABLE_LOCAL_TOOLS", "true").lower() == "true",
        mcp_connections=_parse_mcp_connections(),
        require_mcp_approval=_env("MCP_REQUIRE_APPROVAL", "false").lower() == "true",
        otel_endpoint=_env("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        otel_service_name=_env("OTEL_SERVICE_NAME", "foundry-harness"),
        otel_content_recording=_env("OTEL_CAPTURE_CONTENT", "false").lower() == "true",
        otel_bearer_token=_env("OTEL_EXPORTER_OTLP_BEARER_TOKEN") or None,
        otel_log_level=_env("OTEL_LOG_LEVEL", "INFO").upper(),
    )


def _parse_mcp_connections() -> dict[str, MCPConnectionConfig]:
    raw = os.environ.get("MCP_CONNECTIONS", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return {
            label: MCPConnectionConfig(
                server_url=cfg["server_url"],
                connection_id=cfg.get("connection_id"),
                require_approval=cfg.get("require_approval", "never"),
            )
            for label, cfg in parsed.items()
        }
    except (json.JSONDecodeError, KeyError) as exc:
        raise ValueError(f"Invalid MCP_CONNECTIONS format: {exc}") from exc
