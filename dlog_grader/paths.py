"""Project-local paths and runtime environment isolation.

Every file the application creates (logs, caches, temporary files, outputs by
default) is rooted at PROJECT_ROOT.  Third-party libraries are also told to use
the project cache/temp directories via environment variables.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if getattr(sys, "frozen", False):
    # In the PyInstaller onedir build, bundled modules live under _internal/;
    # user data (luts, config, logs, temp, output) must stay next to the .exe.
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
LUT_DIR = PROJECT_ROOT / "luts"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORT_DIR = PROJECT_ROOT / "reports"
LOG_DIR = PROJECT_ROOT / "logs"
TEMP_DIR = PROJECT_ROOT / "temp"
CACHE_DIR = PROJECT_ROOT / ".cache"
UPDATES_DIR = PROJECT_ROOT / "updates"
LICENSE_DIR = PROJECT_ROOT / "license"
LICENSE_FILE = LICENSE_DIR / "license.json"
TOOLS_DIR = PROJECT_ROOT / "tools"

DEFAULT_LUT_RELATIVE = "luts/DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube"
DEFAULT_LUT_NAME = "DJI Air 3s DJI D-Log M to Rec.709.cube"
DEFAULT_LUT_PATH = PROJECT_ROOT / DEFAULT_LUT_RELATIVE
SETTINGS_PATH = CONFIG_DIR / "settings.json"
QUEUE_STATE_PATH = CONFIG_DIR / "queue_state.json"


def ensure_runtime_dirs() -> None:
    """Create all project-local runtime directories if necessary."""
    for path in (CONFIG_DIR, LUT_DIR, OUTPUT_DIR, REPORT_DIR, LOG_DIR, TEMP_DIR, CACHE_DIR, UPDATES_DIR, LICENSE_DIR, TOOLS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def configure_environment() -> None:
    """Redirect common caches and temporary files into this project.

    This function is intentionally called as early as possible by main.py and
    by all entry points.  It affects child processes too because environment
    variables are inherited.
    """
    ensure_runtime_dirs()
    # Python bytecode caches
    os.environ["PYTHONPYCACHEPREFIX"] = str(CACHE_DIR / "pycache")
    sys.pycache_prefix = str(CACHE_DIR / "pycache")
    # pip / Python package caches
    os.environ["PIP_CACHE_DIR"] = str(CACHE_DIR / "pip")
    # Temporary files used by this process and by ffmpeg
    os.environ["TEMP"] = str(TEMP_DIR)
    os.environ["TMP"] = str(TEMP_DIR)
    os.environ["TMPDIR"] = str(TEMP_DIR)
    try:
        tempfile.tempdir = str(TEMP_DIR)
    except Exception:
        pass
    # Common third-party cache locations
    os.environ["XDG_CACHE_HOME"] = str(CACHE_DIR)
    os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
    os.environ["MPLCONFIGDIR"] = str(CACHE_DIR / "matplotlib")
    os.environ["NUMBA_CACHE_DIR"] = str(CACHE_DIR / "numba")
    # Keep the working directory deterministic for ffmpeg relative paths.
    try:
        os.chdir(PROJECT_ROOT)
    except OSError:
        pass


def project_path(value: str | os.PathLike[str]) -> Path:
    """Resolve a config/CLI path relative to the project root."""
    p = Path(value)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


def child_environment() -> dict[str, str]:
    """Environment passed to ffmpeg/other child processes."""
    env = os.environ.copy()
    env["TEMP"] = str(TEMP_DIR)
    env["TMP"] = str(TEMP_DIR)
    env["TMPDIR"] = str(TEMP_DIR)
    return env
