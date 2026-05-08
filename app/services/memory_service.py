"""Memory service for contact preferences and vendor information."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.contact_memory import ContactMemory


class MemoryService:
    """Manages contact memory entries for vendor preferences, follow-up times, etc."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self, limit: int = 100) -> list[ContactMemory]:
        return self.db.query(ContactMemory).order_by(ContactMemory.updated_at.desc()).limit(limit).all()

    def get_by_key(self, key: str) -> Optional[ContactMemory]:
        return self.db.query(ContactMemory).filter(ContactMemory.key == key).first()

    def create(
        self,
        key: str,
        value: str,
        category: str = "general",
        metadata_json: Optional[dict] = None,
    ) -> ContactMemory:
        existing = self.get_by_key(key)
        if existing:
            raise ValueError(f"Memory key '{key}' already exists. Use update instead.")
        entry = ContactMemory(
            id=str(uuid.uuid4()),
            key=key,
            value=value,
            category=category,
            metadata_json=metadata_json,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def update(
        self,
        memory_id: str,
        value: Optional[str] = None,
        category: Optional[str] = None,
        metadata_json: Optional[dict] = None,
    ) -> Optional[ContactMemory]:
        entry = self.db.query(ContactMemory).filter(ContactMemory.id == memory_id).first()
        if not entry:
            return None
        if value is not None:
            entry.value = value
        if category is not None:
            entry.category = category
        if metadata_json is not None:
            entry.metadata_json = metadata_json
        entry.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def delete(self, memory_id: str) -> bool:
        entry = self.db.query(ContactMemory).filter(ContactMemory.id == memory_id).first()
        if not entry:
            return False
        self.db.delete(entry)
        self.db.commit()
        return True
