"""Send a message to the agent and print the response.

Usage:
    python scripts/run.py "Your message here"
    python scripts/run.py "Follow-up message" --conversation <conv_id>
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.runner.runner import AgentRunner
from harness.telemetry import setup_telemetry


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a message through the harness agent.")
    parser.add_argument("message", help="User message to send")
    parser.add_argument(
        "--conversation", "-c", default=None,
        help="Conversation ID to continue (omit to start a new conversation)"
    )
    args = parser.parse_args()

    config = load_config()
    setup_telemetry(config)
    runner = AgentRunner(config)

    print(f"Sending: {args.message!r}\n")
    response_text, conv_id = runner.run(args.message, conversation_id=args.conversation)

    print(f"\n--- Response ---\n{response_text}")
    print(f"\nConversation ID: {conv_id}  (use --conversation {conv_id} to continue)")


if __name__ == "__main__":
    main()
