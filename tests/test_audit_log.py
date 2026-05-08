"""Tests for the audit service."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.database import init_db, sync_engine
from app.models.audit_log import AuditLog
from app.services.audit_service import AuditService


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db() -> Session:
    """Provide a sync session for tests."""
    with Session(sync_engine) as session:
        yield session
        session.query(AuditLog).delete()
        session.commit()


@pytest.fixture
def workflow_id() -> str:
    return str(uuid.uuid4())


class TestAuditService:

    def test_log_call_success(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        entry = svc.log_call(
            workflow_id=workflow_id,
            tool_name="search_email",
            input_payload={"query": "invoice"},
            output_payload={"threads_found": 3},
        )
        assert entry.status == "success"
        assert entry.tool_name == "search_email"
        assert entry.workflow_id == workflow_id
        assert entry.input_payload == {"query": "invoice"}
        assert entry.output_payload == {"threads_found": 3}

    def test_log_call_failure(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        entry = svc.log_call(
            workflow_id=workflow_id,
            tool_name="search_email",
            input_payload={"query": "invoice"},
            status="failed",
            error_message="Connection timeout",
        )
        assert entry.status == "failed"
        assert entry.error_message == "Connection timeout"

    def test_log_call_start_complete_lifecycle(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        audit_id, start_time = svc.log_call_start(
            workflow_id=workflow_id,
            tool_name="draft_email",
            input_payload={"to": "test@example.com"},
        )

        entry = svc.log_call_complete(
            audit_id=audit_id,
            output_payload={"draft_id": "draft-123"},
            started_at=start_time,
        )
        assert entry.status == "success"
        assert entry.output_payload == {"draft_id": "draft-123"}
        assert entry.duration_ms is not None
        assert entry.duration_ms >= 0

    def test_log_call_complete_with_error(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        audit_id, start_time = svc.log_call_start(
            workflow_id=workflow_id, tool_name="draft_email"
        )

        entry = svc.log_call_complete(
            audit_id=audit_id,
            error_message="Permission denied",
            started_at=start_time,
        )
        assert entry.status == "failed"
        assert entry.error_message == "Permission denied"

    def test_get_logs_for_workflow(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        svc.log_call(workflow_id=workflow_id, tool_name="tool_a")
        svc.log_call(workflow_id=workflow_id, tool_name="tool_b")
        svc.log_call(workflow_id=str(uuid.uuid4()), tool_name="other_workflow_tool")

        logs = svc.get_logs_for_workflow(workflow_id)
        assert len(logs) == 2
        assert {l.tool_name for l in logs} == {"tool_a", "tool_b"}

    def test_get_all_logs_with_limit(self, db: Session, workflow_id: str):
        svc = AuditService(db)
        for i in range(5):
            svc.log_call(workflow_id=workflow_id, tool_name=f"tool_{i}")

        logs = svc.get_all_logs(limit=3)
        assert len(logs) == 3

    def test_log_call_missing_audit_id(self, db: Session):
        svc = AuditService(db)
        with pytest.raises(ValueError, match="not found"):
            svc.log_call_complete(audit_id="nonexistent")
