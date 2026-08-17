"""Shared fixtures: an isolated on-disk sqlite DB seeded with demo cases."""
import os
import tempfile

import pytest

# point the app at a throwaway DB BEFORE backend modules read config
_tmp = tempfile.mkdtemp(prefix="dispute-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ.setdefault("AI_MODE", "demo")
os.environ.setdefault("GRAPH_MODE", "memory")
os.environ.setdefault("QUEUE_MODE", "memory")


@pytest.fixture(scope="session")
def seeded_db():
    from backend.db.init import init_db
    from backend.db.database import SessionLocal
    init_db(drop=True)
    from data.demo_cases import seed_all
    with SessionLocal() as db:
        seed_all(db)
        db.commit()
    return SessionLocal


@pytest.fixture()
def db(seeded_db):
    s = seeded_db()
    try:
        yield s
        s.rollback()
    finally:
        s.close()


@pytest.fixture(scope="session")
def client(seeded_db):
    from fastapi.testclient import TestClient
    from backend.api.app import app
    with TestClient(app) as c:
        yield c
