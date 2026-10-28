"""Standalone updater engine for DJI D-Log M Batch Grader.

The updater runs in a separate process so the main window can close before the
application files are replaced.  It persists progress to
``updates/update_progress.json`` and resumes partial downloads on retry.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

APP_EXE = "DJI_DLogM_BatchGrader.exe"
UPDATER_EXE = "DJI_Updater.exe"
USER_AGENT = "DJI-DLogM-BatchGrader-Updater/1.0"
PROTECTED_TOP_LEVEL = {
    "output", "logs", "reports", "temp", "updates", "license", ".cache",
}


class UpdateError(RuntimeError):
    pass


@dataclass
class UpdateRequest:
    version: str
    current_version: str
    url: str
    sha256: str
    asset_name: str
    asset_size: int
    app_root: str
    page_url: str = ""

    @classmethod
    def from_file(cls, path: Path) -> "UpdateRequest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        try:
            return cls(
                version=str(data["version"]),
                current_version=str(data.get("current_version") or ""),
                url=str(data["url"]),
                sha256=str(data.get("sha256") or "").lower(),
                asset_name=str(data["asset_name"]),
                asset_size=int(data.get("asset_size") or 0),
                app_root=str(data["app_root"]),
                page_url=str(data.get("page_url") or ""),
            )
        except KeyError as exc:
            raise UpdateError(f"更新请求缺少字段：{exc}") from exc

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UpdateState:
    stage: str
    message: str
    percent: float
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0
    eta_seconds: float | None = None
    error: str = ""
    retryable: bool = False
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)


class StateStore:
    def __init__(self, path: Path):
        self.path = path.resolve()

    def write(self, state: UpdateState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None


def format_bytes(value: int | float | None) -> str:
    if not value:
        return "0 B"
    size = float(value)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "计算中"
    if seconds < 1:
        return "<1 秒"
    if seconds < 60:
        return f"{int(seconds)} 秒"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes} 分 {secs} 秒"


def _atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)


def launch_old_app(app_root: Path) -> None:
    exe = Path(app_root) / APP_EXE
    if not exe.exists():
        return
    subprocess.Popen(
        [str(exe)],
        cwd=str(app_root),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _wait_for_main_window(pid: int, timeout: float = 90.0) -> bool:
    """Wait until the new process creates a visible main window."""
    user32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = {"value": False}

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if "正在更新" in title:
                return True
            if process_id.value == pid and (title.startswith("DJI D-Log M") or "软件授权" in title):
                found["value"] = True
                return False
            # PyInstaller onefile child processes may own the visible window.
            if title.startswith("DJI D-Log M") or "软件授权" in title:
                found["value"] = True
                return False
            return True

        user32.EnumWindows(callback, 0)
        if found["value"]:
            return True
        time.sleep(0.5)
    return False


class UpdateEngine:
    def __init__(
        self,
        request: UpdateRequest,
        request_path: Path,
        on_state: Callable[[UpdateState], None] | None = None,
    ):
        self.request = request
        self.request_path = Path(request_path).resolve()
        self.updates_dir = self.request_path.parent
        self.app_root = Path(request.app_root).resolve()
        self.state_store = StateStore(self.updates_dir / "update_progress.json")
        self.on_state = on_state
        self._last_state = UpdateState("preparing", "准备中", 0)

    def _emit(
        self,
        stage: str,
        message: str,
        percent: float,
        *,
        downloaded: int = 0,
        total: int = 0,
        speed_bps: float = 0,
        eta_seconds: float | None = None,
        error: str = "",
        retryable: bool = False,
    ) -> None:
        state = UpdateState(
            stage=stage,
            message=message,
            percent=max(0.0, min(100.0, float(percent))),
            downloaded_bytes=downloaded,
            total_bytes=total,
            speed_bps=speed_bps,
            eta_seconds=eta_seconds,
            error=error,
            retryable=retryable,
        )
        self._last_state = state
        self.state_store.write(state)
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def _download_or_reuse(self) -> Path:
        destination = self.updates_dir / self.request.asset_name
        partial = destination.with_suffix(destination.suffix + ".part")
        if destination.exists():
            self._emit("verifying", "检测到已下载更新包，正在校验…", 56, total=destination.stat().st_size)
            try:
                self._verify_hash(destination)
                return destination
            except UpdateError:
                destination.unlink(missing_ok=True)

        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(self.request.url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                partial.unlink(missing_ok=True)
                existing = 0
                response = urllib.request.urlopen(
                    urllib.request.Request(self.request.url, headers={"User-Agent": USER_AGENT}),
                    timeout=60,
                )
            else:
                raise UpdateError(f"下载更新失败：HTTP {exc.code}") from exc
        except Exception as exc:
            raise UpdateError(f"连接更新服务器失败：{exc}") from exc

        if existing and getattr(response, "status", 200) != 206:
            response.close()
            partial.unlink(missing_ok=True)
            existing = 0
            response = urllib.request.urlopen(
                urllib.request.Request(self.request.url, headers={"User-Agent": USER_AGENT}),
                timeout=60,
            )

        content_length = int(response.headers.get("Content-Length") or 0)
        total = existing + content_length if content_length else int(self.request.asset_size or 0)
        downloaded = existing
        window_start = time.monotonic()
        window_bytes = downloaded
        try:
            with partial.open("ab" if existing else "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    elapsed = max(0.001, now - window_start)
                    speed = (downloaded - window_bytes) / elapsed
                    if elapsed > 0.75:
                        window_start = now
                        window_bytes = downloaded
                    eta = (total - downloaded) / speed if speed > 0 and total > downloaded else None
                    percent = 5.0 + (downloaded / total * 50.0 if total > 0 else 0.0)
                    self._emit(
                        "downloading",
                        "正在下载新版本…",
                        percent,
                        downloaded=downloaded,
                        total=total,
                        speed_bps=speed,
                        eta_seconds=eta,
                    )
        except Exception as exc:
            raise UpdateError(f"下载中断：{exc}") from exc
        finally:
            response.close()

        partial.replace(destination)
        return destination

    def _verify_hash(self, path: Path) -> None:
        expected = self.request.sha256.lower().strip()
        if not expected:
            raise UpdateError("更新请求缺少 SHA-256 校验值")
        total = max(1, path.stat().st_size)
        digest = hashlib.sha256()
        done = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                done += len(chunk)
                self._emit(
                    "verifying",
                    "正在校验更新包…",
                    56.0 + 9.0 * done / total,
                    downloaded=done,
                    total=total,
                )
        if digest.hexdigest().lower() != expected:
            path.unlink(missing_ok=True)
            raise UpdateError("SHA-256 校验失败，更新包已删除")

    def _extract(self, archive: Path) -> Path:
        stage = self.updates_dir / f"stage_{self.request.version}"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                total = max(1, sum(max(1, item.file_size) for item in members))
                done = 0
                last_emit = 0.0
                for index, item in enumerate(members, 1):
                    target = (stage / item.filename).resolve()
                    if not target.is_relative_to(stage.resolve()):
                        raise UpdateError("更新包包含非法路径")
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(item) as source, target.open("wb") as output:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            done += len(chunk)
                            now = time.monotonic()
                            if now - last_emit >= 0.2:
                                last_emit = now
                                self._emit(
                                    "extracting",
                                    "正在解压更新包…",
                                    65.0 + 15.0 * done / total,
                                    downloaded=done,
                                    total=total,
                                )
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"解压更新包失败：{exc}") from exc
        return stage

    def _stage_root(self, stage: Path) -> Path:
        preferred = stage / "DJI_DLogM_BatchGrader"
        if (preferred / APP_EXE).exists():
            return preferred
        for exe in stage.rglob(APP_EXE):
            return exe.parent
        raise UpdateError("更新包中未找到主程序")

    def _install(self, stage: Path) -> None:
        root = self._stage_root(stage)
        self.app_root.mkdir(parents=True, exist_ok=True)
        settings_path = self.app_root / "config" / "settings.json"
        settings_backup = settings_path.read_bytes() if settings_path.exists() else None
        custom_luts = self.app_root / "luts" / "custom"
        custom_backup = self.updates_dir / "custom_luts_backup"
        if custom_backup.exists():
            shutil.rmtree(custom_backup)
        if custom_luts.exists():
            shutil.copytree(custom_luts, custom_backup, dirs_exist_ok=True)

        candidates = [
            source for source in root.rglob("*")
            if source.is_file()
            and source.relative_to(root).parts[0] not in PROTECTED_TOP_LEVEL
        ]
        total = max(1, sum(max(1, source.stat().st_size) for source in candidates))
        done = 0
        try:
            for index, source in enumerate(candidates, 1):
                relative = source.relative_to(root)
                destination = self.app_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                done += max(1, source.stat().st_size)
                self._emit(
                    "installing",
                    "正在安装新版本…",
                    80.0 + 15.0 * done / total,
                    downloaded=done,
                    total=total,
                )
            if settings_backup is not None:
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                settings_path.write_bytes(settings_backup)
            if custom_backup.exists():
                if custom_luts.exists():
                    shutil.rmtree(custom_luts)
                custom_luts.mkdir(parents=True, exist_ok=True)
                shutil.copytree(custom_backup, custom_luts, dirs_exist_ok=True)
                shutil.rmtree(custom_backup, ignore_errors=True)
            old_internal = self.app_root / "_internal"
            if old_internal.exists() and not (root / "_internal").exists():
                shutil.rmtree(old_internal, ignore_errors=True)
        except Exception as exc:
            raise UpdateError(f"安装新版本失败：{exc}") from exc

    def _append_cleanup_log(self, message: str) -> None:
        try:
            self.updates_dir.mkdir(parents=True, exist_ok=True)
            line = (
                f"{datetime.now().astimezone().isoformat(timespec='seconds')} "
                f"{message}" + chr(10)
            )
            with (self.updates_dir / "cleanup.log").open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:
            pass

    @staticmethod
    def _version_key(value: str) -> tuple[int, ...]:
        parts = [int(x) for x in re.findall(r"\d+", value)[:4]]
        return tuple(parts + [0] * (4 - len(parts)))

    def _cleanup_updates_after_success(self) -> None:
        """Keep current + one previous archive; remove stale stages/partials."""
        current = self.request.version
        previous = self.request.current_version
        keep = {current}
        if previous:
            keep.add(previous)
        self._append_cleanup_log(
            f"cleanup start current={current} previous={previous or '-'} keep={sorted(keep)}"
        )
        for archive in sorted(self.updates_dir.glob("*.zip")):
            match = re.search(r"v(\d+(?:\.\d+){1,3})", archive.name, re.IGNORECASE)
            version = match.group(1) if match else ""
            if archive.name == self.request.asset_name or version in keep:
                self._append_cleanup_log(f"cleanup keep archive {archive.name}")
                continue
            try:
                archive.unlink()
                self._append_cleanup_log(f"cleanup removed archive {archive.name}")
            except Exception as exc:
                self._append_cleanup_log(f"cleanup failed archive {archive.name}: {exc}")
        for partial in sorted(self.updates_dir.glob("*.part")):
            try:
                partial.unlink()
                self._append_cleanup_log(f"cleanup removed partial {partial.name}")
            except Exception as exc:
                self._append_cleanup_log(f"cleanup failed partial {partial.name}: {exc}")
        for stage in sorted(self.updates_dir.glob("stage_*")):
            if not stage.is_dir():
                continue
            try:
                shutil.rmtree(stage)
                self._append_cleanup_log(f"cleanup removed stage {stage.name}")
            except Exception as exc:
                self._append_cleanup_log(f"cleanup failed stage {stage.name}: {exc}")
        backup = self.updates_dir / "custom_luts_backup"
        if backup.exists():
            try:
                shutil.rmtree(backup)
                self._append_cleanup_log("cleanup removed custom_luts_backup")
            except Exception as exc:
                self._append_cleanup_log(f"cleanup failed custom_luts_backup: {exc}")
        runtimes = sorted(
            self.updates_dir.glob("DJI_Updater_runtime_*.exe"),
            key=lambda item: item.stat().st_mtime,
        )
        for runtime in runtimes[:-1]:
            try:
                runtime.unlink()
                self._append_cleanup_log(f"cleanup removed updater runtime {runtime.name}")
            except Exception as exc:
                self._append_cleanup_log(f"cleanup failed runtime {runtime.name}: {exc}")
        self._append_cleanup_log("cleanup done")

    def _launch(self) -> None:
        exe = self.app_root / APP_EXE
        if not exe.exists():
            raise UpdateError("安装完成后未找到主程序")
        self._emit("launching", "正在启动新版本…", 97)
        try:
            process = subprocess.Popen(
                [str(exe)],
                cwd=str(self.app_root),
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            raise UpdateError(f"无法启动新版本：{exc}") from exc

        if not _wait_for_main_window(process.pid):
            raise UpdateError("新版本启动超时，请重试或退出后手动打开软件")
        self._emit("cleaning", "新版本已打开，正在清理旧版本文件…", 99)
        try:
            self._cleanup_updates_after_success()
        except Exception as exc:
            self._append_cleanup_log(f"cleanup top-level failure: {exc}")
        self._emit("completed", "新版本已成功打开", 100)

    def run(self) -> None:
        try:
            self._emit("preparing", "正在准备更新…", 1)
            archive = self._download_or_reuse()
            self._verify_hash(archive)
            stage = self._extract(archive)
            self._install(stage)
            self._launch()
        except Exception as exc:
            message = str(exc)
            self._emit(
                "failed",
                "更新失败",
                self._last_state.percent,
                error=message,
                retryable=True,
            )
            raise
