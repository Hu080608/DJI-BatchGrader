"""Photo LUT grading using Pillow + the project-local trilinear LUT engine."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from .config import AppConfig
from .lut import CubeLUT

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif"}
HEIC_EXTS = {".heic", ".heif"}
# Common LibRaw-supported camera RAW containers. Actual decoding still
# depends on the bundled LibRaw version; unsupported files fail per-file.
RAW_EXTS = {
    ".3fr", ".arw", ".bay", ".cr2", ".cr3", ".dcr", ".dng", ".erf",
    ".fff", ".iiq", ".k25", ".kdc", ".mef", ".mos", ".mrw", ".nef",
    ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2", ".rwl", ".sr2",
    ".srf", ".srw", ".x3f",
}

_heif_available = False
try:  # Optional extra: pip install -r requirements-optional.txt
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _heif_available = True
except Exception:
    _heif_available = False

_raw_available = False
_tifffile_available = False
try:
    import rawpy  # type: ignore
    _raw_available = True
except Exception:
    rawpy = None  # type: ignore
try:
    import tifffile  # type: ignore
    _tifffile_available = True
except Exception:
    tifffile = None  # type: ignore


def heic_available() -> bool:
    return _heif_available


def raw_available() -> bool:
    return bool(_raw_available and _tifffile_available)


class PhotoCancelled(RuntimeError):
    pass


def _alpha_from(image: Image.Image) -> Image.Image | None:
    if image.mode in ("RGBA", "LA"):
        return image.getchannel("A")
    if image.mode == "P" and "transparency" in image.info:
        return image.convert("RGBA").getchannel("A")
    return None


def process_photo(
    *,
    input_path: Path,
    output_path: Path,
    lut: CubeLUT,
    config: AppConfig,
    lut_strength: float = 1.0,
    cancel_callback: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
    chunk_rows: int = 256,
) -> None:
    """Apply the LUT to one photo and save at the original pixel dimensions."""
    suffix = input_path.suffix.lower()
    if suffix in HEIC_EXTS and not _heif_available:
        raise RuntimeError(
            "当前环境未安装 HEIC 支持。请运行："
            "pip install -r requirements-optional.txt"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_path) as opened:
        opened.load()
        width, height = opened.size
        alpha = _alpha_from(opened)
        rgb_source = opened.convert("RGB")
        exif = opened.info.get("exif")
        icc_profile = opened.info.get("icc_profile")
        dpi = opened.info.get("dpi")
        n_frames = getattr(opened, "n_frames", 1)
        if log and n_frames > 1:
            log(f"多帧图片仅处理第一帧：{input_path.name}（共 {n_frames} 帧）")

        graded = Image.new("RGB", (width, height))
        pillow_lut = lut.blended(lut_strength).pillow_filter()
        total_chunks = max(1, (height + chunk_rows - 1) // chunk_rows)
        for index, y in enumerate(range(0, height, chunk_rows)):
            if cancel_callback and cancel_callback():
                raise PhotoCancelled("用户取消图片处理")
            bottom = min(y + chunk_rows, height)
            rgb_chunk = rgb_source.crop((0, y, width, bottom))
            graded_chunk = rgb_chunk.filter(pillow_lut)
            graded.paste(graded_chunk, (0, y))
            if progress_callback:
                progress_callback((index + 1) / total_chunks)
            if log and index > 0 and index % 8 == 0:
                log(f"图片处理中：{input_path.name} ({index + 1}/{total_chunks})")

        if alpha is not None:
            final_image: Image.Image = graded.convert("RGBA")
            final_image.putalpha(alpha)
        else:
            final_image = graded

        out_suffix = output_path.suffix.lower()
        save_kwargs: dict = {}
        if exif:
            save_kwargs["exif"] = exif
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile
        if dpi:
            save_kwargs["dpi"] = dpi

        if out_suffix in {".jpg", ".jpeg"}:
            if final_image.mode not in ("RGB", "L"):
                final_image = final_image.convert("RGB")
            save_kwargs.update(
                format="JPEG",
                quality=int(config.jpeg_quality),
                optimize=True,
                progressive=True,
            )
        elif out_suffix == ".png":
            save_kwargs.update(
                format="PNG",
                compress_level=int(config.png_compress_level),
                optimize=False,
            )
        elif out_suffix in {".tif", ".tiff"}:
            save_kwargs.update(
                format="TIFF",
                compression=config.tiff_compression,
            )
            if alpha is None and final_image.mode != "RGB":
                final_image = final_image.convert("RGB")
        else:
            # HEIC inputs normally produce JPG outputs; keep a safe fallback.
            save_kwargs.update(format="JPEG", quality=int(config.jpeg_quality))
            final_image = final_image.convert("RGB")

        try:
            final_image.save(output_path, **save_kwargs)
        except Exception:
            try:
                output_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def process_raw_photo(
    *,
    input_path: Path,
    output_path: Path,
    lut: CubeLUT,
    config: AppConfig,
    lut_strength: float = 1.0,
    cancel_callback: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
    chunk_rows: int = 128,
) -> None:
    """Decode a camera RAW and export a 16-bit sRGB TIFF after LUT grading.

    White balance: use the camera-recorded WB when available, otherwise LibRaw
    auto WB.  Color space: LibRaw postprocesses to sRGB with the standard
    sRGB transfer curve.  The LUT is applied in float32 in chunks and the result
    is written as 16-bit RGB TIFF so the decoded bit depth is not truncated.
    """
    if not raw_available():
        raise RuntimeError(
            "当前环境未安装 RAW 支持。请安装 rawpy 和 tifffile，"
            "或使用包含 RAW 依赖的发布包。"
        )
    assert rawpy is not None and tifffile is not None
    if input_path.suffix.lower() not in RAW_EXTS:
        raise RuntimeError(f"不支持的 RAW 扩展名：{input_path.suffix}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with rawpy.imread(str(input_path)) as raw:
            camera_wb = list(getattr(raw, "camera_whitebalance", []) or [])
            use_camera_wb = any(abs(float(value)) > 0 for value in camera_wb)
            log and log(
                f"RAW 解码：{input_path.name}，白平衡="
                f"{'相机' if use_camera_wb else '自动'}，输出色彩空间=sRGB"
            )
            rgb16 = raw.postprocess(
                use_camera_wb=use_camera_wb,
                use_auto_wb=not use_camera_wb,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                gamma=(2.222, 4.5),
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                highlight_mode=rawpy.HighlightMode.Blend,
                half_size=False,
            )
    except Exception as exc:
        raise RuntimeError(f"RAW 解码失败：{input_path.name}：{exc}") from exc

    if rgb16.ndim != 3 or rgb16.shape[2] != 3 or rgb16.dtype != np.uint16:
        raise RuntimeError(f"RAW 解码结果格式异常：{input_path.name}")
    height = int(rgb16.shape[0])
    width = int(rgb16.shape[1])
    graded16 = np.empty_like(rgb16)
    effective_lut = lut.blended(lut_strength)
    total_chunks = max(1, (height + chunk_rows - 1) // chunk_rows)
    try:
        for index, y in enumerate(range(0, height, chunk_rows)):
            if cancel_callback and cancel_callback():
                raise PhotoCancelled("用户取消 RAW 图片处理")
            bottom = min(y + chunk_rows, height)
            chunk = rgb16[y:bottom].reshape((-1, 3)).astype(np.float32) / 65535.0
            graded = effective_lut.transform(chunk)
            graded16[y:bottom] = np.rint(graded * 65535.0).astype(np.uint16).reshape(
                (bottom - y, width, 3)
            )
            if progress_callback:
                progress_callback((index + 1) / total_chunks)
            if log and index > 0 and index % 8 == 0:
                log(f"RAW 处理中：{input_path.name} ({index + 1}/{total_chunks})")

        out_suffix = output_path.suffix.lower()
        if out_suffix in {".tif", ".tiff"}:
            tifffile.imwrite(
                output_path,
                graded16,
                photometric="rgb",
                compression="zlib",
                metadata={"software": "DJI D-Log M Batch Grader"},
            )
        elif out_suffix in {".jpg", ".jpeg"}:
            u8 = np.rint(graded16.astype(np.float32) / 257.0).astype(np.uint8)
            Image.fromarray(u8, "RGB").save(
                output_path,
                format="JPEG",
                quality=int(config.jpeg_quality),
                optimize=True,
                progressive=True,
            )
        else:
            raise RuntimeError(f"RAW 输出格式只支持 TIFF/JPEG：{output_path.suffix}")
    except Exception:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
