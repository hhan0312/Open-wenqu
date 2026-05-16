from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.storage.database import get_db, json_dumps, json_loads


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunStore:
    def create_run(
        self,
        *,
        run_id: str,
        client_id: str,
        skill_id: str,
        status: str,
        input_snapshot: dict[str, Any],
    ) -> None:
        now = utc_now_iso()
        with get_db().connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, client_id, skill_id, status, input_snapshot_json, final_artifact_id, created_at, updated_at, canceled_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL)
                """,
                (run_id, client_id, skill_id, status, json_dumps(input_snapshot), now, now),
            )

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        final_artifact_id: str | None = None,
        canceled_at: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if final_artifact_id is not None:
            fields.append("final_artifact_id = ?")
            values.append(final_artifact_id)
        if canceled_at is not None:
            fields.append("canceled_at = ?")
            values.append(canceled_at)
        values.append(run_id)
        with get_db().connection() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with get_db().connection() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "client_id": row["client_id"],
            "skill_id": row["skill_id"],
            "status": row["status"],
            "input_snapshot": json_loads(row["input_snapshot_json"]),
            "final_artifact_id": row["final_artifact_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "canceled_at": row["canceled_at"],
        }

    def append_event(
        self,
        run_id: str,
        *,
        seq: int,
        event_type: str,
        node: str | None,
        payload: dict[str, Any],
    ) -> None:
        with get_db().connection() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, seq, type, node, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, seq, event_type, node, json_dumps(payload), utc_now_iso()),
            )

    def next_event_seq(self, run_id: str) -> int:
        with get_db().connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["m"]) + 1

    def list_events_after(self, run_id: str, after_seq: int) -> list[dict[str, Any]]:
        with get_db().connection() as conn:
            rows = conn.execute(
                """
                SELECT seq, type, node, payload_json, created_at
                FROM events
                WHERE run_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (run_id, after_seq),
            ).fetchall()
        return [
            {
                "seq": r["seq"],
                "type": r["type"],
                "node": r["node"],
                "payload": json_loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def save_artifact(
        self,
        *,
        artifact_id: str,
        run_id: str,
        artifact_type: str,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        with get_db().connection() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (id, run_id, type, version, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, run_id, artifact_type, version, json_dumps(payload), utc_now_iso()),
            )

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with get_db().connection() as conn:
            rows = conn.execute(
                """
                SELECT id, type, version, payload_json, created_at
                FROM artifacts
                WHERE run_id = ?
                ORDER BY version ASC, created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "type": r["type"],
                "version": r["version"],
                "payload": json_loads(r["payload_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def latest_artifact_version(self, run_id: str) -> int:
        with get_db().connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS m FROM artifacts WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return int(row["m"])

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with get_db().connection() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "type": row["type"],
            "version": row["version"],
            "payload": json_loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def record_llm_call(self, row: dict[str, Any]) -> None:
        with get_db().connection() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    id, run_id, node, provider, model, prompt_version, input_hash,
                    request_json, raw_response_json, parsed_response_json,
                    latency_ms, input_tokens, output_tokens, status, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["run_id"],
                    row["node"],
                    row["provider"],
                    row["model"],
                    row["prompt_version"],
                    row["input_hash"],
                    row["request_json"],
                    row.get("raw_response_json"),
                    row.get("parsed_response_json"),
                    row.get("latency_ms"),
                    row.get("input_tokens"),
                    row.get("output_tokens"),
                    row["status"],
                    row.get("error"),
                    row["created_at"],
                ),
            )

    def cache_get(self, cache_key: str) -> str | None:
        with get_db().connection() as conn:
            row = conn.execute(
                "SELECT artifact_id FROM cache_entries WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return row["artifact_id"] if row else None

    def cache_put(
        self,
        *,
        cache_key: str,
        artifact_id: str,
        model: str,
        skill_id: str,
        skill_version: str,
        prompt_version: str,
    ) -> None:
        now = utc_now_iso()
        with get_db().connection() as conn:
            conn.execute(
                """
                INSERT INTO cache_entries (cache_key, artifact_id, model, skill_id, skill_version, prompt_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    artifact_id=excluded.artifact_id,
                    model=excluded.model,
                    skill_id=excluded.skill_id,
                    skill_version=excluded.skill_version,
                    prompt_version=excluded.prompt_version,
                    created_at=excluded.created_at
                """,
                (cache_key, artifact_id, model, skill_id, skill_version, prompt_version, now),
            )


def get_run_store() -> RunStore:
    return RunStore()
