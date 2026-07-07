"""Create a new toolbox version with all tools and skill references."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.client import build_client
from harness.skills.manager import SkillManager
from harness.toolbox.builder import ToolboxBuilder
from harness.telemetry import setup_telemetry


def main() -> None:
    config = load_config()
    setup_telemetry(config)
    project = build_client(config)

    skill_names = SkillManager(project, config).skill_names()
    print(f"Attaching {len(skill_names)} skill(s): {', '.join(skill_names) or 'none'}")

    builder = ToolboxBuilder(project, config)
    builder.create_version(skill_names)

    print(f"Toolbox MCP endpoint: {builder.toolbox_mcp_url()}")
    print("Done.")


if __name__ == "__main__":
    main()
