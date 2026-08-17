"""Run the Rahul demo case end-to-end through the REAL pipeline.

Executes every layer (0-9) against the seeded Rahul dispute and writes the
complete stage-by-stage machine-readable record plus all three role views to
evaluation/results/rahul_pipeline_result.json.

Usage:
    python -m evaluation.run_rahul
"""
from __future__ import annotations

import json
import sys
import time

from backend.db.database import SessionLocal
from backend.db.models import Dispute
from backend.paths import EVAL_RESULTS_DIR
from backend.pipeline.orchestrator import run_pipeline_sync
from backend.services import role_views

RAHUL_DISPUTE_ID = "D-DEMO-RAHUL"


def main() -> int:
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        dispute = db.get(Dispute, RAHUL_DISPUTE_ID)
        if dispute is None:
            print("Rahul demo case not found. Seed it first:\n"
                  "  python -m data.generate --demo", file=sys.stderr)
            return 1

        t0 = time.perf_counter()
        ctx = run_pipeline_sync(db, dispute, trigger="rahul_e2e")
        db.commit()
        elapsed = time.perf_counter() - t0

        db.refresh(dispute)
        record = ctx.as_record()
        out = {
            "dispute_id": dispute.id,
            "elapsed_seconds": round(elapsed, 3),
            "final_state": dispute.state,
            **record,
            "role_views": {
                "card_member": role_views.card_member_view(db, dispute),
                "merchant": role_views.merchant_view(db, dispute),
                "analyst": role_views.analyst_view(db, dispute),
            },
        }

    path = EVAL_RESULTS_DIR / "rahul_pipeline_result.json"
    path.write_text(json.dumps(out, indent=2, default=str))

    dec = record.get("decision", {})
    act = record.get("action", {})
    print(f"Rahul pipeline complete in {elapsed:.2f}s")
    print(f"  classification : {record.get('classification', {}).get('primary_code')} "
          f"(conf {record.get('classification', {}).get('confidence')})")
    print(f"  decision score : {dec.get('final_score')}")
    print(f"  action         : {act.get('action')} (confidence {act.get('confidence')})")
    print(f"  final state    : {dispute.state}")
    print(f"  written        : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
