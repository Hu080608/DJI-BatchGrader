"""GitHub Releases-based application updater.

The public GitHub repository is the only application-update source:
  https://github.com/Hu080608/DJI-BatchGrader

LUT library content synchronization is a separate feature and is handled by
lut_updater.py from DJI's official LUT catalog.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__
from .paths import PROJECT_ROOT, UPDATES_DIR

GITHUB_OWNER = "Hu080608"
GITHUB_REPO = "DJI-BatchGrader"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"{GITHUB_REPO_URL}/releases"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ASSET_PREFIX = "DJI_DLogM_BatchGrader_Windows_x64_"
ASSET_SUFFIX = ".zip"
USER_AGENT = f"DJI-DLogM-BatchGrader/{__version__}"
UPDATE_REQUEST_FILE = UPDATES_DIR / "update_request.json"
UPDATER_EXE_NAME = "DJI_Updater.exe"
UPDATE_SUMMARY_START = "<!-- UPDATE_SUMMARY_START -->"
UPDATE_SUMMARY_END = "<!-- UPDATE_SUMMARY_END -->"


class UpdateError(RuntimeError):
    pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""
    sha256: str = ""
    tag: str = ""
    asset_name: str = ""
    asset_size: int = 0
    page_url: str = GITHUB_RELEASES_URL


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", value)[:4]]
    return tuple(parts + [0] * (4 - len(parts)))


def _github_headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": accept}


def _read_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers=_github_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read(1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("GitHub 仓库尚未发布任何版本") from exc
        raise UpdateError(f"GitHub Releases 请求失败：HTTP {exc.code}") from exc
    except Exception as exc:
        raise UpdateError(f"无法连接 GitHub Releases：{exc}") from exc


def _sha_from_sidecar(asset_name: str, timeout: int = 10) -> str:
    sidecar = f"{GITHUB_REPO_URL}/releases/latest/download/{urllib.parse.quote(asset_name + '.sha256')}"
    try:
        req = urllib.request.Request(sidecar, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read(4096).decode("utf-8", errors="replace")
        match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
        return match.group(1).lower() if match else ""
    except Exception:
        return ""


def check_for_update(timeout: int = 10) -> UpdateInfo | None:
    data = _read_json(GITHUB_RELEASES_API, timeout=timeout)
    tag = str(data.get("tag_name") or "").strip()
    latest = tag[1:] if tag.lower().startswith("v") else tag
    if not latest:
        raise UpdateError("GitHub Release 缺少版本标签")
    if _version_tuple(latest) <= _version_tuple(__version__):
        return None
    assets = list(data.get("assets") or [])
    candidates = [
        asset for asset in assets
        if str(asset.get("name", "")).startswith(ASSET_PREFIX)
        and str(asset.get("name", "")).lower().endswith(ASSET_SUFFIX)
    ]
    if not candidates:
        raise UpdateError("最新 Release 中没有可用的 Windows 更新包（.zip）")
    asset = candidates[0]
    asset_name = str(asset.get("name") or "")
    sha256 = ""
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        sha256 = digest.split(":", 1)[1].strip().lower()
    if not sha256:
        sha256 = _sha_from_sidecar(asset_name, timeout=timeout)
    return UpdateInfo(
        version=latest,
        tag=tag,
        url=str(asset.get("browser_download_url") or ""),
        notes=str(data.get("body") or ""),
        sha256=sha256,
        asset_name=asset_name,
        asset_size=int(asset.get("size") or 0),
        page_url=str(data.get("html_url") or GITHUB_RELEASES_URL),
    )

def extract_update_summary(notes: str, *, max_lines: int = 8, max_chars: int = 700) -> str:
    """Return only the concise change summary for the update prompt.

    Release bodies may contain full release notes for the GitHub page. The
    desktop prompt should show a short, change-focused excerpt instead.
    """
    newline = chr(10)
    text = str(notes or "").replace(chr(13) + newline, newline).strip()
    if not text:
        return ""
    if UPDATE_SUMMARY_START in text and UPDATE_SUMMARY_END in text:
        text = text.split(UPDATE_SUMMARY_START, 1)[1].split(UPDATE_SUMMARY_END, 1)[0]
    else:
        lines = [line.rstrip() for line in text.splitlines()]
        bullets = [line for line in lines if line.lstrip().startswith(("- ", "* "))]
        if bullets:
            text = newline.join(bullets[:max_lines])
        else:
            text = newline.join(line for line in lines if line.strip())
    result_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) > 180:
            line = line[:180].rstrip() + "…"
        result_lines.append(line)
        if len(result_lines) >= max_lines:
            break
    result = newline.join(result_lines).strip()
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "…"
    return result


def write_update_request(info: UpdateInfo) -> Path:
    """Persist update metadata for the independent updater process."""
    payload = {
        "version": info.version,
        "current_version": __version__,
        "url": info.url,
        "sha256": info.sha256.lower(),
        "asset_name": info.asset_name,
        "asset_size": info.asset_size,
        "app_root": str(PROJECT_ROOT.resolve()),
        "page_url": info.page_url,
    }
    UPDATE_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = UPDATE_REQUEST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(UPDATE_REQUEST_FILE)
    return UPDATE_REQUEST_FILE


def launch_updater(info: UpdateInfo) -> Path:
    """Copy the updater outside the app root and start its independent UI."""
    source = PROJECT_ROOT / UPDATER_EXE_NAME
    if not source.exists():
        raise UpdateError(
            "缺少独立更新程序 DJI_Updater.exe，请重新下载完整发布包。"
        )
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    runtime = UPDATES_DIR / f"DJI_Updater_runtime_{int(time.time())}.exe"
    shutil.copy2(source, runtime)
    request_path = write_update_request(info)
    startupinfo = None
    flags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [str(runtime), "--request", str(request_path)],
        cwd=str(UPDATES_DIR),
        creationflags=flags,
        startupinfo=startupinfo,
        close_fds=True,
    )
    return request_path


def download_update(
    info: UpdateInfo,
    progress_callback: Callable[[int, int], None] | None = None,
    timeout: int = 120,
) -> Path:
    if not info.url:
        raise UpdateError("GitHub Release 更新包缺少下载地址")
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPDATES_DIR / info.asset_name
    partial = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(info.url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length") or info.asset_size or 0)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)
        digest = h.hexdigest()
        if info.sha256 and digest.lower() != info.sha256.lower():
            raise UpdateError("更新包 SHA-256 校验失败，已拒绝安装")
        partial.replace(destination)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_apply_script(zip_path: Path, app_root: Path | None = None) -> Path:
    app_root = (app_root or PROJECT_ROOT).resolve()
    exe_name = "DJI_DLogM_BatchGrader.exe"
    script = UPDATES_DIR / "apply_update.ps1"
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    settings_backup = Path(tempfile.gettempdir()) / "DJI_DLogM_BatchGrader_settings_backup.json"
    content = f"""$ErrorActionPreference = 'Stop'
$app = {_ps_quote(str(app_root))}
$zip = {_ps_quote(str(zip_path.resolve()))}
$exe = {_ps_quote(exe_name)}
$stage = Join-Path $env:TEMP 'DJI_DLogM_BatchGrader_update_stage'
$settings = Join-Path (Join-Path $app 'config') 'settings.json'
$settingsBackup = {_ps_quote(str(settings_backup))}
Start-Sleep -Milliseconds 800
try {{ Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue -Timeout 30 }} catch {{}}
Start-Sleep -Milliseconds 600
if (Test-Path $settings) {{ Copy-Item $settings $settingsBackup -Force }}
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
$targetExe = Get-ChildItem $stage -Recurse -Filter $exe | Select-Object -First 1
if (-not $targetExe) {{ throw '更新包中未找到主程序' }}
$src = $targetExe.Directory.FullName
if (Test-Path (Join-Path $app '_internal')) {{ Remove-Item (Join-Path $app '_internal') -Recurse -Force }}
Copy-Item (Join-Path $src '*') $app -Recurse -Force
if (Test-Path $settingsBackup) {{ Copy-Item $settingsBackup (Join-Path (Join-Path $app 'config') 'settings.json') -Force }}
Start-Process -FilePath (Join-Path $app $exe) -WorkingDirectory $app
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $settingsBackup -Force -ErrorAction SilentlyContinue
Remove-Item $zip -Force -ErrorAction SilentlyContinue
"""
    script.write_text(content, encoding="utf-8-sig")
    return script


def launch_apply_script(script_path: Path) -> None:
    flags = 0
    startupinfo = None
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(script_path),
        ],
        cwd=str(script_path.parent),
        creationflags=flags,
        startupinfo=startupinfo,
        close_fds=True,
    )
