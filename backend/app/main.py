from __future__ import annotations

import threading
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent.runtime import AgentRuntime
from app.config import Settings, get_settings
from app.models.api_dto import (
    CreateRunRequest,
    CreateRunResponse,
    ExportDocxRequest,
    RunDetailResponse,
    SkillSummaryResponse,
    UpdateArtifactRequest,
    UpdateArtifactResponse,
)
from app.skills.loader import SkillRegistry, default_required_tool_names
from app.storage.database import get_db, new_id
from app.storage.run_store import get_run_store
from app.tools.docx_export import build_student_teacher_docx

_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


def get_cancel_event(run_id: str) -> threading.Event:
    with _cancel_lock:
        if run_id not in _cancel_events:
            _cancel_events[run_id] = threading.Event()
        return _cancel_events[run_id]


_skill_registry_singleton: SkillRegistry | None = None
_skill_registry_lock = threading.Lock()


def get_skill_registry(settings: Settings = Depends(get_settings)) -> SkillRegistry:
    global _skill_registry_singleton
    with _skill_registry_lock:
        if _skill_registry_singleton is None:
            _skill_registry_singleton = SkillRegistry.load(
                settings.skills_root,
                required_tool_names=default_required_tool_names(),
            )
        return _skill_registry_singleton


def create_app() -> FastAPI:
    app = FastAPI(title="Open Wenqu API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        get_db()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/skills", response_model=list[SkillSummaryResponse])
    def list_skills(reg: SkillRegistry = Depends(get_skill_registry)) -> list[SkillSummaryResponse]:
        out: list[SkillSummaryResponse] = []
        for sid, spec in reg.index.items():
            if spec.task == "base_prompt_fragments":
                continue
            out.append(
                SkillSummaryResponse(
                    id=sid,
                    version=spec.version,
                    subject=spec.subject,
                    stage=spec.stage,
                    domain=spec.domain,
                    question_format=spec.question_format,
                    task=spec.task,
                    required_tools=list(spec.required_tools),
                )
            )
        return sorted(out, key=lambda x: x.id)

    def _run_worker(run_id: str, body: CreateRunRequest, settings: Settings) -> None:
        reg = get_skill_registry(settings)
        ev = get_cancel_event(run_id)
        runtime = AgentRuntime(
            settings=settings,
            skill_registry=reg,
            cancel_check=ev.is_set,
        )
        try:
            runtime.execute(run_id=run_id, req=body)
        finally:
            with _cancel_lock:
                _cancel_events.pop(run_id, None)

    @app.post("/api/runs", response_model=CreateRunResponse)
    def create_run(
        body: CreateRunRequest,
        background_tasks: BackgroundTasks,
        settings: Settings = Depends(get_settings),
    ) -> CreateRunResponse:
        if body.skill_id not in get_skill_registry(settings).index:
            raise HTTPException(status_code=400, detail="Unknown skill_id")
        run_id = new_id()
        store = get_run_store()
        store.create_run(
            run_id=run_id,
            client_id=body.client_id,
            skill_id=body.skill_id,
            status="running",
            input_snapshot=body.model_dump(),
        )
        store.append_event(
            run_id,
            seq=store.next_event_seq(run_id),
            event_type="run_started",
            node=None,
            payload={"skill_id": body.skill_id},
        )
        get_cancel_event(run_id).clear()
        background_tasks.add_task(_run_worker, run_id, body, settings)
        return CreateRunResponse(run_id=run_id, status="running")

    def _require_run(run_id: str, client_id: str) -> dict[str, Any]:
        store = get_run_store()
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run["client_id"] != client_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return run

    @app.get("/api/runs/{run_id}", response_model=RunDetailResponse)
    def get_run_detail(run_id: str, client_id: str = Query(...)) -> RunDetailResponse:
        _require_run(run_id, client_id)
        store = get_run_store()
        run = store.get_run(run_id)
        assert run is not None
        arts = store.list_artifacts(run_id)
        snap = run["input_snapshot"]
        doc_payload = None
        if arts:
            fid = run.get("final_artifact_id")
            picked = next((a for a in arts if a["id"] == fid), arts[-1])
            doc_payload = picked["payload"].get("document")
        return RunDetailResponse(
            run_id=run["id"],
            client_id=run["client_id"],
            skill_id=run["skill_id"],
            status=run["status"],
            current_node=None,
            error=None,
            document=doc_payload,
            source_question=snap.get("source_question"),
            generation=snap.get("generation"),
            artifacts=[
                {"id": a["id"], "type": a["type"], "version": a["version"], "payload": a["payload"]}
                for a in arts
            ],
            final_artifact_id=run["final_artifact_id"],
            retry_count=0,
            rollback_count=0,
        )

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        request: Request,
        run_id: str,
        client_id: str = Query(...),
        after_seq: int = Query(0, ge=0),
    ) -> StreamingResponse:
        _require_run(run_id, client_id)
        store = get_run_store()

        async def gen():
            import asyncio
            import json as _json

            last = after_seq
            while True:
                if await request.is_disconnected():
                    return
                batch = store.list_events_after(run_id, last)
                for ev in batch:
                    last = int(ev["seq"])
                    yield f"data: {_json.dumps({'seq': last, 'type': ev['type'], 'node': ev['node'], 'payload': ev['payload']}, ensure_ascii=False)}\n\n"
                run = store.get_run(run_id)
                if run and run["status"] in ("completed", "failed_fatal", "failed_recoverable", "canceled"):
                    yield "event: end\n\ndata: {}\n\n"
                    return
                await asyncio.sleep(0.4)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str, client_id: str = Query(...)) -> dict[str, str]:
        _require_run(run_id, client_id)
        get_cancel_event(run_id).set()
        store = get_run_store()
        store.append_event(
            run_id,
            seq=store.next_event_seq(run_id),
            event_type="cancel_requested",
            node=None,
            payload={},
        )
        return {"status": "cancel_requested"}

    @app.patch("/api/runs/{run_id}/artifacts/{artifact_id}", response_model=UpdateArtifactResponse)
    def patch_artifact(
        run_id: str,
        artifact_id: str,
        body: UpdateArtifactRequest,
    ) -> UpdateArtifactResponse:
        _require_run(run_id, body.client_id)
        store = get_run_store()
        art = store.get_artifact(artifact_id)
        if not art or art["run_id"] != run_id:
            raise HTTPException(status_code=404, detail="Artifact not found")
        ver = store.latest_artifact_version(run_id) + 1
        new_id_ = new_id()
        store.save_artifact(
            artifact_id=new_id_,
            run_id=run_id,
            artifact_type="edited",
            version=ver,
            payload=body.payload,
        )
        store.update_run(run_id, final_artifact_id=new_id_)
        return UpdateArtifactResponse(artifact_id=new_id_, version=ver)

    @app.post("/api/runs/{run_id}/export/docx")
    def export_docx(
        run_id: str,
        body: ExportDocxRequest,
        settings: Settings = Depends(get_settings),
    ) -> Response:
        _require_run(run_id, body.client_id)
        store = get_run_store()
        art = store.get_artifact(body.artifact_id)
        if not art or art["run_id"] != run_id:
            raise HTTPException(status_code=404, detail="Artifact not found")
        run = store.get_run(run_id)
        assert run is not None
        snap = run["input_snapshot"]
        passage = str(snap.get("passage") or "")
        title = body.title or "导出"
        binary = build_student_teacher_docx(title=title, passage=passage, payload=art["payload"])
        filename = f"open-wenqu-{run_id}.docx"
        return Response(
            content=binary,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


app = create_app()
