"""Create or update the Foundry agent and write its reference to .agent_ref."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.client import build_client
from harness.runner.runner import AgentRunner
from harness.telemetry import setup_telemetry


def main() -> None:
    config = load_config()
    setup_telemetry(config)
    print(f"Deploying agent '{config.agent_name}' to {config.endpoint}")
    runner = AgentRunner(config)
    agent = runner.deploy()
    print(f"Agent ready: name={agent.name} version={agent.version}")
    print(f"Reference saved to .agent_ref")


if __name__ == "__main__":
    main()
