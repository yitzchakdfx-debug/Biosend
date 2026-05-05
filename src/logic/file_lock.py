"""Single-instance process lock using a PID lock file."""

from __future__ import annotations

import os
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    """Raised when another live process owns the lock file."""


class SingleInstanceLock:
    def __init__(self, lock_path: Path) -> None:
        self._lock_path = Path(lock_path)
        self._fd: int | None = None

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self._fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(self._fd, str(os.getpid()).encode("ascii"))
                return
            except FileExistsError:
                try:
                    existing_text = self._lock_path.read_text(encoding="ascii").strip()
                    existing_pid = int(existing_text)
                except (OSError, ValueError):
                    existing_pid = -1
                if not self._is_pid_alive(existing_pid):
                    try:
                        self._lock_path.unlink()
                        continue
                    except OSError:
                        pass
                raise AlreadyRunningError("Application is already running.")

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self._lock_path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
