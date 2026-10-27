"""Anonymous crash/local diagnostics with optional explicit upload endpoint."""
from __future__ import annotations

import json
import platform
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from urllib import request

from . import __version__
from .paths import LOG_DIR, PROJECT_ROOT

DIAG_DIR = LOG_DIR / "diagnostics"


def _sanitize(text: str) -> str:
    text = text.replace(str(PROJECT_ROOT), "<project>")
    text = text.replace(chr(92), "/")
    text = re.sub(r"[A-Za-z]:/Users/[^/\s]+", "<user>", text)
    text = re.sub(r"/home/[^/\s]+", "<user>", text)
    return text[-8000:]

def record_exception(
    exc_type,
    exc,
    tb,
    *,
    enabled: bool = True,
    endpoint: str = "",
) -> Path | None:
    if not enabled:
        return None
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = DIAG_DIR / f"crash_{stamp}.json"
    stack = []
    cursor = tb
    while cursor is not None:
        code = cursor.tb_frame.f_code
        stack.append({
            "file": _sanitize(str(code.co_filename)),
            "line": int(cursor.tb_lineno),
            "function": str(code.co_name),
        })
        cursor = cursor.tb_next
    payload = {
        "version": __version__,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "error_type": getattr(exc_type, "__name__", str(exc_type)),
        "error_message": _sanitize(str(exc)),
        "stack": stack,
        "anonymous": True,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if endpoint:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = request.Request(
                endpoint, data=data,
                headers={"Content-Type": "application/json", "User-Agent": f"DJI-DLogM-Grader/{__version__}"},
                method="POST",
            )
            with request.urlopen(req, timeout=4) as resp:
                resp.read(1024)
        except Exception:
            pass
    return path


def install_exception_hooks(enabled: bool = True, endpoint: str = "") -> None:
    def _hook(exc_type, exc, tb):
        try:
            record_exception(exc_type, exc, tb, enabled=enabled, endpoint=endpoint)
        finally:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
