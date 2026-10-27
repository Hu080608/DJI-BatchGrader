"""Hardware encoder probing, caching, and selection."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .formats import OutputProfile
from .paths import CONFIG_DIR, PROJECT_ROOT, child_environment

CACHE_PATH = CONFIG_DIR / "encoder_cache.json"

_VENDOR_LABELS = {
    "nvidia": "NVIDIA NVENC",
    "intel": "Intel QSV",
    "amd": "AMD AMF",
}
_ENCODER_VENDORS = {
    "h264_nvenc": "nvidia", "hevc_nvenc": "nvidia",
    "h264_qsv": "intel", "hevc_qsv": "intel",
    "h264_amf": "amd", "hevc_amf": "amd",
}
_ENCODER_LABELS = {
    "h264_nvenc": "NVIDIA NVENC · H.264",
    "hevc_nvenc": "NVIDIA NVENC · HEVC",
    "h264_qsv": "Intel QSV · H.264",
    "hevc_qsv": "Intel QSV · HEVC",
    "h264_amf": "AMD AMF · H.264",
    "hevc_amf": "AMD AMF · HEVC",
    "libx264": "CPU · libx264",
    "libx265": "CPU · libx265",
    "prores_ks": "CPU · ProRes 422 HQ",
}


@dataclass(frozen=True)
class EncoderChoice:
    name: str
    label: str
    hardware: bool
    vendor: str = "cpu"

    @property
    def vendor_label(self) -> str:
        return _VENDOR_LABELS.get(self.vendor, "CPU")


def _fingerprint(ffmpeg: Path) -> str:
    try:
        st = Path(ffmpeg).resolve().stat()
        return f"{Path(ffmpeg).resolve()}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return str(ffmpeg)


def _load_cache(ffmpeg: Path) -> dict:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if data.get("fingerprint") == _fingerprint(ffmpeg):
            return data
    except Exception:
        pass
    return {"fingerprint": _fingerprint(ffmpeg), "probes": {}}


def _save_cache(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        pass


def _spawn_kwargs() -> dict:
    kw: dict = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def probe_encoder(ffmpeg: Path, encoder_name: str, pixel_format: str = "yuv420p") -> bool:
    """Actually encode one tiny frame; -encoders alone is not enough."""
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.2",
        "-frames:v", "1", "-an",
        "-c:v", encoder_name, "-pix_fmt", pixel_format,
        "-f", "null", "-",
    ]
    try:
        cp = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=25, cwd=str(PROJECT_ROOT), env=child_environment(), **_spawn_kwargs(),
        )
        return cp.returncode == 0
    except Exception:
        return False


def choose_encoder(
    ffmpeg: Path,
    profile: OutputProfile,
    preference: str = "auto",
    *,
    log: Callable[[str], None] | None = None,
) -> EncoderChoice:
    """Choose the first truly working hardware encoder, or CPU fallback."""
    preference = (preference or "auto").lower()
    if preference == "cpu" or not profile.supports_hardware:
        return EncoderChoice(profile.software_encoder, _ENCODER_LABELS.get(profile.software_encoder, profile.software_encoder), False)

    cache = _load_cache(ffmpeg)
    probes: dict = cache.setdefault("probes", {})
    candidates = list(profile.hardware_candidates)
    if preference in {"nvidia", "intel", "amd"}:
        candidates = [c for c in candidates if _ENCODER_VENDORS.get(c) == preference]
    for name in candidates:
        cache_key = f"{name}|{profile.pixel_format}"
        if cache_key not in probes:
            if log:
                log(f"正在测试硬件编码器：{_ENCODER_LABELS.get(name, name)}")
            probes[cache_key] = probe_encoder(ffmpeg, name, profile.pixel_format)
            _save_cache(cache)
        if probes.get(cache_key):
            if log:
                log(f"使用硬件编码器：{_ENCODER_LABELS.get(name, name)}")
            return EncoderChoice(name, _ENCODER_LABELS.get(name, name), True, _ENCODER_VENDORS.get(name, "cpu"))
    if log:
        log("未找到可用硬件编码器，使用 CPU 编码。")
    return EncoderChoice(profile.software_encoder, _ENCODER_LABELS.get(profile.software_encoder, profile.software_encoder), False)


def encoder_summary(choice: EncoderChoice) -> dict:
    return asdict(choice) | {"vendor_label": choice.vendor_label}
