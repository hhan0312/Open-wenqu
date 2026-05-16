from __future__ import annotations

import hashlib
import json
import traceback
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.config import Settings, get_settings
from app.llm.deepseek_client import DeepSeekClient, LLMFatalError, LLMTransientError, estimate_tokens
from app.models.agent_state import AgentError, PreviousAttemptFailure
from app.models.api_dto import CreateRunRequest
from app.models.domain import Block, Document, DistractorReview, GeneratedQuestion, QualityReview, SourceOption
from app.models.llm_contract import LLMQuestionBundle
from app.skills.loader import SkillRegistry
from app.storage.database import json_dumps
from app.storage.run_store import RunStore, get_run_store, utc_now_iso
from app.tools.evidence import locate_evidence


def truncate(s: str, max_len: int = 4000) -> str:
    s = s or ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 20] + "\n...[truncated]..."


def stable_hash(obj: Any) -> str:
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def normalized_input_snapshot(req: CreateRunRequest) -> dict[str, Any]:
    return {
        "skill_id": req.skill_id,
        "passage": req.passage.strip(),
        "source_question": req.source_question.model_dump(),
        "curriculum_text": (req.curriculum_text or "").strip(),
        "generation": req.generation.model_dump(),
    }


def passage_to_document(passage: str, doc_id: str) -> Document:
    blocks: list[Block] = []
    parts = [p.strip() for p in passage.split("\n\n") if p.strip()]
    if not parts:
        parts = [passage.strip()]
    for i, p in enumerate(parts):
        bid = f"b{i+1}"
        blocks.append(
            Block(
                id=bid,
                type="paragraph",
                text=p,
                source_span=None,
            )
        )
    return Document(id=doc_id, title=None, blocks=blocks, metadata={})


def bundle_to_generated_questions(bundle: LLMQuestionBundle) -> list[GeneratedQuestion]:
    out: list[GeneratedQuestion] = []
    for q in bundle.questions:
        opts = [
            SourceOption(key="A", text=q.option_a.strip()),
            SourceOption(key="B", text=q.option_b.strip()),
            SourceOption(key="C", text=q.option_c.strip()),
            SourceOption(key="D", text=q.option_d.strip()),
        ]
        out.append(
            GeneratedQuestion(
                id=q.id,
                question_type=q.question_type,
                stem=q.stem.strip(),
                options=opts,
                correct_answer=q.correct_answer,
                explanation_zh=q.explanation_zh.strip(),
                evidence_text=q.evidence_text.strip(),
                evidence_span=None,
                distractor_reviews=[
                    DistractorReview(
                        option_key=d.option_key,
                        why_wrong_zh=d.why_wrong_zh,
                        confusion_risk_zh=d.confusion_risk_zh,
                    )
                    for d in q.distractor_reviews
                ],
                learning_objective_zh=q.learning_objective_zh,
                quality=QualityReview(
                    score=q.quality.score,
                    clarity_zh=q.quality.clarity_zh,
                    difficulty_match_zh=q.quality.difficulty_match_zh,
                    uniqueness_zh=q.quality.uniqueness_zh,
                    issues_zh=list(q.quality.issues_zh or []),
                ),
            )
        )
    return out


@dataclass
class Emitter:
    run_id: str
    store: RunStore

    def emit(self, *, seq: int, event_type: str, node: str | None, payload: dict[str, Any]) -> int:
        self.store.append_event(
            self.run_id, seq=seq, event_type=event_type, node=node, payload=payload
        )
        return seq + 1


class AgentRuntime:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        skill_registry: SkillRegistry,
        llm: DeepSeekClient | None = None,
        store: RunStore | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ):
        self.settings = settings or get_settings()
        self.skills = skill_registry
        self.llm = llm or DeepSeekClient(self.settings)
        self.store = store or get_run_store()
        self.cancel_check = cancel_check or (lambda: False)

    def execute(self, *, run_id: str, req: CreateRunRequest) -> None:
        self.run_id = run_id
        seq = self.store.next_event_seq(run_id)
        em = Emitter(run_id, self.store)

        try:
            normalized = normalized_input_snapshot(req)
            self.skills.validate_instance(req.skill_id, normalized, "input")
        except Exception as e:
            seq = em.emit(
                seq=seq,
                event_type="failed_recoverable",
                node="normalize_input",
                payload={
                    "error": AgentError(
                        code="invalid_input",
                        message="输入未通过课程包 schema 校验",
                        action="edit_input",
                        detail=str(e),
                    ).model_dump()
                },
            )
            self.store.update_run(run_id, status="failed_recoverable")
            return

        if not req.bypass_cache:
            cache_key = stable_hash(
                {
                    "input": normalized,
                    "prompt_version": self.settings.prompt_version,
                    "model": self.settings.deepseek_model,
                    "skill_version": self.skills.get(req.skill_id).version,
                }
            )
            cached_artifact_id = self.store.cache_get(cache_key)
            if cached_artifact_id:
                art = self.store.get_artifact(cached_artifact_id)
                if art:
                    new_art = uuid.uuid4().hex
                    self.store.save_artifact(
                        artifact_id=new_art,
                        run_id=run_id,
                        artifact_type="final",
                        version=self.store.latest_artifact_version(run_id) + 1,
                        payload=art["payload"],
                    )
                    self.store.update_run(run_id, status="completed", final_artifact_id=new_art)
                    seq = em.emit(
                        seq=seq,
                        event_type="completed",
                        node="cache_hit",
                        payload={"artifact_id": new_art, "cache": True},
                    )
                    return

        # token budget (rough)
        est = estimate_tokens(req.passage) + estimate_tokens(json_dumps(normalized))
        if est > 12_000:
            seq = em.emit(
                seq=seq,
                event_type="failed_recoverable",
                node="normalize_input",
                payload={
                    "error": AgentError(
                        code="context_too_long",
                        message="输入过长，请缩短阅读材料或减少题目数量。",
                        action="edit_input",
                        detail=f"estimated_tokens={est}",
                    ).model_dump()
                },
            )
            self.store.update_run(run_id, status="failed_recoverable")
            return

        doc = passage_to_document(req.passage, doc_id=f"doc-{run_id}")

        seq = em.emit(
            seq=seq,
            event_type="node_started",
            node="normalize_input",
            payload={"document_id": doc.id},
        )
        seq = em.emit(
            seq=seq,
            event_type="node_completed",
            node="normalize_input",
            payload={"blocks": len(doc.blocks)},
        )

        rollback_count = 0
        previous: PreviousAttemptFailure | None = None

        while rollback_count <= 2:
            if self.cancel_check():
                seq = em.emit(seq=seq, event_type="canceled", node="generate_questions_bundle", payload={})
                self.store.update_run(run_id, status="canceled", canceled_at=utc_now_iso())
                return

            bundle: LLMQuestionBundle | None = None
            last_raw: str | None = None
            gen_attempt_err: str | None = None

            seq = em.emit(
                seq=seq,
                event_type="node_started",
                node="generate_questions_bundle",
                payload={"rollback_count": rollback_count},
            )

            prompt_body = self.skills.prompt_for(req.skill_id)
            sys_msg = (
                "你是高中英语阅读和试题命制专家。你必须输出严格 JSON（json_object），"
                "并遵循用户给出的结构约束与字段命名。"
            )

            user_obj: dict[str, Any] = {
                "task": "parallel_mcq_generation",
                "normalized_input": normalized,
                "instruction": "输出 JSON：包含 plan_summary_zh、plan_focus_points、questions。",
                "skill_prompt_fragments": prompt_body,
            }
            if previous is not None:
                user_obj["previous_attempt_failure"] = previous.model_dump()

            user_msg = json_dumps(user_obj)

            attempt_idx = 0
            while attempt_idx < 3:
                if self.cancel_check():
                    seq = em.emit(
                        seq=seq, event_type="canceled", node="generate_questions_bundle", payload={}
                    )
                    self.store.update_run(run_id, status="canceled", canceled_at=utc_now_iso())
                    return

                call_id = uuid.uuid4().hex
                parsed_local: dict[str, Any] | None = None
                try:
                    parsed, meta = self.llm.generate_json(
                        messages=[
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        response_format_model=None,
                    )
                    parsed_local = parsed
                    last_raw = json.dumps(meta.get("raw", {}), ensure_ascii=False)
                    bundle = LLMQuestionBundle.model_validate(parsed)
                    gen_attempt_err = None
                    self.store.record_llm_call(
                        {
                            "id": call_id,
                            "run_id": run_id,
                            "node": "generate_questions_bundle",
                            "provider": "deepseek",
                            "model": self.settings.deepseek_model,
                            "prompt_version": self.settings.prompt_version,
                            "input_hash": meta["input_hash"],
                            "request_json": json_dumps(
                                {"messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]}
                            ),
                            "raw_response_json": json_dumps(meta.get("raw")),
                            "parsed_response_json": json_dumps(parsed),
                            "latency_ms": meta.get("latency_ms"),
                            "input_tokens": meta.get("input_tokens"),
                            "output_tokens": meta.get("output_tokens"),
                            "status": "ok",
                            "error": None,
                            "created_at": utc_now_iso(),
                        }
                    )
                    break
                except (LLMTransientError, json.JSONDecodeError) as e:
                    gen_attempt_err = str(e)
                    attempt_idx += 1
                    self.store.record_llm_call(
                        {
                            "id": call_id,
                            "run_id": run_id,
                            "node": "generate_questions_bundle",
                            "provider": "deepseek",
                            "model": self.settings.deepseek_model,
                            "prompt_version": self.settings.prompt_version,
                            "input_hash": "",
                            "request_json": user_msg,
                            "raw_response_json": None,
                            "parsed_response_json": None,
                            "latency_ms": None,
                            "input_tokens": None,
                            "output_tokens": None,
                            "status": "error",
                            "error": gen_attempt_err,
                            "created_at": utc_now_iso(),
                        }
                    )
                except LLMFatalError as e:
                    seq = em.emit(
                        seq=seq,
                        event_type="failed_fatal",
                        node="generate_questions_bundle",
                        payload={
                            "error": AgentError(
                                code="llm_fatal",
                                message=str(e),
                                action="fix_config",
                                detail=traceback.format_exc(),
                            ).model_dump()
                        },
                    )
                    self.store.update_run(run_id, status="failed_fatal")
                    return
                except Exception as e:
                    gen_attempt_err = f"schema_error: {e}"
                    bad_json = ""
                    if parsed_local is not None:
                        try:
                            bad_json = json.dumps(parsed_local, ensure_ascii=False)
                        except Exception:
                            bad_json = str(parsed_local)
                    prev = PreviousAttemptFailure(
                        failure_kind="schema_or_validation",
                        schema_errors=gen_attempt_err,
                        evidence_failures=[],
                        quality_failures=[],
                        raw_output_truncated=truncate(last_raw or bad_json),
                    )
                    user_obj["previous_attempt_failure"] = prev.model_dump()
                    user_msg = json_dumps(user_obj)
                    attempt_idx += 1
                    self.store.record_llm_call(
                        {
                            "id": call_id,
                            "run_id": run_id,
                            "node": "generate_questions_bundle",
                            "provider": "deepseek",
                            "model": self.settings.deepseek_model,
                            "prompt_version": self.settings.prompt_version,
                            "input_hash": "",
                            "request_json": user_msg,
                            "raw_response_json": None,
                            "parsed_response_json": None,
                            "latency_ms": None,
                            "input_tokens": None,
                            "output_tokens": None,
                            "status": "error",
                            "error": gen_attempt_err,
                            "created_at": utc_now_iso(),
                        }
                    )

            if bundle is None:
                seq = em.emit(
                    seq=seq,
                    event_type="failed_recoverable",
                    node="generate_questions_bundle",
                    payload={
                        "error": AgentError(
                            code="llm_failed",
                            message="模型多次重试仍失败。",
                            action="retry",
                            detail=gen_attempt_err,
                        ).model_dump()
                    },
                )
                self.store.update_run(run_id, status="failed_recoverable")
                return

            seq = em.emit(
                seq=seq,
                event_type="node_completed",
                node="generate_questions_bundle",
                payload={"questions": len(bundle.questions)},
            )

            # verify
            seq = em.emit(seq=seq, event_type="node_started", node="verify_evidence_and_quality_gate", payload={})

            questions = bundle_to_generated_questions(bundle)
            evidence_failures: list[str] = []
            for q in questions:
                res = locate_evidence(document=doc, evidence_text=q.evidence_text)
                if not res.ok or not res.span or res.confidence < 0.9:
                    evidence_failures.append(f"{q.id}: {res.reason or 'low_confidence'}")
                else:
                    span_obj = res.span
                    span_obj.confidence = float(res.confidence)
                    q.evidence_span = span_obj

            quality_scores = [q.quality.score for q in questions]
            avg_q = sum(quality_scores) / max(1, len(quality_scores))

            type_ok = True
            detail_n = sum(1 for q in questions if q.question_type == "detail")
            inf_n = sum(1 for q in questions if q.question_type == "inference")
            if len(questions) != req.generation.total_questions:
                type_ok = False
            if detail_n != req.generation.detail_questions or inf_n != req.generation.inference_questions:
                # allow small mismatch? strict per plan
                type_ok = False

            quality_ok = avg_q >= 75 and all(s >= 60 for s in quality_scores)

            if not evidence_failures and type_ok and quality_ok:
                payload: dict[str, Any] = {
                    "document": doc.model_dump(),
                    "source_question": req.source_question.model_dump(),
                    "curriculum_text": req.curriculum_text,
                    "generation": req.generation.model_dump(),
                    "plan": {"summary_zh": bundle.plan_summary_zh, "focus_points": bundle.plan_focus_points},
                    "questions": [q.model_dump() for q in questions],
                    "metrics": {"avg_quality": avg_q},
                }
                ver = self.store.latest_artifact_version(run_id) + 1
                art_id = uuid.uuid4().hex
                self.store.save_artifact(
                    artifact_id=art_id,
                    run_id=run_id,
                    artifact_type="final",
                    version=ver,
                    payload=payload,
                )
                self.store.update_run(run_id, status="completed", final_artifact_id=art_id)

                if not req.bypass_cache:
                    cache_key = stable_hash(
                        {
                            "input": normalized,
                            "prompt_version": self.settings.prompt_version,
                            "model": self.settings.deepseek_model,
                            "skill_version": self.skills.get(req.skill_id).version,
                        }
                    )
                    self.store.cache_put(
                        cache_key=cache_key,
                        artifact_id=art_id,
                        model=self.settings.deepseek_model,
                        skill_id=req.skill_id,
                        skill_version=self.skills.get(req.skill_id).version,
                        prompt_version=self.settings.prompt_version,
                    )

                seq = em.emit(
                    seq=seq,
                    event_type="node_completed",
                    node="verify_evidence_and_quality_gate",
                    payload={"avg_quality": avg_q},
                )
                seq = em.emit(
                    seq=seq,
                    event_type="completed",
                    node="done",
                    payload={"artifact_id": art_id},
                )
                return

            seq = em.emit(
                seq=seq,
                event_type="node_failed_recoverable",
                node="verify_evidence_and_quality_gate",
                payload={
                    "evidence_failures": evidence_failures,
                    "avg_quality": avg_q,
                    "type_ok": type_ok,
                },
            )

            if rollback_count >= 2:
                seq = em.emit(
                    seq=seq,
                    event_type="failed_recoverable",
                    node="verify_evidence_and_quality_gate",
                    payload={
                        "error": AgentError(
                            code="quality_gate",
                            message="质量门槛未达标且已用尽回退次数。",
                            action="retry",
                            detail=json_dumps(
                                {
                                    "evidence_failures": evidence_failures,
                                    "avg_quality": avg_q,
                                    "type_ok": type_ok,
                                }
                            ),
                        ).model_dump()
                    },
                )
                self.store.update_run(run_id, status="failed_recoverable")
                return

            rollback_count += 1
            previous = PreviousAttemptFailure(
                failure_kind="verify",
                schema_errors=None,
                evidence_failures=evidence_failures,
                quality_failures=[]
                if quality_ok
                else [f"avg_quality={avg_q:.1f}", "per_question_min_60"],
                raw_output_truncated=truncate(json_dumps(bundle.model_dump(), ensure_ascii=False)),
            )
            continue
