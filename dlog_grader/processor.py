"""Batch discovery and orchestration."""
from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .applog import AppLogger
from .config import AppConfig
from .encoders import EncoderChoice, choose_encoder
from .ffmpeg_tools import (
    FFmpegCancelled,
    FFmpegError,
    find_ffmpeg,
    ffmpeg_version,
    probe_media,
    transcode_video,
)
from .formats import OutputProfile, get_output_profile
from .jobs import JobRecord, QueueStore, format_duration_hms, now_iso
from .lut import CubeLUT
from .paths import PROJECT_ROOT, TEMP_DIR
from .photo import HEIC_EXTS, PHOTO_EXTS, RAW_EXTS, PhotoCancelled, process_photo, process_raw_photo

VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
IGNORED_EXTS = {".srt"}
SUPPORTED_EXTS = PHOTO_EXTS | RAW_EXTS | VIDEO_EXTS

SCOPE_VIDEO_ONLY = "video_only"
SCOPE_VIDEO_RAW = "video_raw"
SCOPE_ALL = "all"
DEFAULT_SCOPE = SCOPE_ALL
SCOPE_LABELS = {
    SCOPE_VIDEO_ONLY: "只处理视频",
    SCOPE_VIDEO_RAW: "处理视频 + RAW",
    SCOPE_ALL: "全部处理",
}


def normalize_scope(scope: str | None) -> str:
    value = str(scope or DEFAULT_SCOPE)
    return value if value in SCOPE_LABELS else DEFAULT_SCOPE


def is_ext_in_scope(ext: str, scope: str | None = None) -> bool:
    value = ext.lower()
    selected = normalize_scope(scope)
    if value in VIDEO_EXTS:
        return True
    if selected == SCOPE_VIDEO_ONLY:
        return False
    if value in RAW_EXTS:
        return True
    if selected == SCOPE_VIDEO_RAW:
        return False
    return value in PHOTO_EXTS


def is_file_in_scope(path: Path, scope: str | None = None) -> bool:
    return is_ext_in_scope(path.suffix, scope)


class BatchError(RuntimeError):
    pass


class BatchCancelled(RuntimeError):
    pass


@dataclass
class BatchResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped_unsupported: int = 0
    skipped_existing: int = 0
    skipped_scope: int = 0
    cancelled: bool = False
    failures: list[str] = field(default_factory=list)
    scope_skipped_files: list[str] = field(default_factory=list)
    jobs: list[JobRecord] = field(default_factory=list)
    report_json: str = ""
    report_csv: str = ""
    encoder: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_sec: float = 0.0

    @property
    def processed(self) -> int:
        return self.success + self.failed + self.skipped_existing


@dataclass
class MediaItem:
    source: Path
    rel_path: Path
    kind: str  # photo / video
    output: Path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _unique_output(path: Path, used: set[Path]) -> Path:
    if path not in used:
        used.add(path)
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if candidate not in used:
            used.add(candidate)
            return candidate
        index += 1


def collect_media(
    input_dir: Path,
    output_dir: Path,
    *,
    recursive: bool,
    suffix: str,
    log: AppLogger,
    selected_files: list[Path] | None = None,
    video_out_ext: str = ".mp4",
    scope: str = DEFAULT_SCOPE,
    skipped_scope: list[Path] | None = None,
) -> tuple[list[MediaItem], int]:
    """Discover supported files, preserving relative paths.

    If selected_files is provided, only those explicitly dropped/selected files
    are considered. Otherwise the input folder is scanned.
    """
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    items: list[MediaItem] = []
    unsupported = 0
    used_outputs: set[Path] = set()

    def add_source(source: Path) -> None:
        nonlocal unsupported
        source = source.resolve()
        if not source.exists() or not source.is_file():
            unsupported += 1
            log.warning(f"跳过不存在或不是文件的条目：{source}")
            return
        if _is_relative_to(source, output_dir):
            return
        ext = source.suffix.lower()
        if ext in IGNORED_EXTS:
            log.info(f"忽略辅助字幕文件：{source}")
            return
        if ext not in SUPPORTED_EXTS:
            unsupported += 1
            log.warning(f"跳过不支持格式：{source}")
            return
        if not is_ext_in_scope(ext, scope):
            if skipped_scope is not None:
                skipped_scope.append(source)
            log.info(f"按处理范围跳过：{source}")
            return
        try:
            rel = source.relative_to(input_dir)
        except ValueError:
            rel = Path(source.name)
        if ext in VIDEO_EXTS:
            kind = "video"
            out_ext = video_out_ext
        elif ext in RAW_EXTS:
            kind = "photo"
            out_ext = ".tif"
        elif ext in HEIC_EXTS:
            kind = "photo"
            out_ext = ".jpg"
        else:
            kind = "photo"
            out_ext = ext
        out_name = f"{source.stem}{suffix}{out_ext}"
        out_path = _unique_output(output_dir / rel.parent / out_name, used_outputs)
        items.append(MediaItem(source, rel, kind, out_path))

    if selected_files is not None:
        seen: set[Path] = set()
        for raw in sorted(Path(p) for p in selected_files):
            resolved = raw.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            add_source(resolved)
        return items, unsupported

    if recursive:
        walker: Iterable[tuple[str, list[str], list[str]]] = os.walk(input_dir, followlinks=False)
    else:
        try:
            names = sorted(
                name for name in os.listdir(input_dir)
                if (input_dir / name).is_file()
            )
        except OSError as exc:
            raise BatchError(f"无法读取输入目录：{input_dir}\n{exc}") from exc
        walker = [(str(input_dir), [], names)]

    for root, dirs, files in walker:
        root_path = Path(root)
        dirs.sort(key=str.casefold)
        files.sort(key=str.casefold)
        # Never scan our output subtree when it is nested under input.
        dirs[:] = [
            d for d in dirs
            if not _is_relative_to((root_path / d).resolve(), output_dir)
        ]
        for name in files:
            add_source(root_path / name)
    return items, unsupported


def validate_folders(input_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise BatchError(f"输入文件夹不存在或不是文件夹：{input_dir}")
    if input_dir == output_dir:
        raise BatchError("输入文件夹和输出文件夹不能相同。为保护原文件，请选择独立输出目录。")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BatchError(f"无法创建输出目录：{output_dir}\n{exc}") from exc
    if not os.access(output_dir, os.W_OK):
        raise BatchError(f"输出目录不可写：{output_dir}")
    return input_dir, output_dir


class BatchProcessor:
    def __init__(
        self,
        *,
        input_dir: Path,
        output_dir: Path,
        lut: CubeLUT,
        config: AppConfig,
        logger: AppLogger,
        cancel_callback: Callable[[], bool] | None = None,
        progress_callback: Callable[[float, str, BatchResult], None] | None = None,
        job_callback: Callable[[dict], None] | None = None,
        dry_run: bool = False,
        selected_files: list[Path] | None = None,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.lut = lut
        self.config = config
        self.log = logger
        self.cancel_callback = cancel_callback or (lambda: False)
        self.progress_callback = progress_callback
        self.job_callback = job_callback
        self.dry_run = dry_run
        self.selected_files = list(selected_files) if selected_files else None
        self.profile = get_output_profile(config.output_profile)
        self.queue_store = QueueStore()
        self._progress_lock = threading.Lock()
        self._job_progress: dict[int, float] = {}

    def _cancelled(self) -> bool:
        return bool(self.cancel_callback and self.cancel_callback())

    def _emit(self, frac: float, detail: str, result: BatchResult) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(max(0.0, min(1.0, frac)), detail, result)
            except Exception:
                pass

    def _notify_job(self, job: JobRecord) -> None:
        if self.job_callback:
            try:
                self.job_callback(job.to_dict())
            except Exception:
                pass

    def _set_job_status(self, job: JobRecord, status: str, **fields) -> None:
        job.status = status
        for key, value in fields.items():
            setattr(job, key, value)
        if status in {"success", "failed", "cancelled", "skipped"}:
            job.progress = 1.0
            if not job.finished_at:
                job.finished_at = now_iso()
            with self._progress_lock:
                self._job_progress[job.job_id] = 1.0
        self._notify_job(job)

    def _set_job_progress(self, job: JobRecord, fraction: float) -> None:
        fraction = max(0.0, min(1.0, float(fraction)))
        if fraction < 1.0 and abs(fraction - job.progress) < 0.02:
            return
        job.progress = fraction
        with self._progress_lock:
            self._job_progress[job.job_id] = fraction
        self._notify_job(job)
        if getattr(self, "_active_result", None) is not None:
            self._emit_overall(
                f"正在处理：{job.relative} ({fraction * 100:.0f}%)",
                self._active_result,
            )

    def _emit_overall(self, detail: str, result: BatchResult) -> None:
        total = max(1, len(getattr(self, "_all_jobs", [])))
        with self._progress_lock:
            current = sum(self._job_progress.values())
        self._emit(min(1.0, current / total), detail, result)

    def _process_job(self, item: MediaItem, job: JobRecord, ffmpeg, encoder) -> str:
        if self._cancelled():
            self._set_job_status(job, "cancelled", error="用户在任务开始前取消")
            return "cancelled"
        job.started_at = now_iso()
        self._set_job_status(job, "running")
        started = time.perf_counter()
        try:
            item.output.parent.mkdir(parents=True, exist_ok=True)
            if item.kind == "video":
                assert ffmpeg is not None and encoder is not None
                info = probe_media(ffmpeg, item.source)
                duration = info.get("duration")
                self.log.info(
                    f"视频：{item.rel_path} "
                    f"({info.get('width')}x{info.get('height')}, "
                    f"{info.get('fps')} fps, {duration}s, "
                    f"编码={info.get('video_codec')}, 音频={info.get('audio_codecs')})"
                )
                job_temp = TEMP_DIR / f"job_{os.getpid()}_{job.job_id}_{item.source.stem[:24]}"
                try:
                    result = transcode_video(
                        ffmpeg=ffmpeg,
                        input_path=item.source,
                        output_path=item.output,
                        lut_path=self.lut.path,
                        job_temp_dir=job_temp,
                        duration=duration,
                        profile=self.profile,
                        encoder=encoder,
                        crf=self.config.video_crf,
                        preset=self.config.video_preset,
                        audio_bitrate=self.config.audio_bitrate,
                        hardware_bitrate=self.config.hardware_bitrate,
                        audio_policy=self.config.audio_policy,
                        source_audio_codecs=info.get("audio_codecs", []),
                        input_height=info.get("height"),
                        lut_interp=getattr(self.config, "video_lut_interp", "tetrahedral"),
                        cancel_callback=self._cancelled,
                        progress_callback=lambda frac: self._set_job_progress(job, frac),
                        log_callback=lambda msg: self.log.info(f"{item.rel_path}: {msg}"),
                    )
                    job.encoder = result.get("encoder", "")
                    job.audio_mode = result.get("audio_mode", "")
                    job.attempts = len(result.get("attempts", []))
                finally:
                    if not self.config.keep_temp:
                        shutil.rmtree(job_temp, ignore_errors=True)
            elif item.source.suffix.lower() in RAW_EXTS:
                process_raw_photo(
                    input_path=item.source,
                    output_path=item.output,
                    lut=self.lut,
                    config=self.config,
                    cancel_callback=self._cancelled,
                    log=lambda msg: self.log.info(msg),
                    progress_callback=lambda frac: self._set_job_progress(job, frac),
                )
            else:
                process_photo(
                    input_path=item.source,
                    output_path=item.output,
                    lut=self.lut,
                    config=self.config,
                    cancel_callback=self._cancelled,
                    log=lambda msg: self.log.info(msg),
                    progress_callback=lambda frac: self._set_job_progress(job, frac),
                )
            job.duration_sec = round(time.perf_counter() - started, 3)
            self._set_job_status(job, "success")
            self.log.info(f"完成：{item.rel_path} -> {item.output}")
            return "success"
        except (PhotoCancelled, FFmpegCancelled) as exc:
            job.duration_sec = round(time.perf_counter() - started, 3)
            self._set_job_status(job, "cancelled", error=str(exc))
            self.log.warning(f"已取消：{item.rel_path}")
            return "cancelled"
        except Exception as exc:
            job.duration_sec = round(time.perf_counter() - started, 3)
            error = str(exc)
            self._set_job_status(job, "failed", error=error[-1600:])
            self.log.exception(f"处理失败：{item.rel_path}", exc)
            return "failed"

    def run(self) -> BatchResult:
        input_dir, output_dir = validate_folders(self.input_dir, self.output_dir)
        self.input_dir, self.output_dir = input_dir, output_dir
        result = BatchResult()
        self._active_result = result
        started_at = now_iso()
        self._run_started_perf = time.perf_counter()
        result.started_at = started_at

        self.log.info(f"输入目录：{input_dir}")
        if self.selected_files:
            self.log.info(f"拖入文件数：{len(self.selected_files)}（仅处理这些文件）")
        self.log.info(f"输出目录：{output_dir}")
        self.log.info(f"LUT：{self.lut.path.name}")
        self.log.info(f"LUT 实际路径：{self.lut.path}")
        self.log.info(f"LUT 尺寸：{self.lut.size}^3")
        self.log.info(f"输出格式：{self.profile.label}")
        self.log.info(f"递归子目录：{'是' if self.config.recursive else '否'}")
        self.log.info(f"输出后缀：{self.config.output_suffix}")
        scope = normalize_scope(getattr(self.config, "import_scope", DEFAULT_SCOPE))
        self.log.info(f"处理范围：{SCOPE_LABELS[scope]}")

        scope_skipped: list[Path] = []
        items, unsupported = collect_media(
            input_dir,
            output_dir,
            recursive=bool(self.config.recursive),
            suffix=str(self.config.output_suffix),
            log=self.log,
            selected_files=self.selected_files,
            video_out_ext=self.profile.extension,
            scope=scope,
            skipped_scope=scope_skipped,
        )
        jobs = [
            JobRecord(
                job_id=index,
                source=str(item.source),
                relative=str(item.rel_path),
                output=str(item.output),
                kind=item.kind,
            )
            for index, item in enumerate(items)
        ]
        result.total = len(items)
        result.skipped_unsupported = unsupported
        result.skipped_scope = len(scope_skipped)
        result.scope_skipped_files = [str(path) for path in scope_skipped]
        result.jobs = jobs
        self._all_jobs = jobs
        for job in jobs:
            self._notify_job(job)
        with self._progress_lock:
            self._job_progress = {job.job_id: 0.0 for job in jobs}
        self.queue_store.save_state(jobs, status="prepared")

        if unsupported:
            self.log.info(f"已跳过 {unsupported} 个不支持的文件（详见上方日志）")
        if scope_skipped:
            self.log.info(
                f"已按处理范围跳过 {len(scope_skipped)} 个文件（{SCOPE_LABELS[scope]}）"
            )
        self.log.info(f"发现 {len(items)} 个符合当前处理范围的照片/视频文件")
        self._emit(0.0, "扫描完成", result)

        pending: list[tuple[MediaItem, JobRecord]] = []
        for item, job in zip(items, jobs):
            if item.output.exists() and not self.config.overwrite:
                result.skipped_existing += 1
                self._set_job_status(job, "skipped", error="输出已存在，按设置为跳过")
                self.log.warning(f"已存在，跳过：{item.output}")
            else:
                pending.append((item, job))
        self.queue_store.save_state(jobs, status="prepared")

        if not items:
            self.log.warning(
                "没有找到可处理的文件。当前处理范围："
                f"{SCOPE_LABELS[scope]}；支持 JPG/JPEG/PNG/TIF/TIFF/HEIC、"
                "常见 RAW（DNG/CR2/CR3/NEF/ARW 等）+ MP4/MOV/M4V；SRT 自动忽略"
            )
            self._finish_report(result, input_dir, output_dir, started_at, finished=False)
            self._emit(1.0, "没有可处理的文件", result)
            return result

        if self._cancelled():
            result.cancelled = True
            for job in jobs:
                if job.status == "pending":
                    self._set_job_status(job, "cancelled", error="批处理开始前取消")
            self.log.warning("批处理已取消（尚未开始）")
            self._finish_report(result, input_dir, output_dir, started_at, finished=False)
            return result

        source_bytes = sum(item.source.stat().st_size for item, _job in pending if item.source.exists())
        factor = 3.0 if self.profile.family == "prores" else 1.6
        required = int(source_bytes * factor) + 512 * 1024 * 1024
        try:
            free = shutil.disk_usage(output_dir).free
            self.log.info(
                f"磁盘预检：预计需要约 {required / (1024**3):.2f} GB，"
                f"输出盘可用 {free / (1024**3):.2f} GB"
            )
            if free < required:
                raise BatchError(
                    f"输出磁盘空间不足：预计需要 {required / (1024**3):.2f} GB，"
                    f"当前可用 {free / (1024**3):.2f} GB。"
                )
        except BatchError:
            raise
        except OSError:
            pass

        ffmpeg = None
        encoder: EncoderChoice | None = None
        if any(item.kind == "video" for item, _job in pending):
            ffmpeg = find_ffmpeg()
            self.log.info(f"FFmpeg：{ffmpeg}")
            self.log.info(f"FFmpeg 版本：{ffmpeg_version(ffmpeg)}")
            encoder = choose_encoder(
                ffmpeg, self.profile, self.config.encoder_preference, log=self.log.info
            )
            self.log.info(f"视频编码器：{encoder.label}")
            result.encoder = encoder.label

        video_workers = int(self.config.video_workers)
        if video_workers <= 0:
            video_workers = 2 if (encoder and encoder.hardware) else max(1, min(4, (os.cpu_count() or 4) // 2))
        photo_workers = int(self.config.photo_workers)
        if photo_workers <= 0:
            photo_workers = max(1, min(8, os.cpu_count() or 4))
        self.log.info(f"并发配置：视频 {video_workers} 路 / 照片 {photo_workers} 路")

        if self.dry_run:
            for item, job in pending:
                self._set_job_status(job, "skipped", error="DRY-RUN 未执行")
                self.log.info(f"[DRY-RUN] {item.source}  ->  {item.output}")
            self.log.info("DRY-RUN 完成，未写入任何媒体文件。")
            self._finish_report(result, input_dir, output_dir, started_at, finished=False)
            self._emit(1.0, "DRY-RUN 完成", result)
            return result

        futures: dict = {}
        try:
            with ThreadPoolExecutor(max_workers=max(1, video_workers), thread_name_prefix="video") as video_pool, \
                 ThreadPoolExecutor(max_workers=max(1, photo_workers), thread_name_prefix="photo") as photo_pool:
                for item, job in pending:
                    pool = video_pool if item.kind == "video" else photo_pool
                    future = pool.submit(self._process_job, item, job, ffmpeg, encoder)
                    futures[future] = (item, job)
                for future in as_completed(futures):
                    item, job = futures[future]
                    try:
                        status = future.result()
                    except Exception as exc:
                        status = "failed"
                        job.error = str(exc)[-1600:]
                        self._set_job_status(job, "failed", error=job.error)
                    if status == "success":
                        result.success += 1
                    elif status == "failed":
                        result.failed += 1
                        result.failures.append(f"{item.rel_path}: {job.error}")
                    elif status == "cancelled":
                        result.cancelled = True
                    self.queue_store.save_state(jobs, status="running")
                    completed = result.success + result.failed + result.skipped_existing
                    self._emit(
                        min(1.0, completed / max(1, len(items))),
                        f"已处理 {completed}/{len(items)}",
                        result,
                    )
        except Exception as exc:
            self.log.exception("批处理调度失败", exc)
            for _item, job in futures.values() if futures else []:
                if job.status == "pending":
                    self._set_job_status(job, "failed", error=f"调度失败：{exc}")
            result.failed += 1
            result.failures.append(f"批处理调度失败：{exc}")

        if result.cancelled:
            for job in jobs:
                if job.status == "pending":
                    self._set_job_status(job, "cancelled", error="批处理取消")
            self.log.warning("批处理已取消；当前文件的部分输出已清理，之前成功的文件保留。")
        self._finish_report(result, input_dir, output_dir, started_at, finished=not result.cancelled)
        self._emit(1.0, "批处理结束", result)
        self.log.info(
            f"汇总：成功 {result.success}，失败 {result.failed}，"
            f"跳过不支持 {result.skipped_unsupported}，"
            f"跳过范围 {result.skipped_scope}，跳过已存在 {result.skipped_existing}，"
            f"总耗时 {result.duration_sec:.2f}s"
        )
        return result

    def _finish_report(self, result: BatchResult, input_dir: Path, output_dir: Path,
                       started_at: str, *, finished: bool) -> None:
        result.finished_at = now_iso()
        try:
            started_perf = getattr(self, "_run_started_perf", None)
            if started_perf is not None:
                result.duration_sec = max(0.001, round(time.perf_counter() - started_perf, 3))
            else:
                start_dt = datetime.fromisoformat(started_at)
                end_dt = datetime.fromisoformat(result.finished_at)
                result.duration_sec = max(0.001, round((end_dt - start_dt).total_seconds(), 3))
        except Exception:
            result.duration_sec = 0.001
        status = "finished" if finished and not result.cancelled else "cancelled"
        self.queue_store.save_state(result.jobs, status=status)
        self.log.info(
            f"本次处理总耗时：{format_duration_hms(result.duration_sec)}"
            f"（{result.duration_sec:.2f} 秒）"
        )
        if self.config.write_reports and result.jobs:
            try:
                json_path, csv_path = self.queue_store.write_report(
                    result.jobs,
                    input_dir=input_dir,
                    output_dir=output_dir,
                    started_at=started_at,
                    cancelled=result.cancelled,
                    duration_sec=result.duration_sec,
                    scope=normalize_scope(getattr(self.config, "import_scope", DEFAULT_SCOPE)),
                    skipped_scope=result.skipped_scope,
                    scope_skipped_files=result.scope_skipped_files,
                )
                result.report_json = str(json_path)
                result.report_csv = str(csv_path)
                self.log.info(f"报告：{json_path}")
                self.log.info(f"报告：{csv_path}")
            except Exception as exc:
                self.log.warning(f"生成报告失败：{exc}")
