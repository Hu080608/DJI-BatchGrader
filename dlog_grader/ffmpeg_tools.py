"""FFmpeg discovery, media probing, and video transcoding."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .encoders import EncoderChoice
from .formats import OutputProfile
from .lut import CubeLUT
from .paths import PROJECT_ROOT, TEMP_DIR, TOOLS_DIR, child_environment


class FFmpegError(RuntimeError):
    pass


class FFmpegNotFoundError(FFmpegError):
    pass


class FFmpegCancelled(FFmpegError):
    pass


def find_ffmpeg() -> Path:
    """Find a project-bundled ffmpeg first, then fall back to PATH."""
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.append(TOOLS_DIR / "ffmpeg.exe")
    candidates.append(TOOLS_DIR / "ffmpeg")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    found = shutil.which("ffmpeg")
    if found:
        return Path(found).resolve()
    raise FFmpegNotFoundError(
        "找不到 FFmpeg。请确认项目内存在 tools/ffmpeg.exe，"
        "或把 ffmpeg 加入 PATH。所有路径均应位于本项目内。"
    )


def ffmpeg_version(ffmpeg: Path) -> str:
    try:
        cp = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-version"],
            capture_output=True,
            timeout=20,
            env=child_environment(),
            cwd=str(PROJECT_ROOT),
            **_ffmpeg_spawn_kwargs(),
        )
        text = (cp.stdout or cp.stderr).decode("utf-8", errors="replace")
        return text.splitlines()[0] if text else "unknown"
    except Exception as exc:
        raise FFmpegError(f"无法运行 FFmpeg：{ffmpeg}\n{exc}") from exc


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_SIZE_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?Audio:")
_VIDEO_CODEC_RE = re.compile(r"Video:\s*([^\s,]+)")
_PIX_FMT_RE = re.compile(r"Video:.*?,\s*([A-Za-z0-9_]+)(?:\([^)]*\))?(?:,|$)")
_AUDIO_CODEC_RE = re.compile(r"Audio:\s*([^\s,]+)")
_SUBTITLE_RE = re.compile(r"Stream #\d+:\d+.*?Subtitle:")
_ROTATION_RE = re.compile(r"rotate\s*:\s*(-?\d+)")


def _parse_duration(text: str) -> float | None:
    m = _DURATION_RE.search(text)
    if not m:
        return None
    h, minute, sec = m.groups()
    return int(h) * 3600 + int(minute) * 60 + float(sec)


def probe_media(ffmpeg: Path, path: Path) -> dict:
    """Return stream metadata from ffmpeg's banner without requiring ffprobe."""
    cmd = [str(ffmpeg), "-hide_banner", "-i", str(path)]
    cp = subprocess.run(
        cmd, capture_output=True, timeout=60,
        env=child_environment(), cwd=str(PROJECT_ROOT),
        **_ffmpeg_spawn_kwargs(),
    )
    text = (cp.stderr or b"").decode("utf-8", errors="replace")
    if not text:
        text = (cp.stdout or b"").decode("utf-8", errors="replace")
    duration = _parse_duration(text)
    width = height = None
    fps = None
    video_codec = None
    pix_fmt = None
    audio_codecs: list[str] = []
    for line in text.splitlines():
        if "Video:" in line and width is None:
            sm = _VIDEO_SIZE_RE.search(line)
            if sm:
                width, height = int(sm.group(1)), int(sm.group(2))
            fm = _FPS_RE.search(line)
            if fm:
                fps = float(fm.group(1))
            cm = _VIDEO_CODEC_RE.search(line)
            if cm:
                video_codec = cm.group(1)
            pm = _PIX_FMT_RE.search(line)
            if pm:
                pix_fmt = pm.group(1)
        elif "Audio:" in line:
            am = _AUDIO_CODEC_RE.search(line)
            if am:
                audio_codecs.append(am.group(1))
    rotation_match = _ROTATION_RE.search(text)
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "video_codec": video_codec,
        "pix_fmt": pix_fmt,
        "audio_codecs": audio_codecs,
        "has_audio": bool(audio_codecs),
        "has_subtitles": bool(_SUBTITLE_RE.search(text)),
        "rotation": int(rotation_match.group(1)) if rotation_match else 0,
        "raw": text,
    }


def _tail(path: Path, max_chars: int = 5000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[-max_chars:]


def _ffmpeg_spawn_kwargs() -> dict:
    kw: dict = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _audio_args(mode: str, audio_bitrate: str) -> list[str]:
    if mode == "copy":
        return ["-c:a", "copy"]
    if mode == "aac":
        return ["-c:a", "aac", "-b:a", str(audio_bitrate)]
    if mode.startswith("pcm_"):
        return ["-c:a", mode]
    return ["-c:a", "aac", "-b:a", str(audio_bitrate)]


def build_video_command(
    *,
    ffmpeg: Path,
    input_path: Path,
    output_path: Path,
    filter_graph: str,
    profile: OutputProfile,
    encoder_name: str,
    audio_mode: str,
    crf: int,
    preset: str,
    audio_bitrate: str,
    hardware_bitrate: str,
    hardware_decode: bool = False,
) -> list[str]:
    cmd = [
        str(ffmpeg), "-hide_banner", "-y",
    ]
    if hardware_decode:
        cmd += ["-hwaccel", "auto"]
    cmd += [
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-vf", filter_graph,
        "-map_metadata", "0",
        "-map_chapters", "0",
        "-sn", "-dn",
        "-threads", "0",
        "-c:v", encoder_name,
    ]
    if encoder_name == "libx264" or encoder_name == "libx265":
        cmd += ["-preset", str(preset), "-crf", str(int(crf))]
        if encoder_name == "libx265":
            cmd += ["-x265-params", "log-level=error"]
    elif encoder_name.endswith("_nvenc"):
        cmd += ["-preset", "p5", "-rc", "vbr", "-cq", str(int(crf)), "-b:v", "0"]
    elif encoder_name.endswith("_qsv"):
        cmd += ["-preset", "balanced", "-b:v", str(hardware_bitrate)]
    elif encoder_name.endswith("_amf"):
        cmd += ["-quality", "quality", "-b:v", str(hardware_bitrate)]
    elif encoder_name == "prores_ks":
        cmd += ["-profile:v", str(profile.prores_profile or 3), "-vendor", "apl0"]
    else:
        cmd += ["-preset", str(preset), "-crf", str(int(crf))]

    cmd += [
        "-pix_fmt", profile.pixel_format,
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-color_range", "tv",
    ]
    if profile.video_tag:
        cmd += ["-tag:v", profile.video_tag]
    cmd += _audio_args(audio_mode, audio_bitrate)
    cmd += [
        "-movflags", "+faststart",
        "-fps_mode", "passthrough",
        "-max_muxing_queue_size", "4096",
        "-progress", "pipe:1",
        "-nostats",
        str(output_path),
    ]
    return cmd


def _audio_copy_compatible(profile: OutputProfile, codecs: list[str] | None) -> bool:
    if not codecs:
        return False
    normalized = [str(c).lower() for c in codecs]
    if profile.container == "mp4":
        supported = {"aac", "alac", "mp3"}
    else:
        supported = {"aac", "alac", "mp3", "ac3", "eac3"}
    for codec in normalized:
        if codec.startswith("pcm_") and profile.container == "mov":
            continue
        if codec not in supported:
            return False
    return True


def _attempt_plan(
    profile: OutputProfile,
    encoder: EncoderChoice,
    audio_policy: str,
    source_audio_codecs: list[str] | None = None,
    hardware_decode: bool = False,
) -> list[tuple[str, str, bool]]:
    can_copy = audio_policy != "aac" and _audio_copy_compatible(profile, source_audio_codecs)
    audio_modes = ["copy", profile.audio_fallback] if can_copy else [profile.audio_fallback]
    plan: list[tuple[str, str, bool]] = []
    if encoder.hardware:
        for mode in audio_modes:
            if hardware_decode:
                plan.append((encoder.name, mode, True))
            plan.append((encoder.name, mode, False))
    for mode in audio_modes:
        plan.append((profile.software_encoder, mode, False))
    # De-duplicate while preserving order.
    unique: list[tuple[str, str, bool]] = []
    for item in plan:
        if item not in unique:
            unique.append(item)
    return unique


def _run_ffmpeg_attempt(
    cmd: list[str],
    *,
    output_path: Path,
    stderr_path: Path,
    duration: float | None,
    progress_callback: Callable[[float], None] | None,
    cancel_callback: Callable[[], bool] | None,
) -> tuple[int, bool]:
    with stderr_path.open("w", encoding="utf-8", errors="replace") as err_file:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=err_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_environment(),
            cwd=str(PROJECT_ROOT),
            **_ffmpeg_spawn_kwargs(),
        )
        cancelled = False
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if cancel_callback and cancel_callback():
                    cancelled = True
                    proc.terminate()
                    break
                if line.startswith("out_time_us=") and duration and duration > 0:
                    try:
                        us = int(line.split("=", 1)[1])
                        frac = max(0.0, min(1.0, (us / 1_000_000.0) / duration))
                        if progress_callback:
                            progress_callback(frac)
                    except (ValueError, ZeroDivisionError):
                        pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
    return int(proc.returncode or 0), cancelled


def transcode_video(
    *,
    ffmpeg: Path,
    input_path: Path,
    output_path: Path,
    lut_path: Path,
    job_temp_dir: Path,
    duration: float | None,
    profile: OutputProfile,
    encoder: EncoderChoice,
    crf: int,
    preset: str,
    audio_bitrate: str,
    hardware_bitrate: str,
    audio_policy: str,
    source_audio_codecs: list[str] | None = None,
    input_height: int | None = None,
    lut_interp: str = "tetrahedral",
    lut_strength: float = 1.0,
    progress_callback: Callable[[float], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict:
    """Apply LUT with automatic encoder/audio fallback.

    Attempt order: chosen encoder + audio copy, software encoder + copy,
    software encoder + compatibility audio fallback.  Hardware failure never
    aborts the job if a CPU fallback can succeed.
    """
    job_temp_dir = job_temp_dir.resolve()
    job_temp_dir.mkdir(parents=True, exist_ok=True)
    work_lut = job_temp_dir / "active_lut.cube"
    strength = min(1.0, max(0.0, float(lut_strength)))
    if strength >= 0.9999:
        shutil.copyfile(lut_path, work_lut)
    else:
        CubeLUT.from_file(lut_path).blended(strength).write_cube(
            work_lut,
            f"{Path(lut_path).stem} @ {strength * 100:.0f}%",
        )
    try:
        rel_lut = work_lut.relative_to(PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise FFmpegError("内部临时 LUT 路径必须位于项目内") from exc
    if lut_interp not in {"trilinear", "tetrahedral", "nearest"}:
        lut_interp = "tetrahedral"
    filter_graph = f"lut3d=file={rel_lut}:interp={lut_interp}"

    # lut3d runs on the CPU.  Hardware decoding would upload frames to the GPU
    # only to download them again for the LUT, so software decode is faster in
    # the measured 4K pipeline.  Hardware encoding remains enabled through the
    # selected NVENC/QSV/AMF encoder.
    hardware_decode = False
    if log_callback:
        log_callback(
            f"LUT 插值={lut_interp}；强度={strength * 100:.0f}%；"
            f"解码=软件（避免 CPU LUT 的显存往返），编码={encoder.name}"
        )
    plan = _attempt_plan(profile, encoder, audio_policy, source_audio_codecs, hardware_decode)
    last_error = ""
    attempted: list[str] = []
    for attempt_index, (encoder_name, audio_mode, decode_hw) in enumerate(plan, 1):
        if cancel_callback and cancel_callback():
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise FFmpegCancelled("用户取消视频处理")
        if attempt_index > 1:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
        attempted.append(f"{encoder_name}/{'hwdec' if decode_hw else 'swdec'}/{audio_mode}")
        if log_callback:
            log_callback(
                f"编码尝试 {attempt_index}/{len(plan)}：{encoder_name}，"
                f"解码={'硬件加速' if decode_hw else '软件'}，"
                f"音频={'原始复制' if audio_mode == 'copy' else audio_mode}"
            )
        cmd = build_video_command(
            ffmpeg=ffmpeg,
            input_path=input_path,
            output_path=output_path,
            filter_graph=filter_graph,
            profile=profile,
            encoder_name=encoder_name,
            audio_mode=audio_mode,
            crf=crf,
            preset=preset,
            audio_bitrate=audio_bitrate,
            hardware_bitrate=hardware_bitrate,
            hardware_decode=decode_hw,
        )
        stderr_path = job_temp_dir / f"ffmpeg_stderr_{attempt_index}.log"
        returncode, cancelled = _run_ffmpeg_attempt(
            cmd,
            output_path=output_path,
            stderr_path=stderr_path,
            duration=duration,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
        if cancelled:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise FFmpegCancelled("用户取消视频处理")
        if returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return {
                "encoder": encoder_name,
                "audio_mode": audio_mode,
                "attempts": attempted,
            }
        last_error = _tail(stderr_path)
        if log_callback:
            log_callback(f"编码尝试失败：{encoder_name}/{audio_mode}；准备回退。")

    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        pass
    raise FFmpegError(
        f"FFmpeg 处理失败：{input_path.name}\n"
        f"尝试组合：{', '.join(attempted)}\n{last_error}"
    )
