"""Async task queue for evidence-gathering & notifications.

QUEUE_MODE=memory -> in-process asyncio-friendly queue (default, zero infra)
QUEUE_MODE=kafka  -> real Kafka producer via confluent-kafka/kafka-python
                     (docker compose --profile kafka up). Each dispute is an
                     independent pipeline; Kafka partitioning by dispute_id
                     gives horizontal scaling to 10K+ concurrent disputes.
"""
from __future__ import annotations

import json
import queue as _q
from functools import lru_cache

from backend.config import settings


class QueueBackend:
    name = "base"
    mode = "memory"

    def publish(self, topic: str, key: str, message: dict): ...


class MemoryQueue(QueueBackend):
    name = "MemoryQueue (in-process)"
    mode = "memory"

    def __init__(self):
        self.topics: dict[str, _q.Queue] = {}

    def publish(self, topic, key, message):
        self.topics.setdefault(topic, _q.Queue()).put((key, message))

    def drain(self, topic):
        out, q = [], self.topics.get(topic)
        while q and not q.empty():
            out.append(q.get())
        return out


class KafkaQueue(QueueBackend):
    name = "Kafka"
    mode = "kafka"

    def __init__(self, bootstrap: str):
        from kafka import KafkaProducer  # pip install kafka-python
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            key_serializer=lambda k: k.encode(),
            value_serializer=lambda v: json.dumps(v, default=str).encode())

    def publish(self, topic, key, message):
        self.producer.send(topic, key=key, value=message)


_warning = None


@lru_cache(maxsize=1)
def get_queue() -> QueueBackend:
    global _warning
    if settings.queue_mode == "kafka":
        try:
            return KafkaQueue(settings.kafka_bootstrap)
        except Exception as exc:
            _warning = f"Kafka unavailable ({exc}); using MemoryQueue."
            print(f"[queue] WARNING: {_warning}")
    return MemoryQueue()


def queue_info():
    q = get_queue()
    return {"component": "message_queue", "requested_mode": settings.queue_mode,
            "model": q.name, "mode": q.mode, "fallback_warning": _warning}
