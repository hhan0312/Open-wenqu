from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMQualitySelfReview(BaseModel):
    score: int = Field(ge=0, le=100)
    clarity_zh: str
    difficulty_match_zh: str
    uniqueness_zh: str
    issues_zh: list[str] = Field(default_factory=list)


class LLMDistractorReview(BaseModel):
    option_key: Literal["A", "B", "C", "D"]
    why_wrong_zh: str
    confusion_risk_zh: str | None = None


class LLMGeneratedQuestion(BaseModel):
    id: str
    question_type: Literal["detail", "inference"]
    stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: Literal["A", "B", "C", "D"]
    explanation_zh: str
    evidence_text: str
    distractor_reviews: list[LLMDistractorReview]
    learning_objective_zh: str | None = None
    quality: LLMQualitySelfReview


class LLMQuestionBundle(BaseModel):
    plan_summary_zh: str
    plan_focus_points: list[str] = Field(default_factory=list)
    questions: list[LLMGeneratedQuestion]
