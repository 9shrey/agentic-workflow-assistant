# Agentic Workflow Automation Assistant

LangGraph-based workflow automation agent integrating Gmail and Google Calendar APIs to search email threads, summarize invoice context, draft reminder emails, and schedule follow-ups with human approval checkpoints.

## Resume Bullet Points

- Built a LangGraph-based workflow automation agent integrating Gmail and Google Calendar APIs to search email threads, summarize invoice context, draft reminder emails, and schedule follow-ups with human approval checkpoints.

- Implemented typed agent state, Pydantic tool schemas, OAuth-based Google API access, retry/fallback handling, SQLite audit logs, and deterministic routing for reliable multi-step agent workflows.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Layer                            │
│  POST /workflows/start    GET /workflows/{id}                   │
│  POST /approvals/{id}/approve    GET /memory    POST /memory    │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│                     LangGraph Workflow                          │
│                                                                 │
│  Planner → Search Email → Summarize → Extract Invoices          │
│       → Draft Emails → Propose Calendar → [APPROVAL CHECKPOINT] │
│       → Execute Approved → Final Summary                        │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│                      Tool Layer                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Gmail Search   │  │ Thread Summary │  │  Draft Email   │    │
│  │  (mock/real)    │  │  (mock/real)   │  │  (mock/real)   │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │ Calendar Event  │  │ Contact Memory │  │   Audit Log    │    │
│  │  (mock/real)    │  │   (SQLite)     │  │   (SQLite)     │    │
│  └────────────────┘  └────────────────┘  └────────────────┘    │
└──────────┬──────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────┐
│                     Data Layer (SQLite)                          │
│  workflow_runs │ approvals │ audit_logs │ contact_memory        │
└─────────────────────────────────────────────────────────────────┘
```

## Workflow Steps (Deterministic, No LLM Required)

1. **Planner** - Parse user request, generate structured multi-step plan
2. **Search Email** - Query Gmail threads for invoice/payment-related emails
3. **Summarize Threads** - Extract context from each thread
4. **Extract Invoices** - Identify pending invoices with vendor, amount, due date
5. **Draft Reminders** - Generate email draft content for each vendor
6. **Propose Calendar** - Suggest follow-up events for urgent invoices
7. **Approval Checkpoint** - Pause for human review before any write operations
8. **Execute Approved** - Create Gmail drafts and Calendar events for approved items
9. **Final Summary** - Generate comprehensive action report

## Safety Rules (Enforced)

- **NEVER sends emails automatically** - Gmail scopes are `gmail.compose` (draft only) + `gmail.readonly`
- **Calendar events require approval** - No event is created without explicit human approval
- **All tool calls are audit logged** - Complete input/output/error tracking per workflow

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Seed demo data (optional)
python -m app.scripts.seed_demo_data

# Run the server
uvicorn app.main:app --reload

# Health check
curl http://localhost:8000/health
```

## Run Mock Demo

The demo runs the entire workflow with mock data (no Google API required):

```bash
python -m app.scripts.run_demo_workflow
```

Output:
```
[USER REQUEST] Find all pending invoices, draft reminder emails...

[WORKFLOW CREATED] ID: <uuid>
[EXECUTING WORKFLOW...]

GENERATED PLAN
  1. search_email_threads
     └─ Search email threads for pending invoice/payment-related emails
  2. summarize_threads
     └─ Summarize each relevant email thread to extract context
  3. extract_pending_invoices
     └─ Extract invoice details from summarized threads
  4. draft_reminder_emails
     └─ Generate reminder email drafts for each pending invoice
  5. propose_calendar_followups
     └─ Propose calendar follow-up events for pending invoices
  6. request_approval [REQUIRES APPROVAL]
     └─ Request human approval for draft emails and calendar events

PENDING INVOICES (5)
  [HIGH] Acme Corp - INV-2026-0042 for $5,000
  [MEDIUM] Globex Inc - GL-2026-018 for $12,500
  [HIGH] Initech - INIT-889 for $3,200
  ...

PROPOSED EMAIL DRAFTS (5)
  To: billing@acme.example.com | Subject: Reminder: INV-2026-0042
  ...

PENDING APPROVALS (5)
  [<uuid>] gmail_draft  | Action: Create Gmail draft to billing@acme.example.com
  ...

SIMULATING HUMAN APPROVAL
  Approved 5 action(s)

FINAL SUMMARY
  Workflow Complete
  - 5 pending invoices found
  - 5 reminder email drafts generated
  - 5 calendar follow-ups proposed

DEMO COMPLETE - Status: completed
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root - project info |
| GET | `/health` | Health check |
| POST | `/workflows/start` | Start a new workflow |
| GET | `/workflows/{id}` | Get workflow status |
| GET | `/workflows/{id}/pending-approvals` | List pending approvals |
| GET | `/workflows/{id}/audit-logs` | List tool call audit logs |
| POST | `/approvals/{id}/approve` | Approve a pending action |
| POST | `/approvals/{id}/reject` | Reject a pending action |
| GET | `/memory` | List contact memory entries |
| POST | `/memory` | Create memory entry |
| DELETE | `/memory/{id}` | Delete memory entry |

### Example API Calls

```bash
# Start a workflow
curl -X POST http://localhost:8000/workflows/start \
  -H "Content-Type: application/json" \
  -d '{"user_request": "Find all pending invoices, draft reminder emails, and schedule follow-ups."}'

# Check workflow status
curl http://localhost:8000/workflows/{workflow_id}

# View pending approvals
curl http://localhost:8000/workflows/{workflow_id}/pending-approvals

# Approve an action
curl -X POST http://localhost:8000/approvals/{approval_id}/approve

# View audit logs
curl http://localhost:8000/workflows/{workflow_id}/audit-logs

# Manage memory
curl -X POST http://localhost:8000/memory \
  -H "Content-Type: application/json" \
  -d '{"key": "vendor:acme", "value": "net30 terms", "category": "vendor"}'

curl http://localhost:8000/memory
```

## Run Tests

```bash
# Run all tests
pytest -v

# Run specific test files
pytest tests/test_planner.py -v
pytest tests/test_approval_flow.py -v

# With coverage
pytest --cov=app tests/
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLite database path | `sqlite+aiosqlite:///./workflow_agent.db` |
| `GOOGLE_API_ENABLED` | Enable real Google APIs | `false` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | - |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `http://localhost:8000/oauth/callback` |
| `GOOGLE_TOKEN_PATH` | Token storage path | `./google_token.json` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Google OAuth Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable Gmail API and Google Calendar API
3. Create OAuth 2.0 credentials (Desktop application type)
4. Set `GOOGLE_API_ENABLED=true` in `.env`
5. Set your `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
6. Run the OAuth flow (built into the google_auth_service module)

## Tech Stack

- **Python 3.11+**, **FastAPI** - Web framework
- **LangGraph** - Agent workflow orchestration with deterministic routing
- **Pydantic v2** - Schema validation for all tool I/O
- **SQLAlchemy + SQLite** - Data persistence
- **Gmail API** - Email thread search and draft creation (readonly + compose)
- **Google Calendar API** - Calendar event creation with approval
- **Google OAuth** - Secure API authentication
- **tenacity** - Retry/fallback logic for transient failures
- **structlog** - Structured logging
- **pytest** - Comprehensive test suite (75+ tests)

## Project Structure

```
agentic-workflow-assistant/
  app/
    main.py                  # FastAPI app entry point
    config.py                # Settings via pydantic-settings
    database.py              # SQLAlchemy setup
    models/
      workflow_run.py        # WorkflowRun ORM model
      approval.py            # Approval ORM model
      audit_log.py           # AuditLog ORM model
      contact_memory.py      # ContactMemory ORM model
    schemas/
      requests.py            # Request/response schemas
      tool_schemas.py        # Tool input/output schemas
      approvals.py           # Approval schemas
      memory.py              # Memory schemas
    agent/
      state.py               # Typed AgentState (Pydantic)
      graph.py               # Workflow execution orchestration
      planner.py             # Deterministic plan generator
      router.py              # Deterministic node routing
      nodes.py               # Workflow node implementations
    tools/
      mock_tools.py          # Mock tool implementations
      gmail_tool.py          # Real Gmail API adapter
      calendar_tool.py       # Real Calendar API adapter
      tool_registry.py       # Tool dispatcher (mock/real)
      retry_utils.py         # Tenacity retry wrappers
    services/
      audit_service.py       # Audit logging service
      approval_service.py    # Approval management
      memory_service.py      # Contact memory CRUD
      google_auth_service.py # Google OAuth2 authentication
      workflow_routes.py     # Workflow API endpoints
      approval_routes.py     # Approval API endpoints
      memory_routes.py       # Memory API endpoints
    scripts/
      seed_demo_data.py      # Seed demo contact memory
      run_demo_workflow.py   # Full end-to-end demo
  tests/
    test_health.py           # Health endpoint tests
    test_models.py           # Database model tests
    test_tool_schemas.py     # Schema validation tests
    test_audit_log.py        # Audit service tests
    test_mock_tools.py       # Mock tool tests
    test_planner.py          # Planner tests
    test_agent_state.py      # Workflow execution tests
    test_approval_flow.py    # Approval flow tests
  .env.example
  requirements.txt
  pyproject.toml
  README.md
```

## Key Design Decisions

1. **Deterministic Planner** - No LLM dependency for testing; keyword-based step generation
2. **Mock-First Development** - All tools have mock implementations for fast local iteration
3. **Approval Guardrails** - Write operations (drafts, events) require explicit human approval
4. **Typed State** - Pydantic models for agent state ensure type safety throughout
5. **Comprehensive Auditing** - Every tool call is logged with timing, input, output, and errors
6. **Retry/Fallback** - Transient failures are retried; critical operations have fallback paths
7. **Google API Behind Flag** - `GOOGLE_API_ENABLED=false` runs everything locally with mocks
