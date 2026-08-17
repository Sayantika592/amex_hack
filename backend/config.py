"""Runtime configuration.

Every heavyweight dependency (Hugging Face BART-large-MNLI, CLIP, BLIP-2,
Neo4j, PostgreSQL, Kafka) has a mode switch with a fully-working local
fallback so the system runs anywhere.  The active mode of every model is
reported through /api/meta/models and shown in the UI — the system never
claims a real model ran when the deterministic fallback was used.
"""
import os
from dataclasses import dataclass, field, asdict

from backend.paths import DEFAULT_SQLITE


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower()


@dataclass
class Settings:
    # "real"  -> load Hugging Face BART-large-MNLI / CLIP / BLIP-2 weights
    # "demo"  -> deterministic, fully-explainable fallbacks (no downloads)
    ai_mode: str = field(default_factory=lambda: _env("AI_MODE", "demo"))
    # Damage-assessment checkpoint for AI_MODE=real.  BLIP-2 OPT-2.7B needs
    # ~8 GB of VRAM in fp16; on smaller cards set VISION_VQA_MODEL to
    # "Salesforce/blip-vqa-base" (~1.5 GB), which answers the same visual
    # questions and fits comfortably on a 6 GB laptop GPU.
    vision_vqa_model: str = field(default_factory=lambda: os.environ.get(
        "VISION_VQA_MODEL", "Salesforce/blip2-opt-2.7b").strip())
    # "spacy" | "simple" | "auto" (auto = spaCy if importable, else simple)
    nlp_mode: str = field(default_factory=lambda: _env("NLP_MODE", "auto"))
    # "memory" | "neo4j"
    graph_mode: str = field(default_factory=lambda: _env("GRAPH_MODE", "memory"))
    # "memory" | "kafka"
    queue_mode: str = field(default_factory=lambda: _env("QUEUE_MODE", "memory"))
    database_url: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE}"))
    neo4j_uri: str = field(default_factory=lambda: os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.environ.get("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.environ.get("NEO4J_PASSWORD", "password"))
    kafka_bootstrap: str = field(default_factory=lambda: os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092"))
    default_network: str = field(default_factory=lambda: _env("DEFAULT_NETWORK", "amex"))
    api_host: str = field(default_factory=lambda: os.environ.get("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.environ.get("API_PORT", "8000")))
    random_seed: int = field(default_factory=lambda: int(os.environ.get("RANDOM_SEED", "42")))

    def as_dict(self):
        d = asdict(self)
        d.pop("neo4j_password", None)
        return d


settings = Settings()
