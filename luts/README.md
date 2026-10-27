# DJI LUT Library / DJI LUT 库

本目录已内置从 DJI 官方下载中心/CDN 下载的 **55 个 3D LUT 文件**，覆盖 **25 个设备/系列**。

## 目录结构

```text
luts/
├─ manifest.json                 # 自动生成：设备、类别、SHA-256、来源 URL
├─ SOURCES.md                    # 官方来源链接清单
├─ DOWNLOAD_REPORT.json          # 下载/校验结果
├─ DJI Air 3S/
│  └─ Normalization/
├─ DJI Mavic 4 Pro/
├─ DJI Mavic 3/
├─ DJI Mini 4 Pro/
├─ DJI Mini 5 Pro/
├─ DJI Air 3/
├─ DJI Flip/
├─ DJI Avata 2/
├─ DJI Avata 360/
├─ DJI Lito X1/
├─ DJI O4 Air Unit 系列/
├─ DJI Ronin 4D/
├─ Osmo Action 4/
│  ├─ Normalization/
│  └─ Color Grading/
├─ Osmo Action 5 Pro/
│  ├─ Normalization/
│  └─ Color Grading/
├─ Osmo Action 6/
├─ Osmo Pocket 3/
│  ├─ Normalization/
│  └─ Color Grading/
├─ Osmo Pocket 4/
├─ Osmo Pocket 4P/
├─ Osmo 360/
├─ Osmo Nano/
├─ 御 Mavic 2/
├─ 悟 Inspire 1/
├─ 精灵 Phantom 3 Pro/
├─ 精灵 Phantom 4/
├─ 禅思 Zenmuse X5S/
└─ custom/                      # 用户导入 LUT
```

## 来源

- DJI 下载中心目录：
  - https://www.dji.com/cn/downloads/softwares/mavic-4-pro-dlog-m-to-rec709-lut
- 完整来源 URL 见 `SOURCES.md`
- 每个 LUT 的 SHA-256 见 `manifest.json`
- 程序运行时会默认每 24 小时检查 DJI 官方目录；发现新机型/LUT 会自动下载、校验并补充到本目录。
- 也可以在界面 LUT 区域点击“同步 LUT 库”立即检查。
- 开发环境整体重新下载：

```bat
python tools\download_dji_luts.py
```

## 说明

- 默认 LUT 仍为 `luts/DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube`。
- 内置文件均为 DJI 官方 CDN 的 `.cube` 资产。
- 旧 Phantom/X5 包内部分 `.cube` 是 1D shaper/gamma LUT，不是本软件支持的 3D LUT；同包内有效的 3D LUT 已提取。
- DJI 及相关标识归 DJI 所有。商业再分发前请再次确认 DJI 当前条款；详见项目根目录 `THIRD_PARTY_NOTICES.md`。
