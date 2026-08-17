# Frictionless Dispute & Chargeback Resolution

A complete, runnable implementation of the 10-layer dispute-resolution
pipeline from the Technical Design Document (Amex Codestreet Hackathon):

```
Layer 0  Knowledge Graph        backend/graph/            (memory or Neo4j)
Layer 1  Classification         backend/pipeline/layer1_* (spaCy + BART-MNLI adapter)
Layer 2  Evidence Mapping       config/evidence_matrix.yaml (per network)
Layer 3  Dynamic Collection     backend/pipeline/layer3_* (async dispatch)
Layer 4  Evidence Scoring       config/evidence_strength.yaml
Layer 5  Dispute Integrity      advisory only — never auto-denies
Layer 6  Decision Model         category weight matrix + conclusive-evidence rule
Layer 7  Reasoning & Compliance network rules + burden of proof + templates
Layer 8  Action Recommendation  5 outcomes, cost-asymmetric
Layer 9  Feedback & Learning    accuracy reports + retraining candidates
```

Architecture per `claude_prompt.txt`:
`description → NLP → InternalDisputeType (36+3) → network mapping (Excel) →
NetworkReasonCode → evidence rules → decision engine`.
Internal dispute types and network reason codes are **separate concepts**
(many-to-many; see `validation/taxonomy_validation_report.md`).

Everything runs locally with zero external services:
SQLite + in-memory graph + in-memory queue + deterministic model adapters
(`AI_MODE=demo`). PostgreSQL / Neo4j / Kafka / real Hugging Face models are
switch-on upgrades, not dependencies.

---

## STEP-BY-STEP EXECUTION

### STEP 1 — enter the project
```bash
cd dispute-resolution
```

### STEP 2 — create a virtual environment
```bash
python -m venv .venv
```

### STEP 3 — activate it
```bash
source .venv/bin/activate            # Windows: .venv\Scripts\activate
```

### STEP 4 — install the backend
```bash
pip install -r backend/requirements.txt
```
If the spaCy model line fails (no GitHub access), run
`python -m spacy download en_core_web_sm` afterwards. The system still runs
without spaCy (NLP features degrade gracefully to regex extraction).

Optional REAL model mode (BART-large-MNLI, CLIP ViT-L/14, BLIP-2):
```bash
pip install -r backend/requirements-ml.txt
python scripts/fetch_models.py          # download + VERIFY each checkpoint
python scripts/fetch_models.py --only bart clip   # skip the 15 GB BLIP-2
```
`fetch_models.py` loads each model and runs it once (BART on Rahul's text,
CLIP on Rahul's photo vs the listing image), so you know what works before
demo day. Afterwards the models run with no internet at all:
```bash
export HF_HUB_OFFLINE=1 AI_MODE=real
```
Anything that fails to load falls back to DEMO and says so in the UI —
the mode badge never claims a model ran when it did not.

### STEP 5 — install the frontend
```bash
cd frontend
npm install
cd ..
```

### STEP 6 — configure
```bash
cp .env.example .env
```
Defaults: `AI_MODE=demo`, SQLite, in-memory graph/queue. Set `AI_MODE=real`
only if you installed `requirements-ml.txt` and have internet access.

### STEP 7 — initialise the database (schema + taxonomy from the Excel)
```bash
python -m backend.db.init
```

### STEP 8 — validate the taxonomy (tech-doc vs Excel discrepancy report)
```bash
python -m validation.validate_taxonomy
```
Writes `validation/taxonomy_validation_report.{md,json}` — 36 tech-doc types,
39 Excel internal codes, `BA-09`/`AR-04`/`AR-05` preserved as Excel-only.

### STEP 9 — generate synthetic data (also seeds the Rahul demo case)
```bash
python -m data.generate --count 10000 --seed 42
```
Writes 14 CSVs + `disputes_master.jsonl` + `ground_truth.csv` to
`data/generated/`, plus ~1,960 rendered evidence **images** under
`data/generated/images/` (a studio listing shot per product and a card
member photo per photo-bearing dispute, with fracture lines or dents drawn
on where the claim says so). The vision pipeline analyses those actual
pixels — in DEMO mode via classical CV (`backend/vision/pixels.py`:
background-masked colour histograms + coarse structure for Stage A,
local-contrast fracture detection for Stage B), in REAL mode via CLIP and
BLIP-2. Ground truth is **never** read by the pipeline — only by evaluation.

Other sizes:
```bash
python -m data.generate --count 100 --seed 42
python -m data.generate --count 1000 --seed 42
python -m data.generate --count 50000 --seed 42
python -m data.generate --demo                       # demo scenarios only
python -m data.generate --include-demo-case rahul    # ensure Rahul is seeded
```

### STEP 10 — validate the dataset
```bash
python -m data.validate
```
Writes `data/generated/data_quality_report.{json,md}` (foreign keys, IDs,
dates, amounts, taxonomy codes, ground-truth consistency).

### STEP 11 — run the evaluation
```bash
python -m evaluation.run_evaluation
```
Runs every live dispute through the full pipeline and writes to
`evaluation/results/`: `results.csv`, `classification_results.csv`,
`decision_results.csv`, `confusion_matrix.csv`, `error_cases.csv`,
`summary.json`, `evaluation_report.{json,csv,md}` — including the
counterfactual identity-swap fairness check.

Run the Rahul worked example end-to-end (writes
`evaluation/results/rahul_pipeline_result.json`):
```bash
python -m evaluation.run_rahul
```

### STEP 12 — start the backend
```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```
Health check: http://localhost:8000/api/health

### STEP 13 — start the frontend (new terminal)
```bash
cd frontend
npm run dev
```

### STEP 14 — open the application
http://localhost:5173 — the dashboard opens on the **flagship demo case**:
one click on "Run live resolution" streams Rahul's dispute through all 10
stages over SSE. The case page shows the decision card (outcome, refund,
confidence, score vs threshold), the evidence ledger (source / status /
strength / supports, with the vision panel and missing evidence), the
"Why this decision?" weighted breakdown, the live event stream, the
network-rule inspector, and the three role portals (card member /
merchant / analyst with override + feedback). A REAL/DEMO AI-mode badge
is always visible — the UI never claims a model ran when it did not.
Edge-case launchers on the dashboard: CONFLICT → human review,
FRAUD → integrity escalation (never auto-denied), NORESP → network-rule
override, and five more.

---

## One-command demo

```bash
./scripts/start_demo.sh        # or: make demo
```
Initialises the DB, validates the taxonomy, generates + validates 1,000
disputes (override with `COUNT=10000`), seeds and runs Rahul, then starts
backend and frontend together.

## Freeing the disk space afterwards

```bash
python scripts/clean_models.py             # dry run — shows what would be freed
python scripts/clean_models.py --yes       # delete this project's checkpoints
python scripts/clean_models.py --all --yes # the whole Hugging Face cache
pip uninstall -y torch transformers accelerate sentencepiece   # a further ~3 GB
```
Deleting the weights is safe: the system falls back to DEMO mode and says so
in the UI. `python scripts/fetch_models.py` gets them back.

## Tests

```bash
python -m pytest backend/tests/ -q
```
46 tests: taxonomy preservation, classification, evidence mapping/scoring,
decision bands + conclusive-evidence rule, compliance overrides, integrity
advisory-only guarantee, lifecycle state machine, demo-case regression,
pixel-level vision analysis (same product verifies, different product does
not, blurred photos stay inconclusive, severity scales with visible
fractures), and API smoke tests.

## Docker

```bash
docker compose up --build                 # backend :8000 + frontend :5173
docker compose --profile full up --build  # + Neo4j, PostgreSQL, Kafka
```

## Repository map

```
backend/
  api/app.py            FastAPI app (REST + SSE pipeline events)
  pipeline/             layers 0-9 + orchestrator + shared context
  models/classification BART-MNLI adapter + deterministic fallback (AI_MODE)
  vision/               CLIP verification + BLIP-2 damage adapters (AI_MODE)
  nlp/                  spaCy processing (REAL if installed)
  taxonomy/             Excel-driven registry: internal types + network codes
  lifecycle/            dispute state machine
  workflows/            merchant response, representment, analyst override
  graph/                knowledge graph (memory / Neo4j)
  tests/                pytest suite
config/                 evidence matrix, weights, thresholds, network rules (YAML)
data/generate.py        synthetic data generator (+ demo cases incl. Rahul)
data/validate.py        dataset quality checks
data/generated/         the actual generated dataset (CSV + JSONL + reports)
validation/             taxonomy discrepancy validator + report
evaluation/             full-corpus evaluation + Rahul end-to-end runner
frontend/               React + Vite three-portal UI
```

## Honest model modes

The UI (`/models`) and `/api/meta/models` always report which mode each
component runs in. With `AI_MODE=demo` (default): classification uses a
deterministic weighted-lexicon classifier and vision uses deterministic
adapters — the system never claims BART/CLIP/BLIP-2 ran when they did not.
spaCy runs REAL whenever installed. With `AI_MODE=real` and the ML
requirements installed, the Hugging Face BART-large-MNLI, CLIP ViT-L/14 and
BLIP-2 adapters load instead.
