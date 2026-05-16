from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REQUIRED_SECTION_ORDER = [
    "适用场景",
    "输入要求",
    "命题原则",
    "原题分析规则",
    "平行题生成规则",
    "证据定位要求",
    "干扰项设计要求",
    "中文解析要求",
    "质量评价 Rubric",
    "输出格式约束",
    "示例",
]


@dataclass
class SkillSpec:
    skill_dir: Path
    id: str
    version: str
    subject: str
    stage: str
    domain: str
    question_format: str
    task: str
    required_tools: list[str]
    includes: list[dict[str, Any]]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    fragments: dict[str, str] = field(default_factory=dict)


_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _split_frontmatter(md: str) -> tuple[dict[str, Any], str]:
    text = md.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter ---")
    fm_lines: list[str] = []
    i = 1
    while i < len(lines):
        if lines[i].strip() == "---":
            i += 1
            break
        fm_lines.append(lines[i])
        i += 1
    else:
        raise ValueError("Unterminated YAML frontmatter")
    body = "\n".join(lines[i:]).lstrip("\n")
    data = yaml.safe_load("\n".join(fm_lines)) or {}
    if not isinstance(data, dict):
        raise ValueError("Frontmatter must be a mapping")
    return data, body


def _extract_fragments(body: str) -> dict[str, str]:
    matches = list(_HEADER_RE.finditer(body))
    frags: dict[str, str] = {}
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip("\n")
        frags[title] = content
    return frags


def _validate_section_order(frags: dict[str, str]) -> None:
    titles = list(frags.keys())
    if titles != REQUIRED_SECTION_ORDER:
        missing = [t for t in REQUIRED_SECTION_ORDER if t not in frags]
        extra = [t for t in titles if t not in REQUIRED_SECTION_ORDER]
        wrong_order = not missing and not extra and titles != REQUIRED_SECTION_ORDER
        msg = f"Section titles must match required order. missing={missing} extra={extra} wrong_order={wrong_order}"
        raise ValueError(msg)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_skill(skill_md_path: Path) -> SkillSpec:
    md = skill_md_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(md)
    frags = _extract_fragments(body)
    _validate_section_order(frags)

    try:
        sid = str(fm["id"])
        version = str(fm["version"])
        subject = str(fm["subject"])
        stage = str(fm["stage"])
        domain = str(fm["domain"])
        question_format = str(fm["question_format"])
        task = str(fm["task"])
        required_tools = list(fm.get("required_tools") or [])
        includes = list(fm.get("includes") or [])
        input_rel = str(fm["input_schema"])
        output_rel = str(fm["output_schema"])
    except KeyError as e:
        raise ValueError(f"Missing required frontmatter field: {e}") from e

    skill_dir = skill_md_path.parent
    input_schema = _load_json(skill_dir / input_rel)
    output_schema = _load_json(skill_dir / output_rel)

    return SkillSpec(
        skill_dir=skill_dir,
        id=sid,
        version=version,
        subject=subject,
        stage=stage,
        domain=domain,
        question_format=question_format,
        task=task,
        required_tools=required_tools,
        includes=includes,
        input_schema=input_schema,
        output_schema=output_schema,
        fragments=frags,
    )


def walk_skill_files(skills_root: Path) -> list[Path]:
    return sorted(skills_root.rglob("SKILL.md"))


def build_skill_index(skills_root: Path) -> dict[str, SkillSpec]:
    by_id: dict[str, SkillSpec] = {}
    for p in walk_skill_files(skills_root):
        rel = p.relative_to(skills_root)
        if rel.parts and rel.parts[0] == "_shared":
            # still indexed by id from file
            pass
        spec = load_skill(p)
        if spec.id in by_id:
            raise ValueError(f"Duplicate skill id: {spec.id}")
        by_id[spec.id] = spec
    return by_id


def merge_includes(
    *,
    spec: SkillSpec,
    index: dict[str, SkillSpec],
    short_name_index: dict[str, str],
) -> dict[str, str]:
    merged = dict(spec.fragments)
    for inc in spec.includes:
        ref = str(inc.get("skill"))
        sections = list(inc.get("sections") or [])
        target_id = short_name_index.get(ref, ref)
        if target_id not in index:
            raise ValueError(f"include references unknown skill: {ref}")
        base = index[target_id].fragments
        for sec in sections:
            if sec not in base:
                raise ValueError(f"include section not found in {target_id}: {sec}")
            merged[sec] = base[sec]
    return merged


def build_short_name_index(index: dict[str, SkillSpec]) -> dict[str, str]:
    out: dict[str, str] = {}
    for sid, spec in index.items():
        out[spec.skill_dir.name] = sid
    return out


@dataclass
class SkillRegistry:
    skills_root: Path
    index: dict[str, SkillSpec] = field(default_factory=dict)
    merged_fragments: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, skills_root: Path, required_tool_names: set[str]) -> SkillRegistry:
        index = build_skill_index(skills_root)
        short = build_short_name_index(index)
        merged: dict[str, dict[str, str]] = {}
        for sid, spec in index.items():
            mf = merge_includes(spec=spec, index=index, short_name_index=short)
            merged[sid] = mf
            for tool in spec.required_tools:
                if tool not in required_tool_names:
                    raise ValueError(f"Skill {sid} requires missing tool: {tool}")
        return cls(skills_root=skills_root, index=index, merged_fragments=merged)

    def get(self, skill_id: str) -> SkillSpec:
        if skill_id not in self.index:
            raise KeyError(skill_id)
        return self.index[skill_id]

    def prompt_for(self, skill_id: str, sections: list[str] | None = None) -> str:
        frags = self.merged_fragments[skill_id]
        if sections is None:
            parts = [f"## {title}\n{frags[title]}" for title in REQUIRED_SECTION_ORDER]
        else:
            parts = []
            for title in sections:
                parts.append(f"## {title}\n{frags[title]}")
        return "\n\n".join(parts).strip()

    def validate_instance(self, skill_id: str, payload: dict[str, Any], schema_kind: str) -> None:
        spec = self.get(skill_id)
        schema = spec.input_schema if schema_kind == "input" else spec.output_schema
        Draft202012Validator(schema).validate(payload)


def default_required_tool_names() -> set[str]:
    return {"llm.generate_json", "evidence.locate", "docx.export"}
