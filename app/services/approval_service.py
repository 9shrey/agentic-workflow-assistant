"""Approval service for managing workflow approval records."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.approval import Approval


class ApprovalService:
    """Manages approval records for workflow write operations.

    Write operations (Gmail drafts, Calendar events) require explicit
    human approval before execution in the MVP.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_approval(
        self,
        workflow_id: str,
        approval_type: str,
        proposed_action: str,
        proposed_payload: Optional[dict] = None,
    ) -> Approval:
        approval = Approval(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            approval_type=approval_type,
            proposed_action=proposed_action,
            proposed_payload=proposed_payload,
            status="pending",
        )
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def get_approval(self, approval_id: str) -> Optional[Approval]:
        return self.db.query(Approval).filter(Approval.id == approval_id).first()

    def get_pending_for_workflow(self, workflow_id: str) -> list[Approval]:
        return (
            self.db.query(Approval)
            .filter(Approval.workflow_id == workflow_id, Approval.status == "pending")
            .all()
        )

    def decide_approval(self, approval_id: str, status: str) -> Optional[Approval]:
        """Approve or reject an approval request."""
        if status not in ("approved", "rejected"):
            raise ValueError("Status must be 'approved' or 'rejected'")
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        if approval.status != "pending":
            raise ValueError(f"Approval {approval_id} is already {approval.status}")
        approval.status = status
        approval.decided_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def approve_all_for_workflow(self, workflow_id: str) -> int:
        """Approve all pending approvals for a workflow (convenience for demo)."""
        pending = self.get_pending_for_workflow(workflow_id)
        for approval in pending:
            approval.status = "approved"
            approval.decided_at = datetime.now(timezone.utc)
        self.db.commit()
        return len(pending)
