from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.domain import Document, GeneratedQuestion, SourceQuestion
from app.models.api_dto import GenerationSettings

NodeStatus = Literal[
    "success",
    "retry",
    "failed_recoverable",
    "failed_fatal",
    "waiting_human",
]

ErrorAction = Literal["retry", "edit_input", "fix_config", "report_bug"]


class AgentError(BaseModel):
    code: str
    message: str
    action: ErrorAction
    detail: str | None = None


class NodeMetrics(BaseModel):
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempt: int = 1


class ArtifactRef(BaseModel):
    type: str
    version: int
    payload: dict[str, Any]


class NodeResult(BaseModel):
    status: NodeStatus
    next_node: str | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    error: AgentError | None = None
    metrics: NodeMetrics = Field(default_factory=NodeMetrics)


class GenerationPlan(BaseModel):
    summary_zh: str
    focus_points: list[str] = Field(default_factory=list)


class PreviousAttemptFailure(BaseModel):
    failure_kind: str
    schema_errors: str | None = None
    evidence_failures: list[str] = Field(default_factory=list)
    quality_failures: list[str] = Field(default_factory=list)
    raw_output_truncated: str | None = None


class GenerationAttempt(BaseModel):
    index: int
    llm_ok: bool = False
    verify_ok: bool = False
    failure: PreviousAttemptFailure | None = None


class QualityGateResult(BaseModel):
    passed: bool
    avg_quality: float | None = None
    reasons: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    run_id: str
    client_id: str
    skill_id: str
    status: str = "pending"
    current_node: str | None = "normalize_input"
    canceled: bool = False

    document: Document | None = None
    source_question: SourceQuestion | None = None
    curriculum_text: str | None = None
    generation: GenerationSettings | None = None

    plan: GenerationPlan | None = None
    questions: list[GeneratedQuestion] = Field(default_factory=list)

    llm_bundle: dict[str, Any] | None = None
    quality_gate: QualityGateResult | None = None

    retry_count: int = 0
    rollback_count: int = 0
    generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    previous_attempt_failure: PreviousAttemptFailure | None = None

    final_artifact_id: str | None = None
    error: AgentError | None = None
