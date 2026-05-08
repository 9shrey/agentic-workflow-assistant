import pytest
from sqlalchemy import inspect

from app.database import init_db, sync_engine
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.models.audit_log import AuditLog
from app.models.contact_memory import ContactMemory


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def test_all_tables_exist():
    inspector = inspect(sync_engine)
    table_names = inspector.get_table_names()
    assert "workflow_runs" in table_names
    assert "approvals" in table_names
    assert "audit_logs" in table_names
    assert "contact_memory" in table_names


def test_workflow_run_columns():
    inspector = inspect(sync_engine)
    columns = {c["name"] for c in inspector.get_columns("workflow_runs")}
    expected = {"id", "user_request", "status", "plan", "agent_state", "final_response", "error_message", "created_at", "updated_at"}
    assert expected.issubset(columns)


def test_approval_columns():
    inspector = inspect(sync_engine)
    columns = {c["name"] for c in inspector.get_columns("approvals")}
    expected = {"id", "workflow_id", "approval_type", "proposed_action", "proposed_payload", "status", "created_at", "decided_at"}
    assert expected.issubset(columns)


def test_audit_log_columns():
    inspector = inspect(sync_engine)
    columns = {c["name"] for c in inspector.get_columns("audit_logs")}
    expected = {"id", "workflow_id", "tool_name", "input_payload", "output_payload", "status", "error_message", "started_at", "completed_at", "duration_ms"}
    assert expected.issubset(columns)


def test_contact_memory_columns():
    inspector = inspect(sync_engine)
    columns = {c["name"] for c in inspector.get_columns("contact_memory")}
    expected = {"id", "key", "value", "category", "metadata_", "created_at", "updated_at"}
    assert expected.issubset(columns)


def test_contact_memory_unique_key():
    """Verify the key column has a unique constraint."""
    inspector = inspect(sync_engine)
    indexes = inspector.get_indexes("contact_memory")
    unique_indexes = [idx for idx in indexes if idx.get("unique")]
    assert len(unique_indexes) >= 1
