"""Regex/heuristic NLP fallback (DEMO mode) used when spaCy or its English
model is unavailable. Same NLPFeatures contract."""
import re

from backend.nlp.base import NLPFeatures, NLPProcessor

_AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|\$|usd|eur|€)\s?([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
_DATE_RE = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}"
                      r"|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", re.I)
_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_NEG = {"not", "no", "never", "nothing", "without", "none", "didn't", "won't",
        "doesn't", "hasn't", "wasn't", "isn't", "can't", "cannot"}


class SimpleNLP(NLPProcessor):
    name = "SimpleNLP (regex heuristics)"
    mode = "demo"

    def process(self, text: str) -> NLPFeatures:
        text = (text or "").strip()
        tokens = re.findall(r"[a-zA-Z']+|\d+", text.lower())
        return NLPFeatures(
            clean_text=" ".join(text.split()),
            sentences=[s.strip() for s in _SENT_RE.split(text) if s.strip()],
            entities=[],
            lemmas=tokens,
            amounts=[m.group(0) for m in _AMOUNT_RE.finditer(text)],
            dates=[m.group(0) for m in _DATE_RE.finditer(text)],
            negations=sum(1 for t in tokens if t in _NEG),
            token_count=len(tokens),
            model=self.name, mode=self.mode,
        )
