"""Parser for debate spec files (Markdown format).

A spec file defines the topic, background, and per-agent guidelines
using a simple heading structure:

    # Topic
    Should AI replace humans in the workplace?

    # Background
    Recent advances in AI have led to...

    # Agent Guidelines
    ## Agent Alpha
    Argue strongly in favor of AI replacing humans...
    ## Agent Beta
    Argue against AI replacing humans...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SpecData:
    """Parsed content of a debate spec file."""

    topic: str
    background: str
    agent_guidelines: dict[str, str] = field(default_factory=dict)
    max_rounds: int | None = None


def parse_spec_file(path: Path) -> SpecData:
    """Parse a Markdown spec file into a ``SpecData`` object."""
    text = path.read_text(encoding="utf-8")

    topic = ""
    background = ""
    agent_guidelines: dict[str, str] = {}
    max_rounds: int | None = None

    current_section: str | None = None
    current_agent: str | None = None
    current_lines: list[str] = []
    agent_lines: list[str] = []

    def _flush_section() -> None:
        nonlocal topic, background, max_rounds
        if current_section == "topic":
            topic = "\n".join(current_lines).strip()
        elif current_section == "background":
            background = "\n".join(current_lines).strip()
        elif current_section == "agent_guidelines" and current_agent:
            agent_guidelines[current_agent] = "\n".join(agent_lines).strip()
        elif current_section == "max_rounds":
            text_val = "\n".join(current_lines).strip()
            try:
                max_rounds = int(text_val)
            except (ValueError, TypeError):
                pass

    for line in text.splitlines():
        if line.startswith("# "):
            _flush_section()

            section_name = line[2:].strip().lower()
            if section_name == "topic":
                current_section = "topic"
            elif section_name == "background":
                current_section = "background"
            elif section_name in ("agent guidelines", "agent_guidelines"):
                current_section = "agent_guidelines"
            elif section_name in ("max rounds", "max_rounds"):
                current_section = "max_rounds"
            else:
                current_section = None

            current_lines = []
            current_agent = None
            agent_lines = []

        elif line.startswith("## ") and current_section == "agent_guidelines":
            # Flush previous agent block
            if current_agent:
                agent_guidelines[current_agent] = "\n".join(agent_lines).strip()
            current_agent = line[3:].strip()
            agent_lines = []

        elif current_section == "agent_guidelines" and current_agent:
            agent_lines.append(line)

        elif current_section in ("topic", "background", "max_rounds"):
            current_lines.append(line)

    # Flush last section
    _flush_section()

    return SpecData(
        topic=topic,
        background=background,
        agent_guidelines=agent_guidelines,
        max_rounds=max_rounds,
    )
