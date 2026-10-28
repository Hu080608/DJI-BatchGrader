#!/usr/bin/env python3
"""Build the bundled "热门网络 LUT" collection.

The creative looks come from MIT-licensed public LUT collections.  Each shipped
.cube is a D-Log M ready composite: the DJI Air 3S D-Log M -> Rec.709 transform
is applied first, then the source creative LUT.  Source files are downloaded to
temp/ and are not redistributed as-is; the generated composites and the MIT
licence notices are shipped in luts/热门网络 LUT/.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from dlog_grader.lut import CubeLUT

ROOT = Path(__file__).resolve().parents[1]
BASE_LUT = ROOT / "luts" / "DJI Air 3S" / "Normalization" / "DJI Air 3s DJI D-Log M to Rec.709.cube"
TARGET_ROOT = ROOT / "luts" / "热门网络 LUT"
SOURCE_CACHE = ROOT / "temp" / "network_luts_src"
MANIFEST = ROOT / "luts" / "manifest.json"
GRID = 33

SOURCE_REPOS = {
    "stripedpurple": {
        "label": "Striped Purple LUT Collection",
        "author": "Nixua / Striped Purple",
        "repo": "https://github.com/stripedpurple/color-grading-luts",
        "raw": "https://raw.githubusercontent.com/stripedpurple/color-grading-luts/master/",
        "license": "MIT",
        "license_file": "THIRD_PARTY_LICENSES/StripedPurple-MIT.txt",
    },
    "aicinema": {
        "label": "AI Cinema Studio Engine LUT Collection",
        "author": "PopTech Studio LLC",
        "repo": "https://github.com/poptechstudio/ai-cinema-studio-engine",
        "raw": "https://raw.githubusercontent.com/poptechstudio/ai-cinema-studio-engine/main/",
        "license": "MIT",
        "license_file": "THIRD_PARTY_LICENSES/AI_Cinema_Studio_Engine-MIT.txt",
    },
}


@dataclass(frozen=True)
class Look:
    source: str
    source_path: str
    output: str
    category: str
    name: str
    scene: str
    note: str


LOOKS = [
    Look("stripedpurple", "Cinema Through The Ages/Striped Purple - 1980_s.cube",
         "DLogM_Cinematic_80sFilm_StripedPurple.cube", "电影感", "80s 电影胶片",
         "夜景、霓虹、复古叙事、城市街拍", "暖黄高光、轻微褪色；避免高光过曝。"),
    Look("stripedpurple", "Avant Garde/Striped Purple - Arcade Dayz.cube",
         "DLogM_Cyberpunk_ArcadeDayz_StripedPurple.cube", "赛博朋克", "街机霓虹",
         "夜景、霓虹、游戏/音乐视频", "蓝紫霓虹较强，肤色会偏冷。"),
    Look("stripedpurple", "Avant Garde/Striped Purple - Amber Haze.cube",
         "DLogM_Retro_AmberHaze_StripedPurple.cube", "复古暖调", "琥珀薄雾",
         "黄昏、室内暖光、人像", "暖调明显，天空可能偏黄。"),
    Look("stripedpurple", "Avant Garde/Striped Purple - Caramel Plum Cake.cube",
         "DLogM_Retro_CaramelPlumCake_StripedPurple.cube", "复古暖调", "焦糖梅子",
         "咖啡店、室内、复古街拍", "洋红与焦糖交织，注意肤色保护。"),
    Look("stripedpurple", "Avant Garde/Striped Purple - Polaroid Mint Cream.cube",
         "DLogM_Retro_PolaroidMintCream_StripedPurple.cube", "复古暖调", "宝丽来薄荷奶油",
         "日常记录、旅行、人像", "低对比、薄荷绿高光。"),
    Look("stripedpurple", "Avant Garde/Striped Purple - Woelfelly Neon.cube",
         "DLogM_Cyberpunk_WoelfellyNeon_StripedPurple.cube", "赛博朋克", "狼霓虹",
         "夜景、赛博朋克、霓虹招牌", "高饱和蓝紫，建议降低曝光。"),
    Look("stripedpurple", "Drink it in!/Striped Purple - Horchata.cube",
         "DLogM_Retro_Horchata_StripedPurple.cube", "复古暖调", "欧洽塔奶油",
         "室内、美食、暖光人像", "奶油高光、暖棕阴影。"),
    Look("stripedpurple", "Drink it in!/Striped Purple - Vanilla Bean.cube",
         "DLogM_Japanese_VanillaBean_StripedPurple.cube", "日系清新", "香草豆",
         "日系日常、旅行、人像", "柔和低对比、轻微暖色。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Spring Water.cube",
         "DLogM_Japanese_SpringWater_StripedPurple.cube", "日系清新", "春水",
         "日系街拍、清新风景、阴天", "清淡青蓝、低饱和。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Philly Fog.cube",
         "DLogM_Japanese_PhillyFog_StripedPurple.cube", "日系清新", "费城雾",
         "雾天、城市、阴天", "灰蓝低对比，注意肤色。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Emerald Malaise.cube",
         "DLogM_Japanese_EmeraldMalaise_StripedPurple.cube", "日系清新", "祖母绿忧郁",
         "森林、雨天、日系人像", "绿色偏青，避免绿植过饱和。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - December Greens.cube",
         "DLogM_Nature_DecemberGreens_StripedPurple.cube", "自然风光", "十二月绿",
         "森林、山川、户外", "针叶绿和冷高光。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Sea Turtle.cube",
         "DLogM_Nature_SeaTurtle_StripedPurple.cube", "自然风光", "海龟",
         "海岛、水下、自然纪录片", "青绿蓝调，适合大面积自然色。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Teal Embers.cube",
         "DLogM_Cool_TealEmbers_StripedPurple.cube", "冷调夜景", "青蓝余烬",
         "夜景、城市、情绪片", "青蓝阴影、暖高光。"),
    Look("stripedpurple", "Scenic Moods/Striped Purple - Snowy Blues.cube",
         "DLogM_Cool_SnowyBlues_StripedPurple.cube", "冷调夜景", "雪蓝",
         "雪景、冬日、清晨", "冷白高光、蓝阴影。"),
    Look("stripedpurple", "MISC/Striped Purple - Grey Matter.cube",
         "DLogM_Cool_GreyMatter_StripedPurple.cube", "冷调夜景", "灰质",
         "工业、城市、纪实", "低饱和灰蓝。"),
    Look("stripedpurple", "Film Simulations/Lomography/Lomochrome Purple.cube",
         "DLogM_Film_LomochromePurple_StripedPurple.cube", "胶片风", "Lomochrome 紫",
         "实验胶片、花草、街拍", "紫绿偏移明显，不适合标准肤色。"),
    Look("stripedpurple", "Film Simulations/Infrared/Striped Purple - Infrared.cube",
         "DLogM_Experimental_Infrared_StripedPurple.cube", "实验风格", "红外胶片",
         "实验、艺术、植物", "红/洋红偏移，谨慎用于人像。"),
    Look("stripedpurple", "Zoology/Striped Purple - Kraken.cube",
         "DLogM_Cinematic_Kraken_StripedPurple.cube", "电影感", "海妖",
         "深海、夜景、情绪片", "深青黑位。"),
    Look("stripedpurple", "Zoology/Striped Purple - Tiger.cube",
         "DLogM_Retro_Tiger_StripedPurple.cube", "复古暖调", "虎纹",
         "沙漠、日落、户外", "暖橙高饱和。"),
    Look("aicinema", "luts/creative/teal_orange_blockbuster.cube",
         "DLogM_Cinematic_TealOrange_AICinema.cube", "电影感", "青橙大片",
         "商业片、旅拍、人物", "标准青橙，肤色偏暖。"),
    Look("aicinema", "luts/creative/bleach_bypass.cube",
         "DLogM_Film_BleachBypass_AICinema.cube", "胶片风", "漂白旁路",
         "战争、工业、硬朗人像", "高对比、低饱和。"),
    Look("aicinema", "luts/creative/faded_film_aged.cube",
         "DLogM_Film_FadedAged_AICinema.cube", "胶片风", "褪色老电影",
         "回忆、旧时光、家庭影像", "低对比、褪色。"),
    Look("aicinema", "luts/creative/cross_process.cube",
         "DLogM_Experimental_CrossProcess_AICinema.cube", "实验风格", "交叉冲洗",
         "时尚、实验、音乐视频", "青绿阴影与暖高光。"),
    Look("aicinema", "luts/film_stocks/kodak_vision3_250d.cube",
         "DLogM_Film_KodakVision3_250D_AICinema.cube", "胶片风", "Kodak Vision3 250D",
         "日光、人像、纪录片", "电影负片色。"),
    Look("aicinema", "luts/film_stocks/fuji_eterna_250d.cube",
         "DLogM_Film_FujiEterna250D_AICinema.cube", "胶片风", "Fuji Eterna 250D",
         "日系电影、室内、人像", "低饱和柔和。"),
    Look("aicinema", "luts/film_stocks/kodak_ektachrome_100d.cube",
         "DLogM_Film_KodakEktachrome100D_AICinema.cube", "胶片风", "Kodak Ektachrome 100D",
         "日光、风光、商业", "反转片高饱和。"),
    Look("aicinema", "luts/film_stocks/super_8mm_home_movie.cube",
         "DLogM_Retro_Super8HomeMovie_AICinema.cube", "复古暖调", "Super 8 家庭电影",
         "复古回忆、旅行、家庭", "暖黄、低对比、轻微颗粒感。"),
    # -- second expansion --
    Look('stripedpurple', 'Cinema Through The Ages/Striped Purple - 1920s.cube',
         'DLogM_Cinematic_1920sFilm_StripedPurple.cube', '电影感', '1920s 电影胶片',
         '年代片、黑白转彩色、复古叙事', '偏暖棕与低饱和，适合复古质感。'),
    Look('stripedpurple', 'Cinema Through The Ages/Striped Purple - 1950s.cube',
         'DLogM_Cinematic_1950sFilm_StripedPurple.cube', '电影感', '1950s 彩色电影',
         '年代片、复古广告、怀旧街拍', '暖黄高光、柔和反差。'),
    Look('stripedpurple', 'Cinema Through The Ages/Striped Purple - 1970s.cube',
         'DLogM_Cinematic_1970sFilm_StripedPurple.cube', '电影感', '1970s 胶片电影',
         '复古电影、公路片、怀旧纪实', '偏暖绿、低对比、胶片褪色感。'),
    Look('aicinema', 'luts/creative/desaturated_moody.cube',
         'DLogM_Cinematic_DesaturatedMoody_AICinema.cube', '电影感', '低饱和情绪片',
         '城市、阴天、情绪叙事', '低饱和冷调，人物肤色偏稳。'),
    Look('aicinema', 'luts/creative/split_tone_warm_shadows.cube',
         'DLogM_Cinematic_WarmShadowSplit_AICinema.cube', '电影感', '暖阴影分离调',
         '人像、夜景、室内', '暖阴影、冷高光，适合肤色。'),
    Look('stripedpurple', 'Drink it in!/Striped Purple - Aricha Blend.cube',
         'DLogM_Film_ArichaBlend_StripedPurple.cube', '胶片风', 'Aricha 混合胶片',
         '咖啡、室内、复古街拍', '暖棕胶片色，低饱和。'),
    Look('stripedpurple', 'Scenic Moods/Striped Purple - Irish Uprising.cube',
         'DLogM_Film_IrishUprising_StripedPurple.cube', '胶片风', '爱尔兰起义',
         '户外、草地、阴天', '绿色偏青、胶片低对比。'),
    Look('aicinema', 'luts/film_stocks/kodak_vision3_500t.cube',
         'DLogM_Film_KodakVision3_500T_AICinema.cube', '胶片风', 'Kodak Vision3 500T',
         '夜景、室内、钨丝灯', '高感负片色，暗部偏青。'),
    Look('aicinema', 'luts/film_stocks/fuji_eterna_vivid_500.cube',
         'DLogM_Film_FujiEternaVivid500_AICinema.cube', '胶片风', 'Fuji Eterna Vivid 500',
         '日系电影、夜景、人像', '比 Eterna 更鲜艳，适合晚上。'),
    Look('aicinema', 'luts/film_stocks/16mm_reversal_vintage.cube',
         'DLogM_Film_16mmReversal_AICinema.cube', '胶片风', '16mm 反转片',
         '复古纪录、旅行、实验', '高对比、轻微偏色。'),
    Look('aicinema', 'luts/film_stocks/technicolor_3strip.cube',
         'DLogM_Film_Technicolor3Strip_AICinema.cube', '胶片风', 'Technicolor 三色',
         '复古大片、红绿蓝强色场景', '高饱和、强色彩分离。'),
    Look('stripedpurple', 'Drink it in!/Striped Purple - Blue Lagoon.cube',
         'DLogM_Japanese_BlueLagoon_StripedPurple.cube', '日系清新', '蓝泻湖',
         '海边、夏日、清新旅拍', '清透蓝绿、低对比。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Turquoise.cube',
         'DLogM_Japanese_Turquoise_StripedPurple.cube', '日系清新', '绿松石',
         '海边、泳池、夏日人像', '青绿色高光，肤色偏冷。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Cherry Champagne.cube',
         'DLogM_Cyberpunk_CherryChampagne_StripedPurple.cube', '赛博朋克', '樱桃香槟',
         '夜景、派对、霓虹人像', '洋红/樱桃色高光，适合霓虹。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Sugar Plums.cube',
         'DLogM_Cyberpunk_SugarPlums_StripedPurple.cube', '赛博朋克', '糖梅紫',
         '夜景、音乐视频、时尚', '紫粉阴影，高饱和。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Pendleton.cube',
         'DLogM_Retro_Pendleton_StripedPurple.cube', '复古暖调', 'Pendleton 复古',
         '户外、露营、复古生活', '暖橙与灰绿交织。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Lobster.cube',
         'DLogM_Retro_Lobster_StripedPurple.cube', '复古暖调', '龙虾红',
         '美食、夜市、暖光人像', '红色饱和度高，注意肤色。'),
    Look('stripedpurple', 'Scenic Moods/Striped Purple - Teal Supreme.cube',
         'DLogM_Nature_TealSupreme_StripedPurple.cube', '自然风光', '青绿至上',
         '森林、湖泊、航拍', '青绿突出，适合大面积自然景。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Ara.cube',
         'DLogM_Nature_Ara_StripedPurple.cube', '自然风光', '金刚鹦鹉',
         '雨林、花卉、热带', '高饱和红绿蓝，适合生态。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Boa.cube',
         'DLogM_Nature_Boa_StripedPurple.cube', '自然风光', '蟒蛇',
         '丛林、湿地、暗调自然', '深绿与暖棕。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Dodo.cube',
         'DLogM_Nature_Dodo_StripedPurple.cube', '自然风光', '渡渡鸟',
         '海岛、沙滩、旅行', '暖沙色与柔和蓝。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Great Auk.cube',
         'DLogM_Cool_GreatAuk_StripedPurple.cube', '冷调夜景', '大海雀',
         '海岸、阴天、冷色纪实', '冷灰蓝、低饱和。'),
    Look('stripedpurple', 'Zoology/Striped Purple - Moa.cube',
         'DLogM_Nature_Moa_StripedPurple.cube', '自然风光', '恐鸟',
         '森林、山地、自然纪录', '深绿暖棕、沉稳。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Blow Me Down.cube',
         'DLogM_Experimental_BlowMeDown_StripedPurple.cube', '实验风格', '风吹草动',
         '实验短片、音乐视频、时尚', '偏色与反差较强，注意肤色。'),
    Look('stripedpurple', 'Avant Garde/Striped Purple - Veggie Crisps.cube',
         'DLogM_Experimental_VeggieCrisps_StripedPurple.cube', '实验风格', '蔬菜脆片',
         '实验、创意、色彩测试', '黄绿偏色，适合非写实场景。'),
    Look('aicinema', 'luts/creative/day_for_night.cube',
         'DLogM_Cool_DayForNight_AICinema.cube', '冷调夜景', '日转夜',
         '白天拍夜景、城市、情绪片', '压暗并偏蓝，需适当提高曝光。'),
    Look('aicinema', 'luts/creative/high_contrast_bw.cube',
         'DLogM_BW_HighContrast_AICinema.cube', '黑白纪实', '高反差黑白',
         '街头、建筑、硬光人像', '黑白高反差，适合硬朗纪实。'),
    Look('aicinema', 'luts/film_stocks/kodak_doublex_5222_bw.cube',
         'DLogM_BW_KodakDoubleX_AICinema.cube', '黑白纪实', 'Kodak Double-X 黑白',
         '街头、人像、纪实', '经典黑白负片，层次丰富。'),
    Look('aicinema', 'luts/film_stocks/kodak_trix_400_bw.cube',
         'DLogM_BW_KodakTriX400_AICinema.cube', '黑白纪实', 'Kodak Tri-X 400 黑白',
         '街拍、新闻、低光纪实', '粗颗粒、高反差黑白。'),
    Look('aicinema', 'luts/film_stocks/ilford_hp5_bw.cube',
         'DLogM_BW_IlfordHP5_AICinema.cube', '黑白纪实', 'Ilford HP5 黑白',
         '人像、街头、室内', '宽容度高的黑白，适合人像。'),
]


def source_url(source: str, source_path: str) -> str:
    return SOURCE_REPOS[source]["repo"] + "/blob/" + (
        "master/" if source == "stripedpurple" else "main/"
    ) + urllib.parse.quote(source_path)


def fetch(source: str, source_path: str) -> Path:
    SOURCE_CACHE.mkdir(parents=True, exist_ok=True)
    out = SOURCE_CACHE / (source + "__" + Path(source_path).name)
    if out.exists() and out.stat().st_size > 1000:
        return out
    out.unlink(missing_ok=True)
    url = SOURCE_REPOS[source]["raw"] + urllib.parse.quote(source_path)
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=90) as response:
                payload = response.read()
            if len(payload) < 1000:
                raise RuntimeError("downloaded file is too small")
            out.write_bytes(payload)
            return out
        except Exception as exc:
            last_error = exc
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"下载失败：{source_path}：{last_error}")


def build_grid() -> np.ndarray:
    values = np.linspace(0.0, 1.0, GRID, dtype=np.float32)
    blue, green, red = np.meshgrid(values, values, values, indexing="ij")
    return np.stack((red, green, blue), axis=-1).reshape((-1, 3))


def write_cube(path: Path, title: str, table: np.ndarray, comments: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
def write_cube(path: Path, title: str, table: np.ndarray, comments: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'TITLE "{title}"',
        f"LUT_3D_SIZE {GRID}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    lines.extend("# " + line for line in comments)
    lines.append("")
    for r, g, b in table.reshape((-1, 3)):
        lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_docs(entries: list[dict]) -> None:
    categories: dict[str, list[Look]] = {}
    for look in LOOKS:
        categories.setdefault(look.category, []).append(look)
    readme = [
        "# 热门网络 LUT",
        "",
        f"本分区收录 {len(LOOKS)} 个面向 DJI D-Log M 的网络热门风格 LUT。",
        "风格来源均为 MIT 许可的公开 LUT 作品；发布文件是项目生成的 D-Log M 直用版本，",
        "不是对原 LUT 文件的简单改名或直接转载。",
        "",
        "## 生成方式",
        "",
        "```text",
        "DJI Air 3S D-Log M -> Rec.709 基准 LUT",
        "        ↓",
        "公开风格 LUT（MIT）",
        "        ↓",
        "33^3 D-Log M 复合 LUT",
        "```",
        "",
        "因此这些文件可以直接在软件中作为单个 LUT 使用，不需要先手动还原 Rec.709。",
        "由于 D-Log M 在不同 DJI 设备间存在轻微差异，建议正式批处理前先抽 1-2 个镜头试色。",
        "",
        "## 二级分类",
        "",
    ]
    for category in sorted(categories):
        readme.append(f"### {category}")
        readme.append("")
        for look in categories[category]:
            readme.append(f"- `{look.output}`：{look.name}；适用：{look.scene}；注意：{look.note}")
        readme.append("")
    readme.extend([
        "## 来源与许可",
        "",
        "详见 `SOURCES.md` 和 `THIRD_PARTY_LICENSES/`。",
        "",
        "## 重新生成",
        "",
        "```bat",
        "python tools\build_network_luts.py",
        "```",
        "",
        "脚本会下载 MIT 源 LUT 到 `temp/`，应用 DJI D-Log M 基准变换后重新生成 33^3 `.cube`，",
        "并更新 `luts/manifest.json`、`SOURCES.md` 和本说明。",
        "",
    ])
    (TARGET_ROOT / "README.md").write_text(chr(10).join(readme), encoding="utf-8")

    lines = [
        "# 热门网络 LUT 来源",
        "",
        "源 LUT 与生成文件均为 MIT 许可；下表中的链接指向原始项目文件。",
        "",
        "| 文件 | 风格 | 来源项目 / 原始文件 | 适用场景 | 许可 |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        src = SOURCE_REPOS[
            "stripedpurple" if "StripedPurple" in entry["file"] else "aicinema"
        ]
        lines.append(
            f"| `{entry['file']}` | {entry['name']} | "
            f"[{src['label']}]({entry['source_url']}) | {entry['description']} | MIT |"
        )
    lines.extend([
        "",
        "## 许可文件",
        "",
        "- `THIRD_PARTY_LICENSES/StripedPurple-MIT.txt`",
        "- `THIRD_PARTY_LICENSES/AI_Cinema_Studio_Engine-MIT.txt`",
        "",
    ])
    (TARGET_ROOT / "SOURCES.md").write_text(chr(10).join(lines), encoding="utf-8")


def main() -> int:
    base = CubeLUT.from_file(BASE_LUT)
    grid = build_grid()
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    (TARGET_ROOT / "THIRD_PARTY_LICENSES").mkdir(parents=True, exist_ok=True)
    for source, meta in SOURCE_REPOS.items():
        license_src = SOURCE_CACHE / (source + "_LICENSE.txt")
        if license_src.exists():
            shutil.copy2(license_src, TARGET_ROOT / meta["license_file"])
    entries = []
    for look in LOOKS:
        source_file = fetch(look.source, look.source_path)
        style = CubeLUT.from_file(source_file)
        output = TARGET_ROOT / look.category / look.output
        table = style.transform(base.transform(grid))
        source_meta = SOURCE_REPOS[look.source]
        comments = [
            f"Source style: {look.source_path}",
            f"Source collection: {source_meta['label']} ({source_meta['repo']})",
            f"License: {source_meta['license']}; attribution: {source_meta['author']}",
            "Generated for DJI D-Log M: DJI Air 3S D-Log M -> Rec.709 base, then source style.",
            f"Scene: {look.scene}",
            f"Notes: {look.note}",
        ]
        write_cube(output, look.name, table, comments)
        import hashlib
        sha = hashlib.sha256(output.read_bytes()).hexdigest()
        rel = output.relative_to(ROOT / "luts").as_posix()
        entries.append({
            "file": rel,
            "device": "热门网络 LUT",
            "profile": "D-Log M",
            "category": look.category,
            "name": look.name,
            "description": f"{look.name}：{look.scene}。{look.note}",
            "sha256": sha,
            "source_url": source_url(look.source, look.source_path),
            "source_page": source_meta["repo"],
            "source_author": source_meta["author"],
            "source_collection": source_meta["label"],
            "license": source_meta["license"],
            "license_file": "热门网络 LUT/" + source_meta["license_file"],
            "generated": "D-Log M composite, 33^3",
        })
        print("built", rel)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old = [
        e for e in manifest.get("entries", [])
        if not str(e.get("file", "")).startswith("热门网络 LUT/")
    ]
    manifest["entries"] = old + entries
    manifest["count"] = len(manifest["entries"])
    manifest["network_collection"] = {
        "name": "热门网络 LUT",
        "count": len(entries),
        "generated_at": datetime.now().strftime("%Y-%m-%d"),
        "base_lut": BASE_LUT.relative_to(ROOT / "luts").as_posix(),
        "license": "MIT source LUTs; see THIRD_PARTY_LICENSES and SOURCES.md",
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_docs(entries)
    print("manifest entries", manifest["count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
