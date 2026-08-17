"""Hugging Face BART-large-MNLI zero-shot classifier (REAL mode).

Loaded through the Hugging Face Transformers ecosystem exactly as specified:

    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

Classifies the free-text dispute description against the INTERNAL 36-type
taxonomy labels (never directly against raw Amex codes).  Requires
`pip install -r backend/requirements-ml.txt` and network access to the
Hugging Face hub on first run.  If unavailable, the factory falls back to the
DeterministicClassifier and reports mode=demo — the system never claims BART
ran when it did not.
"""
from __future__ import annotations

from backend.models.classification.base import ClassificationModel

CHECKPOINT = "facebook/bart-large-mnli"


class BARTMNLIClassifier(ClassificationModel):
    name = f"BART-large-MNLI ({CHECKPOINT})"
    mode = "real"

    def __init__(self, checkpoint: str = CHECKPOINT, device: int = -1):
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer, pipeline)
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        self.model = AutoModelForSequenceClassification.from_pretrained(checkpoint)
        self.pipe = pipeline(
            "zero-shot-classification",
            model=self.model,
            tokenizer=self.tokenizer,
            device=device,
        )

    def score_labels(self, description, labels):
        if not description.strip():
            return []
        result = self.pipe(
            description,
            candidate_labels=labels,
            multi_label=True,
            hypothesis_template="This dispute is about {}.",
        )
        return list(zip(result["labels"], [float(s) for s in result["scores"]]))


def is_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except Exception:
        return False
