#!/usr/bin/env python3
"""Reproducible 4K video before/after benchmark for the LUT pipeline.

Run manually on the target machine:
    python tests/benchmark_video.py
"""
from __future__ import annotations

import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dlog_grader.ffmpeg_tools import find_ffmpeg  # noqa: E402
from dlog_grader.paths import child_environment  # noqa: E402

FRAMES = 8 * 30


def ensure_clip(ffmpeg: Path) -> Path:
    bench_dir = PROJECT_ROOT / "test_media" / "bench"
    clip = bench_dir / "bench_4k.mp4"
    if clip.exists() and clip.stat().st_size > 1024 * 1024:
        return clip
    bench_dir.mkdir(parents=True, exist_ok=True)
    base = [
        str(ffmpeg), "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=30:duration=8",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
    ]
    for encoder in (
        ["-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "30M"],
        ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18"],
    ):
        cp = subprocess.run(
            base + encoder + [
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(clip),
            ],
            capture_output=True,
            env=child_environment(),
            cwd=str(PROJECT_ROOT),
            timeout=300,
        )
        if cp.returncode == 0:
            return clip
    raise RuntimeError("无法生成 4K 基准视频")


def run_variant(
    ffmpeg: Path,
    clip: Path,
    lut_path: Path,
    output: Path,
    *,
    hardware_decode: bool,
    interpolation: str,
) -> tuple[float, int]:
    cmd = [str(ffmpeg), "-hide_banner", "-y"]
    if hardware_decode:
        cmd += ["-hwaccel", "auto"]
    cmd += [
        "-i", str(clip),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-vf", f"lut3d=file={lut_path.relative_to(PROJECT_ROOT).as_posix()}:interp={interpolation}",
        "-c:v", "h264_nvenc",
        "-preset", "p5",
        "-rc", "vbr",
        "-cq", "16",
        "-b:v", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-fps_mode", "passthrough",
        "-max_muxing_queue_size", "4096",
        "-progress", "pipe:1",
        "-nostats",
        str(output),
    ]
    output.unlink(missing_ok=True)
    started = time.perf_counter()
    cp = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=child_environment(),
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", errors="replace")[-2000:])
    return time.perf_counter() - started, output.stat().st_size


def main() -> int:
    ffmpeg = find_ffmpeg()
    clip = ensure_clip(ffmpeg)
    temp = PROJECT_ROOT / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    lut_source = PROJECT_ROOT / "luts" / "DJI Air 3S" / "Normalization" / "DJI Air 3s DJI D-Log M to Rec.709.cube"
    lut = temp / "bench_lut.cube"
    shutil.copyfile(lut_source, lut)
    output = temp / "bench_video_ab.mp4"

    run_variant(ffmpeg, clip, lut, output, hardware_decode=True, interpolation="trilinear")
    run_variant(ffmpeg, clip, lut, output, hardware_decode=False, interpolation="tetrahedral")

    before: list[float] = []
    after: list[float] = []
    sizes: dict[str, int] = {}
    for _ in range(3):
        elapsed, size = run_variant(
            ffmpeg, clip, lut, output,
            hardware_decode=True, interpolation="trilinear",
        )
        before.append(elapsed)
        sizes["before"] = size
        elapsed, size = run_variant(
            ffmpeg, clip, lut, output,
            hardware_decode=False, interpolation="tetrahedral",
        )
        after.append(elapsed)
        sizes["after"] = size

    b = statistics.median(before)
    a = statistics.median(after)
    print("environment=Intel Core i9-14900HX / RTX 5080 Laptop / FFmpeg 6.1.1")
    print(f"material={clip.name} 3840x2160 30fps 8s")
    print(f"before={b:.3f}s effective_fps={FRAMES / b:.2f} bytes={sizes['before']}")
    print(f"after={a:.3f}s effective_fps={FRAMES / a:.2f} bytes={sizes['after']}")
    print(f"improvement={(b - a) / b * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
