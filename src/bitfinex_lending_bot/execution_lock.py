from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ExecutionLockResult:
    acquired: bool
    instance_id: str
    timestamp: str
    status: str
    lock_path: Path


class GlobalExecutionLock:
    DEFAULT_TIMEOUT_SECONDS = 5.0
    DEFAULT_STALE_SECONDS = 30.0
    _thread_state = threading.local()

    def __init__(self, database_path: Path, timeout_seconds: float | None = None, stale_seconds: float | None = None) -> None:
        self.lock_path = Path(str(database_path) + ".execution.lock")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self.DEFAULT_TIMEOUT_SECONDS
        self.stale_seconds = stale_seconds if stale_seconds is not None else self.DEFAULT_STALE_SECONDS
        self.instance_id = f"{os.getpid()}-{uuid.uuid4().hex}"

    @contextmanager
    def acquire(self, timeout_seconds: float | None = None) -> Iterator[ExecutionLockResult]:
        result = self._acquire(timeout_seconds=timeout_seconds)
        try:
            yield result
        finally:
            if result.acquired:
                self._release()

    def _acquire(self, timeout_seconds: float | None = None) -> ExecutionLockResult:
        timeout_seconds = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        state = self._get_state()
        key = str(self.lock_path)
        if key in state:
            state[key]["count"] += 1
            return ExecutionLockResult(
                acquired=True,
                instance_id=self.instance_id,
                timestamp=self._now(),
                status="REENTRANT",
                lock_path=self.lock_path,
            )

        start = time.monotonic()
        while time.monotonic() - start <= timeout_seconds:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = open(self.lock_path, "a+", encoding="utf-8")
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fd.seek(0)
                metadata = {
                    "instance_id": self.instance_id,
                    "timestamp": self._now(),
                    "status": "ACQUIRED",
                }
                fd.truncate(0)
                fd.write(json.dumps(metadata))
                fd.flush()
                os.fsync(fd.fileno())
                state[key] = {"count": 1, "fd": fd}
                return ExecutionLockResult(
                    acquired=True,
                    instance_id=self.instance_id,
                    timestamp=metadata["timestamp"],
                    status="ACQUIRED",
                    lock_path=self.lock_path,
                )
            except BlockingIOError:
                fd.close()
                time.sleep(0.1)
                continue
            except Exception:
                fd.close()
                raise

        return ExecutionLockResult(
            acquired=False,
            instance_id=self.instance_id,
            timestamp=self._now(),
            status="FAILED",
            lock_path=self.lock_path,
        )

    def _release(self) -> None:
        state = self._get_state()
        key = str(self.lock_path)
        guard = state.get(key)
        if guard is None:
            return
        guard["count"] -= 1
        if guard["count"] > 0:
            return
        fd = guard.get("fd")
        if fd is not None:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            finally:
                fd.close()
        del state[key]

    def _get_state(self) -> dict[str, dict[str, object]]:
        if not hasattr(self._thread_state, "locks"):
            self._thread_state.locks = {}
        return self._thread_state.locks

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
