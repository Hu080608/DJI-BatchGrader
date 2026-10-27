"""Simple recursive folder watcher for auto-enqueueing new media."""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from .processor import DEFAULT_SCOPE, IGNORED_EXTS, SUPPORTED_EXTS, is_file_in_scope


class FolderWatcher:
    def __init__(
        self,
        folder: Path,
        *,
        recursive: bool = True,
        interval_seconds: float = 2.0,
        output_queue: "queue.Queue[list[Path]]",
        exclude_dirs: list[Path] | None = None,
        scope: str = DEFAULT_SCOPE,
    ):
        self.folder = folder.resolve()
        self.recursive = recursive
        self.interval_seconds = max(0.5, float(interval_seconds))
        self.output_queue = output_queue
        self.exclude_dirs = [p.resolve() for p in (exclude_dirs or [])]
        self.scope = scope
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: dict[Path, tuple[int, int]] = {}

    def _iter_files(self):
        if self.recursive:
            iterator = self.folder.rglob("*")
        else:
            iterator = (p for p in self.folder.iterdir())
        for path in iterator:
            try:
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if any(resolved.is_relative_to(ex) for ex in self.exclude_dirs):
                    continue
                ext = resolved.suffix.lower()
                if ext in IGNORED_EXTS or ext not in SUPPORTED_EXTS:
                    continue
                if not is_file_in_scope(resolved, self.scope):
                    continue
                st = resolved.stat()
                yield resolved, (st.st_size, int(st.st_mtime))
            except OSError:
                continue

    def _scan(self, initial: bool = False) -> list[Path]:
        new_files: list[Path] = []
        for path, fingerprint in self._iter_files():
            previous = self._seen.get(path)
            self._seen[path] = fingerprint
            if not initial and previous != fingerprint:
                new_files.append(path)
        return new_files

    def _run(self) -> None:
        self._scan(initial=True)
        while not self._stop.wait(self.interval_seconds):
            new_files = self._scan(initial=False)
            if new_files:
                self.output_queue.put(new_files)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="media-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
