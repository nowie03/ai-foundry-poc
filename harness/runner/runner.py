from __future__ import annotations

import logging
import pathlib

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition, WebSearchTool
from openai.types.responses.response_input_param import McpApprovalResponse

from ..config import HarnessConfig, load_config
from ..client import build_client, build_openai_client
from ..toolbox.builder import ToolboxBuilder
from ..memory_store.builder import MemoryStoreBuilder

logger = logging.getLogger(__name__)

_AGENT_REF_FILE = ".agent_ref"

BASE_INSTRUCTIONS = (
    "You are an agentic assistant with access to web search, external integrations via MCP, "
    "file system tools, shell execution, and reusable skills. "
    "Skills are available as MCP resources on the toolbox endpoint — discover and load them "
    "when the user's request matches a skill's description. "
    "Use tools proactively to complete tasks."
)


class AgentRunner:
    def __init__(self, config: HarnessConfig | None = None) -> None:
        self._config = config or load_config()
        self._project: AIProjectClient = build_client(self._config)
        self._toolbox = ToolboxBuilder(self._project, self._config)
        self._memory_store = MemoryStoreBuilder(self._config, f"{self._config.agent_name}-memory-store")


    # ── deployment ────────────────────────────────────────────────────────────

    def deploy(self) -> object:
        """Create a new agent version and save the reference to .agent_ref."""
        logger.info(
            "deploying agent: name=%r model=%s endpoint=%s",
            self._config.agent_name, self._config.model_deployment, self._config.endpoint,
        )
        tools = [
            self._memory_store.get_memory_search_tool(),
            WebSearchTool(),
        ]
        if self._config.enable_local_tools:
            tools.append(
                MCPTool(
                    server_label="local-tools",
                    server_url=self._config.local_mcp_url,
                    require_approval="never",
                )
            )
        definition = PromptAgentDefinition(
            model=self._config.model_deployment,
            instructions=BASE_INSTRUCTIONS,
            tools=tools,
        )
        agent = self._project.agents.create_version(
            agent_name=self._config.agent_name,
            definition=definition,
        )
        pathlib.Path(_AGENT_REF_FILE).write_text(f"{agent.name}:{agent.version}")
        logger.info("agent deployed: name=%s version=%s", agent.name, agent.version)
        print(f"  deployed agent '{agent.name}' version {agent.version}")
        return agent

    def _read_agent_name(self) -> str:
        ref = pathlib.Path(_AGENT_REF_FILE)
        if not ref.exists():
            raise FileNotFoundError(
                f"{_AGENT_REF_FILE} not found — run scripts/deploy_agent.py first"
            )
        return ref.read_text().strip().split(":")[0]

    # ── runtime ───────────────────────────────────────────────────────────────

    def _get_openai_client(self):
        # Must use project.get_openai_client() — it configures the project-scoped base URL
        # (.../api/projects/<name>/openai/v1/) which hosts the conversations endpoint.
        # build_openai_client() points at /openai/v1 which lacks conversations support.
        return self._project.get_openai_client()

    def run(
        self,
        user_message: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        """Send a message and return (response_text, conversation_id)."""
        agent_name = self._read_agent_name()
        openai_client = self._get_openai_client()
        agent_ref = {"name": agent_name, "type": "agent_reference"}

        if conversation_id:
            conv_id = conversation_id
            logger.debug("continuing conversation: %s", conv_id)
        else:
            conv_id = openai_client.conversations.create().id
            logger.info("conversation created: %s agent=%s", conv_id, agent_name)

        logger.debug("sending message (%d chars) to conversation %s", len(user_message), conv_id)
        response = openai_client.responses.create(
            conversation=conv_id,
            input=user_message,
            extra_body={"agent_reference": agent_ref},
        )
        response = self._resolve_approvals(response, agent_ref, openai_client)
        logger.info(
            "response complete: conversation=%s output_chars=%d",
            conv_id, len(response.output_text or ""),
        )
        return response.output_text, conv_id

    def _resolve_approvals(self, response, agent_ref: dict, openai_client) -> object:
        while True:
            pending = [
                item
                for item in response.output
                if getattr(item, "type", None) == "mcp_approval_request"
                and getattr(item, "id", None)
            ]
            if not pending:
                return response

            decisions = []
            for item in pending:
                tool_name = getattr(item, "name", "?")
                if self._config.require_mcp_approval:
                    logger.warning(
                        "MCP approval required: server=%s tool=%s",
                        item.server_label, tool_name,
                    )
                    print(f"\n[MCP approval] server={item.server_label} tool={tool_name}")
                    approve = input("Approve? (y/N): ").strip().lower() == "y"
                    logger.info(
                        "MCP approval decision: server=%s tool=%s approved=%s",
                        item.server_label, tool_name, approve,
                    )
                else:
                    logger.debug(
                        "MCP call auto-approved: server=%s tool=%s",
                        item.server_label, tool_name,
                    )
                    approve = True

                decisions.append(
                    McpApprovalResponse(
                        type="mcp_approval_response",
                        approve=approve,
                        approval_request_id=item.id,
                    )
                )

            response = openai_client.responses.create(
                input=decisions,
                previous_response_id=response.id,
                extra_body={"agent_reference": agent_ref},
            )
