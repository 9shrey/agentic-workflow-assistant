"""Seed demo data for local development and testing."""

from app.database import init_db, sync_engine
from app.models.contact_memory import ContactMemory
from sqlalchemy.orm import Session


def seed():
    init_db()
    with Session(sync_engine) as session:
        existing = session.query(ContactMemory).count()
        if existing > 0:
            print(f"Database already has {existing} memory records. Skipping seed.")
            return

        records = [
            ContactMemory(
                key="vendor:acme_corp",
                value="Acme Corp - net30 terms, contact: billing@acme.example.com",
                category="vendor",
                metadata_json={"email": "billing@acme.example.com", "payment_terms": "net30"},
            ),
            ContactMemory(
                key="vendor:globex",
                value="Globex Inc - net15 terms, contact: ap@globex.example.com",
                category="vendor",
                metadata_json={"email": "ap@globex.example.com", "payment_terms": "net15"},
            ),
            ContactMemory(
                key="vendor:initech",
                value="Initech - prefers polite but concise communication",
                category="preference",
                metadata_json={"email": "billing@initech.example.com", "tone": "polite_concise"},
            ),
            ContactMemory(
                key="preference:followup_time",
                value="10:00 AM",
                category="preference",
                metadata_json={"description": "Preferred time for follow-up emails"},
            ),
            ContactMemory(
                key="preference:weekend_policy",
                value="do_not_follow_up",
                category="preference",
                metadata_json={"description": "Do not schedule follow-ups on weekends"},
            ),
        ]
        session.add_all(records)
        session.commit()
        print(f"Seeded {len(records)} contact memory records.")


if __name__ == "__main__":
    seed()
