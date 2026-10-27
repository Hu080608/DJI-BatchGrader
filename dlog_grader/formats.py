"""Video output profiles and friendly labels."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class OutputProfile:
    key: str
    label: str
    family: str                 # h264 / hevc / prores
    extension: str
    container: str              # mp4 / mov
    software_encoder: str
    hardware_candidates: tuple[str, ...]
    pixel_format: str
    bit_depth: int
    video_tag: Optional[str] = None
    prores_profile: Optional[int] = None
    audio_fallback: str = "aac"  # aac / pcm_s16le
    supports_hardware: bool = True


OUTPUT_PROFILES: dict[str, OutputProfile] = {
    "h264_mp4": OutputProfile(
        key="h264_mp4",
        label="H.264 · MP4 · 8-bit（兼容优先）",
        family="h264",
        extension=".mp4",
        container="mp4",
        software_encoder="libx264",
        hardware_candidates=("h264_nvenc", "h264_qsv", "h264_amf"),
        pixel_format="yuv420p",
        bit_depth=8,
        video_tag="avc1",
        audio_fallback="aac",
    ),
    "hevc_mp4": OutputProfile(
        key="hevc_mp4",
        label="H.265/HEVC · MP4 · 8-bit（小体积）",
        family="hevc",
        extension=".mp4",
        container="mp4",
        software_encoder="libx265",
        hardware_candidates=("hevc_nvenc", "hevc_qsv", "hevc_amf"),
        pixel_format="yuv420p",
        bit_depth=8,
        video_tag="hvc1",
        audio_fallback="aac",
    ),
    "hevc10_mp4": OutputProfile(
        key="hevc10_mp4",
        label="H.265/HEVC · MP4 · 10-bit（高动态余量）",
        family="hevc",
        extension=".mp4",
        container="mp4",
        software_encoder="libx265",
        hardware_candidates=(),
        pixel_format="yuv420p10le",
        bit_depth=10,
        video_tag="hvc1",
        audio_fallback="aac",
        supports_hardware=False,
    ),
    "prores_mov": OutputProfile(
        key="prores_mov",
        label="ProRes 422 HQ · MOV · 10-bit（剪辑母版）",
        family="prores",
        extension=".mov",
        container="mov",
        software_encoder="prores_ks",
        hardware_candidates=(),
        pixel_format="yuv422p10le",
        bit_depth=10,
        prores_profile=3,
        audio_fallback="pcm_s16le",
        supports_hardware=False,
    ),
}

DEFAULT_OUTPUT_PROFILE = "h264_mp4"


def get_output_profile(key: str | None) -> OutputProfile:
    return OUTPUT_PROFILES.get(str(key or ""), OUTPUT_PROFILES[DEFAULT_OUTPUT_PROFILE])


def profile_labels() -> dict[str, str]:
    return {key: value.label for key, value in OUTPUT_PROFILES.items()}

# User-facing quality presets.  `custom` keeps whatever CRF / bitrate the
# user configured manually.
QUALITY_PRESETS: dict[str, dict[str, object]] = {
    "maximum": {
        "label": "极致画质",
        "crf": 14,
        "preset": "slow",
        "hardware_bitrate": "150M",
    },
    "high": {
        "label": "高质量",
        "crf": 16,
        "preset": "medium",
        "hardware_bitrate": "100M",
    },
    "standard": {
        "label": "标准",
        "crf": 20,
        "preset": "fast",
        "hardware_bitrate": "60M",
    },
    "fast": {
        "label": "极速",
        "crf": 24,
        "preset": "veryfast",
        "hardware_bitrate": "30M",
    },
    "custom": {
        "label": "自定义",
        "crf": None,
        "preset": None,
        "hardware_bitrate": None,
    },
}

DEFAULT_QUALITY_PRESET = "high"


def quality_preset_labels() -> dict[str, str]:
    return {key: str(value["label"]) for key, value in QUALITY_PRESETS.items()}
