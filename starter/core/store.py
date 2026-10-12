"""The one store: a JSON file, locked with flock and replaced atomically.

snapshot() reads, mutate(fn) is the only way to write, publish(event) appends to the event log
that drives the audit trail and the runs page. Every successful mutate bumps data["version"].
"""

import copy
import fcntl
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")
EMPTY = {"version": 0, "events": []}


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def snapshot(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return copy.deepcopy(EMPTY)

    def mutate(self, fn: Callable[[dict], T]) -> T:
        """Run fn on a copy of the data under an exclusive lock; write only if fn returns."""
        # ponytail: one lock for the whole store; shard by key if writes ever queue.
        with open(self._lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self.snapshot()
            result = fn(data)
            data["version"] = data.get("version", 0) + 1
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".store-")
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            return result

    def publish(self, event: dict) -> dict:
        """Append an event with a sequence number and timestamp; return it as stored."""

        def append(data: dict) -> dict:
            events = data.setdefault("events", [])
            stored = {"seq": len(events) + 1, "ts": time.time(), **event}
            events.append(stored)
            return stored

        return self.mutate(append)
