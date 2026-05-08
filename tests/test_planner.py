"""Tests for the deterministic agent planner."""

import pytest

from app.agent.planner import (
    PlanStepType,
    WorkflowPlan,
    create_plan,
    _contains_keywords,
)


class TestKeywordDetection:
    def test_invoice_keyword_match(self):
        assert _contains_keywords("find pending invoices", ["invoice", "payment"])

    def test_no_match(self):
        assert not _contains_keywords("hello world", ["invoice", "payment"])

    def test_case_insensitive(self):
        assert _contains_keywords("Find INVOICES", ["invoice"])


class TestCreatePlan:
    def test_invoice_reminder_request(self):
        plan = create_plan(
            "Find all pending invoices, draft reminder emails, and schedule follow-ups."
        )
        assert isinstance(plan, WorkflowPlan)
        assert len(plan.steps) >= 6
        step_types = [s.step for s in plan.steps]
        assert PlanStepType.SEARCH_EMAIL_THREADS in step_types
        assert PlanStepType.SUMMARIZE_THREADS in step_types
        assert PlanStepType.EXTRACT_PENDING_INVOICES in step_types
        assert PlanStepType.DRAFT_REMINDER_EMAILS in step_types
        assert PlanStepType.REQUEST_APPROVAL in step_types
        assert PlanStepType.FINAL_SUMMARY in step_types

    def test_plan_includes_calendar_steps(self):
        plan = create_plan(
            "Find invoices, draft emails, and schedule calendar follow-ups."
        )
        step_types = [s.step for s in plan.steps]
        assert PlanStepType.PROPOSE_CALENDAR_FOLLOWUPS in step_types
        assert PlanStepType.CREATE_CALENDAR_FOLLOWUPS in step_types

    def test_plan_has_approval_step(self):
        plan = create_plan("Find invoices and draft reminders")
        approval_steps = [s for s in plan.steps if s.requires_approval]
        assert len(approval_steps) >= 1
        assert approval_steps[0].step in (
            PlanStepType.REQUEST_APPROVAL,
            PlanStepType.CREATE_GMAIL_DRAFTS,
        )

    def test_generic_request_still_works(self):
        plan = create_plan("Check my inbox")
        assert len(plan.steps) >= 2
        assert plan.steps[-1].step == PlanStepType.FINAL_SUMMARY

    def test_deterministic_same_output(self):
        request = "Find all pending invoices"
        plan1 = create_plan(request)
        plan2 = create_plan(request)
        assert plan1.model_dump_json() == plan2.model_dump_json()

    def test_plan_step_has_tool_mapping(self):
        plan = create_plan("Find invoices")
        search_step = next(
            s for s in plan.steps if s.step == PlanStepType.SEARCH_EMAIL_THREADS
        )
        assert search_step.tool_name == "search_email"
        assert "query" in search_step.config

    def test_plan_serialization(self):
        plan = create_plan("Find invoices")
        json_str = plan.model_dump_json()
        assert "search_email_threads" in json_str
        assert "draft_reminder_emails" in json_str
