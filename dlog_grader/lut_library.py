"""Recursive LUT library scanning with optional manifest metadata."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import LUT_DIR


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class LutEntry:
    path: Path
    device: str
    category: str
    name: str
    description: str = ""
    profile: str = ""
    sha256: str = ""
    is_builtin: bool = False

    @property
    def origin(self) -> str:
        return "默认" if self.is_builtin else "自定义"

    @property
    def label(self) -> str:
        parts = [self.device]
        if self.category and self.category not in {"默认", "Normalization"}:
            parts.append(self.category)
        parts.append(self.name)
        return " / ".join(parts)


def _load_manifest(root: Path) -> tuple[dict[str, dict], str | None]:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {}, None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {}
        for item in data.get("entries", []):
            if isinstance(item, dict) and item.get("file"):
                entries[str(item["file"]).replace("\\", "/")] = item
        return entries, data.get("default")
    except Exception:
        return {}, None


def scan_lut_library(root: Path | None = None) -> tuple[list[LutEntry], Path | None]:
    """Scan all .cube files below luts/, including device subdirectories.

    Expected optional structure:
      luts/<Device>/<Normalization|Color Grading>/<look>.cube
    """
    root = (root or LUT_DIR).resolve()
    manifest, default_file = _load_manifest(root)
    entries: list[LutEntry] = []
    for path in sorted(root.rglob("*.cube"), key=lambda p: str(p).casefold()):
        rel = path.relative_to(root)
        parts = rel.parts
        if len(parts) == 1:
            device, category = "通用", "默认"
        elif len(parts) == 2:
            device, category = parts[0], "默认"
        else:
            device, category = parts[0], parts[-2]
        rel_posix = rel.as_posix()
        meta = manifest.get(rel_posix, {})
        desc = str(meta.get("description", ""))
        name = str(meta.get("name") or path.stem)
        profile = str(meta.get("profile", ""))
        is_builtin = bool(meta) and parts[0].casefold() != "custom"
        entries.append(LutEntry(
            path=path,
            device=str(meta.get("device") or device),
            category=str(meta.get("category") or category),
            name=name,
            description=desc,
            profile=profile,
            sha256=str(meta.get("sha256", "")),
            is_builtin=is_builtin,
        ))
    default_path = root / default_file if default_file else None
    return entries, default_path


def validate_lut_manifest(root: Path | None = None) -> list[str]:
    """Return human-readable manifest problems (missing files/hash mismatch)."""
    root = (root or LUT_DIR).resolve()
    manifest, _default = _load_manifest(root)
    problems: list[str] = []
    for rel, meta in manifest.items():
        path = root / rel
        if not path.exists():
            problems.append(f"清单文件不存在：{rel}")
        elif meta.get("sha256") and _sha256(path) != str(meta["sha256"]):
            problems.append(f"清单校验失败：{rel}")
    return problems
