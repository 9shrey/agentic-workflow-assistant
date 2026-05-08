"""Audit service for logging all tool calls during workflow execution."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def _safe_json(v: Any) -> Any:
    """Convert a value to JSON-safe representation."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    if isinstance(v, dict):
        return {k: _safe_json(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_safe_json(item) for item in v]
    return v


class AuditService:
    """Logs every tool call with input, output, status, and timing."""

    def __init__(self, db: Session):
        self.db = db

    def log_call(
        self,
        workflow_id: str,
        tool_name: str,
        input_payload: Optional[dict] = None,
        status: str = "success",
        output_payload: Optional[Any] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_ms: Optional[float] = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            tool_name=tool_name,
            input_payload=_safe_json(input_payload),
            output_payload=_safe_json(output_payload),
            status=status,
            error_message=error_message,
            started_at=started_at or datetime.now(timezone.utc),
            completed_at=completed_at or datetime.now(timezone.utc),
            duration_ms=duration_ms or 0.0,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def log_call_start(self, workflow_id: str, tool_name: str, input_payload: Optional[Any] = None) -> tuple[str, datetime]:
        """Start a tool call and return an audit ID + start time."""
        audit_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        entry = AuditLog(
            id=audit_id,
            workflow_id=workflow_id,
            tool_name=tool_name,
            input_payload=_safe_json(input_payload),
            status="running",
            started_at=start_time,
        )
        self.db.add(entry)
        self.db.commit()
        return audit_id, start_time

    def log_call_complete(
        self,
        audit_id: str,
        output_payload: Optional[Any] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> AuditLog:
        """Mark a previously started tool call as complete."""
        entry = self.db.query(AuditLog).filter(AuditLog.id == audit_id).first()
        if not entry:
            raise ValueError(f"Audit log entry {audit_id} not found")
        now = datetime.now(timezone.utc)
        entry.completed_at = now
        if started_at:
            entry.duration_ms = (now - started_at).total_seconds() * 1000
        entry.status = "failed" if error_message else "success"
        entry.output_payload = _safe_json(output_payload)
        entry.error_message = error_message
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get_logs_for_workflow(self, workflow_id: str) -> list[AuditLog]:
        return (
            self.db.query(AuditLog)
            .filter(AuditLog.workflow_id == workflow_id)
            .order_by(AuditLog.started_at.asc())
            .all()
        )

    def get_all_logs(self, limit: int = 100) -> list[AuditLog]:
        return self.db.query(AuditLog).order_by(AuditLog.started_at.desc()).limit(limit).all()
