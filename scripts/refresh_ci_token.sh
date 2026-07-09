#!/usr/bin/env bash
# Mint a fresh AAD access token for the Azure AI Foundry data plane and push it
# into the AZURE_ACCESS_TOKEN GitHub Actions secret. Run this manually (after
# `az login`) before pushing to main, or whenever a CI run fails auth because
# the token has expired.
#
# AAD user-delegated access tokens live for at most ~60 minutes, so this must
# be re-run before every pipeline trigger if more than an hour has passed
# since the last refresh.
#
# Usage:
#   ./scripts/refresh_ci_token.sh [owner/repo]
# If owner/repo is omitted, gh infers it from the current git remote.

set -euo pipefail

REPO="${1:-}"

TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv)

if [ -z "$TOKEN" ]; then
  echo "error: failed to mint an access token — are you logged in? (az login)" >&2
  exit 1
fi

if [ -n "$REPO" ]; then
  echo "$TOKEN" | gh secret set AZURE_ACCESS_TOKEN --repo "$REPO"
else
  echo "$TOKEN" | gh secret set AZURE_ACCESS_TOKEN
fi

echo "AZURE_ACCESS_TOKEN secret updated. Valid for roughly the next 60 minutes."
