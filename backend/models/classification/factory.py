"""AI_MODE switch for classification.

  AI_MODE=real -> Hugging Face BART-large-MNLI (falls back with a loud
                  warning if transformers/weights are unavailable)
  AI_MODE=demo -> DeterministicClassifier

The active model + mode is exposed via /api/meta/models and shown in the UI.
The system NEVER claims BART ran when the deterministic fallback was used.
"""
from functools import lru_cache

from backend.config import settings
from backend.models.classification.deterministic import DeterministicClassifier

_load_warning = None


@lru_cache(maxsize=1)
def get_classifier():
    global _load_warning
    if settings.ai_mode == "real":
        try:
            from backend.models.classification.bart_mnli import BARTMNLIClassifier
            return BARTMNLIClassifier()
        except Exception as exc:  # transformers missing / hub unreachable
            _load_warning = (f"AI_MODE=real requested but BART-large-MNLI could "
                             f"not be loaded ({exc}); running DeterministicClassifier "
                             f"in DEMO mode instead.")
            print(f"[classification] WARNING: {_load_warning}")
    return DeterministicClassifier()


def classifier_info():
    clf = get_classifier()
    return {"component": "dispute_classification",
            "requested_mode": settings.ai_mode,
            "model": clf.name, "mode": clf.mode,
            "fallback_warning": _load_warning}
