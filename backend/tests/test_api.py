"""API smoke tests (FastAPI TestClient) — health, metadata, dispute
filing, pipeline run, role views, merchant response, analyst override."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_metadata_reports_honest_modes(client):
    r = client.get("/api/meta/models")
    assert r.status_code == 200
    comps = r.json()["components"]
    # deterministic fallback must be reported as DEMO when HF is unavailable
    assert comps["classifier"]["mode"] in ("real", "demo")
    assert "spacy" in str(comps).lower()


def test_taxonomy_endpoint(client):
    r = client.get("/api/meta/taxonomy")
    assert r.status_code == 200
    body = r.json()
    codes = {t["code"] for t in body["internal_types"]}
    assert {"NR-01", "QD-01", "BA-09"} <= codes


def test_list_disputes(client):
    r = client.get("/api/disputes")
    assert r.status_code == 200
    assert any(d["id"].startswith("D-DEMO-") for d in r.json()["items"])


def test_file_run_and_views(client):
    # use Rahul's transaction to file a fresh dispute
    r = client.get("/api/disputes/D-DEMO-RAHUL")
    assert r.status_code == 200
    txn_id = r.json()["dispute"]["transaction_id"]

    r = client.post("/api/disputes", json={
        "transaction_id": txn_id,
        "description": "The laptop screen was cracked when I opened the box.",
        "user_selected_code": "QD-01",
        "evidence": [],
    })
    assert r.status_code == 201, r.text
    did = r.json()["dispute_id"]

    r = client.post(f"/api/disputes/{did}/run")
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec["classification"]["primary_code"] == "QD-01"
    assert rec["action"]["action"] in (
        "auto_approve", "request_more_evidence", "escalate_to_analyst")

    for role in ("card_member", "merchant", "analyst"):
        rv = client.get(f"/api/disputes/{did}/view/{role}")
        assert rv.status_code == 200, (role, rv.text)


def test_merchant_response_rerun(client):
    r = client.get("/api/disputes/D-DEMO-RAHUL")
    txn_id = r.json()["dispute"]["transaction_id"]
    r = client.post("/api/disputes", json={
        "transaction_id": txn_id,
        "description": "Package never arrived, tracking shows nothing.",
        "evidence": []})
    did = r.json()["dispute_id"]
    client.post(f"/api/disputes/{did}/run")

    r = client.post(f"/api/disputes/{did}/merchant-response", json={
        "statement": "We shipped on time with tracking.",
        "response_type": "contest",
        "evidence": [{"evidence_type": "shipping_tracking",
                      "payload": {"delivery_status": "delivered",
                                  "zip_match": True,
                                  "signature_on_file": True},
                      "dated": True, "age_days": 2}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["re_ran_pipeline"] is True


def test_analyst_override_records_feedback(client):
    r = client.get("/api/disputes/D-DEMO-FRAUD")
    assert r.status_code == 200
    r = client.post("/api/disputes/D-DEMO-FRAUD/run")
    assert r.status_code == 200
    r = client.post("/api/disputes/D-DEMO-FRAUD/analyst-override", json={
        "action": "override",
        "new_outcome": "favor_merchant",
        "reason": "Confirmed first-party misuse after manual review.",
        "analyst_id": "AN-TEST",
    })
    assert r.status_code == 200, r.text
    assert r.json().get("final_outcome") == "favor_merchant"


def test_dashboard_stats(client):
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    assert r.json()["total_disputes"] >= 8
