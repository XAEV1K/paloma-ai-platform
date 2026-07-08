"""Versioned prompt repository.

Prompts are product artifacts: they change, they regress, they need
review — so they live as ``prompts/<agent>_<version>.md`` files under
version control, and the active version is a config value
(``PROMPT_VERSION``), not a code change.

Resolution: exact version first; if absent, fall back to the highest
available version for that agent with a warning (a new agent may not
have caught up with the global version bump yet).
"""

from __future__ import annotations

import re
from pathlib import Path

from core.exceptions import ConfigurationError
from core.logging import get_logger

logger = get_logger("crew.prompts")

_VERSION_PATTERN = re.compile(r"^(?P<agent>[a-z_]+)_v(?P<version>\d+)\.md$")


class PromptRepository:
    """Loads agent backstories by (agent, version) from the prompts directory."""

    def __init__(self, prompts_dir: Path, version: str) -> None:
        self._prompts_dir = prompts_dir
        self._version = version.lstrip("v")

    @property
    def version(self) -> str:
        return f"v{self._version}"

    def load(self, agent: str) -> str:
        """Return the prompt text for ``agent`` at the configured version."""
        exact = self._prompts_dir / f"{agent}_v{self._version}.md"
        if exact.is_file():
            logger.debug("Prompt loaded: %s", exact.name)
            return exact.read_text(encoding="utf-8")

        fallback = self._latest_version_file(agent)
        if fallback is None:
            raise ConfigurationError(
                f"No prompt files found for agent '{agent}' in {self._prompts_dir} "
                f"(expected e.g. '{agent}_v1.md')"
            )
        # Per-agent versions may lag the global PROMPT_VERSION — expected,
        # so this is debug-level, not a warning (e.g. conversational agents
        # start at v1 while pipeline agents are on v3).
        logger.debug(
            "Prompt %s_v%s.md not found; using %s", agent, self._version, fallback.name
        )
        return fallback.read_text(encoding="utf-8")

    def available_versions(self, agent: str) -> list[int]:
        """All versions present on disk for an agent, ascending."""
        versions: list[int] = []
        for path in self._prompts_dir.glob(f"{agent}_v*.md"):
            match = _VERSION_PATTERN.match(path.name)
            if match and match.group("agent") == agent:
                versions.append(int(match.group("version")))
        return sorted(versions)

    def _latest_version_file(self, agent: str) -> Path | None:
        versions = self.available_versions(agent)
        if not versions:
            return None
        return self._prompts_dir / f"{agent}_v{versions[-1]}.md"
