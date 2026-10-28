# GitHub Releases 发布与更新

本项目的应用版本更新唯一来源：

```text
https://github.com/Hu080608/DJI-BatchGrader
https://github.com/Hu080608/DJI-BatchGrader/releases
```

客户端不会请求其他应用更新地址。

> LUT 库内容同步是独立功能，仍从 DJI 官方 LUT 目录获取；它不参与应用版本比较，也不下载或替换 EXE。

## 发布资产命名规则

每次发布使用一个版本标签，例如：

```text
v3.8.1
```

发布资产必须包含：

```text
DJI_DLogM_BatchGrader_Windows_x64_v3.8.1.zip
DJI_DLogM_BatchGrader_Windows_x64_v3.8.1.zip.sha256
```

- ZIP 内根目录必须是 `DJI_DLogM_BatchGrader/`
- 根目录中必须包含 `DJI_DLogM_BatchGrader.exe`
- SHA-256 文件格式：
  ```text
  <64位十六进制><两个空格><zip文件名>
  ```
- 发布资产由本地受控构建生成；公开仓库不承担源码构建。

## 发布新版本流程

1. 修改版本号：
   - `VERSION`
   - `dlog_grader/__init__.py`
   - `assets/version_info.txt`
   - `docs/RELEASE_NOTES.md`
   - `COPYRIGHT.md` / `LICENSE.txt` if licensing text changed
   - README 中的版本说明
2. 在本地运行：
   ```bat
   python tests/test_core.py
   python tests/make_test_media.py
   python tests/acceptance_test.py
   cmd /c build_exe.bat
   powershell -ExecutionPolicy Bypass -File tools\package_release.ps1 -Version vX.Y.Z
   ```
3. 公开仓库只提交用户文档和发布说明，不提交源码、私钥或授权签发工具。
4. 在公开仓库创建 `vX.Y.Z` Release，上传 ZIP 和 `.sha256` 资产。
5. 发布成功后可在客户端点击“检查更新”验证。


## 客户端更新流程

1. 请求：
   ```text
   https://api.github.com/repos/Hu080608/DJI-BatchGrader/releases/latest
   ```
2. 读取 `tag_name`、`body`、资产列表。
3. 选择名称匹配：
   ```text
   DJI_DLogM_BatchGrader_Windows_x64_*.zip
   ```
4. 比较版本号，只提示比当前版本更高的 Release。
5. 下载更新包到项目内 `updates\`。
6. 优先使用 GitHub asset digest；缺失时下载同名 `.sha256` 资产。
7. SHA-256 校验失败则拒绝安装并删除临时文件。
8. 用户确认后，主窗口关闭，发布包内的 `DJI_Updater.exe` 独立更新器启动。
9. 独立更新页显示下载、SHA-256 校验、解压、安装和启动新版本进度；失败可重试或退出打开旧版本。
10. 更新过程保留：
   - `config\settings.json`
   - `luts\` 与用户自定义 LUT
   - `output\`、`logs\`、`reports\`、`temp\`

## 本地打包脚本

```powershell
powershell -ExecutionPolicy Bypass -File tools\package_release.ps1 -Version v3.8.1
```

脚本会从 `dist\DJI_DLogM_BatchGrader` 生成 ZIP 和 `.sha256` 到 `release\`。公开 GitHub 仓库不包含源码，发布包由本地受控构建上传。
