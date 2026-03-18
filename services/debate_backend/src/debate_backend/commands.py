# ---------------------------------------------------------------------------
# Debate slash-command dispatcher
#
# Parses commands like /new, /save, /load, /end and dispatches them.
# Also provides file I/O helpers for templates (YAML) and saved debates (JSON).
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path

import yaml

from http_stream_transport.jsonrpc.handler_meta import RequestInfo
from http_stream_transport.jsonrpc.jrpc_service import jrpc_service

from debate_backend.settings import settings

from debate_backend.debate import (
    Debate,
    DebateEngine,
    _engines,
    _make_engine,
    _make_engine_default,
)

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------


@dataclass
class ParsedCommand:
    name: str          # e.g. "new", "save", "save_as", "load", "end"
    args: list[str]    # positional arguments after the command name


def parse_command(text: str) -> ParsedCommand | None:
    """Parse a slash command string.  Returns ``None`` if not a slash command."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    cmd = parts[0].lstrip("/").lower().replace("-", "_")
    args = parts[1:]
    return ParsedCommand(name=cmd, args=args)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def save_debate(debate: Debate, directory: Path, filename: str | None = None) -> str:
    """Save debate to a JSON file.  Returns the filename used."""

    directory.mkdir(parents=True, exist_ok=True)
    fname = filename or debate.debate_id
    if not fname.endswith(".json"):
        fname += ".json"
    path = directory / fname
    path.write_text(json.dumps(debate.to_dict(), indent=2))
    LOG.info("Debate saved: %s -> %s", debate.debate_id, path)
    return fname


def load_debate(directory: Path, filename: str) -> Debate:
    """Load a debate from a JSON file."""

    if not filename.endswith(".json"):
        filename += ".json"
    path = directory / filename
    if not path.exists():
        raise FileNotFoundError(f"Saved debate not found: {filename}")
    data = json.loads(path.read_text())
    return Debate.from_dict(data)


def _get_debate(engine: DebateEngine | None) -> Debate | None:
    """Extract the ``Debate`` object from an engine, or ``None``."""
    return engine.debate if engine is not None else None


def load_template(directory: Path, template_name: str) -> dict:
    """Load and parse a YAML template file."""

    path = directory / f"{template_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {template_name}")
    return yaml.safe_load(path.read_text())


def list_templates(directory: Path) -> list[dict]:
    """List available templates with name and description."""

    if not directory.exists():
        return []
    templates = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            templates.append({
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "agents": len(data.get("agents", [])),
            })
        except Exception:
            continue
    return templates


def load_spec(directory: Path, filename: str):
    """Load and parse a debate spec file.  Returns a ``SpecData`` object."""
    from debate_backend.spec_parser import parse_spec_file

    if not filename.endswith(".md"):
        filename += ".md"
    path = directory / filename
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {filename}")
    return parse_spec_file(path)


def list_specs(directory: Path) -> list[dict]:
    """List available spec files with their topics."""
    from debate_backend.spec_parser import parse_spec_file

    if not directory.exists():
        return []
    specs = []
    for path in sorted(directory.glob("*.md")):
        try:
            data = parse_spec_file(path)
            specs.append({"filename": path.stem, "topic": data.topic})
        except Exception:
            specs.append({"filename": path.stem, "topic": ""})
    return specs


def list_saved_debates(directory: Path) -> list[dict]:
    """List saved debate files with summary info."""

    if not directory.exists():
        return []
    debates = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            debates.append({
                "filename": path.stem,
                "topic": data.get("topic", ""),
                "status": data.get("status", ""),
                "saved_at": data.get("saved_at", ""),
                "turn_count": len(data.get("history", [])),
            })
        except Exception:
            continue
    return debates


# ---------------------------------------------------------------------------
# Command dispatch helpers
# ---------------------------------------------------------------------------


def _error(message: str) -> dict:
    return {"command": "error", "message": message}


def _cmd_new(args: list[str]) -> dict:
    template_name: str | None = None
    output_name: str | None = None
    spec_name: str | None = None
    topic_parts: list[str] = []

    it = iter(args)
    for token in it:
        if token == "-t":
            template_name = next(it, None)
        elif token == "-o":
            output_name = next(it, None)
        elif token == "-s":
            spec_name = next(it, None)
        else:
            topic_parts.append(token)

    if not template_name:
        return _error("Usage: /new -t <template> -o <filename> [-s <spec>] [<topic>]")
    if not output_name:
        return _error("Usage: /new -t <template> -o <filename> [-s <spec>] [<topic>]")

    # Load spec if provided
    background_info = ""
    agent_instructions: dict[str, str] = {}
    spec_topic = ""
    max_rounds: int | None = None
    if spec_name:
        try:
            spec_data = load_spec(settings.specs_dir, spec_name)
        except FileNotFoundError:
            return _error(f"Spec file not found: {spec_name}")
        background_info = spec_data.background
        agent_instructions = spec_data.agent_guidelines
        spec_topic = spec_data.topic
        max_rounds = spec_data.max_rounds

    # Topic from positional args overrides spec; spec overrides missing arg
    topic = " ".join(topic_parts) if topic_parts else spec_topic
    if not topic:
        return _error("Usage: /new -t <template> -o <filename> [-s <spec>] [<topic>]")

    # Check if the output file already exists
    save_path = settings.saves_dir / (output_name if output_name.endswith(".json") else output_name + ".json")
    if save_path.exists():
        return _error(f"File already exists: {save_path.name}")

    try:
        template_data = load_template(settings.templates_dir, template_name)
    except FileNotFoundError:
        return _error(f"Template not found: {template_name}")
    debate = Debate.from_template(
        template_data,
        topic,
        spec_file=spec_name or "",
        background_info=background_info,
        agent_instructions=agent_instructions,
        max_rounds=max_rounds,
    )
    debate.save_filename = output_name
    engine = _make_engine(debate, template_data)
    _engines[engine.debate_id] = engine
    LOG.info("Debate created from template %r: %s — topic=%r, output=%r, spec=%r",
             template_name, debate.debate_id, topic, output_name, spec_name)
    return {
        "command": "new",
        "debate_id": debate.debate_id,
        "topic": topic,
        "agents": [{"name": a.name, "model": a.model} for a in debate.agents],
        "template_name": template_name,
        "spec_file": spec_name or "",
        "max_rounds": debate.max_rounds,
        "status": debate.status,
    }


def _cmd_save(debate_id: str | None) -> dict:
    if not debate_id:
        return _error("No active debate to save")
    debate = _get_debate(_engines.get(debate_id))
    if debate is None:
        return _error("Debate not found")
    fname = save_debate(debate, settings.saves_dir,
                        filename=debate.save_filename or None)
    return {"command": "save", "filename": fname, "debate_id": debate_id}


def _cmd_save_as(debate_id: str | None, args: list[str]) -> dict:
    if not debate_id:
        return _error("No active debate to save")
    if not args:
        return _error("Usage: /save-as <filename>")
    debate = _get_debate(_engines.get(debate_id))
    if debate is None:
        return _error("Debate not found")
    fname = save_debate(debate, settings.saves_dir, filename=args[0])
    return {"command": "save_as", "filename": fname, "debate_id": debate_id}


def _cmd_load(args: list[str]) -> dict:
    if not args:
        return _error("Usage: /load <filename>")
    filename = args[0]
    try:
        debate = load_debate(settings.saves_dir, filename)
    except FileNotFoundError:
        return _error(f"Saved debate not found: {filename}")
    engine = _make_engine_default(debate)
    _engines[engine.debate_id] = engine
    LOG.info("Debate loaded: %s — topic=%r", debate.debate_id, debate.topic)
    return {
        "command": "load",
        "debate_id": debate.debate_id,
        "topic": debate.topic,
        "agents": [{"name": a.name, "model": a.model} for a in debate.agents],
        "current_agent": debate.current_agent.name,
        "status": debate.status,
        "max_rounds": debate.max_rounds,
        "template_name": debate.template_name,
        "spec_file": debate.spec_file,
        "history": debate.history,
        "history_count": len(debate.history),
    }


def _cmd_end(debate_id: str | None) -> dict:
    if not debate_id:
        return _error("No active debate to end")
    engine = _engines.get(debate_id)
    if engine is None:
        return _error("Debate not found")
    engine.stop()
    fname = save_debate(engine.debate, settings.saves_dir,
                        filename=engine.save_filename or None)
    return {
        "command": "end",
        "debate_id": debate_id,
        "filename": fname,
        "turn_count": len(engine.history),
    }


def _cmd_templates() -> dict:
    templates = list_templates(settings.templates_dir)
    return {"command": "templates", "templates": templates}


def _cmd_template(args: list[str]) -> dict:
    if not args:
        return _error("Usage: /template <name>")
    name = args[0]
    path = settings.templates_dir / (name if name.endswith(".yaml") else name + ".yaml")
    if not path.exists():
        return _error(f"Template not found: {name}")
    content = path.read_text()
    return {
        "command": "template",
        "name": name,
        "content": content,
    }


def _cmd_specs() -> dict:
    specs = list_specs(settings.specs_dir)
    return {"command": "specs", "specs": specs}


def _cmd_debate(args: list[str]) -> dict:
    if not args:
        return _error("Usage: /debate <filename>")
    try:
        debate = load_debate(settings.saves_dir, args[0])
    except FileNotFoundError:
        return _error(f"Saved debate not found: {args[0]}")
    return {
        "command": "debate",
        "debate_id": debate.debate_id,
        "topic": debate.topic,
        "status": debate.status,
        "template_name": debate.template_name,
        "spec_file": debate.spec_file,
        "agents": [{"name": a.name, "model": a.model} for a in debate.agents],
        "history": debate.history,
        "history_count": len(debate.history),
    }


def _cmd_debates() -> dict:
    debates = list_saved_debates(settings.saves_dir)
    return {"command": "debates", "debates": debates}


def _cmd_spec(args: list[str]) -> dict:
    if not args:
        return _error("Usage: /spec <filename>")
    filename = args[0]
    if not filename.endswith(".md"):
        filename += ".md"
    path = settings.specs_dir / filename
    if not path.exists():
        return _error(f"Spec file not found: {filename}")
    return {
        "command": "spec",
        "filename": args[0],
        "content": path.read_text(),
    }


def _cmd_continue(debate_id: str | None, args: list[str]) -> dict:
    if not debate_id:
        return _error("No active debate")
    engine = _engines.get(debate_id)
    if engine is None:
        return _error("Debate not found")
    if engine.status != "active":
        return _error(f"Debate is {engine.status}")

    n = 1
    if args:
        try:
            n = int(args[0])
            if n < 1:
                return _error("N must be a positive integer")
            if n > 20:
                return _error("N must be at most 20")
        except ValueError:
            return _error(f"Invalid number: {args[0]}")

    return {
        "command": "continue",
        "debate_id": debate_id,
        "rounds": n,
        "total_turns": n * 2,
        "current_agent": engine.current_agent.name,
    }


def _generate_transcript_html(debate: Debate) -> str:
    """Convert a debate to an HTML transcript fragment."""
    import html as _html

    style = (
        "<style>"
        ".transcript-turn { margin: 1.5em 0; padding: 1em 1.2em; "
        "border-left: 4px solid #6366f1; background: #f8f8fc; border-radius: 0 8px 8px 0; }"
        ".transcript-turn h2 { font-weight: 700; margin: 0 0 0.5em 0; font-size: 1.15em; }"
        ".transcript-turn p { margin: 0; line-height: 1.6; }"
        "hr.turn-sep { border: none; border-top: 1px solid #e5e7eb; margin: 1.5em 0; }"
        ".agent-card { margin: 0.75em 0; padding: 0.75em 1em; "
        "background: #f1f5f9; border-radius: 8px; border: 1px solid #e2e8f0; }"
        ".agent-card h3 { font-weight: 700; margin: 0 0 0.25em 0; font-size: 1.05em; }"
        ".agent-card .meta { color: #64748b; font-size: 0.9em; margin: 0.15em 0; }"
        ".agent-card .prompt { font-style: italic; color: #475569; margin: 0.4em 0 0 0; "
        "font-size: 0.9em; }"
        "</style>"
    )
    parts = [style, f"<h1>{_html.escape(debate.topic)}</h1>"]
    turn_count = sum(1 for h in debate.history if h.get("content"))
    parts.append(f"<p><strong>Status:</strong> {_html.escape(debate.status)}"
                 f" | <strong>Turns:</strong> {turn_count}</p>")
    # Agent info section
    parts.append("<h2>Agents</h2>")
    for agent in debate.agents:
        parts.append('<div class="agent-card">')
        parts.append(f"<h3>{_html.escape(agent.name)}</h3>")
        parts.append(f'<p class="meta"><strong>Model:</strong> {_html.escape(agent.model)}</p>')
        parts.append(f'<p class="prompt">{_html.escape(agent.system_prompt)}</p>')
        parts.append("</div>")
    parts.append('<hr class="turn-sep">')
    first = True
    for entry in debate.history:
        content = entry.get("content", "")
        if not content:
            continue
        name = entry.get("name", "Unknown")
        if not first:
            parts.append('<hr class="turn-sep">')
        first = False
        parts.append('<div class="transcript-turn">')
        parts.append(f"<h2>{_html.escape(name)}</h2>")
        parts.append(f"<p>{_html.escape(content)}</p>")
        parts.append("</div>")
    return "\n".join(parts)


def _generate_transcript_md(debate: Debate) -> str:
    """Convert a debate to a markdown transcript."""
    lines = [f"# Debate: {debate.topic}", ""]
    turn_count = sum(1 for h in debate.history if h.get("content"))
    lines.append(f"**Status:** {debate.status} | **Turns:** {turn_count}")
    lines.append("")
    # Agent info section
    lines.append("## Agents")
    lines.append("")
    for agent in debate.agents:
        lines.append(f"### {agent.name}")
        lines.append(f"- **Model:** {agent.model}")
        lines.append(f"- **System prompt:** *{agent.system_prompt}*")
        lines.append("")
    lines.append("---")
    lines.append("")
    for entry in debate.history:
        content = entry.get("content", "")
        if not content:
            continue
        name = entry.get("name", "Unknown")
        lines.append("---")
        lines.append("")
        lines.append(f"## {name}")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _cmd_transcript(debate_id: str | None, args: list[str]) -> dict:
    html_flag = "-html" in args
    input_file: str | None = None

    it = iter(args)
    for token in it:
        if token == "-html":
            continue
        elif token == "-i":
            input_file = next(it, None)
        else:
            # Legacy positional filename support
            input_file = input_file or token

    if input_file:
        try:
            debate = load_debate(settings.saves_dir, input_file)
        except FileNotFoundError:
            return _error(f"Saved debate not found: {input_file}")
    elif debate_id:
        debate = _get_debate(_engines.get(debate_id))
        if debate is None:
            return _error("Debate not found")
    else:
        return _error("No active debate and no filename specified")

    if html_flag:
        content = _generate_transcript_html(debate)
        fmt = "html"
    else:
        content = _generate_transcript_md(debate)
        fmt = "markdown"

    return {
        "command": "transcript",
        "debate_id": debate.debate_id,
        "topic": debate.topic,
        "content": content,
        "format": fmt,
    }


def _cmd_config() -> dict:
    lines = [
        "Debate configuration:",
        f"  data_dir:       {settings.data_dir}",
        f"  templates_dir:  {settings.templates_dir}",
        f"  saves_dir:      {settings.saves_dir}",
        f"  specs_dir:      {settings.specs_dir}",
    ]
    return {"command": "config", "text": "\n".join(lines)}


_HELP_COMMANDS = [
    {"name": "/new -t <template> -o <filename> [-s <spec>] [<topic>]", "description": "Start a new debate from a template; -s loads topic/background/guidelines from a spec file"},
    {"name": "/save", "description": "Save the current debate"},
    {"name": "/save-as <filename>", "description": "Save the current debate with a specific name"},
    {"name": "/load <filename>", "description": "Load and resume a saved debate"},
    {"name": "/end", "description": "End the current debate and save it"},
    {"name": "/templates", "description": "List available debate templates"},
    {"name": "/template <name>", "description": "Show the contents of a debate template"},
    {"name": "/specs", "description": "List available debate spec files"},
    {"name": "/spec <filename>", "description": "Show contents of a spec file"},
    {"name": "/debates", "description": "List saved debates"},
    {"name": "/debate <filename>", "description": "Show contents of a saved debate"},
    {"name": "/transcript [-html] [-i <filename>]", "description": "Open debate transcript in a new tab (-html for rendered HTML)"},
    {"name": "/continue [N]", "description": "Run N full rounds (default 1, max 20)"},
    {"name": "/help", "description": "Show this help message"},
    {"name": "/config", "description": "Show server configuration"},
]


def _cmd_help() -> dict:
    lines = ["Available commands:"]
    for cmd in _HELP_COMMANDS:
        lines.append(f"  {cmd['name']}  —  {cmd['description']}")
    return {"command": "help", "text": "\n".join(lines), "commands": _HELP_COMMANDS}


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, str] = {
    "new": "new",
    "save": "save",
    "save_as": "save_as",
    "load": "load",
    "end": "end",
    "templates": "templates",
    "template": "template",
    "specs": "specs",
    "spec": "spec",
    "debates": "debates",
    "debate": "debate",
    "transcript": "transcript",
    "continue": "continue",
    "help": "help",
    "config": "config",
}


# ---------------------------------------------------------------------------
# JSON-RPC handler
# ---------------------------------------------------------------------------


@jrpc_service.request("debate.command")
async def debate_command(
    info: RequestInfo,
    command: str,
    debate_id: str | None = None,
) -> dict:
    """Parse and dispatch a slash command."""
    parsed = parse_command(command)
    if parsed is None:
        return _error("Not a valid command (must start with /)")

    if parsed.name not in _DISPATCH:
        return _error(f"Unknown command: /{parsed.name}. Type /help for available commands.")

    match parsed.name:
        case "new":
            return _cmd_new(parsed.args)
        case "save":
            return _cmd_save(debate_id)
        case "save_as":
            return _cmd_save_as(debate_id, parsed.args)
        case "load":
            return _cmd_load(parsed.args)
        case "end":
            return _cmd_end(debate_id)
        case "templates":
            return _cmd_templates()
        case "template":
            return _cmd_template(parsed.args)
        case "specs":
            return _cmd_specs()
        case "spec":
            return _cmd_spec(parsed.args)
        case "debates":
            return _cmd_debates()
        case "debate":
            return _cmd_debate(parsed.args)
        case "transcript":
            return _cmd_transcript(debate_id, parsed.args)
        case "continue":
            return _cmd_continue(debate_id, parsed.args)
        case "help":
            return _cmd_help()
        case "config":
            return _cmd_config()
        case _:
            return _error(f"Unknown command: /{parsed.name}")
