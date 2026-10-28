"""Configuration loading and validation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .paths import DEFAULT_LUT_RELATIVE, SETTINGS_PATH, project_path


@dataclass
class AppConfig:
    # Relative to the project root by default.  The LUT is deliberately not
    # hard-coded to any machine-specific absolute path.
    lut_file: str = DEFAULT_LUT_RELATIVE
    input_dir: str = ""
    output_dir: str = "output"
    recursive: bool = True
    import_scope: str = "all"  # all / video_raw / video_only
    jpeg_quality: int = 95
    png_compress_level: int = 6
    tiff_compression: str = "tiff_lzw"
    output_profile: str = "h264_mp4"
    quality_preset: str = "high"
    video_workers: int = 0            # 0 = auto
    photo_workers: int = 0            # 0 = auto
    encoder_preference: str = "auto"  # auto / cpu / nvidia / intel / amd
    video_crf: int = 16
    video_preset: str = "medium"
    video_lut_interp: str = "tetrahedral"  # trilinear / tetrahedral / nearest
    lut_strength: float = 1.0            # 0.0 = original, 1.0 = full LUT
    ui_mode: str = "simple"              # simple / pro
    hardware_bitrate: str = "100M"
    audio_bitrate: str = "256k"
    audio_policy: str = "copy_then_aac"
    overwrite: bool = True
    keep_temp: bool = False
    output_suffix: str = "_graded"
    write_reports: bool = True
    watch_enabled: bool = False
    watch_interval_seconds: int = 2
    telemetry_enabled: bool = True
    telemetry_endpoint: str = ""
    auto_check_updates: bool = True
    auto_update_luts: bool = True
    lut_update_interval_hours: int = 24

    @property
    def lut_path(self) -> Path:
        return project_path(self.lut_file)

    @property
    def default_output_path(self) -> Path:
        return project_path(self.output_dir)

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not 1 <= int(self.jpeg_quality) <= 100:
            problems.append("JPEG 质量必须在 1..100 之间")
        if not 0 <= int(self.png_compress_level) <= 9:
            problems.append("PNG 压缩等级必须在 0..9 之间")
        from .formats import OUTPUT_PROFILES

        if self.output_profile not in OUTPUT_PROFILES:
            problems.append("输出格式必须是 formats.py 中已定义的配置")
        from .formats import QUALITY_PRESETS
        if self.quality_preset not in QUALITY_PRESETS:
            problems.append("质量预设必须是 formats.py 中已定义的配置")
        if int(self.video_workers) < 0 or int(self.photo_workers) < 0:
            problems.append("并发数不能为负数")
        if self.encoder_preference not in {"auto", "cpu", "nvidia", "intel", "amd"}:
            problems.append("编码器偏好必须是 auto/cpu/nvidia/intel/amd")
        if not 0 <= int(self.video_crf) <= 51:
            problems.append("CRF 必须在 0..51 之间")
        if str(self.audio_bitrate).lower() not in {"128k", "160k", "192k", "256k", "320k"}:
            problems.append("音频码率必须是 128k/160k/192k/256k/320k 之一")
        if self.audio_policy not in {"copy_then_aac", "aac"}:
            problems.append("音频策略必须是 copy_then_aac 或 aac")
        if self.video_lut_interp not in {"trilinear", "tetrahedral", "nearest"}:
            problems.append("视频 LUT 插值必须是 trilinear / tetrahedral / nearest")
        if not 0.0 <= float(self.lut_strength) <= 1.0:
            problems.append("LUT 风格强度必须在 0..1 之间")
        if self.ui_mode not in {"simple", "pro"}:
            problems.append("界面模式必须是 simple 或 pro")
        if self.import_scope not in {"all", "video_raw", "video_only"}:
            problems.append("处理范围必须是 all / video_raw / video_only")
        if int(self.watch_interval_seconds) < 1:
            problems.append("监听间隔不能小于 1 秒")
        if not self.output_suffix:
            problems.append("输出后缀不能为空")
        return problems


def load_config(path: Path | None = None) -> AppConfig:
    """Load settings.json, ignoring unknown keys and invalid JSON gracefully."""
    path = path or SETTINGS_PATH
    cfg = AppConfig()
    if not path.exists():
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return cfg
    if not isinstance(raw, dict):
        return cfg
    allowed = {f.name for f in fields(AppConfig)}
    values: dict[str, Any] = {}
    for key, value in raw.items():
        if key in allowed:
            values[key] = value
    try:
        merged = asdict(cfg)
        merged.update(values)
        cfg = AppConfig(**merged)
    except Exception:
        return AppConfig()
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    """Persist settings inside the project for the next GUI session."""
    path = path or SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
