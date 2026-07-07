"""Delete the deployed agent version and remove .agent_ref."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.client import build_client

_REF_FILE = Path(".agent_ref")


def main() -> None:
    if not _REF_FILE.exists():
        print("No .agent_ref found — nothing to delete.")
        return

    name, version = _REF_FILE.read_text().strip().split(":")
    config = load_config()
    project = build_client(config)

    project.agents.delete_version(agent_name=name, agent_version=version)
    _REF_FILE.unlink()
    print(f"Deleted agent '{name}' version {version}.")


if __name__ == "__main__":
    main()
