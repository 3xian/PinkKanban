"""Coalesced board invalidations for the documented single-process deployment."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from threading import Lock

PENDING_BOARDS = "pending_board_changes"


class BoardEvents:
    def __init__(self):
        self._lock = Lock()
        self._listeners: dict[int, set[tuple]] = {}

    @contextmanager
    def subscribe(self, project_id: int):
        queue = asyncio.Queue(maxsize=1)
        listener = (asyncio.get_running_loop(), queue)
        with self._lock:
            self._listeners.setdefault(project_id, set()).add(listener)
        try:
            yield queue
        finally:
            with self._lock:
                listeners = self._listeners[project_id]
                listeners.discard(listener)
                if not listeners:
                    del self._listeners[project_id]

    def publish(self, project_ids):
        with self._lock:
            listeners = {listener for project_id in project_ids for listener in self._listeners.get(project_id, ())}
        for loop, queue in listeners:
            def signal(queue=queue):
                if queue.empty():
                    queue.put_nowait(None)
            try:
                loop.call_soon_threadsafe(signal)
            except RuntimeError:
                # A disconnected client's event loop may already have stopped.
                pass


board_events = BoardEvents()


def board_changed(db, project_id: int):
    db.info.setdefault(PENDING_BOARDS, set()).add(project_id)
