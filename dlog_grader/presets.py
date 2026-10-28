"""Beginner-friendly style templates built on the existing LUT library."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import LUT_DIR


@dataclass(frozen=True)
class StyleTemplate:
    key: str
    label: str
    description: str
    lut_file: str
    strength: float
    scene: str

    @property
    def path(self) -> Path:
        return LUT_DIR / self.lut_file


TEMPLATES: tuple[StyleTemplate, ...] = (
    StyleTemplate(
        "portrait_soft",
        "人像柔光",
        "柔和肤色、轻微暖调，适合日常人像和家庭照片。",
        "热门网络 LUT/日系清新/DLogM_Japanese_VanillaBean_StripedPurple.cube",
        0.65,
        "人像 / 家庭 / 日常",
    ),
    StyleTemplate(
        "travel_postcard",
        "旅行明信片",
        "暖调高光与胶片色彩，适合旅行照片和城市漫游视频。",
        "热门网络 LUT/复古暖调/DLogM_Retro_AmberHaze_StripedPurple.cube",
        0.70,
        "旅行 / 城市 / 户外",
    ),
    StyleTemplate(
        "cinematic_teal_orange",
        "青橙电影感",
        "青蓝阴影与暖橙高光，适合人物、商业和叙事视频。",
        "热门网络 LUT/电影感/DLogM_Cinematic_TealOrange_AICinema.cube",
        0.75,
        "电影感 / 商业 / 人物",
    ),
    StyleTemplate(
        "bw_documentary",
        "黑白纪实",
        "高反差黑白，适合街头、建筑和纪实内容。",
        "热门网络 LUT/黑白纪实/DLogM_BW_KodakTriX400_AICinema.cube",
        0.85,
        "黑白 / 街头 / 纪实",
    ),
    StyleTemplate(
        "japanese_fresh",
        "日系清新",
        "清淡青蓝、低饱和，适合阴天、海边和日常记录。",
        "热门网络 LUT/日系清新/DLogM_Japanese_SpringWater_StripedPurple.cube",
        0.65,
        "日系 / 清新 / 阴天",
    ),
    StyleTemplate(
        "retro_film",
        "复古胶片",
        "暖黄高光和轻微褪色，适合怀旧和生活记录。",
        "热门网络 LUT/电影感/DLogM_Cinematic_80sFilm_StripedPurple.cube",
        0.70,
        "复古 / 胶片 / 怀旧",
    ),
    StyleTemplate(
        "night_neon",
        "夜景霓虹",
        "蓝紫霓虹与高饱和夜景，适合赛博朋克和音乐视频。",
        "热门网络 LUT/赛博朋克/DLogM_Cyberpunk_WoelfellyNeon_StripedPurple.cube",
        0.75,
        "夜景 / 霓虹 / 赛博朋克",
    ),
    StyleTemplate(
        "product_faithful",
        "电商色保真",
        "只做 D-Log M 到 Rec.709 标准还原，尽量保持商品主色。",
        "DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube",
        1.00,
        "电商 / 商品 / 色彩保真",
    ),
)

TEMPLATE_BY_KEY = {item.key: item for item in TEMPLATES}
DEFAULT_TEMPLATE = TEMPLATE_BY_KEY["cinematic_teal_orange"]


def recommend_template(paths: list[Path] | None = None) -> tuple[StyleTemplate, str]:
    """Small, transparent MVP recommender based on the first sample image."""
    paths = [Path(p) for p in (paths or []) if p]
    if not paths:
        return DEFAULT_TEMPLATE, "未导入素材，默认推荐通用青橙电影感。"
    first = paths[0]
    suffix = first.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif"}:
        try:
            from PIL import Image, ImageStat

            with Image.open(first) as image:
                rgb = image.convert("RGB")
                rgb.thumbnail((96, 96))
                gray = ImageStat.Stat(rgb.convert("L")).mean[0]
                hsv = rgb.convert("HSV")
                saturation = ImageStat.Stat(hsv).mean[1]
            if gray < 72:
                return TEMPLATE_BY_KEY["night_neon"], "画面偏暗，推荐夜景霓虹。"
            if gray > 158 and saturation < 42:
                return TEMPLATE_BY_KEY["japanese_fresh"], "画面明亮且低饱和，推荐日系清新。"
            if saturation > 105:
                return TEMPLATE_BY_KEY["cinematic_teal_orange"], "画面色彩较丰富，推荐青橙电影感。"
            return TEMPLATE_BY_KEY["travel_postcard"], "画面明暗均衡，推荐旅行明信片。"
        except Exception:
            pass
    return DEFAULT_TEMPLATE, "视频或无法读取的素材，默认推荐通用青橙电影感。"
