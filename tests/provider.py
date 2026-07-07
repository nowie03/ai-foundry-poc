"""
Promptfoo Python provider for the Azure AI Foundry harness.

Usage in promptfoo.yaml:
    providers:
      - id: "python:provider.py"

Multi-turn conversations:
    Pass `session_id` in test vars to group turns into the same Foundry conversation.
    The first call with a new session_id creates a conversation; subsequent calls reuse it.

    vars:
      session_id: "alice-demo"
"""
from __future__ import annotations

import logging
import os
import sys

# Make the project root importable regardless of where promptfoo invokes us from.
_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from harness.config import load_config          # pyrefly: ignore [missing-import]
from harness.runner.runner import AgentRunner   # pyrefly: ignore [missing-import]
from harness.telemetry import setup_telemetry   # pyrefly: ignore [missing-import]

logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────
# A single AgentRunner is shared across all test cases in one promptfoo run to
# avoid repeated credential resolution and Foundry client setup.

_runner: AgentRunner | None = None

# Maps  session_id  →  conversation_id  so multi-turn tests can continue the
# same Foundry conversation.  An empty / missing session_id always starts fresh.
_sessions: dict[str, str] = {}


def _get_runner() -> AgentRunner:
    global _runner
    if _runner is None:
        config = load_config()
        setup_telemetry(config)
        _runner = AgentRunner(config)
        logger.info("AgentRunner initialised (endpoint=%s)", config.endpoint)
    return _runner


# ── Provider entry-point ──────────────────────────────────────────────────────

def call_api(prompt: str, options: dict, context: dict) -> dict:
    """
    Called by promptfoo for every test case.

    Returns a dict with at minimum:
        {"output": str}

    Optional keys:
        {"error": str}          — marks the test as errored
        {"metadata": dict}      — available in the result for debugging
    """
    vars_: dict = context.get("vars", {}) or {}
    session_id: str = vars_.get("session_id", "")

    # Resolve existing conversation for this session (if any)
    conversation_id: str | None = _sessions.get(session_id) if session_id else None

    try:
        runner = _get_runner()
        response_text, new_conv_id = runner.run(prompt, conversation_id=conversation_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentRunner.run() failed: %s", exc)
        return {"error": str(exc)}

    # Persist the conversation so the next turn in the same session continues it
    if session_id:
        _sessions[session_id] = new_conv_id

    return {
        "output": response_text,
        "metadata": {
            "conversation_id": new_conv_id,
            "session_id": session_id or None,
        },
    }
