@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%CD%"
set "PIP_CACHE_DIR=%ROOT%\.cache\pip"
set "PYTHONPYCACHEPREFIX=%ROOT%\.cache\pycache"
set "TEMP=%ROOT%\temp"
set "TMP=%ROOT%\temp"
set "TMPDIR=%ROOT%\temp"
set "XDG_CACHE_HOME=%ROOT%\.cache"
set "HF_HOME=%ROOT%\.cache\huggingface"
set "PYTHONUTF8=1"
if not exist "%ROOT%\.cache\pip" mkdir "%ROOT%\.cache\pip"
if not exist "%ROOT%\temp" mkdir "%ROOT%\temp"

echo [1/2] 检查/安装构建依赖 ...
python -m pip install -r "%ROOT%\requirements-build.txt"
if errorlevel 1 goto fail

echo [2/2] 使用 Nuitka 构建 GUI 并组装便携目录 ...
python tools\build_app.py
if errorlevel 1 goto fail

echo.
echo 构建完成：
echo   %ROOT%\dist\DJI_DLogM_BatchGrader\DJI_DLogM_BatchGrader.exe
echo 请保留整个 DJI_DLogM_BatchGrader 文件夹一起分发。
exit /b 0

:fail
echo.
echo 构建失败，请查看上方错误信息。
exit /b 1
