from azure.ai.projects import AIProjectClient
# pyrefly: ignore [missing-import]
from azure.identity import DefaultAzureCredential
from openai import OpenAI

from .config import HarnessConfig


def build_client(config: HarnessConfig) -> AIProjectClient:
    return AIProjectClient(
        endpoint=config.endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def build_openai_client(config: HarnessConfig) -> OpenAI:
    if not config.azure_openai_endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT is required")
    if not config.api_key:
        raise ValueError("AZURE_OPENAI_API_KEY is required")
    return OpenAI(
        base_url=config.azure_openai_endpoint,
        api_key=config.api_key,
    )
