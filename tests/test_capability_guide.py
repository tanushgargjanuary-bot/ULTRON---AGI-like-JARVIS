"""Focused routing checks for the capability guide."""

from types import SimpleNamespace

from actions import capability_guide as guide


def _entry(name, category, summary, available=True, reason=""):
    return SimpleNamespace(
        name=name, category=category, summary=summary,
        available=available, reason=reason,
    )


def _skill(identity, title, purpose):
    return SimpleNamespace(identity=identity, title=title, purpose=purpose)


def _run(monkeypatch, request, entries, skills=()):
    monkeypatch.setattr(guide.tool_catalog, "build", lambda: entries)
    monkeypatch.setattr(guide, "SKILLS", list(skills))
    return guide.run({"request": request})


def test_indirect_compression_request_finds_file_processor(monkeypatch):
    result = _run(
        monkeypatch,
        "This file is too large to send; can you make it smaller?",
        [_entry("file_processor", "files", "Processes uploaded files.", True)],
    )
    assert "file_processor (ready)" in result


def test_review_wording_matches_skill_identifier(monkeypatch):
    result = _run(
        monkeypatch,
        "Review my workspace changes",
        [],
        [_skill("review_changes", "Review change footprint", "Inspect status and diff.")],
    )
    assert "Review change footprint [review_changes]" in result


def test_generic_file_request_does_not_guess_a_tool(monkeypatch):
    result = _run(
        monkeypatch, "Help with this file",
        [_entry("file_processor", "files", "Processes uploaded files.", True)],
    )
    assert "No strong tool match" in result


def test_unavailable_tool_is_reported_and_gap_is_explicit(monkeypatch):
    result = _run(
        monkeypatch, "Compress this file",
        [_entry("file_processor", "files", "Processes uploaded files.", False, "missing codec")],
    )
    assert "unavailable: missing codec" in result
    assert "research candidate GitHub projects" in result


def test_unknown_task_offers_research_without_claiming_a_tool(monkeypatch):
    result = _run(
        monkeypatch, "Teleport a person to Mars",
        [_entry("file_processor", "files", "Processes uploaded files.", True)],
    )
    assert "No strong tool match" in result
    assert "research candidate GitHub projects" in result
