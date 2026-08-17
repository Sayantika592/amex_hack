"""spaCy NLP processor (REAL mode when en_core_web_sm is installed).

Responsibilities per the design brief: text preprocessing, sentence
segmentation, entity extraction, normalization, structured NLP features.
"""
import re

from backend.nlp.base import NLPFeatures, NLPProcessor

_AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|\$|usd|eur|€)\s?([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)
_NEG = {"not", "no", "never", "n't", "nothing", "without", "none"}


class SpacyNLP(NLPProcessor):
    name = "spaCy en_core_web_sm"
    mode = "real"

    def __init__(self):
        import spacy
        self.nlp = spacy.load("en_core_web_sm")

    def process(self, text: str) -> NLPFeatures:
        text = (text or "").strip()
        doc = self.nlp(text)
        entities = [{"text": e.text, "label": e.label_} for e in doc.ents]
        return NLPFeatures(
            clean_text=" ".join(text.split()),
            sentences=[s.text.strip() for s in doc.sents],
            entities=entities,
            lemmas=[t.lemma_.lower() for t in doc if not t.is_punct and not t.is_space],
            amounts=[m.group(0) for m in _AMOUNT_RE.finditer(text)],
            dates=[e["text"] for e in entities if e["label"] == "DATE"],
            negations=sum(1 for t in doc if t.lower_ in _NEG or t.dep_ == "neg"),
            token_count=len(doc),
            model=self.name, mode=self.mode,
        )


def is_available() -> bool:
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False
