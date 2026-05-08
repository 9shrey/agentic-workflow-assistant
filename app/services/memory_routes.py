"""FastAPI routes for contact memory management."""

from fastapi import APIRouter, HTTPException

from app.database import sync_engine
from app.services.memory_service import MemoryService
from app.schemas.memory import MemoryCreate, MemoryOut
from sqlalchemy.orm import Session

router = APIRouter(prefix="/memory", tags=["memory"])


def _get_sync_db() -> Session:
    db = Session(sync_engine)
    try:
        yield db
    finally:
        db.close()


@router.get("")
async def list_memory():
    """List all contact memory entries."""
    db = next(_get_sync_db())
    try:
        svc = MemoryService(db)
        entries = svc.get_all()
        return [
            {
                "id": e.id,
                "key": e.key,
                "value": e.value,
                "category": e.category,
                "metadata_json": e.metadata_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in entries
        ]
    finally:
        db.close()


@router.post("")
async def create_memory(data: MemoryCreate):
    """Create a new contact memory entry."""
    db = next(_get_sync_db())
    try:
        svc = MemoryService(db)
        entry = svc.create(
            key=data.key,
            value=data.value,
            category=data.category,
            metadata_json=data.metadata_json,
        )
        return {
            "id": entry.id,
            "key": entry.key,
            "value": entry.value,
            "category": entry.category,
            "metadata_json": entry.metadata_json,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    finally:
        db.close()


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a contact memory entry."""
    db = next(_get_sync_db())
    try:
        svc = MemoryService(db)
        deleted = svc.delete(memory_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        return {"deleted": True, "id": memory_id}
    finally:
        db.close()
