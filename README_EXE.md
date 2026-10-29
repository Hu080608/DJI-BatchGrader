# DJI D-Log M Batch Grader — Windows GUI EXE

**作者：Hu080608**  
**版本：3.8.5**  
**许可：商业软件，购买后授权使用**  
**仅 Windows 10/11 x64 GUI 版本，无 CLI**

## 1. 启动

解压完整便携包后双击：

```text
DJI_DLogM_BatchGrader.exe
```

> 必须保留整个文件夹：
> DLL、PIL、numpy、cryptography、tk/tcl 等运行文件，以及 `luts\`、`tools\`、`config\`、`docs\`。

无需安装 Python，无需安装 FFmpeg。

## 2. 拖拽上传与处理范围

拖到顶部拖拽区域：

- 文件：只处理拖入的文件；
- 文件夹：扫描整个文件夹，是否递归由开关决定；
- 多个文件：自动计算公共上级目录；
- `.SRT`：自动忽略，不计入失败；
- 文件夹和文件同时拖入：优先文件夹；
- 处理范围：只处理视频 / 视频 + RAW / 全部处理，默认全部处理。

也可以点击拖拽区域或“选择文件夹”。

## 3. RAW 与输出格式

支持 LibRaw 常见 RAW 扩展名（DNG/CR2/CR3/NEF/NRW/ARW/SRF/SR2/RAF/RW2/ORF/PEF/SRW 等）。
RAW 使用相机白平衡和 sRGB 色彩处理，输出为 16-bit TIFF。


GUI 可选：

- H.264 · MP4 · 8-bit（兼容优先）
- H.265/HEVC · MP4 · 8-bit（高压缩效率）
- H.265/HEVC · MP4 · 10-bit（保留 D-Log M 高动态余量）
- ProRes 422 HQ · MOV · 10-bit（剪辑母版）

自动检测 NVIDIA NVENC / Intel QSV / AMD AMF 并真实试编码；失败自动回退 CPU。视频/照片分别可配置并发。

质量预设：极致画质 / 高质量 / 标准 / 极速 / 自定义，自动映射 CRF、CPU preset 和 GPU 码率。

## 4. 音频与元数据

- 优先无损复制音轨；目标容器不兼容时自动回退 AAC/PCM。
- 保留多个音轨、章节和元数据。
- 保留原分辨率、帧率、时长。
- 输出 BT.709 色彩标记。
- `.SRT` 侧车字幕文件自动忽略。

## 5. 任务队列

右侧“任务队列”显示每个文件的：

- 状态
- 进度
- 实际编码器
- 音频策略
- 错误摘要

状态流转：`待处理 → 处理中 → 成功 / 失败`；另有 `已取消`、`跳过`、`导入失败`。文件导入后立即出现在队列中，并一直保留；任务表包含“耗时”，完成后显示总耗时。

支持：

- 每次启动自动清空任务队列；只清空队列，不删除报告、配置或历史记录
- 右键单个任务项提供“开始 / 重试 / 取消 / 删除”；删除只移除队列项，不删除源文件
- 批处理运行中状态菜单只读，完成后可修改
- 失败项重试
- 清空已完成
- 打开报告目录

报告自动写入：

```text
reports\batch_YYYYMMDD_HHMMSS.json
reports\batch_YYYYMMDD_HHMMSS.csv
```

界面、日志和完成提示会显示“本次处理总耗时：时:分:秒”。处理范围跳过的普通照片会计入“跳过范围”，不会报错或中断流程。

## 6. LUT 库

默认 LUT：

```text
luts\DJI Air 3S\Normalization\DJI Air 3s DJI D-Log M to Rec.709.cube
```

点击“浏览官方LUT库”“浏览网络热门LUT库”或“浏览自定义LUT库”，可分别打开对应分区，并按设备/类别筛选、搜索、滚轮浏览。
点击“导入 .cube”可选择自定义 LUT，外部文件会复制到 `luts\custom\`。

程序默认每 24 小时自动检查 DJI 官方 LUT 目录，新增机型/LUT 会自动下载补充；也可点击“同步DJI官方LUT库”手动检查。

已内置 **55 个 DJI 官方 LUT，覆盖 25 个设备/系列**，包括 D-Log/D-Log M 还原 LUT 和 Action 4/5 Pro、Pocket 3 官方 Color Grading LUT。默认 Air 3S 路径保持不变。

简易模式提供 8 个快速模板、一键推荐、风格强度和批量导出；专业模式保留完整 LUT、RAW、编码和并发控制。

“色彩管理”卡片分为两个模式：
- 色彩还原：使用 DJI 官方 LUT，强度固定 100%。
- 调色：使用网络热门或自定义 LUT，可调强度、套用模板、撤销上一步，并通过“预览”查看默认样片或队列素材的前后对比。

另新增 **58 个“热门网络 LUT”**（D-Log M 直用复合版本，本次新增 30 个），按电影感、胶片风、日系清新、赛博朋克、复古暖调、自然风光、冷调夜景、黑白纪实和实验风格分类；来源与 MIT 许可见 `luts\热门网络 LUT\SOURCES.md`。

其他 LUT 可按以下结构放置，GUI 自动扫描：

```text
luts\<设备名>\<Normalization 或 Color Grading>\<look>.cube
```

详见 `luts\README.md`、`luts\SOURCES.md` 和 `luts\manifest.json`。

## 7. 监听文件夹

输入素材区域每次启动为空，不自动恢复上次选择的文件夹。

启用“监听输入文件夹”后：

- 每 2 秒扫描新文件/变化文件；
- 新文件自动加入队列；
- 当前任务忙时等待，完成后自动处理下一批；
- 自动排除输出目录。

## 8. 隐私与更新

- 默认本地离线处理，不上传素材。
- 匿名诊断写入 `logs\diagnostics\`，只有配置 `telemetry_endpoint` 才会上传。
- 应用更新只从 GitHub Releases 检查。确认后会关闭主窗口并打开独立进度页，显示下载、校验、解压、安装和启动新版本进度。
- 更新成功并确认新版本窗口出现后，自动清理 `updates\` 旧文件，最多保留当前版本和 1 个上一版本更新包；失败时保留回滚文件。
- 仓库：https://github.com/Hu080608/DJI-BatchGrader
- 详见 `docs\PRIVACY.md`、`docs\GITHUB_RELEASES.md`。

## 9. GitHub Releases 分发

所有构建、测试、发布和更新均通过 GitHub 完成：

```text
https://github.com/Hu080608/DJI-BatchGrader/releases
```

发布资产为便携 ZIP；软件可公开下载，但运行需要导入机器绑定授权。

## 10. 免费试用与购买

本软件为商业软件。软件可从 GitHub Releases 免费下载，首次启动自动开始 **7 天免费试用**，无需注册或授权文件。

试用到期后停止新建任务，但不会删除已有文件、配置、日志和报告。如需继续使用，请点击“授权信息”复制机器码，添加作者 QQ：3643791089 购买买断授权，再导入收到的 `license.json`。


## 11. 内置使用说明与快速帮助

右上角“使用说明”按钮与“检查更新”处于同一区域，点击可打开内置快速指南。

## 12. 注意事项

- 当前 EXE 未代码签名；商发前请使用 `tools\sign_exe.ps1` 完成签名。
- FFmpeg 为 GPL 构建，分发前需完成许可证合规审核。
- 已内置 55 个 DJI 官方 LUT 和 58 个热门网络风格 LUT；旧 Phantom/X5 包中的 1D gamma shaper 不适用于 3D LUT 流程，未作为可选项。
- `.SRT` 自动忽略；嵌入字幕不转码。
- 应用更新唯一来源为 GitHub Releases，详见 `docs\GITHUB_RELEASES.md`。
