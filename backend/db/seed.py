"""Convenience seeder: schema + demo cases (Rahul et al.), keeping any
existing generated data.

Usage:
    python -m backend.db.seed
"""
from __future__ import annotations

from backend.db.database import SessionLocal
from backend.db.init import init_db


def main() -> None:
    init_db(drop=False)
    from data.demo_cases import seed_all
    with SessionLocal() as db:
        ids = seed_all(db)
        db.commit()
    print(f"Seeded demo cases: {', '.join(ids)}")


if __name__ == "__main__":
    main()
