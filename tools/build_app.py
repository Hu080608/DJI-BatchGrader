"""Build the standalone Windows application with Nuitka.

The public release contains compiled artifacts and runtime data only. Python
source, the license guard implementation and seller tooling are not copied.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlog_grader.config import AppConfig

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build_nuitka"
UPDATER_BUILD = ROOT / "build_updater"
DIST_DIR = ROOT / "dist"
TARGET = DIST_DIR / "DJI_DLogM_BatchGrader"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
VERSION4 = VERSION + ".0"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def include_zig_on_path() -> None:
    try:
        import ziglang
    except Exception:
        return
    zig_dir = Path(ziglang.__file__).resolve().parent
    if (zig_dir / "zig.exe").exists():
        os.environ["PATH"] = str(zig_dir) + os.pathsep + os.environ.get("PATH", "")


def assemble_runtime_data() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(BUILD_DIR / "main.dist", TARGET)
    duplicate_exe = TARGET / "DJI_DLogM_BatchGrader"
    if duplicate_exe.exists() and duplicate_exe.is_file():
        duplicate_exe.unlink()

    shutil.copytree(ROOT / "config", TARGET / "config")
    # Never publish machine-specific input/output paths from the developer's
    # local settings.json. Use safe application defaults for every release.
    (TARGET / "config" / "settings.json").write_text(
        json.dumps(asdict(AppConfig()), ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
    )
    shutil.copytree(ROOT / "luts", TARGET / "luts")

    tools_dir = TARGET / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tools" / "ffmpeg.exe", tools_dir / "ffmpeg.exe")
    preview_asset = ROOT / "assets" / "preview_sample.jpg"
    if preview_asset.exists():
        assets_target = TARGET / "assets"
        assets_target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(preview_asset, assets_target / "preview_sample.jpg")
    shutil.copy2(ROOT / "tools" / "README_FFMPEG.txt", tools_dir / "README_FFMPEG.txt")

    docs_dir = TARGET / "docs"
    images_dir = docs_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE_AND_TRIAL.md", "PRIVACY.md", "RELEASE_NOTES.md"):
        shutil.copy2(ROOT / "docs" / name, docs_dir / name)
    for image in (ROOT / "docs" / "images").glob("*.png"):
        shutil.copy2(image, images_dir / image.name)

    for name in (
        "README.md",
        "README_EXE.md",
        "VERSION",
        "LICENSE.txt",
        "COPYRIGHT.md",
        "THIRD_PARTY_NOTICES.md",
    ):
        shutil.copy2(ROOT / name, TARGET / name)

    updater_exe = UPDATER_BUILD / "DJI_Updater.exe"
    if not updater_exe.exists():
        raise RuntimeError(f"Updater build output not found: {updater_exe}")
    shutil.copy2(updater_exe, TARGET / "DJI_Updater.exe")

    for directory in ("license", "logs", "output", "reports", "temp", "updates"):
        path = TARGET / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    for stale in (
        TARGET / "config" / "queue_state.json",
        TARGET / "config" / "encoder_cache.json",
        TARGET / "config" / "lut_update_state.json",
    ):
        stale.unlink(missing_ok=True)

    # rawpy's raw_r.dll needs the MSVC runtime. Nuitka includes vcruntime140
    # but may not copy msvcp140 on a machine without Visual Studio.
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    runtime_candidates = [
        system_root / "System32" / "msvcp140.dll",
        ROOT / "tools" / "msvcp140.dll",
    ]
    for candidate in runtime_candidates:
        if candidate.exists():
            shutil.copy2(candidate, TARGET / "msvcp140.dll")
            break
    vcomp_candidate = Path(sys.prefix) / "Lib" / "site-packages" / "rawpy" / "vcomp140.dll"
    if vcomp_candidate.exists() and not (TARGET / "vcomp140.dll").exists():
        shutil.copy2(vcomp_candidate, TARGET / "vcomp140.dll")


def main() -> int:
    include_zig_on_path()
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if UPDATER_BUILD.exists():
        shutil.rmtree(UPDATER_BUILD)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=tk-inter",
        "--include-package=customtkinter",
        "--include-package-data=customtkinter",
        "--include-package=cryptography",
        "--include-package-data=cryptography",
        "--include-package=rawpy",
        "--include-package-data=rawpy",
        "--include-package=tifffile",
        "--include-package-data=tifffile",
        "--nofollow-import-to=cv2",
        "--nofollow-import-to=lxml",
        "--nofollow-import-to=imagecodecs",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ROOT / 'assets' / 'app.ico'}",
        "--assume-yes-for-downloads",
        f"--output-dir={BUILD_DIR}",
        "--output-filename=DJI_DLogM_BatchGrader.exe",
        "main.py",
    ]
    run(cmd)

    updater_cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--enable-plugin=tk-inter",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ROOT / 'assets' / 'app.ico'}",
        "--assume-yes-for-downloads",
        f"--output-dir={UPDATER_BUILD}",
        "--output-filename=DJI_Updater.exe",
        "updater_main.py",
    ]
    run(updater_cmd)
    assemble_runtime_data()
    print(f"Build complete: {TARGET / 'DJI_DLogM_BatchGrader.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
