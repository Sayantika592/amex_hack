"""NLP preprocessor interface. spaCy handles preprocessing, sentence
segmentation, entity extraction and normalization; classification itself is
BART-large-MNLI (or the deterministic fallback)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NLPFeatures:
    clean_text: str
    sentences: list = field(default_factory=list)
    entities: list = field(default_factory=list)      # [{text,label}]
    lemmas: list = field(default_factory=list)
    amounts: list = field(default_factory=list)
    dates: list = field(default_factory=list)
    negations: int = 0
    token_count: int = 0
    model: str = ""
    mode: str = ""

    def as_dict(self):
        return {
            "clean_text": self.clean_text, "sentences": self.sentences,
            "entities": self.entities, "amounts": self.amounts,
            "dates": self.dates, "negations": self.negations,
            "token_count": self.token_count, "model": self.model, "mode": self.mode,
        }


class NLPProcessor(ABC):
    name = "base"
    mode = "demo"

    @abstractmethod
    def process(self, text: str) -> NLPFeatures: ...
