"""Runtime updater for the DJI official LUT library.

The DJI Download Center page embeds a catalog of current transcode/LUT assets.
This module extracts new official .cube and LUT .zip links, downloads only the
new sources, validates every 3D LUT, installs it into luts/<Device>/<Category>/,
and appends metadata to luts/manifest.json.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .lut import CubeLUT
from .paths import LUT_DIR, PROJECT_ROOT

OFFICIAL_CATALOG_URL = "https://www.dji.com/cn/downloads/softwares/mavic-4-pro-dlog-m-to-rec709-lut"
MANIFEST_PATH = LUT_DIR / "manifest.json"
UPDATE_STATE_PATH = PROJECT_ROOT / "config" / "lut_update_state.json"
CACHE_DIR = PROJECT_ROOT / "temp" / "lut_update_cache"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DJI-DLogM-Grader/2.3"
DEFAULT_LUT_REL = "DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube"


@dataclass
class LutUpdateResult:
    checked_sources: int = 0
    new_sources: int = 0
    new_files: int = 0
    new_devices: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_reason: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _safe_component(name: str) -> str:
    name = urllib.parse.unquote(name)
    name = re.sub(r'[<>:"/\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "DJI Other"


def _quote_url(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?&=%#[]@!$'()*+,;~")


def _read_url(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(_quote_url(url), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_official_catalog(html: str) -> list[dict]:
    """Extract current LUT/transcoding sources from DJI's embedded catalog."""
    objects: dict[str, dict] = {}
    for match in re.finditer(r'"slug":"([^"]+)"', html):
        slug = match.group(1)
        start = html.rfind("{", 0, match.start())
        if start < 0:
            continue
        try:
            obj, _end = json.JSONDecoder().raw_decode(html[start:])
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("slug") != slug or "name" not in obj:
            continue
        objects[slug] = obj

    sources: list[dict] = []
    seen_urls: set[str] = set()
    for slug, obj in sorted(objects.items()):
        if obj.get("sub_category") != "transcoding":
            continue
        name = str(obj.get("name") or "")
        links = list(((obj.get("windows") or {}).get("links") or []))
        for link in links:
            url = str(link.get("url") or "")
            category = str(link.get("category") or "").lower()
            is_cube = category == ".cube" or url.lower().endswith(".cube")
            is_lut_zip = url.lower().endswith(".zip") and ("lut" in name.lower() or "3dlut" in name.lower())
            if not (is_cube or is_lut_zip):
                continue
            if slug == "transcoding-log-mode" or not url:
                continue
            products = obj.get("products") or []
            device = str((products[0].get("title") if products else "") or "DJI Other")
            category_name = "Color Grading" if "color grading" in name.lower() else "Normalization"
            lower = name.lower()
            profile = "D-Log M" if "d-log m" in lower else ("D-Log2" if "d-log2" in lower else ("D-Log" if "d-log" in lower else ""))
            source = {
                "slug": slug,
                "device": device,
                "category": category_name,
                "profile": profile,
                "name": name,
                "url": url,
                "format": ".cube" if is_cube else "zip",
                "version": str((obj.get("windows") or {}).get("version") or ""),
                "release_at": str((obj.get("windows") or {}).get("release_at") or ""),
                "source_page": OFFICIAL_CATALOG_URL,
            }
            key = url.casefold()
            if key not in seen_urls:
                seen_urls.add(key)
                sources.append(source)
    return sources


def fetch_official_sources(timeout: int = 60) -> list[dict]:
    html = _read_url(OFFICIAL_CATALOG_URL, timeout=timeout).decode("utf-8", errors="replace")
    sources = parse_official_catalog(html)
    if not sources:
        raise RuntimeError("DJI 官方目录未解析到任何 LUT 资源")
    return sources

def _unique_destination(folder: Path, filename: str, digest: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / _safe_component(filename)
    if not candidate.suffix:
        candidate = candidate.with_suffix(".cube")
    index = 2
    while candidate.exists():
        if _sha256_file(candidate) == digest:
            return candidate
        candidate = folder / f"{candidate.stem}_{index}.cube"
        index += 1
    return candidate


def _install_cube_bytes(source: dict, filename: str, data: bytes, target_dir: Path) -> dict | None:
    cache_file = CACHE_DIR / f"validate_{int(time.time() * 1000)}_{_safe_component(filename)}"
    cache_file.write_bytes(data)
    try:
        CubeLUT.from_file(cache_file)
    except Exception:
        cache_file.unlink(missing_ok=True)
        return None
    dest = _unique_destination(target_dir, filename, _sha256(data))
    if not dest.exists():
        dest.write_bytes(data)
    cache_file.unlink(missing_ok=True)
    return {
        "file": dest.relative_to(LUT_DIR).as_posix(),
        "device": _safe_component(str(source.get("device") or "DJI Other")),
        "profile": str(source.get("profile") or ""),
        "category": _safe_component(str(source.get("category") or "Normalization")),
        "name": Path(filename).stem,
        "description": f"{source.get('device', 'DJI')} · {source.get('name', '')} · {Path(filename).name}（DJI 官方同步）",
        "sha256": _sha256_file(dest),
        "source_url": str(source.get("url") or ""),
        "source_page": str(source.get("source_page") or OFFICIAL_CATALOG_URL),
        "version": str(source.get("version") or ""),
        "release_at": str(source.get("release_at") or ""),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def install_source(source: dict) -> tuple[list[dict], str]:
    """Download one official source and install all valid 3D LUT files."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = str(source.get("url") or "")
    fmt = str(source.get("format") or "")
    data = _read_url(url, timeout=120)
    device = _safe_component(str(source.get("device") or "DJI Other"))
    category = _safe_component(str(source.get("category") or "Normalization"))
    target_dir = LUT_DIR / device / category
    records: list[dict] = []
    if fmt == ".cube" or url.lower().endswith(".cube"):
        filename = Path(urllib.parse.urlsplit(url).path).name or f"{source.get('slug', 'lut')}.cube"
        record = _install_cube_bytes(source, filename, data, target_dir)
        if record:
            records.append(record)
            return records, ""
        return [], f"{source.get('name')}: 下载内容不是有效 3D LUT"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".cube") and not n.endswith("/")]
            if not members:
                return [], f"{source.get('name')}: ZIP 内没有 .cube 文件"
            for member in members:
                record = _install_cube_bytes(source, Path(member).name, archive.read(member), target_dir)
                if record:
                    records.append(record)
    except zipfile.BadZipFile:
        return [], f"{source.get('name')}: 下载的 ZIP 无效"
    return records, ""


def _write_sources_md(sources: list[dict]) -> None:
    lines = [
        "# DJI Official LUT Sources",
        "",
        "Generated by the application's runtime LUT updater.",
        "",
        "| Device | Category | LUT / pack | Source URL |",
        "|---|---|---|---|",
    ]
    for source in sources:
        name = str(source.get("name", "")).replace("|", r"\|")
        lines.append(f"| {source.get('device','')} | {source.get('category','')} | {name} | {source.get('url','')} |")
    lines.append("")
    (LUT_DIR / "SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


def _write_state(result: LutUpdateResult) -> None:
    UPDATE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_check": datetime.now().astimezone().isoformat(timespec="seconds"),
        "last_new_files": result.new_files,
        "last_errors": result.errors[-20:],
    }
    UPDATE_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def auto_lut_check_due(interval_hours: int = 24) -> bool:
    if not UPDATE_STATE_PATH.exists():
        return True
    try:
        data = json.loads(UPDATE_STATE_PATH.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(str(data["last_check"]))
        return datetime.now().astimezone() - last >= timedelta(hours=max(1, int(interval_hours)))
    except Exception:
        return True

def check_and_update_luts(progress_callback=None) -> LutUpdateResult:
    """Check DJI's official catalog and download only newly listed LUT sources."""
    result = LutUpdateResult()
    try:
        sources = fetch_official_sources()
    except Exception as exc:
        result.errors.append(f"读取 DJI 官方 LUT 目录失败：{exc}")
        _write_state(result)
        return result
    result.checked_sources = len(sources)
    manifest = {"version": 1, "default": DEFAULT_LUT_REL, "entries": []}
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    entries = list(manifest.get("entries") or [])
    existing_urls = {str(e.get("source_url") or "").casefold() for e in entries if e.get("source_url")}
    ignored_urls = {str(u).casefold() for u in (manifest.get("ignored_source_urls") or [])}
    new_sources = [
        s for s in sources
        if str(s.get("url") or "").casefold() not in existing_urls
        and str(s.get("url") or "").casefold() not in ignored_urls
    ]
    result.new_sources = len(new_sources)
    if not new_sources:
        result.skipped_reason = "DJI 官方 LUT 目录已是最新"
        _write_state(result)
        return result

    known_devices = {str(e.get("device") or "") for e in entries}
    for index, source in enumerate(new_sources, 1):
        if progress_callback:
            progress_callback(index, len(new_sources), str(source.get("name") or ""))
        try:
            records, error = install_source(source)
            if error:
                result.errors.append(error)
            elif records:
                entries.extend(records)
                result.new_files += len(records)
                for record in records:
                    device = str(record.get("device") or "")
                    if device and device not in known_devices:
                        known_devices.add(device)
                        result.new_devices.append(device)
            else:
                ignored_urls.add(str(source.get("url") or "").casefold())
        except Exception as exc:
            result.errors.append(f"{source.get('name')}: {exc}")

    # De-duplicate by (file, sha256), preserving the built-in order.
    deduped = []
    seen = set()
    for entry in entries:
        key = (str(entry.get("file") or ""), str(entry.get("sha256") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    manifest["version"] = 1
    manifest["default"] = str(manifest.get("default") or DEFAULT_LUT_REL)
    manifest["generated_at"] = datetime.now().strftime("%Y-%m-%d")
    manifest["source_catalog"] = OFFICIAL_CATALOG_URL
    manifest["count"] = len(deduped)
    manifest["entries"] = deduped
    manifest["ignored_source_urls"] = sorted(ignored_urls)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_sources_md(sources)
    (LUT_DIR / "DOWNLOAD_REPORT.json").write_text(
        json.dumps({"auto_update": True, "new_files": result.new_files, "errors": result.errors, "sources": sources},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_state(result)
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
    return result
