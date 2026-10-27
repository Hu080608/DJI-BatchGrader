"""3D .cube LUT parsing and a memory-friendly trilinear implementation."""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .paths import LUT_DIR, PROJECT_ROOT, project_path


class LutError(RuntimeError):
    """Base class for usable, user-facing LUT errors."""


class LutNotFoundError(LutError):
    pass


class LutConfirmationRequired(LutError):
    pass


@dataclass
class LutCandidate:
    path: Path
    reason: str


def _normalise_name(name: str) -> str:
    """Compare names while tolerating tabs / one-vs-two spaces and case."""
    return re.sub(r"\s+", " ", name.strip()).casefold()


def resolve_lut(
    requested: str | Path,
    *,
    confirm: Callable[[LutCandidate], bool] | None = None,
    assume_yes: bool = False,
) -> tuple[Path, bool]:
    """Resolve the configured LUT.

    Returns (path, exact_match).  The exact path is always tried first.  If it
    is absent, *.cube files under luts/ are searched by whitespace-normalised
    name and then by uniqueness.  A non-exact match requires confirmation unless
    assume_yes is True.
    """
    requested_path = project_path(requested)
    if requested_path.exists() and requested_path.is_file():
        return requested_path, True

    luts_dir = requested_path.parent if requested_path.parent.exists() else LUT_DIR
    candidates = sorted(
        (p for p in luts_dir.glob("*.cube") if p.is_file()),
        key=lambda p: p.name.casefold(),
    )
    wanted = _normalise_name(requested_path.name)
    normalised = [p for p in candidates if _normalise_name(p.name) == wanted]
    chosen: Path | None = None
    reason = ""
    if len(normalised) == 1:
        chosen = normalised[0]
        reason = "文件名仅空白字符不同（已按标准双空格规则匹配）"
    elif len(candidates) == 1:
        chosen = candidates[0]
        reason = "luts/ 目录下唯一的 .cube 文件"
    elif len(candidates) > 1:
        listing = "\n".join(f"  - {p.name}" for p in candidates)
        raise LutNotFoundError(
            "找不到指定的 LUT，且无法唯一自动匹配。\n"
            f"期望路径：{requested_path}\n"
            f"luts/ 目录候选：\n{listing}\n"
            "请把 LUT 放到上面的期望路径，或在 config/settings.json 的 "
            "lut_file 中填写准确文件名。"
        )

    if chosen is None:
        raise LutNotFoundError(
            "找不到 LUT 文件。\n"
            f"期望路径：{requested_path}\n"
            f"请将 LUT 文件放到：{LUT_DIR}\n"
            "LUT 文件名必须与 config/settings.json 的 lut_file 完全一致。\n"
            "注意：目标文件名中包含两个连续空格："
            "'DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube'"
        )

    candidate = LutCandidate(chosen, reason)
    if not assume_yes:
        if confirm is None:
            raise LutConfirmationRequired(
                f"未找到精确文件名，但发现可自动匹配的 LUT：\n{chosen}\n"
                f"原因：{reason}\n"
                "请在 GUI 中确认，或 CLI 添加 --yes 接受自动匹配。"
            )
        if not confirm(candidate):
            raise LutError(
                "用户未确认自动匹配的 LUT。请把正确 LUT 放到期望路径：\n"
                f"{requested_path}"
            )
    return chosen, False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _is_inside_project(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECT_ROOT)
        return True
    except ValueError:
        return False


def import_lut_into_project(
    source: str | Path,
    *,
    target_dir: Path | None = None,
) -> tuple[Path, bool]:
    """Return a project-local LUT path for a user-selected .cube file.

    A LUT chosen from outside the project is copied to ``luts/custom/`` so the
    bundled application remains self-contained.  A file already inside the
    project is used in place.  Same-name/different-content files are kept side
    by side with a numeric suffix.

    Returns (path, copied).
    """
    source_path = Path(source).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise LutError(f"LUT 文件不存在：{source_path}")
    if source_path.suffix.lower() != ".cube":
        raise LutError(f"只支持 .cube 格式的 3D LUT：{source_path}")
    if _is_inside_project(source_path):
        return source_path, False

    destination_dir = (target_dir or (LUT_DIR / "custom")).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source_path.name
    if destination.exists():
        if _sha256(destination) == _sha256(source_path):
            return destination, False
        index = 2
        while True:
            candidate = destination_dir / f"{source_path.stem}_{index}{source_path.suffix.lower()}"
            if not candidate.exists():
                destination = candidate
                break
            if _sha256(candidate) == _sha256(source_path):
                return candidate, False
            index += 1
    shutil.copy2(source_path, destination)
    return destination.resolve(), True


class CubeLUT:
    """Parsed 3D LUT with trilinear interpolation.

    .cube data rows are ordered with red varying fastest, i.e. the natural
    table is indexed as table[blue, green, red].  This is the same convention
    used by FFmpeg's lut3d filter and Resolve.
    """

    def __init__(self, size: int, table: np.ndarray, domain_min: np.ndarray, domain_max: np.ndarray, path: Path):
        self.size = int(size)
        self.table = table.astype(np.float32, copy=False)
        self.domain_min = domain_min.astype(np.float32, copy=False)
        self.domain_max = domain_max.astype(np.float32, copy=False)
        self.path = path
        self._flat = self.table.reshape((-1, 3))

    def pillow_filter(self):
        """Return a Pillow C-level Color3DLUT filter for fast 8-bit photos."""
        from PIL import ImageFilter

        return ImageFilter.Color3DLUT(
            self.size,
            self.table.reshape(-1).tolist(),
            channels=3,
            target_mode="RGB",
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "CubeLUT":
        path = Path(path)
        if not path.exists():
            raise LutNotFoundError(f"LUT 文件不存在：{path}")
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        size: int | None = None
        domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        values: list[tuple[float, float, float]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            upper = line.upper()
            if upper.startswith("TITLE"):
                continue
            if upper.startswith("LUT_3D_SIZE"):
                parts = line.split()
                if len(parts) < 2:
                    raise LutError("LUT_3D_SIZE 行格式错误")
                size = int(parts[1])
                continue
            if upper.startswith("DOMAIN_MIN"):
                nums = line.split()
                if len(nums) >= 4:
                    domain_min = np.array([float(x) for x in nums[1:4]], dtype=np.float32)
                continue
            if upper.startswith("DOMAIN_MAX"):
                nums = line.split()
                if len(nums) >= 4:
                    domain_max = np.array([float(x) for x in nums[1:4]], dtype=np.float32)
                continue
            if upper.startswith("LUT_3D_INPUT_RANGE"):
                nums = line.split()
                if len(nums) >= 3:
                    lo, hi = float(nums[1]), float(nums[2])
                    domain_min = np.array([lo, lo, lo], dtype=np.float32)
                    domain_max = np.array([hi, hi, hi], dtype=np.float32)
                continue
            if upper.startswith("LUT_1D_SIZE"):
                raise LutError("检测到 1D LUT；本软件只支持 3D .cube LUT（需要 LUT_3D_SIZE）")
            parts = line.split()
            if len(parts) >= 3:
                try:
                    values.append((float(parts[0]), float(parts[1]), float(parts[2])))
                except ValueError:
                    raise LutError(f"无法解析 LUT 数据行：{raw_line!r}") from None

        if size is None:
            raise LutError(f"LUT 缺少 LUT_3D_SIZE：{path}")
        if size < 2 or size > 129:
            raise LutError(f"不支持的 LUT_3D_SIZE={size}（支持 2..129）")
        expected = size ** 3
        if len(values) != expected:
            raise LutError(
                f"LUT 数据行数不正确：期望 {expected} 行（{size}^3），实际 {len(values)} 行。\n"
                f"文件：{path}"
            )
        if np.any(domain_max <= domain_min):
            raise LutError("LUT DOMAIN_MAX 必须大于 DOMAIN_MIN")
        data = np.asarray(values, dtype=np.float32)
        if not np.isfinite(data).all():
            raise LutError("LUT 数据包含 NaN/Inf")
        # R varies fastest. Reshape directly to [b, g, r, 3].
        table = data.reshape((size, size, size, 3))
        return cls(size, table, domain_min, domain_max, path)

    def transform(self, rgb: np.ndarray) -> np.ndarray:
        """Apply the LUT to an (N, 3) float RGB array in 0..1 display units."""
        if rgb.size == 0:
            return np.empty((0, 3), dtype=np.uint8)
        n = self.size
        span = self.domain_max - self.domain_min
        xyz = (rgb.astype(np.float32, copy=False) - self.domain_min) / span
        xyz = np.clip(xyz, 0.0, 1.0) * float(n - 1)
        i0 = np.floor(xyz).astype(np.int32)
        np.minimum(i0, n - 2, out=i0)
        frac = xyz - i0.astype(np.float32)
        fr = frac[:, 0:1]
        fg = frac[:, 1:2]
        fb = frac[:, 2:3]
        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]

        flat = self._flat
        base = (b0.astype(np.int32) * n + g0.astype(np.int32)) * n + r0.astype(np.int32)
        out = np.zeros((rgb.shape[0], 3), dtype=np.float32)
        # Accumulate eight weighted corners without keeping eight N x 3 arrays.
        for db, wb in ((0, 1.0 - fb), (1, fb)):
            for dg, wg in ((0, 1.0 - fg), (1, fg)):
                for dr, wr in ((0, 1.0 - fr), (1, fr)):
                    weight = wb * wg * wr
                    offset = (db * n + dg) * n + dr
                    out += flat[base + offset] * weight
        return np.clip(out, 0.0, 1.0)


def apply_lut_to_rgb_array(lut: CubeLUT, rgb_u8: np.ndarray) -> np.ndarray:
    """Apply a LUT to a uint8 RGB array. Keeps a single copy of the chunk."""
    h, w = rgb_u8.shape[:2]
    flat = rgb_u8.reshape((-1, 3)).astype(np.float32) / np.float32(255.0)
    graded = lut.transform(flat)
    return np.rint(graded * 255.0).astype(np.uint8).reshape((h, w, 3))
