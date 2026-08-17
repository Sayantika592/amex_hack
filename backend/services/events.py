"""In-process pub/sub used to stream live pipeline stage events to the
frontend over SSE (Server-Sent Events). The frontend animates the ACTUAL
backend stages — never fake frontend-only animations."""
from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import defaultdict


class EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[dict]] = defaultdict(list)

    def publish(self, channel: str, event: dict):
        event = {**event, "ts": time.time()}
        with self._lock:
            self._history[channel].append(event)
            self._history[channel] = self._history[channel][-200:]
            queues = list(self._subscribers.get(channel, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers[channel].append(q)
            for e in self._history.get(channel, []):
                q.put_nowait(e)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        with self._lock:
            if q in self._subscribers.get(channel, []):
                self._subscribers[channel].remove(q)

    @staticmethod
    def sse_format(event: dict) -> str:
        return f"data: {json.dumps(event, default=str)}\n\n"


bus = EventBus()
