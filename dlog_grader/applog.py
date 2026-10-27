"""Small thread-safe logger that always writes inside the project's logs/."""
from __future__ import annotations

import shutil
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

from .paths import LOG_DIR, PROJECT_ROOT


def new_session_log_path() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return LOG_DIR / f"batch_{stamp}.log"


class AppLogger:
    def __init__(
        self,
        path: Path | None = None,
        *,
        mirror_stdout: bool = False,
        callback: Callable[[str, str], None] | None = None,
    ):
        self.path = path or new_session_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()
        self.mirror_stdout = mirror_stdout
        self.callback = callback
        self.closed = False

    def set_callback(self, callback: Callable[[str, str], None] | None) -> None:
        self.callback = callback

    def _write(self, level: str, message: str) -> None:
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {message}"
        with self._lock:
            if self.closed:
                return
            self._fh.write(line + "\n")
            self._fh.flush()
        if self.mirror_stdout:
            print(line, flush=True)
        if self.callback:
            try:
                self.callback(level, message)
            except Exception:
                pass

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warning(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def debug(self, message: str) -> None:
        self._write("DEBUG", message)

    def exception(self, message: str, exc: BaseException | None = None) -> None:
        if exc is not None:
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self._write("ERROR", f"{message}\n{detail.rstrip()}")
        else:
            self._write("ERROR", message)

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self.closed = True
            try:
                self._fh.close()
            except Exception:
                pass
        # Keep a stable path for quick inspection.
        try:
            shutil.copyfile(self.path, LOG_DIR / "latest.log")
        except Exception:
            pass
        if self.mirror_stdout:
            print(f"日志文件：{self.path}", flush=True)


def print_banner(log: AppLogger) -> None:
    log.info("=" * 72)
    log.info("DJI D-Log M 批量调色（Rec.709）")
    log.info(f"项目目录：{PROJECT_ROOT}")
    log.info("=" * 72)
