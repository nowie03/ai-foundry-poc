"""Upload or update all local skills/*/SKILL.md files to the Foundry Skills API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.config import load_config
from harness.client import build_client
from harness.skills.manager import SkillManager
from harness.telemetry import setup_telemetry


def main() -> None:
    config = load_config()
    setup_telemetry(config)
    project = build_client(config)
    print("Skills dir ", config.skills_dir)
    manager = SkillManager(project, config)

    skill_names = manager.skill_names()
    if not skill_names:
        print("No skills found in", config.skills_dir)
        return

    print(f"Syncing {len(skill_names)} skill(s): {', '.join(skill_names)}")
    manager.sync_all()
    print("Done.")


if __name__ == "__main__":
    main()
