"""NLP_MODE switch: spacy | simple | auto (spaCy if importable)."""
from functools import lru_cache

from backend.config import settings
from backend.nlp.simple_nlp import SimpleNLP

_warning = None


@lru_cache(maxsize=1)
def get_nlp():
    global _warning
    if settings.nlp_mode in ("spacy", "auto"):
        try:
            from backend.nlp.spacy_nlp import SpacyNLP
            return SpacyNLP()
        except Exception as exc:
            _warning = f"spaCy unavailable ({exc}); using SimpleNLP fallback."
            if settings.nlp_mode == "spacy":
                print(f"[nlp] WARNING: {_warning}")
    return SimpleNLP()


def nlp_info():
    n = get_nlp()
    return {"component": "nlp_parsing", "requested_mode": settings.nlp_mode,
            "model": n.name, "mode": n.mode, "fallback_warning": _warning}
