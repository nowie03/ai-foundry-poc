from __future__ import annotations

import logging

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    ToolboxSearchPreviewTool,
    ToolboxSkillReference,
    WebSearchTool,
)

from ..config import HarnessConfig

logger = logging.getLogger(__name__)


class ToolboxBuilder:
    def __init__(self, project: AIProjectClient, config: HarnessConfig) -> None:
        self._project = project
        self._config = config

    def toolbox_mcp_url(self) -> str:
        base = self._config.endpoint.rstrip("/")
        return f"{base}/toolboxes/{self._config.toolbox_name}/mcp?api-version=v1"

    def create_version(self, skill_names: list[str]) -> object:
        tools = [
            WebSearchTool(name="web-search"),
            ToolboxSearchPreviewTool(name="toolbox-search"),
        ]

        for label, cfg in self._config.mcp_connections.items():
            tools.append(
                MCPTool(
                    server_label=label,
                    server_url=cfg.server_url,
                    require_approval=cfg.require_approval,
                    project_connection_id=cfg.connection_id,
                )
            )

        skill_refs = [ToolboxSkillReference(name=n) for n in skill_names]

        logger.info(
            "creating toolbox version: name=%r tools=%d skills=%d",
            self._config.toolbox_name, len(tools), len(skill_refs),
        )
        version = self._project.beta.toolboxes.create_version(
            name=self._config.toolbox_name,
            description="Agentic harness toolbox: web search, MCP integrations, and skills",
            tools=tools,
            skills=skill_refs,
        )
        logger.info("toolbox version created: %s", version.version)
        print(
            f"  created toolbox '{self._config.toolbox_name}' version {version.version}"
        )
        return version

    def list_versions(self) -> list:
        return list(
            self._project.beta.toolboxes.list_versions(name=self._config.toolbox_name)
        )
