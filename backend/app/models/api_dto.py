from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.domain import Document, GeneratedQuestion, SourceQuestion


class GenerationSettings(BaseModel):
    total_questions: int = Field(ge=1, le=10, default=3)
    detail_questions: int = Field(ge=0, le=10, default=2)
    inference_questions: int = Field(ge=0, le=10, default=1)

    @model_validator(mode="after")
    def _sum_matches_total(self) -> "GenerationSettings":
        if self.detail_questions + self.inference_questions != self.total_questions:
            raise ValueError(
                "detail_questions + inference_questions 必须等于 total_questions（V1 约束）"
            )
        return self


class CreateRunRequest(BaseModel):
    client_id: str
    skill_id: str
    passage: str
    source_question: SourceQuestion
    curriculum_text: str | None = None
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    bypass_cache: bool = False
    export_title: str | None = "高中英语阅读平行题"


class CreateRunResponse(BaseModel):
    run_id: str
    status: str


class RunDetailResponse(BaseModel):
    run_id: str
    client_id: str
    skill_id: str
    status: str
    current_node: str | None = None
    error: dict[str, Any] | None = None
    document: Document | None = None
    source_question: SourceQuestion | None = None
    generation: GenerationSettings | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    final_artifact_id: str | None = None
    retry_count: int = 0
    rollback_count: int = 0


class RunEventResponse(BaseModel):
    seq: int
    type: str
    node: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class UpdateArtifactRequest(BaseModel):
    client_id: str
    payload: dict[str, Any]


class UpdateArtifactResponse(BaseModel):
    artifact_id: str
    version: int


class ExportDocxRequest(BaseModel):
    client_id: str
    artifact_id: str
    title: str | None = "导出"


class SkillSummaryResponse(BaseModel):
    id: str
    version: str
    subject: str
    stage: str
    domain: str
    question_format: str
    task: str
    required_tools: list[str]
