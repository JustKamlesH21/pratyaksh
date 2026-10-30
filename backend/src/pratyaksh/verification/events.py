"""In-process fan-out of Audit Trail events to live Console connections.

publish() is safe to call from worker threads (FastAPI runs sync routes in a thread pool).
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator


class EventHub:
    def __init__(self, max_queue: int = 500):
        self._subs: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = set()
        self._lock = threading.Lock()
        self._max = max_queue

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, queue in subs:
            loop.call_soon_threadsafe(_offer, queue, event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(self._max)
        entry = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._subs.add(entry)
        try:
            yield queue
        finally:
            with self._lock:
                self._subs.discard(entry)


def _offer(queue: asyncio.Queue, event: dict) -> None:
    if queue.full():  # a slow Console drops its oldest event rather than blocking Calls
        queue.get_nowait()
    queue.put_nowait(event)
