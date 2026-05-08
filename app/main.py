import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.services.workflow_routes import router as workflow_router
from app.services.approval_routes import router as approval_router
from app.services.memory_routes import router as memory_router

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up - initializing database")
    init_db()
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Agentic Workflow Automation Assistant",
    description="LangGraph-based agent that automates email workflows with human approval checkpoints",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(workflow_router)
app.include_router(approval_router)
app.include_router(memory_router)


@app.get("/")
async def root():
    return {"message": "Agentic Workflow Automation Assistant", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "google_api_enabled": settings.google_api_enabled}
