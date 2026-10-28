# 热门网络 LUT

本分区收录 58 个面向 DJI D-Log M 的网络热门风格 LUT。
风格来源均为 MIT 许可的公开 LUT 作品；发布文件是项目生成的 D-Log M 直用版本，
不是对原 LUT 文件的简单改名或直接转载。

## 生成方式

```text
DJI Air 3S D-Log M -> Rec.709 基准 LUT
        ↓
公开风格 LUT（MIT）
        ↓
17^3 D-Log M 复合 LUT
```

因此这些文件可以直接在软件中作为单个 LUT 使用，不需要先手动还原 Rec.709。
由于 D-Log M 在不同 DJI 设备间存在轻微差异，建议正式批处理前先抽 1-2 个镜头试色。

## 二级分类

### 冷调夜景

- `DLogM_Cool_TealEmbers_StripedPurple.cube`：青蓝余烬；适用：夜景、城市、情绪片；注意：青蓝阴影、暖高光。
- `DLogM_Cool_SnowyBlues_StripedPurple.cube`：雪蓝；适用：雪景、冬日、清晨；注意：冷白高光、蓝阴影。
- `DLogM_Cool_GreyMatter_StripedPurple.cube`：灰质；适用：工业、城市、纪实；注意：低饱和灰蓝。
- `DLogM_Cool_GreatAuk_StripedPurple.cube`：大海雀；适用：海岸、阴天、冷色纪实；注意：冷灰蓝、低饱和。
- `DLogM_Cool_DayForNight_AICinema.cube`：日转夜；适用：白天拍夜景、城市、情绪片；注意：压暗并偏蓝，需适当提高曝光。

### 复古暖调

- `DLogM_Retro_AmberHaze_StripedPurple.cube`：琥珀薄雾；适用：黄昏、室内暖光、人像；注意：暖调明显，天空可能偏黄。
- `DLogM_Retro_CaramelPlumCake_StripedPurple.cube`：焦糖梅子；适用：咖啡店、室内、复古街拍；注意：洋红与焦糖交织，注意肤色保护。
- `DLogM_Retro_PolaroidMintCream_StripedPurple.cube`：宝丽来薄荷奶油；适用：日常记录、旅行、人像；注意：低对比、薄荷绿高光。
- `DLogM_Retro_Horchata_StripedPurple.cube`：欧洽塔奶油；适用：室内、美食、暖光人像；注意：奶油高光、暖棕阴影。
- `DLogM_Retro_Tiger_StripedPurple.cube`：虎纹；适用：沙漠、日落、户外；注意：暖橙高饱和。
- `DLogM_Retro_Super8HomeMovie_AICinema.cube`：Super 8 家庭电影；适用：复古回忆、旅行、家庭；注意：暖黄、低对比、轻微颗粒感。
- `DLogM_Retro_Pendleton_StripedPurple.cube`：Pendleton 复古；适用：户外、露营、复古生活；注意：暖橙与灰绿交织。
- `DLogM_Retro_Lobster_StripedPurple.cube`：龙虾红；适用：美食、夜市、暖光人像；注意：红色饱和度高，注意肤色。

### 实验风格

- `DLogM_Experimental_Infrared_StripedPurple.cube`：红外胶片；适用：实验、艺术、植物；注意：红/洋红偏移，谨慎用于人像。
- `DLogM_Experimental_CrossProcess_AICinema.cube`：交叉冲洗；适用：时尚、实验、音乐视频；注意：青绿阴影与暖高光。
- `DLogM_Experimental_BlowMeDown_StripedPurple.cube`：风吹草动；适用：实验短片、音乐视频、时尚；注意：偏色与反差较强，注意肤色。
- `DLogM_Experimental_VeggieCrisps_StripedPurple.cube`：蔬菜脆片；适用：实验、创意、色彩测试；注意：黄绿偏色，适合非写实场景。

### 日系清新

- `DLogM_Japanese_VanillaBean_StripedPurple.cube`：香草豆；适用：日系日常、旅行、人像；注意：柔和低对比、轻微暖色。
- `DLogM_Japanese_SpringWater_StripedPurple.cube`：春水；适用：日系街拍、清新风景、阴天；注意：清淡青蓝、低饱和。
- `DLogM_Japanese_PhillyFog_StripedPurple.cube`：费城雾；适用：雾天、城市、阴天；注意：灰蓝低对比，注意肤色。
- `DLogM_Japanese_EmeraldMalaise_StripedPurple.cube`：祖母绿忧郁；适用：森林、雨天、日系人像；注意：绿色偏青，避免绿植过饱和。
- `DLogM_Japanese_BlueLagoon_StripedPurple.cube`：蓝泻湖；适用：海边、夏日、清新旅拍；注意：清透蓝绿、低对比。
- `DLogM_Japanese_Turquoise_StripedPurple.cube`：绿松石；适用：海边、泳池、夏日人像；注意：青绿色高光，肤色偏冷。

### 电影感

- `DLogM_Cinematic_80sFilm_StripedPurple.cube`：80s 电影胶片；适用：夜景、霓虹、复古叙事、城市街拍；注意：暖黄高光、轻微褪色；避免高光过曝。
- `DLogM_Cinematic_Kraken_StripedPurple.cube`：海妖；适用：深海、夜景、情绪片；注意：深青黑位。
- `DLogM_Cinematic_TealOrange_AICinema.cube`：青橙大片；适用：商业片、旅拍、人物；注意：标准青橙，肤色偏暖。
- `DLogM_Cinematic_1920sFilm_StripedPurple.cube`：1920s 电影胶片；适用：年代片、黑白转彩色、复古叙事；注意：偏暖棕与低饱和，适合复古质感。
- `DLogM_Cinematic_1950sFilm_StripedPurple.cube`：1950s 彩色电影；适用：年代片、复古广告、怀旧街拍；注意：暖黄高光、柔和反差。
- `DLogM_Cinematic_1970sFilm_StripedPurple.cube`：1970s 胶片电影；适用：复古电影、公路片、怀旧纪实；注意：偏暖绿、低对比、胶片褪色感。
- `DLogM_Cinematic_DesaturatedMoody_AICinema.cube`：低饱和情绪片；适用：城市、阴天、情绪叙事；注意：低饱和冷调，人物肤色偏稳。
- `DLogM_Cinematic_WarmShadowSplit_AICinema.cube`：暖阴影分离调；适用：人像、夜景、室内；注意：暖阴影、冷高光，适合肤色。

### 胶片风

- `DLogM_Film_LomochromePurple_StripedPurple.cube`：Lomochrome 紫；适用：实验胶片、花草、街拍；注意：紫绿偏移明显，不适合标准肤色。
- `DLogM_Film_BleachBypass_AICinema.cube`：漂白旁路；适用：战争、工业、硬朗人像；注意：高对比、低饱和。
- `DLogM_Film_FadedAged_AICinema.cube`：褪色老电影；适用：回忆、旧时光、家庭影像；注意：低对比、褪色。
- `DLogM_Film_KodakVision3_250D_AICinema.cube`：Kodak Vision3 250D；适用：日光、人像、纪录片；注意：电影负片色。
- `DLogM_Film_FujiEterna250D_AICinema.cube`：Fuji Eterna 250D；适用：日系电影、室内、人像；注意：低饱和柔和。
- `DLogM_Film_KodakEktachrome100D_AICinema.cube`：Kodak Ektachrome 100D；适用：日光、风光、商业；注意：反转片高饱和。
- `DLogM_Film_ArichaBlend_StripedPurple.cube`：Aricha 混合胶片；适用：咖啡、室内、复古街拍；注意：暖棕胶片色，低饱和。
- `DLogM_Film_IrishUprising_StripedPurple.cube`：爱尔兰起义；适用：户外、草地、阴天；注意：绿色偏青、胶片低对比。
- `DLogM_Film_KodakVision3_500T_AICinema.cube`：Kodak Vision3 500T；适用：夜景、室内、钨丝灯；注意：高感负片色，暗部偏青。
- `DLogM_Film_FujiEternaVivid500_AICinema.cube`：Fuji Eterna Vivid 500；适用：日系电影、夜景、人像；注意：比 Eterna 更鲜艳，适合晚上。
- `DLogM_Film_16mmReversal_AICinema.cube`：16mm 反转片；适用：复古纪录、旅行、实验；注意：高对比、轻微偏色。
- `DLogM_Film_Technicolor3Strip_AICinema.cube`：Technicolor 三色；适用：复古大片、红绿蓝强色场景；注意：高饱和、强色彩分离。

### 自然风光

- `DLogM_Nature_DecemberGreens_StripedPurple.cube`：十二月绿；适用：森林、山川、户外；注意：针叶绿和冷高光。
- `DLogM_Nature_SeaTurtle_StripedPurple.cube`：海龟；适用：海岛、水下、自然纪录片；注意：青绿蓝调，适合大面积自然色。
- `DLogM_Nature_TealSupreme_StripedPurple.cube`：青绿至上；适用：森林、湖泊、航拍；注意：青绿突出，适合大面积自然景。
- `DLogM_Nature_Ara_StripedPurple.cube`：金刚鹦鹉；适用：雨林、花卉、热带；注意：高饱和红绿蓝，适合生态。
- `DLogM_Nature_Boa_StripedPurple.cube`：蟒蛇；适用：丛林、湿地、暗调自然；注意：深绿与暖棕。
- `DLogM_Nature_Dodo_StripedPurple.cube`：渡渡鸟；适用：海岛、沙滩、旅行；注意：暖沙色与柔和蓝。
- `DLogM_Nature_Moa_StripedPurple.cube`：恐鸟；适用：森林、山地、自然纪录；注意：深绿暖棕、沉稳。

### 赛博朋克

- `DLogM_Cyberpunk_ArcadeDayz_StripedPurple.cube`：街机霓虹；适用：夜景、霓虹、游戏/音乐视频；注意：蓝紫霓虹较强，肤色会偏冷。
- `DLogM_Cyberpunk_WoelfellyNeon_StripedPurple.cube`：狼霓虹；适用：夜景、赛博朋克、霓虹招牌；注意：高饱和蓝紫，建议降低曝光。
- `DLogM_Cyberpunk_CherryChampagne_StripedPurple.cube`：樱桃香槟；适用：夜景、派对、霓虹人像；注意：洋红/樱桃色高光，适合霓虹。
- `DLogM_Cyberpunk_SugarPlums_StripedPurple.cube`：糖梅紫；适用：夜景、音乐视频、时尚；注意：紫粉阴影，高饱和。

### 黑白纪实

- `DLogM_BW_HighContrast_AICinema.cube`：高反差黑白；适用：街头、建筑、硬光人像；注意：黑白高反差，适合硬朗纪实。
- `DLogM_BW_KodakDoubleX_AICinema.cube`：Kodak Double-X 黑白；适用：街头、人像、纪实；注意：经典黑白负片，层次丰富。
- `DLogM_BW_KodakTriX400_AICinema.cube`：Kodak Tri-X 400 黑白；适用：街拍、新闻、低光纪实；注意：粗颗粒、高反差黑白。
- `DLogM_BW_IlfordHP5_AICinema.cube`：Ilford HP5 黑白；适用：人像、街头、室内；注意：宽容度高的黑白，适合人像。

## 来源与许可

详见 `SOURCES.md` 和 `THIRD_PARTY_LICENSES/`。

## 重新生成

```bat
python toolsuild_network_luts.py
```

脚本会下载 MIT 源 LUT 到 `temp/`，应用 DJI D-Log M 基准变换后重新生成 17^3 `.cube`，
并更新 `luts/manifest.json`、`SOURCES.md` 和本说明。
