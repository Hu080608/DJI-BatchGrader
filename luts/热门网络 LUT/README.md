# 热门网络 LUT

本分区收录 28 个面向 DJI D-Log M 的网络热门风格 LUT。
风格来源均为 MIT 许可的公开 LUT 作品；发布文件是项目生成的 D-Log M 直用版本，
不是对原 LUT 文件的简单改名或直接转载。

## 生成方式

```text
DJI Air 3S D-Log M -> Rec.709 基准 LUT
        ↓
公开风格 LUT（MIT）
        ↓
33^3 D-Log M 复合 LUT
```

因此这些文件可以直接在软件中作为单个 LUT 使用，不需要先手动还原 Rec.709。
由于 D-Log M 在不同 DJI 设备间存在轻微差异，建议正式批处理前先抽 1-2 个镜头试色。

## 二级分类

### 冷调夜景

- `DLogM_Cool_TealEmbers_StripedPurple.cube`：青蓝余烬；适用：夜景、城市、情绪片；注意：青蓝阴影、暖高光。
- `DLogM_Cool_SnowyBlues_StripedPurple.cube`：雪蓝；适用：雪景、冬日、清晨；注意：冷白高光、蓝阴影。
- `DLogM_Cool_GreyMatter_StripedPurple.cube`：灰质；适用：工业、城市、纪实；注意：低饱和灰蓝。

### 复古暖调

- `DLogM_Retro_AmberHaze_StripedPurple.cube`：琥珀薄雾；适用：黄昏、室内暖光、人像；注意：暖调明显，天空可能偏黄。
- `DLogM_Retro_CaramelPlumCake_StripedPurple.cube`：焦糖梅子；适用：咖啡店、室内、复古街拍；注意：洋红与焦糖交织，注意肤色保护。
- `DLogM_Retro_PolaroidMintCream_StripedPurple.cube`：宝丽来薄荷奶油；适用：日常记录、旅行、人像；注意：低对比、薄荷绿高光。
- `DLogM_Retro_Horchata_StripedPurple.cube`：欧洽塔奶油；适用：室内、美食、暖光人像；注意：奶油高光、暖棕阴影。
- `DLogM_Retro_Tiger_StripedPurple.cube`：虎纹；适用：沙漠、日落、户外；注意：暖橙高饱和。
- `DLogM_Retro_Super8HomeMovie_AICinema.cube`：Super 8 家庭电影；适用：复古回忆、旅行、家庭；注意：暖黄、低对比、轻微颗粒感。

### 实验风格

- `DLogM_Experimental_Infrared_StripedPurple.cube`：红外胶片；适用：实验、艺术、植物；注意：红/洋红偏移，谨慎用于人像。
- `DLogM_Experimental_CrossProcess_AICinema.cube`：交叉冲洗；适用：时尚、实验、音乐视频；注意：青绿阴影与暖高光。

### 日系清新

- `DLogM_Japanese_VanillaBean_StripedPurple.cube`：香草豆；适用：日系日常、旅行、人像；注意：柔和低对比、轻微暖色。
- `DLogM_Japanese_SpringWater_StripedPurple.cube`：春水；适用：日系街拍、清新风景、阴天；注意：清淡青蓝、低饱和。
- `DLogM_Japanese_PhillyFog_StripedPurple.cube`：费城雾；适用：雾天、城市、阴天；注意：灰蓝低对比，注意肤色。
- `DLogM_Japanese_EmeraldMalaise_StripedPurple.cube`：祖母绿忧郁；适用：森林、雨天、日系人像；注意：绿色偏青，避免绿植过饱和。

### 电影感

- `DLogM_Cinematic_80sFilm_StripedPurple.cube`：80s 电影胶片；适用：夜景、霓虹、复古叙事、城市街拍；注意：暖黄高光、轻微褪色；避免高光过曝。
- `DLogM_Cinematic_Kraken_StripedPurple.cube`：海妖；适用：深海、夜景、情绪片；注意：深青黑位。
- `DLogM_Cinematic_TealOrange_AICinema.cube`：青橙大片；适用：商业片、旅拍、人物；注意：标准青橙，肤色偏暖。

### 胶片风

- `DLogM_Film_LomochromePurple_StripedPurple.cube`：Lomochrome 紫；适用：实验胶片、花草、街拍；注意：紫绿偏移明显，不适合标准肤色。
- `DLogM_Film_BleachBypass_AICinema.cube`：漂白旁路；适用：战争、工业、硬朗人像；注意：高对比、低饱和。
- `DLogM_Film_FadedAged_AICinema.cube`：褪色老电影；适用：回忆、旧时光、家庭影像；注意：低对比、褪色。
- `DLogM_Film_KodakVision3_250D_AICinema.cube`：Kodak Vision3 250D；适用：日光、人像、纪录片；注意：电影负片色。
- `DLogM_Film_FujiEterna250D_AICinema.cube`：Fuji Eterna 250D；适用：日系电影、室内、人像；注意：低饱和柔和。
- `DLogM_Film_KodakEktachrome100D_AICinema.cube`：Kodak Ektachrome 100D；适用：日光、风光、商业；注意：反转片高饱和。

### 自然风光

- `DLogM_Nature_DecemberGreens_StripedPurple.cube`：十二月绿；适用：森林、山川、户外；注意：针叶绿和冷高光。
- `DLogM_Nature_SeaTurtle_StripedPurple.cube`：海龟；适用：海岛、水下、自然纪录片；注意：青绿蓝调，适合大面积自然色。

### 赛博朋克

- `DLogM_Cyberpunk_ArcadeDayz_StripedPurple.cube`：街机霓虹；适用：夜景、霓虹、游戏/音乐视频；注意：蓝紫霓虹较强，肤色会偏冷。
- `DLogM_Cyberpunk_WoelfellyNeon_StripedPurple.cube`：狼霓虹；适用：夜景、赛博朋克、霓虹招牌；注意：高饱和蓝紫，建议降低曝光。

## 来源与许可

详见 `SOURCES.md` 和 `THIRD_PARTY_LICENSES/`。

## 重新生成

```bat
python toolsuild_network_luts.py
```

脚本会下载 MIT 源 LUT 到 `temp/`，应用 DJI D-Log M 基准变换后重新生成 33^3 `.cube`，
并更新 `luts/manifest.json`、`SOURCES.md` 和本说明。
