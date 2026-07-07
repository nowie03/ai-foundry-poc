from __future__ import annotations

import logging
import re
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import SkillInlineContent

from ..config import HarnessConfig

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KV_RE = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)


def _parse_skill_md(text: str) -> tuple[str, str]:
    """Return (description, instructions) from a SKILL.md string."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("SKILL.md is missing a valid YAML front matter block (--- ... ---)")
    front = m.group(1)
    body = text[m.end():].strip()
    meta = dict(_KV_RE.findall(front))
    description = meta.get("description", "").strip()
    if not description:
        raise ValueError("SKILL.md front matter must contain a 'description' field")
    return description, body


class SkillManager:
    def __init__(self, project: AIProjectClient, config: HarnessConfig) -> None:
        self._project = project
        self._skills_dir = Path(config.skills_dir)

    def skill_names(self) -> list[str]:
        return [
            d.name
            for d in self._skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    def sync_all(self) -> None:
        """Upload each skills/<name>/SKILL.md to Foundry and promote to default version."""
        for skill_dir in sorted(self._skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_dir.is_dir() or not skill_md.exists():
                continue
            name = skill_dir.name
            logger.debug("parsing skill %r from %s", name, skill_md)
            description, instructions = _parse_skill_md(
                skill_md.read_text(encoding="utf-8")
            )
            version = self._project.beta.skills.create(
                name=name,
                inline_content=SkillInlineContent(
                    description=description,
                    instructions=instructions,
                ),
            )
            self._project.beta.skills.update(
                name=name, default_version=version.version
            )
            logger.info("skill synced: name=%r version=%s", name, version.version)
            print(f"  synced '{name}' → version {version.version}")

    def list_remote(self) -> list:
        return list(self._project.beta.skills.list())

    def delete_remote(self, name: str) -> None:
        self._project.beta.skills.delete(name=name)
