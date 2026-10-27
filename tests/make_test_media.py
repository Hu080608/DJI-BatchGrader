#!/usr/bin/env python3
"""Create project-local synthetic test media (one photo + one short video + nested files)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["PYTHONUTF8"] = "1"

from dlog_grader.ffmpeg_tools import find_ffmpeg  # noqa: E402
from dlog_grader.paths import PROJECT_ROOT as ROOT, child_environment, configure_environment  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def make_photo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = 720, 1280
    y, x = np.mgrid[0:h, 0:w]
    # A deliberately flat, low-contrast "log-like" pattern so the LUT change is obvious.
    r = 18 + (x / max(1, w - 1)) * 120 + 10 * np.sin(y / 38.0)
    g = 16 + (y / max(1, h - 1)) * 110 + 8 * np.sin(x / 44.0)
    b = 20 + ((x + y) / max(1, w + h - 2)) * 105
    arr = np.stack([r, g, b], axis=-1)
    arr[:, :, 0] += (x > w * 0.68) * 80
    arr[:, :, 1] += (x < w * 0.30) * 60
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(path, quality=94)


def make_alpha_photo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = 480, 640
    y, x = np.mgrid[0:h, 0:w]
    arr = np.stack(
        [40 + x * 160 // w, 30 + y * 160 // h, 55 + (x + y) * 140 // (w + h)], axis=-1
    ).astype(np.uint8)
    alpha = np.clip(255 * (1.0 - y / h), 0, 255).astype(np.uint8)
    rgba = np.dstack([arr, alpha])
    Image.fromarray(rgba, "RGBA").save(path)


def make_tiff(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.zeros((360, 640, 3), dtype=np.uint8)
    arr[..., 0] = np.linspace(10, 220, 640, dtype=np.uint8)[None, :]
    arr[..., 1] = np.linspace(10, 200, 360, dtype=np.uint8)[:, None]
    arr[..., 2] = 45
    Image.fromarray(arr, "RGB").save(path, compression="tiff_lzw")


def make_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    cmd = [
        str(ffmpeg), "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", "-t", "3", str(path),
    ]
    cp = subprocess.run(
        cmd, capture_output=True, env=child_environment(), cwd=str(ROOT), timeout=120
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", errors="replace"))


def main() -> int:
    configure_environment()
    base = ROOT / "test_media" / "input"
    base.mkdir(parents=True, exist_ok=True)
    make_photo(base / "sample_photo.jpg")
    make_photo(base / "sample_photo_copy.jpg")
    make_alpha_photo(base / "nested" / "sample_alpha.png")
    make_tiff(base / "nested" / "sample_scan.tif")
    make_video(base / "sample_clip.mp4")
    raw_source = ROOT / "test_media" / "raw" / "sample_blackmagic.dng"
    if raw_source.exists():
        shutil.copy2(raw_source, base / "sample_blackmagic.dng")
    else:
        print("警告：未找到 RAW 测试素材 test_media/raw/sample_blackmagic.dng", file=sys.stderr)
    (base / "sample_clip.srt").write_text("1  00:00:00,000 --> 00:00:02,000  DJI D-Log M test clip", encoding="utf-8")
    (base / "unsupported_notes.txt").write_text(
        "Unsupported test file. The app must skip this and log it.\n", encoding="utf-8"
    )
    print(f"测试素材已生成：{base}")
    for path in sorted(base.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
