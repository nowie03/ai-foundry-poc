import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions, MemorySearchPreviewTool
from dataclasses import dataclass
import jwt
import logging

from ..auth import get_credential
from ..config import HarnessConfig


logger = logging.getLogger(__name__)

@dataclass
class MemoryStoreOptions:
    chat_summary_enabled: bool = True
    user_profile_enabled: bool = True
    procedural_memory_enabled: bool = True
    default_ttl_seconds: int = 30 * 24 * 60 * 60
    user_profile_details: str = "Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials"


class MemoryStoreBuilder:
    def __init__(self, config: HarnessConfig, name: str, options: MemoryStoreOptions = MemoryStoreOptions()) -> None:
        self._config = config
        self._name = name
        self._client = AIProjectClient(
            endpoint=config.endpoint,
            credential=get_credential(),
        )
        self._definition = MemoryStoreDefaultDefinition(
            chat_model=config.model_deployment,
            embedding_model=config.embedding_model_deployment,
            options=MemoryStoreDefaultOptions(
                chat_summary_enabled=options.chat_summary_enabled,
                user_profile_enabled=options.user_profile_enabled,
                procedural_memory_enabled=options.procedural_memory_enabled,
                default_ttl_seconds=options.default_ttl_seconds,
                user_profile_details=options.user_profile_details,
            ),
        )

    def create_if_not_exist(self) -> str:
        stores= list(self._client.beta.memory_stores.list())

        if self._name in [s.name for s in stores]:
            return self._name
        
        logger.info(f"Creating memory store {self._name}")
        created_store =  self._client.beta.memory_stores.create(
            name=self._name,
            definition=self._definition,
            description="Memory store with procedural memory and 30-day default TTL",
        )
        logger.info(f"Created Memory Store with name :{created_store.name}")

    def get_memory_search_tool(self) -> MemorySearchPreviewTool:
        tool = MemorySearchPreviewTool(
            memory_store=self._name,
            scope=self.__get_user_name(),
            update_delay=5
        )
        return tool

    def __get_user_name(self) -> str:
        credential = get_credential()
        token = credential.get_token("https://management.azure.com/.default")
        claims = jwt.decode(token.token, options={"verify_signature": False})
        logger.info(f"User name from the Token")
        return claims.get("upn") or claims.get("preferred_username") or claims.get("oid")
        
