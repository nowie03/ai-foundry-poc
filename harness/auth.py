"""Credential resolution for the harness.

Local dev authenticates via `az login` and `DefaultAzureCredential`. CI cannot do
that (the tenant does not allow creating an app registration / service principal
for OIDC or client-secret login), so CI instead supplies a pre-minted AAD access
token via the `AZURE_ACCESS_TOKEN` env var, wrapped in `StaticTokenCredential`.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import jwt
from azure.core.credentials import AccessToken
# pyrefly: ignore [missing-import]
from azure.identity import DefaultAzureCredential


class StaticTokenCredential:
    """Returns a single pre-minted AAD access token, ignoring requested scopes.

    Deliberately does NOT implement `get_token_info` — azure-core's bearer-token
    policy checks for that method's presence and, if found, switches to a newer
    TokenRequestOptions-based code path with different semantics.
    """

    def __init__(self, token: str) -> None:
        claims = jwt.decode(token, options={"verify_signature": False})
        exp = claims.get("exp")
        if exp and exp < time.time():
            expired_at = datetime.fromtimestamp(exp, tz=timezone.utc)
            raise RuntimeError(
                f"AZURE_ACCESS_TOKEN expired at {expired_at.isoformat()} — "
                "run scripts/refresh_ci_token.sh and re-trigger the workflow."
            )
        self._token = AccessToken(token, exp or int(time.time()) + 3600)

    def get_token(self, *scopes: str, **kwargs) -> AccessToken:
        return self._token


def get_credential():
    """StaticTokenCredential in CI (AZURE_ACCESS_TOKEN set), DefaultAzureCredential locally."""
    token = os.environ.get("AZURE_ACCESS_TOKEN")
    if token:
        return StaticTokenCredential(token)
    return DefaultAzureCredential()
