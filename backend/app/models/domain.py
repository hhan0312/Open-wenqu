from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    document_id: str
    block_id: str | None = None
    start_offset: int = 0
    end_offset: int = 0
    page: int | None = None
    bbox: dict | None = None
    image_ref: str | None = None
    confidence: float = 1.0


class Block(BaseModel):
    id: str
    type: Literal["paragraph", "question", "option", "image", "table", "unknown"] = "paragraph"
    text: str
    source_span: SourceSpan | None = None


class Document(BaseModel):
    id: str
    title: str | None = None
    blocks: list[Block] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SourceOption(BaseModel):
    key: Literal["A", "B", "C", "D"]
    text: str


class SourceQuestion(BaseModel):
    stem: str
    options: list[SourceOption]
    correct_answer: Literal["A", "B", "C", "D"]
    notes: str | None = None


class DistractorReview(BaseModel):
    option_key: Literal["A", "B", "C", "D"]
    why_wrong_zh: str
    confusion_risk_zh: str | None = None


class QualityReview(BaseModel):
    score: int = Field(ge=0, le=100)
    clarity_zh: str
    difficulty_match_zh: str
    uniqueness_zh: str
    issues_zh: list[str] = Field(default_factory=list)


class GeneratedQuestion(BaseModel):
    id: str
    question_type: Literal["detail", "inference"]
    stem: str
    options: list[SourceOption]
    correct_answer: Literal["A", "B", "C", "D"]
    explanation_zh: str
    evidence_text: str
    evidence_span: SourceSpan | None = None
    distractor_reviews: list[DistractorReview]
    learning_objective_zh: str | None = None
    quality: QualityReview
