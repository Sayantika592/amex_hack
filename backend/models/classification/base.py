"""ClassificationModel interface.

Layer 1 answers exactly one question — "what type of dispute is this?" — and
outputs internal category code(s) + confidence.  It never determines evidence
requirements (Layer 2) and never decides the outcome (Layer 6): the model does
UNDERSTANDING, the rule engine does DECISION.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ClassificationResult:
    status: str                       # auto_classified | needs_review | unclassified
    primary_code: str | None
    primary_label: str | None
    confidence: float
    categories: list = field(default_factory=list)   # [{code,label,confidence}]
    override: bool = False
    override_reason: str | None = None
    model_name: str = ""
    mode: str = ""                    # real | demo — the UI must show this

    def as_dict(self):
        return {
            "status": self.status,
            "primary_code": self.primary_code,
            "primary_label": self.primary_label,
            "confidence": round(self.confidence, 3),
            "categories": self.categories,
            "override": self.override,
            "override_reason": self.override_reason,
            "model": self.model_name,
            "mode": self.mode,
        }


# Confidence routing thresholds (TDD §4)
HIGH = 0.65        # auto_classified
MEDIUM = 0.45      # needs_review
MULTI = 0.35       # secondary categories above this -> multi-category candidate
OVERRIDE_CONF = 0.75


class ClassificationModel(ABC):
    name: str = "base"
    mode: str = "demo"

    @abstractmethod
    def score_labels(self, description: str, labels: list[str]) -> list[tuple[str, float]]:
        """Return [(label, score)] sorted desc.  Scores in [0,1]."""

    def classify(self, description: str, labels: list[str],
                 label_to_code, user_code: str | None = None) -> ClassificationResult:
        ranked = self.score_labels(description or "", labels)
        if not ranked:
            return ClassificationResult("unclassified", None, None, 0.0,
                                        model_name=self.name, mode=self.mode)
        top_label, top_score = ranked[0]
        active = [{"code": label_to_code(l), "label": l, "confidence": round(s, 3)}
                  for l, s in ranked if s > MULTI]

        override, override_reason = False, None
        mapped = label_to_code(top_label)
        if user_code and top_score > OVERRIDE_CONF and mapped and mapped != user_code:
            override = True
            override_reason = (f"Description suggests {mapped} ({top_label}), "
                               f"not the selected {user_code}")

        if top_score >= HIGH:
            status = "auto_classified"
        elif top_score >= MEDIUM:
            status = "needs_review"
        else:
            status = "unclassified"

        return ClassificationResult(
            status=status,
            primary_code=mapped if top_score >= MEDIUM else None,
            primary_label=top_label if top_score >= MEDIUM else None,
            confidence=top_score,
            categories=active,
            override=override,
            override_reason=override_reason,
            model_name=self.name,
            mode=self.mode,
        )
