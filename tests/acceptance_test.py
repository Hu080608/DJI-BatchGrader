#!/usr/bin/env python3
"""End-to-end acceptance test. All input/output/temp files stay in the project."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["PYTHONUTF8"] = "1"

from dlog_grader.applog import AppLogger  # noqa: E402
from dlog_grader.config import AppConfig, load_config  # noqa: E402
from dlog_grader.ffmpeg_tools import find_ffmpeg, probe_media  # noqa: E402
from dlog_grader.lut import CubeLUT  # noqa: E402
from dlog_grader.paths import TEMP_DIR, child_environment, configure_environment  # noqa: E402
from dlog_grader.photo import PHOTO_EXTS, RAW_EXTS  # noqa: E402
from dlog_grader.processor import BatchProcessor, IGNORED_EXTS, VIDEO_EXTS  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def expected_output(src: Path, root: Path, out_root: Path) -> Path:
    rel = src.relative_to(root)
    ext = src.suffix.lower()
    if ext in VIDEO_EXTS:
        out_ext = ".mp4"
    elif ext in {".heic", ".heif"}:
        out_ext = ".jpg"
    elif ext in RAW_EXTS:
        out_ext = ".tif"
    else:
        out_ext = ext
    return out_root / rel.parent / f"{src.stem}_graded{out_ext}"


def extract_frame(ffmpeg: Path, video: Path, out_png: Path) -> np.ndarray:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ffmpeg), "-hide_banner", "-v", "error", "-y",
        "-ss", "1.0", "-i", str(video), "-frames:v", "1",
        "-pix_fmt", "rgb24", str(out_png),
    ]
    cp = subprocess.run(cmd, capture_output=True, env=child_environment(), cwd=str(PROJECT_ROOT))
    if cp.returncode != 0:
        raise AssertionError(cp.stderr.decode("utf-8", errors="replace"))
    return np.asarray(Image.open(out_png).convert("RGB"))


def main() -> int:
    configure_environment()
    input_dir = PROJECT_ROOT / "test_media" / "input"
    output_dir = PROJECT_ROOT / "test_media" / "output"
    if not input_dir.exists():
        print("缺少测试素材，先运行：python tests/make_test_media.py", file=sys.stderr)
        return 2
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs = [p for p in input_dir.rglob("*") if p.is_file()]
    original_hashes = {p: sha256(p) for p in inputs}
    supported = [p for p in inputs if p.suffix.lower() in PHOTO_EXTS | RAW_EXTS | VIDEO_EXTS]
    unsupported = [
        p for p in inputs
        if p.suffix.lower() not in PHOTO_EXTS | RAW_EXTS | VIDEO_EXTS
        and p.suffix.lower() not in IGNORED_EXTS
    ]
    ignored = [p for p in inputs if p.suffix.lower() in IGNORED_EXTS]
    if not supported:
        print("FAIL: 没有支持的测试输入", file=sys.stderr)
        return 1

    cfg = load_config()
    cfg.recursive = True
    cfg.overwrite = True
    cfg.output_profile = "h264_mp4"
    cfg.video_workers = 2
    cfg.photo_workers = 2
    cfg.write_reports = True
    cfg.audio_policy = "copy_then_aac"
    log = AppLogger()
    try:
        lut = CubeLUT.from_file(cfg.lut_path)
        processor = BatchProcessor(
            input_dir=input_dir,
            output_dir=output_dir,
            lut=lut,
            config=cfg,
            logger=log,
        )
        result = processor.run()
    finally:
        log.close()
    assert not result.failed, f"默认 LUT 批处理失败：{result.failures}"
    assert result.success == len(supported), (
        f"输出数量不符：成功 {result.success}，支持格式输入 {len(supported)}"
    )
    assert result.skipped_unsupported == len(unsupported), (
        f"忽略规则计数错误：跳过 {result.skipped_unsupported}，应为 {len(unsupported)}"
    )
    assert ignored, "测试素材缺少 .SRT 辅助字幕文件"
    assert result.jobs and all(job.status == "success" for job in result.jobs), "Job 状态未全部成功"
    assert result.duration_sec > 0, "批处理总耗时未记录"
    assert all(job.duration_sec is not None and job.duration_sec >= 0 for job in result.jobs), "单文件耗时未记录"
    assert result.report_json and Path(result.report_json).exists(), "JSON 报告未生成"
    assert result.report_csv and Path(result.report_csv).exists(), "CSV 报告未生成"
    report_data = json.loads(Path(result.report_json).read_text(encoding="utf-8"))
    assert report_data.get("duration_sec", 0) > 0, "报告缺少批处理耗时"
    assert report_data.get("scope") == "all", "报告缺少默认处理范围"
    assert "skipped_scope" in report_data, "报告缺少范围跳过计数"
    print(
        f"GUI 后端批处理通过：成功 {result.success}，失败 {result.failed}，"
        f"忽略 .SRT {len(ignored)} 个"
    )

    outputs = [p for p in output_dir.rglob("*") if p.is_file()]
    expected = {expected_output(src, input_dir, output_dir) for src in supported}
    actual = set(outputs)
    assert actual == expected, (
        "输出文件集合不符合预期。\n"
        f"缺少：{[str(p) for p in sorted(expected - actual)]}\n"
        f"多余：{[str(p) for p in sorted(actual - expected)]}"
    )

    # Original files must be byte-for-byte unchanged.
    for path, digest in original_hashes.items():
        assert sha256(path) == digest, f"原文件被修改：{path}"

    # No output should be generated for unsupported input.
    for path in unsupported:
        assert not expected_output(path, input_dir, output_dir).exists()

    # Photos: dimensions preserved and color changed.
    for src in supported:
        if src.suffix.lower() not in PHOTO_EXTS:
            continue
        dst = expected_output(src, input_dir, output_dir)
        with Image.open(src) as a, Image.open(dst) as b:
            assert a.size == b.size, f"照片分辨率改变：{src}"
            arr_a = np.asarray(a.convert("RGB")).astype(np.int16)
            arr_b = np.asarray(b.convert("RGB")).astype(np.int16)
        diff = float(np.abs(arr_a - arr_b).mean())
        assert diff > 1.0, f"照片颜色变化过小：{src} diff={diff}"
        print(f"照片通过：{src.name}  分辨率={a.size}  平均色差={diff:.2f}")

    # RAW: decode with LibRaw, preserve full output dimensions, write 16-bit TIFF.
    raw_sources = [src for src in supported if src.suffix.lower() in RAW_EXTS]
    for src in raw_sources:
        import rawpy
        import tifffile
        dst = expected_output(src, input_dir, output_dir)
        with rawpy.imread(str(src)) as raw:
            reference = raw.postprocess(
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                no_auto_bright=False,
                gamma=(2.222, 4.5),
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                highlight_mode=rawpy.HighlightMode.Blend,
                half_size=False,
            )
        graded = tifffile.imread(dst)
        assert graded.dtype == np.uint16, f"RAW 输出不是 16-bit：{graded.dtype}"
        assert graded.shape == reference.shape, (
            f"RAW 输出尺寸/通道异常：{graded.shape} vs {reference.shape}"
        )
        diff = float(
            np.abs(graded.astype(np.int32) - reference.astype(np.int32)).mean()
        )
        assert diff > 20.0, f"RAW LUT 未明显生效：{src} diff={diff}"
        print(f"RAW 通过：{src.name}  {graded.shape[1]}x{graded.shape[0]}  16-bit  平均色差={diff:.2f}")

    # Video: resolution/fps/duration/audio preserved; first frame visibly changed.
    ffmpeg = find_ffmpeg()
    temp = TEMP_DIR / "acceptance_frames"
    temp.mkdir(parents=True, exist_ok=True)
    for src in supported:
        if src.suffix.lower() not in VIDEO_EXTS:
            continue
        dst = expected_output(src, input_dir, output_dir)
        before = probe_media(ffmpeg, src)
        after = probe_media(ffmpeg, dst)
        assert before["width"] == after["width"] and before["height"] == after["height"], (
            f"视频分辨率改变：{src} {before} -> {after}"
        )
        assert before["fps"] and after["fps"] and abs(before["fps"] - after["fps"]) < 0.05, (
            f"视频帧率改变：{before} -> {after}"
        )
        assert before["duration"] and after["duration"] and abs(before["duration"] - after["duration"]) <= 0.15, (
            f"视频时长改变：{before} -> {after}"
        )
        assert after["has_audio"], f"输出视频丢失音频：{dst}"
        frame_a = extract_frame(ffmpeg, src, temp / f"{src.stem}_before.png")
        frame_b = extract_frame(ffmpeg, dst, temp / f"{src.stem}_after.png")
        assert frame_a.shape == frame_b.shape
        diff = float(np.abs(frame_a.astype(np.int16) - frame_b.astype(np.int16)).mean())
        assert diff > 1.0, f"视频画面颜色变化过小：diff={diff}"
        print(
            f"视频通过：{dst.name}  {after['width']}x{after['height']} "
            f"{after['fps']}fps {after['duration']}s 音频=有 平均色差={diff:.2f}"
        )



    # Explicit file list (as produced by GUI drag-and-drop) must process only
    # the dropped files, not every file in the parent folder.
    selected_root = TEMP_DIR / "selected_files_test"
    if selected_root.exists():
        shutil.rmtree(selected_root)
    selected_input = selected_root / "input"
    selected_output = selected_root / "output"
    selected_input.mkdir(parents=True)
    shutil.copy2(input_dir / "sample_photo.jpg", selected_input / "dropped.jpg")
    shutil.copy2(input_dir / "sample_photo_copy.jpg", selected_input / "not_selected.jpg")
    (selected_input / "dropped.srt").write_text("SRT sidecar must be ignored", encoding="utf-8")
    selected_cfg = AppConfig(**cfg.__dict__)
    selected_log = AppLogger()
    try:
        selected_result = BatchProcessor(
            input_dir=selected_input,
            output_dir=selected_output,
            lut=CubeLUT.from_file(cfg.lut_path),
            config=selected_cfg,
            logger=selected_log,
            selected_files=[selected_input / "dropped.jpg", selected_input / "dropped.srt"],
        ).run()
    finally:
        selected_log.close()
    selected_outputs = {p.name for p in selected_output.rglob("*") if p.is_file()}
    assert selected_result.success == 1 and not selected_result.failed
    assert selected_outputs == {"dropped_graded.jpg"}, selected_outputs
    print("拖拽文件列表测试通过：只处理显式选择的 1 个文件")

    # Import scope: video_only and video_raw must skip ordinary photos without
    # failing, and must report the skipped count.
    scope_root = TEMP_DIR / "scope_test"
    if scope_root.exists():
        shutil.rmtree(scope_root)
    scope_input = scope_root / "input"
    scope_input.mkdir(parents=True)
    shutil.copy2(input_dir / "sample_photo.jpg", scope_input / "still.jpg")
    shutil.copy2(input_dir / "sample_blackmagic.dng", scope_input / "still.dng")
    shutil.copy2(input_dir / "sample_clip.mp4", scope_input / "clip.mp4")
    for scope, expected_names, expected_skipped in (
        ("video_only", {"clip_graded.mp4"}, 2),
        ("video_raw", {"clip_graded.mp4", "still_graded.tif"}, 1),
    ):
        scope_output = scope_root / scope
        scope_cfg = AppConfig(**cfg.__dict__)
        scope_cfg.import_scope = scope
        scope_cfg.video_workers = 1
        scope_cfg.photo_workers = 1
        scope_cfg.write_reports = False
        scope_log = AppLogger()
        try:
            scope_result = BatchProcessor(
                input_dir=scope_input,
                output_dir=scope_output,
                lut=CubeLUT.from_file(cfg.lut_path),
                config=scope_cfg,
                logger=scope_log,
            ).run()
        finally:
            scope_log.close()
        assert not scope_result.failed, f"{scope} 处理失败：{scope_result.failures}"
        assert scope_result.skipped_scope == expected_skipped, (
            f"{scope} 跳过数量错误：{scope_result.skipped_scope} != {expected_skipped}"
        )
        names = {p.name for p in scope_output.rglob("*") if p.is_file()}
        assert names == expected_names, f"{scope} 输出错误：{names}"
        print(
            f"处理范围通过：{scope} 成功 {scope_result.success}，"
            f"范围跳过 {scope_result.skipped_scope}，输出 {sorted(names)}"
        )
    shutil.rmtree(scope_root)

    # Custom LUT: the same processor backend must accept an alternate LUT
    # without editing config/settings.json.
    custom_root = TEMP_DIR / "custom_lut_test"
    if custom_root.exists():
        shutil.rmtree(custom_root)
    custom_input = custom_root / "input"
    custom_output = custom_root / "output"
    custom_input.mkdir(parents=True)
    shutil.copy2(input_dir / "sample_photo.jpg", custom_input / "photo.jpg")
    invert_lut = custom_root / "invert_test.cube"
    lines = ["# Test invert LUT", "LUT_3D_SIZE 2"]
    for b in (0, 1):
        for g in (0, 1):
            for r in (0, 1):
                lines.append(f"{1 - r} {1 - g} {1 - b}")
    invert_lut.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    custom_cfg = AppConfig(**cfg.__dict__)
    custom_log = AppLogger()
    try:
        custom_lut = CubeLUT.from_file(invert_lut)
        custom_result = BatchProcessor(
            input_dir=custom_input,
            output_dir=custom_output,
            lut=custom_lut,
            config=custom_cfg,
            logger=custom_log,
        ).run()
    finally:
        custom_log.close()
    assert not custom_result.failed, f"自定义 LUT 批处理失败：{custom_result.failures}"
    custom_out = custom_output / "photo_graded.jpg"
    assert custom_out.exists(), "自定义 LUT 未生成输出"
    arr_custom = np.asarray(Image.open(custom_out).convert("RGB")).astype(np.int16)
    arr_src = np.asarray(Image.open(custom_input / "photo.jpg").convert("RGB")).astype(np.int16)
    custom_diff = float(np.abs(arr_custom - arr_src).mean())
    assert custom_diff > 80.0, f"自定义 LUT 未明显生效：diff={custom_diff}"
    default_cfg_text = (PROJECT_ROOT / "config" / "settings.json").read_text(encoding="utf-8")
    assert "DJI Air 3S/Normalization/DJI Air 3s DJI D-Log M to Rec.709.cube" in default_cfg_text, "默认 LUT 配置被意外修改"
    print(f"自定义 LUT 通过：{invert_lut.name}  平均色差={custom_diff:.2f}")

    # 10-bit HEVC output profile
    profile_root = TEMP_DIR / "profile_test"
    if profile_root.exists():
        shutil.rmtree(profile_root)
    profile_input = profile_root / "input"
    profile_output = profile_root / "output"
    profile_input.mkdir(parents=True)
    shutil.copy2(input_dir / "sample_clip.mp4", profile_input / "video.mp4")
    profile_cfg = AppConfig(**cfg.__dict__)
    profile_cfg.output_profile = "hevc10_mp4"
    profile_cfg.video_workers = 1
    profile_cfg.photo_workers = 1
    profile_log = AppLogger()
    try:
        profile_result = BatchProcessor(
            input_dir=profile_input, output_dir=profile_output,
            lut=CubeLUT.from_file(cfg.lut_path), config=profile_cfg, logger=profile_log,
        ).run()
    finally:
        profile_log.close()
    assert profile_result.success == 1 and not profile_result.failed
    profile_out = profile_output / "video_graded.mp4"
    assert profile_out.exists()
    profile_meta = probe_media(ffmpeg, profile_out)
    assert profile_meta["pix_fmt"] and "10" in profile_meta["pix_fmt"], profile_meta
    assert profile_meta["has_audio"]
    print(f"10-bit HEVC 输出通过：{profile_meta['video_codec']} / {profile_meta['pix_fmt']}")

    # PCM MOV audio must fall back to AAC when muxing into MP4.
    pcm_root = TEMP_DIR / "pcm_audio_test"
    if pcm_root.exists():
        shutil.rmtree(pcm_root)
    pcm_input = pcm_root / "input"
    pcm_output = pcm_root / "output"
    pcm_input.mkdir(parents=True)
    pcm_src = pcm_input / "pcm.mov"
    pcm_cmd = [
        str(ffmpeg), "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "pcm_s16le", "-shortest", str(pcm_src),
    ]
    subprocess.run(pcm_cmd, capture_output=True, env=child_environment(), timeout=60, check=True)
    pcm_cfg = AppConfig(**cfg.__dict__)
    pcm_cfg.video_workers = 1
    pcm_log = AppLogger()
    try:
        pcm_result = BatchProcessor(
            input_dir=pcm_input, output_dir=pcm_output,
            lut=CubeLUT.from_file(cfg.lut_path), config=pcm_cfg, logger=pcm_log,
        ).run()
    finally:
        pcm_log.close()
    assert pcm_result.success == 1 and not pcm_result.failed
    pcm_out = pcm_output / "pcm_graded.mp4"
    assert pcm_out.exists()
    pcm_meta = probe_media(ffmpeg, pcm_out)
    assert pcm_meta["has_audio"] and "aac" in [c.lower() for c in pcm_meta["audio_codecs"]]
    print(f"PCM→AAC 音频回退通过：{pcm_meta['audio_codecs']}")

    # Logs are project-local and exist.
    latest_log = PROJECT_ROOT / "logs" / "latest.log"
    assert latest_log.exists() and latest_log.stat().st_size > 0, "日志文件未生成"

    print("\nPASS：端到端验收测试全部通过。")
    print(f"输出位于项目内：{output_dir}")
    print(f"日志位于项目内：{latest_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
