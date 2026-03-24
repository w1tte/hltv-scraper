"""Structured run-state tracking for the hltv-ingest service."""

from __future__ import annotations

import json
from typing import Any


class RunStateRepository:
    """Persist run lifecycle state for dashboard and operations visibility."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def start_run(
        self,
        *,
        run_id: str,
        status: str,
        phase: str,
        hostname: str,
        pipeline: str,
        workers: int,
        concurrent_tabs: int,
        proxy_count: int,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ingest_runs (
                        run_id,
                        service_name,
                        status,
                        phase,
                        hostname,
                        pipeline,
                        workers,
                        concurrent_tabs,
                        proxy_count,
                        source,
                        summary
                    )
                    VALUES (%s, 'hltv-ingest', %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        run_id,
                        status,
                        phase,
                        hostname,
                        pipeline,
                        workers,
                        concurrent_tabs,
                        proxy_count,
                        source,
                        json.dumps(metadata or {}),
                    ),
                )

    def heartbeat(
        self,
        run_id: str,
        *,
        phase: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        clauses = ["last_heartbeat_at = now()"]
        params: list[Any] = []

        if phase is not None:
            clauses.append("phase = %s")
            params.append(phase)
        if metadata is not None:
            clauses.append("summary = COALESCE(summary, '{}'::jsonb) || %s::jsonb")
            params.append(json.dumps(metadata))

        params.append(run_id)
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    f"UPDATE ingest_runs SET {', '.join(clauses)} WHERE run_id = %s",
                    params,
                )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        phase: str,
        summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ingest_runs
                    SET status = %s,
                        phase = %s,
                        finished_at = now(),
                        last_heartbeat_at = now(),
                        summary = COALESCE(summary, '{}'::jsonb) || %s::jsonb,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (
                        status,
                        phase,
                        json.dumps(summary or {}),
                        error_message,
                        run_id,
                    ),
                )
