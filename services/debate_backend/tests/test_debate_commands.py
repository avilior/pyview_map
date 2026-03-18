"""Tests for debate slash-command parsing, dispatch, and file I/O."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from debate_backend.commands import (
    ParsedCommand,
    parse_command,
    save_debate,
    load_debate,
    load_template,
    list_templates,
    list_saved_debates,
    _cmd_new,
    _cmd_save,
    _cmd_save_as,
    _cmd_load,
    _cmd_end,
    _cmd_templates,
    _cmd_debates,
    _cmd_help,
    _cmd_config,
    _cmd_continue,
    _cmd_transcript,
    _generate_transcript_md,
    _generate_transcript_html,
)
from debate_backend.debate import Debate, _debates


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_debates():
    """Ensure a clean debate store for each test."""
    _debates.clear()
    yield
    _debates.clear()


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch):
    """Create a temporary data directory with subdirs and patch settings."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "debates").mkdir()
    (tmp_path / "specs").mkdir()
    monkeypatch.setattr("debate_backend.commands.settings.data_dir", tmp_path)
    return tmp_path


def _make_template_yaml(templates_dir: Path, name: str = "test", **overrides) -> Path:
    data = {
        "name": name,
        "description": f"{name} template",
        "agents": [
            {"name": "A", "model": "m1", "system_prompt": "{name} argues FOR {topic}"},
            {"name": "B", "model": "m2", "system_prompt": "{name} argues AGAINST {topic}"},
        ],
    }
    data.update(overrides)
    path = templates_dir / f"{name}.yaml"
    path.write_text(yaml.dump(data))
    return path


def _make_debate_with_history() -> Debate:
    d = Debate.create(topic="test topic", agent1_name="A", agent2_name="B")
    d.record_turn(0, "first")
    d.record_turn(1, "second")
    return d


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------


def test_parse_new():
    p = parse_command("/new classic AI ethics")
    assert p == ParsedCommand(name="new", args=["classic", "AI", "ethics"])


def test_parse_save():
    p = parse_command("/save")
    assert p == ParsedCommand(name="save", args=[])


def test_parse_save_as():
    p = parse_command("/save-as my-debate")
    assert p == ParsedCommand(name="save_as", args=["my-debate"])


def test_parse_load():
    p = parse_command("/load my-debate")
    assert p == ParsedCommand(name="load", args=["my-debate"])


def test_parse_end():
    p = parse_command("/end")
    assert p == ParsedCommand(name="end", args=[])


def test_parse_templates():
    p = parse_command("/templates")
    assert p == ParsedCommand(name="templates", args=[])


def test_parse_debates():
    p = parse_command("/debates")
    assert p == ParsedCommand(name="debates", args=[])


def test_parse_help():
    p = parse_command("/help")
    assert p == ParsedCommand(name="help", args=[])


def test_parse_not_a_command():
    assert parse_command("hello world") is None


def test_parse_strips_whitespace():
    p = parse_command("  /help  ")
    assert p is not None
    assert p.name == "help"


# ---------------------------------------------------------------------------
# File I/O: save / load debate
# ---------------------------------------------------------------------------


def test_save_debate_creates_file(tmp_path: Path):
    d = _make_debate_with_history()
    fname = save_debate(d, tmp_path)
    assert fname.endswith(".json")
    path = tmp_path / fname
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["debate_id"] == d.debate_id
    assert data["topic"] == "test topic"
    assert len(data["history"]) == 2


def test_save_debate_custom_filename(tmp_path: Path):
    d = _make_debate_with_history()
    fname = save_debate(d, tmp_path, filename="custom")
    assert fname == "custom.json"
    assert (tmp_path / "custom.json").exists()


def test_load_debate_roundtrip(tmp_path: Path):
    d = _make_debate_with_history()
    save_debate(d, tmp_path)
    loaded = load_debate(tmp_path, d.debate_id)
    assert loaded.debate_id == d.debate_id
    assert loaded.topic == d.topic
    assert loaded.history == d.history
    assert loaded.current_turn == d.current_turn


def test_load_debate_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_debate(tmp_path, "nonexistent")


# ---------------------------------------------------------------------------
# File I/O: templates
# ---------------------------------------------------------------------------


def test_load_template(tmp_path: Path):
    _make_template_yaml(tmp_path, "classic")
    data = load_template(tmp_path, "classic")
    assert data["name"] == "classic"
    assert len(data["agents"]) == 2


def test_load_template_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_template(tmp_path, "nonexistent")


def test_list_templates_empty(tmp_path: Path):
    assert list_templates(tmp_path) == []


def test_list_templates_with_files(tmp_path: Path):
    _make_template_yaml(tmp_path, "alpha")
    _make_template_yaml(tmp_path, "beta")
    result = list_templates(tmp_path)
    names = [t["name"] for t in result]
    assert "alpha" in names
    assert "beta" in names


def test_list_templates_nonexistent_dir(tmp_path: Path):
    assert list_templates(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# File I/O: saved debates listing
# ---------------------------------------------------------------------------


def test_list_saved_debates(tmp_path: Path):
    d = _make_debate_with_history()
    save_debate(d, tmp_path)
    result = list_saved_debates(tmp_path)
    assert len(result) == 1
    assert result[0]["topic"] == "test topic"
    assert result[0]["turn_count"] == 2


def test_list_saved_debates_empty(tmp_path: Path):
    assert list_saved_debates(tmp_path) == []


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_new
# ---------------------------------------------------------------------------


def test_cmd_new(data_dir: Path):
    _make_template_yaml(data_dir / "templates", "test")
    result = _cmd_new(["-t", "test", "-o", "my_debate", "AI", "ethics"])
    assert result["command"] == "new"
    assert result["topic"] == "AI ethics"
    assert result["template_name"] == "test"
    assert len(result["agents"]) == 2
    # Debate should be in the store with the save_filename set
    assert result["debate_id"] in _debates
    assert _debates[result["debate_id"]].save_filename == "my_debate"


def test_cmd_new_missing_args():
    result = _cmd_new(["only_template"])
    assert result["command"] == "error"
    assert "usage" in result["message"].lower()


def test_cmd_new_unknown_template(data_dir: Path):
    result = _cmd_new(["-t", "nonexistent", "-o", "output", "topic"])
    assert result["command"] == "error"
    assert "not found" in result["message"].lower()


def test_cmd_new_file_exists(data_dir: Path):
    _make_template_yaml(data_dir / "templates", "test")
    (data_dir / "debates" / "taken.json").write_text("{}")
    result = _cmd_new(["-t", "test", "-o", "taken", "some topic"])
    assert result["command"] == "error"
    assert "already exists" in result["message"].lower()


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_save / _cmd_save_as
# ---------------------------------------------------------------------------


def test_cmd_save(data_dir: Path):
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_save(d.debate_id)
    assert result["command"] == "save"
    assert (data_dir / "debates" / result["filename"]).exists()


def test_cmd_save_no_debate():
    result = _cmd_save(None)
    assert result["command"] == "error"


def test_cmd_save_as(data_dir: Path):
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_save_as(d.debate_id, ["my-debate"])
    assert result["command"] == "save_as"
    assert result["filename"] == "my-debate.json"
    assert (data_dir / "debates" / "my-debate.json").exists()


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_load
# ---------------------------------------------------------------------------


def test_cmd_load(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates", "saved")
    result = _cmd_load(["saved"])
    assert result["command"] == "load"
    assert result["debate_id"] == d.debate_id
    assert result["history_count"] == 2
    assert len(result["history"]) == 2
    assert result["history"][0]["name"] == "A"
    assert result["current_agent"] == d.current_agent.name
    assert d.debate_id in _debates


def test_cmd_load_not_found(data_dir: Path):
    result = _cmd_load(["nope"])
    assert result["command"] == "error"


def test_cmd_load_no_args():
    result = _cmd_load([])
    assert result["command"] == "error"


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_end
# ---------------------------------------------------------------------------


def test_cmd_end(data_dir: Path):
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_end(d.debate_id)
    assert result["command"] == "end"
    assert result["turn_count"] == 2
    assert d.status == "ended"
    assert (data_dir / "debates" / result["filename"]).exists()


def test_cmd_end_no_debate():
    result = _cmd_end(None)
    assert result["command"] == "error"


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_templates / _cmd_debates / _cmd_help
# ---------------------------------------------------------------------------


def test_cmd_templates(data_dir: Path):
    _make_template_yaml(data_dir / "templates", "t1")
    result = _cmd_templates()
    assert result["command"] == "templates"
    assert len(result["templates"]) == 1


def test_cmd_debates(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates")
    result = _cmd_debates()
    assert result["command"] == "debates"
    assert len(result["debates"]) == 1


def test_cmd_help():
    result = _cmd_help()
    assert result["command"] == "help"
    assert "text" in result
    assert len(result["commands"]) > 0


def test_cmd_config():
    result = _cmd_config()
    assert result["command"] == "config"
    assert "text" in result
    assert "templates_dir" in result["text"]
    assert "saves_dir" in result["text"]
    assert "data_dir" in result["text"]


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


def test_generate_transcript_md():
    d = _make_debate_with_history()
    md = _generate_transcript_md(d)
    assert md.startswith("# Debate: test topic")
    assert "**Status:** active" in md
    assert "## Agents" in md
    assert "### A" in md
    assert "### B" in md
    assert "**Model:**" in md
    assert "**System prompt:**" in md
    assert "first" in md
    assert "second" in md


def test_cmd_transcript_active_debate():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_transcript(d.debate_id, [])
    assert result["command"] == "transcript"
    assert result["debate_id"] == d.debate_id
    assert result["format"] == "markdown"
    assert "# Debate:" in result["content"]


def test_cmd_transcript_named_debate(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates", "my-debate")
    result = _cmd_transcript(None, ["my-debate"])
    assert result["command"] == "transcript"
    assert result["format"] == "markdown"
    assert "# Debate:" in result["content"]


def test_cmd_transcript_no_debate():
    result = _cmd_transcript(None, [])
    assert result["command"] == "error"


def test_cmd_transcript_not_found(data_dir: Path):
    result = _cmd_transcript(None, ["nonexistent"])
    assert result["command"] == "error"


def test_generate_transcript_html():
    d = _make_debate_with_history()
    html = _generate_transcript_html(d)
    assert "<h1>" in html
    assert "test topic" in html
    # Agent info section
    assert "agent-card" in html
    assert "<h3>A</h3>" in html
    assert "<h3>B</h3>" in html
    assert "Model:" in html
    # Turn content
    assert "<p>first</p>" in html
    assert "<p>second</p>" in html
    assert "transcript-turn" in html


# ---------------------------------------------------------------------------
# Command dispatch: _cmd_continue
# ---------------------------------------------------------------------------


def test_cmd_continue_default():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, [])
    assert result["command"] == "continue"
    assert result["rounds"] == 1
    assert result["total_turns"] == 2
    assert result["current_agent"] == d.current_agent.name


def test_cmd_continue_custom_rounds():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, ["3"])
    assert result["rounds"] == 3
    assert result["total_turns"] == 6


def test_cmd_continue_invalid_n():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, ["abc"])
    assert result["command"] == "error"


def test_cmd_continue_too_large():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, ["50"])
    assert result["command"] == "error"
    assert "at most 20" in result["message"]


def test_cmd_continue_zero():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, ["0"])
    assert result["command"] == "error"


def test_cmd_continue_no_debate():
    result = _cmd_continue(None, [])
    assert result["command"] == "error"


def test_cmd_continue_ended_debate():
    d = _make_debate_with_history()
    d.stop()
    _debates[d.debate_id] = d
    result = _cmd_continue(d.debate_id, [])
    assert result["command"] == "error"
    assert "ended" in result["message"]


def test_cmd_help_includes_continue():
    result = _cmd_help()
    assert any("/continue" in c["name"] for c in result["commands"])


def test_cmd_transcript_html_flag():
    d = _make_debate_with_history()
    _debates[d.debate_id] = d
    result = _cmd_transcript(d.debate_id, ["-html"])
    assert result["command"] == "transcript"
    assert result["format"] == "html"
    assert "<h1>" in result["content"]


def test_cmd_transcript_html_flag_with_filename(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates", "my-debate")
    result = _cmd_transcript(None, ["-html", "my-debate"])
    assert result["command"] == "transcript"
    assert result["format"] == "html"
    assert "<h1>" in result["content"]


def test_cmd_transcript_input_flag(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates", "flagged")
    result = _cmd_transcript(None, ["-i", "flagged"])
    assert result["command"] == "transcript"
    assert result["format"] == "markdown"
    assert "# Debate:" in result["content"]


def test_cmd_transcript_input_flag_with_html(data_dir: Path):
    d = _make_debate_with_history()
    save_debate(d, data_dir / "debates", "flagged")
    result = _cmd_transcript(None, ["-html", "-i", "flagged"])
    assert result["command"] == "transcript"
    assert result["format"] == "html"
    assert "<h1>" in result["content"]
