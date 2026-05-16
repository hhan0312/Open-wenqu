from __future__ import annotations

from pathlib import Path

import pytest

from app.skills.loader import SkillRegistry, default_required_tool_names, load_skill


def test_parallel_skill_loads(repo_root: Path):
    p = repo_root / "skills" / "english" / "reading" / "mcq" / "parallel_generation" / "SKILL.md"
    spec = load_skill(p)
    assert spec.id == "english.reading.mcq.parallel_generation"
    assert "llm.generate_json" in spec.required_tools


def test_skill_registry_merges_includes(repo_root: Path):
    reg = SkillRegistry.load(repo_root / "skills", default_required_tool_names())
    merged = reg.prompt_for("english.reading.mcq.parallel_generation")
    assert "## 命题原则" in merged
    assert "## 证据定位要求" in merged


def test_evidence_locate():
    from app.models.domain import Block, Document
    from app.tools.evidence import locate_evidence

    doc = Document(
        id="d1",
        blocks=[Block(id="b1", type="paragraph", text="The quick brown fox jumps over the lazy dog.")],
    )
    r = locate_evidence(document=doc, evidence_text="quick brown fox")
    assert r.ok and r.span is not None


def test_generation_settings_enforces_sum():
    from pydantic import ValidationError

    from app.models.api_dto import GenerationSettings

    GenerationSettings(total_questions=3, detail_questions=2, inference_questions=1)
    with pytest.raises(ValidationError):
        GenerationSettings(total_questions=3, detail_questions=1, inference_questions=1)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
