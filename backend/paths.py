"""Central path registry. Every module resolves files through here so the
repo can be relocated without breaking anything."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
CONFIG_DIR = REPO_ROOT / "config"
TAXONOMY_XLSX = CONFIG_DIR / "taxonomy_source" / "Dispute_codes.xlsx"
GENERATED_CONFIG_DIR = CONFIG_DIR / "generated"
DATA_DIR = REPO_ROOT / "data"
GENERATED_DATA_DIR = DATA_DIR / "generated"
EVAL_DIR = REPO_ROOT / "evaluation"
EVAL_RESULTS_DIR = EVAL_DIR / "results"
VALIDATION_DIR = REPO_ROOT / "validation"
VAR_DIR = REPO_ROOT / "var"
DEFAULT_SQLITE = VAR_DIR / "dispute.db"

for _d in (GENERATED_CONFIG_DIR, GENERATED_DATA_DIR, EVAL_RESULTS_DIR, VAR_DIR):
    _d.mkdir(parents=True, exist_ok=True)
