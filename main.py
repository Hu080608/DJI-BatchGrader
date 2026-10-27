#!/usr/bin/env python3
"""GUI entry point. This application intentionally provides no CLI interface."""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Onedir PyInstaller build: the executable directory is the portable project root.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
# Redirect caches/temp before importing numpy/Pillow/Tkinter or spawning FFmpeg.
CACHE = PROJECT_ROOT / ".cache"
TEMP = PROJECT_ROOT / "temp"
for folder in (CACHE / "pip", CACHE / "pycache", TEMP, PROJECT_ROOT / "logs",
               PROJECT_ROOT / "output", PROJECT_ROOT / "luts", PROJECT_ROOT / "config"):
    folder.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(CACHE / "pycache"))
os.environ.setdefault("PIP_CACHE_DIR", str(CACHE / "pip"))
os.environ["TEMP"] = str(TEMP)
os.environ["TMP"] = str(TEMP)
os.environ["TMPDIR"] = str(TEMP)
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE))
os.environ.setdefault("HF_HOME", str(CACHE / "huggingface"))
os.environ.setdefault("MPLCONFIGDIR", str(CACHE / "matplotlib"))
sys.pycache_prefix = str(CACHE / "pycache")
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dlog_grader.gui import launch_gui  # noqa: E402

if __name__ == "__main__":
    launch_gui()
