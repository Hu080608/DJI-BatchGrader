"""Modern CustomTkinter GUI for the batch LUT grader (GUI only)."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from . import __version__
from .applog import AppLogger, print_banner
from .config import AppConfig, load_config, save_config
from .diagnostics import install_exception_hooks, record_exception
from .dnd import enable_file_drop
from .lut import CubeLUT, LutCandidate, LutError, import_lut_into_project, resolve_lut
from .lut_dialog import LutLibraryDialog
from .lut_library import scan_lut_library
from .lut_updater import auto_lut_check_due, check_and_update_luts
from .formats import OUTPUT_PROFILES, QUALITY_PRESETS, get_output_profile, profile_labels, quality_preset_labels
from .presets import DEFAULT_TEMPLATE, TEMPLATES, StyleTemplate, recommend_template
from .preview_dialog import PreviewDialog
from .jobs import (
    JOB_STATUS_LABELS, JOB_STATUS_ORDER, JobRecord, QueueStore,
    format_duration_hms, now_iso,
)
from .license_dialog import LicenseDialog
from ._license_guard import LicenseManager
from .paths import LUT_DIR, LOG_DIR, OUTPUT_DIR, PROJECT_ROOT, REPORT_DIR, configure_environment, project_path
from .processor import (
    DEFAULT_SCOPE, IGNORED_EXTS, RAW_EXTS, SCOPE_LABELS, SUPPORTED_EXTS,
    BatchProcessor, BatchResult, is_file_in_scope, normalize_scope,
)
from .watcher import FolderWatcher
from .updater import check_for_update, extract_update_summary, launch_updater

# Palette
BG = "#080f1c"
CARD = "#111c31"
CARD_ALT = "#0b1526"
BORDER = "#203452"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#2dd4bf"
ACCENT_DARK = "#0d9488"
DANGER = "#fb7185"
WARN = "#fbbf24"
OK = "#4ade80"
FONT_UI = "Microsoft YaHei UI"
FONT_TITLE = (FONT_UI, 30, "bold")
FONT_SECTION = (FONT_UI, 16, "bold")
FONT_BODY = (FONT_UI, 13)
FONT_BODY_BOLD = (FONT_UI, 13, "bold")
FONT_SMALL = (FONT_UI, 12)
FONT_SMALL_BOLD = (FONT_UI, 12, "bold")
FONT_MONO = ("Consolas", 12)
MAX_PREVIEW_FILES = 2000


class GraderGUI:
    def __init__(self, root: ctk.CTk, license_manager: LicenseManager | None = None):
        self.root = root
        self.license_manager = license_manager
        self._license_locked = False
        self._license_warning_shown = False
        self.root.title(f"DJI D-Log M 批量调色  |  作者：Hu080608  |  v{__version__}")
        # CustomTkinter applies DPI scaling. Choose a window that fits the actual
        # screen instead of forcing a partly off-screen 1200x860 window.
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        win_w = min(1200, max(900, int(screen_w - 100)))
        win_h = min(860, max(600, int(screen_h - 110)))
        self.root.geometry(f"{win_w}x{win_h}+10+10")
        self.root.minsize(min(980, win_w), min(560, win_h))
        self.root.configure(fg_color=BG)

        self.config: AppConfig = load_config()
        self.events: queue.Queue = queue.Queue()
        self.drop_queue: queue.Queue = queue.Queue()
        self.watch_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.done = False
        self.closing = False
        self.poll_scheduled = False
        self.log_window: AppLogger | None = None
        self.drop_targets: list = []
        self.watcher: FolderWatcher | None = None
        self.watch_pending: list[Path] = []
        self._lut_update_thread: threading.Thread | None = None

        # Input selection: either a folder or an explicit list of dropped files.
        self.input_path: Path | None = None
        self.selected_files: list[Path] = []
        self.current_jobs: dict[int, dict] = {}
        self.last_jobs: list[dict] = []
        self.job_rows: set[int] = set()
        self.queue_store = QueueStore()
        self._import_token = 0
        self._last_batch_duration_text = "—"

        self._build_vars()
        self._build_ui()
        self._refresh_lut_library()
        self._refresh_lut_label()
        self._update_input_status()
        self.drop_targets = enable_file_drop(
            [self.drop_frame, self.drop_inner, self.drop_icon, self.drop_title, self.drop_hint],
            self.drop_queue,
        )
        self._append_log("INFO", "欢迎使用 DJI D-Log M 批量调色工具")
        self._append_log("INFO", "可直接把照片、视频或文件夹拖拽到窗口中。")
        self._clear_queue_on_open()
        if not self.drop_targets:
            self._append_log("WARN", "当前系统未启用原生拖拽，请使用“选择文件夹”按钮。")

        self.root.report_callback_exception = self._handle_callback_exception
        self._schedule_poll()
        self._schedule_drop_poll()
        self._schedule_watch_poll()
        self._restart_watcher()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.after(100, self._maximize_window)
        if self.config.auto_check_updates:
            self.root.after(1200, lambda: self._check_updates(manual=False))
        if getattr(self.config, "auto_update_luts", True) and auto_lut_check_due(
            int(getattr(self.config, "lut_update_interval_hours", 24))
        ):
            self.root.after(8000, lambda: self._update_lut_library(manual=False))
        self._update_license_badge()
        if self.license_manager:
            self.root.after(60000, self._license_tick)

    # ------------------------------------------------------------------ UI
    def _build_vars(self) -> None:
        self.output_var = tk.StringVar(value=str(self.config.default_output_path))
        self.recursive_var = tk.BooleanVar(value=bool(self.config.recursive))
        self.profile_labels = profile_labels()
        self.profile_key_by_label = {label: key for key, label in self.profile_labels.items()}
        current_profile = getattr(self.config, "output_profile", "h264_mp4")
        self.output_profile_var = tk.StringVar(
            value=self.profile_labels.get(current_profile, next(iter(self.profile_labels.values())))
        )
        self.quality_preset_labels = quality_preset_labels()
        self.quality_preset_key_by_label = {v: k for k, v in self.quality_preset_labels.items()}
        current_preset = getattr(self.config, "quality_preset", "high")
        self.quality_preset_var = tk.StringVar(
            value=self.quality_preset_labels.get(current_preset, "高质量")
        )
        self._applying_preset = False
        self.encoder_labels = {
            "auto": "自动（GPU 优先）", "cpu": "仅 CPU",
            "nvidia": "NVIDIA", "intel": "Intel", "amd": "AMD",
        }
        self.encoder_key_by_label = {v: k for k, v in self.encoder_labels.items()}
        self.encoder_pref_var = tk.StringVar(
            value=self.encoder_labels.get(self.config.encoder_preference, "自动（GPU 优先）")
        )
        self.worker_values = ["自动", "1", "2", "3", "4", "6", "8"]
        self.video_workers_var = tk.StringVar(
            value="自动" if int(self.config.video_workers) <= 0 else str(self.config.video_workers)
        )
        self.photo_workers_var = tk.StringVar(
            value="自动" if int(self.config.photo_workers) <= 0 else str(self.config.photo_workers)
        )
        self.quality_var = tk.IntVar(value=int(self.config.jpeg_quality))
        self.crf_var = tk.IntVar(value=int(self.config.video_crf))
        self.lut_path_var = tk.StringVar(value=str(self.config.lut_path))
        self.lut_entries = {}
        self.lut_meta_var = tk.StringVar(value="")
        self.scope_labels = dict(SCOPE_LABELS)
        self.scope_key_by_label = {label: key for key, label in self.scope_labels.items()}
        current_scope = normalize_scope(getattr(self.config, "import_scope", DEFAULT_SCOPE))
        self.scope_var = tk.StringVar(value=self.scope_labels[current_scope])
        self.ui_mode_var = tk.StringVar(
            value="简易模式" if getattr(self.config, "ui_mode", "simple") != "pro" else "专业模式"
        )
        self.lut_strength_var = tk.IntVar(
            value=int(round(float(getattr(self.config, "lut_strength", 1.0)) * 100))
        )
        self.color_mode_var = tk.StringVar(
            value="色彩还原" if self._is_official_lut_path(self.config.lut_path) else "调色"
        )
        self.template_status_var = tk.StringVar(
            value="选择调色模板，或点击一键推荐；模板应用到本批次全部素材。"
        )
        self.simple_mode = self.ui_mode_var.get() == "简易模式"
        self._lut_history: list[tuple[str, int]] = []
        self._strength_before: tuple[str, int] | None = None
        self._restoring_lut = False
        self.watch_var = tk.BooleanVar(value=bool(self.config.watch_enabled))
        self.telemetry_var = tk.BooleanVar(value=bool(self.config.telemetry_enabled))
        self.auto_update_var = tk.BooleanVar(value=bool(self.config.auto_check_updates))
        self.auto_lut_update_var = tk.BooleanVar(value=bool(getattr(self.config, "auto_update_luts", True)))
        self.status_var = tk.StringVar(value="就绪 · 请选择或拖入素材")
        self.counts_var = tk.StringVar(value="成功 0   失败 0   跳过 0   总计 0")
        self.progress_text_var = tk.StringVar(value="0%")
        self.input_status_var = tk.StringVar(value="")
        self.lut_status_var = tk.StringVar(value="")

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent, fg_color=CARD, corner_radius=18,
            border_width=1, border_color=BORDER,
        )

    @staticmethod
    def _is_official_lut_path(path) -> bool:
        try:
            rel = Path(path).resolve().relative_to(LUT_DIR.resolve())
        except ValueError:
            return False
        parts = rel.parts
        return bool(parts) and parts[0] not in {"热门网络 LUT", "custom"}

    def _set_strength(self, percent: int) -> None:
        percent = max(0, min(100, int(percent)))
        self.lut_strength_var.set(percent)
        try:
            self.strength_slider.set(percent)
        except Exception:
            pass
        if hasattr(self, "strength_value_label"):
            self.strength_value_label.configure(text=f"{percent}%")
        self.config.lut_strength = percent / 100.0

    def _on_color_mode_change(self, label: str) -> None:
        self.color_mode_var.set(label)
        current = project_path(self.lut_path_var.get())
        if label == "色彩还原":
            if not self._is_official_lut_path(current):
                self._push_lut_history()
                self.lut_path_var.set(str(TEMPLATES[-1].path))
                self._set_strength(100)
                self._refresh_lut_library()
                self._refresh_lut_label()
            else:
                self._set_strength(100)
        else:
            if self._is_official_lut_path(current):
                self._apply_template(DEFAULT_TEMPLATE)
        self._apply_color_mode_visibility()

    def _apply_color_mode_visibility(self) -> None:
        if not hasattr(self, "browse_buttons"):
            return
        official = self.color_mode_var.get() == "色彩还原"
        if hasattr(self, "quick_card"):
            if official:
                self.quick_card.grid_remove()
            else:
                self.quick_card.grid()
        if hasattr(self, "strength_row"):
            if official:
                self.strength_row.grid_remove()
            else:
                self.strength_row.grid()
        if hasattr(self, "browse_lut_button"):
            self.browse_lut_button.configure(state="normal")
        if hasattr(self, "import_lut_button"):
            self.import_lut_button.configure(state="normal")
        if hasattr(self, "sync_lut_button"):
            self.sync_lut_button.configure(state="normal")

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="DJI D-Log M  批量调色",
            font=FONT_TITLE,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Rec.709 Batch Grader   ·   作者：Hu080608",
            font=FONT_BODY,
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.mode_menu = ctk.CTkOptionMenu(
            header, values=["简易模式", "专业模式"], variable=self.ui_mode_var,
            width=106, height=30, corner_radius=9, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK,
            text_color=TEXT, font=FONT_SMALL, command=self._on_mode_change,
        )
        self.mode_menu.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        ctk.CTkLabel(
            header,
            text=f"GUI EXE  v{__version__}",
            font=FONT_BODY_BOLD,
            fg_color="#12323a",
            text_color=ACCENT,
            corner_radius=12,
            padx=14,
            pady=6,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))
        self.license_button = ctk.CTkButton(
            header, text="授权信息", width=118, height=30, corner_radius=9,
            fg_color="#12323a", hover_color="#1b2b46", text_color=ACCENT,
            border_width=1, border_color=BORDER, command=self._open_license_dialog,
            font=FONT_SMALL,
        )
        self.license_button.grid(row=0, column=3, rowspan=2, sticky="e", padx=(8, 0))
        ctk.CTkButton(
            header, text="使用说明", width=88, height=30, corner_radius=9,
            fg_color="transparent", hover_color="#1b2b46", text_color=MUTED,
            border_width=1, border_color=BORDER, command=self._open_help,
            font=FONT_SMALL,
        ).grid(row=0, column=4, rowspan=2, sticky="e", padx=(8, 0))
        ctk.CTkButton(
            header, text="检查更新", width=88, height=30, corner_radius=9,
            fg_color="transparent", hover_color="#1b2b46", text_color=MUTED,
            border_width=1, border_color=BORDER, command=self._check_updates,
            font=FONT_SMALL,
        ).grid(row=0, column=5, rowspan=2, sticky="e", padx=(8, 0))

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 18))
        main.grid_columnconfigure(0, weight=3, minsize=700)
        main.grid_columnconfigure(1, weight=2, minsize=520)
        main.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(main, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#1b2b46",
            scrollbar_button_hover_color="#284261",
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(
            main, fg_color=CARD, corner_radius=18,
            border_width=1, border_color=BORDER,
        )
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self._build_source_card(scroll)
        self._build_output_card(scroll)
        self._build_lut_card(scroll)
        self._build_settings_card(scroll)
        self._build_aux_card(scroll)
        self._build_log_panel(right)
        self._build_actions(right, row=1)
        self._build_progress_card(right, row=2)
        self._apply_mode_visibility()
        self.root.bind("<Control-z>", lambda _event: self._undo_lut())

    def _build_source_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 0))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, text="输入素材", font=FONT_SECTION, text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            top, text="支持拖拽上传", font=FONT_BODY_BOLD,
            text_color=ACCENT, fg_color="#12323a", corner_radius=9, padx=9, pady=3,
        ).grid(row=0, column=1, sticky="e")

        self.drop_frame = ctk.CTkFrame(
            card, fg_color="#0a2530", corner_radius=16,
            border_width=2, border_color="#2dd4bf",
        )
        self.drop_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 6))
        self.drop_frame.grid_columnconfigure(0, weight=1)
        self.drop_frame.grid_rowconfigure(0, weight=1)

        self.drop_inner = ctk.CTkFrame(self.drop_frame, fg_color="transparent")
        drop_inner = self.drop_inner
        drop_inner.grid(row=0, column=0, pady=(14, 16))
        self.drop_icon = ctk.CTkLabel(
            drop_inner, text="⇩", font=(FONT_UI, 34, "bold"), text_color=ACCENT,
        )
        self.drop_icon.pack()
        self.drop_title = ctk.CTkLabel(
            drop_inner, text="拖拽照片 / 视频 / 文件夹到这里",
            font=FONT_SECTION, text_color=TEXT,
        )
        self.drop_title.pack(pady=(0, 3))
        self.drop_hint = ctk.CTkLabel(
            drop_inner,
            text="点击选择文件夹   ·   JPG / PNG / TIFF / HEIC / RAW / MP4 / MOV / M4V   ·   .SRT 自动忽略",
            font=FONT_BODY, text_color=MUTED,
            wraplength=640, justify="center",
        )
        self.drop_hint.pack()
        for widget in (self.drop_frame, drop_inner, self.drop_icon, self.drop_title, self.drop_hint):
            widget.bind("<Button-1>", lambda _event: self._browse_input())
            widget.configure(cursor="hand2") if hasattr(widget, "configure") else None

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        bottom.grid_columnconfigure(0, weight=1)
        self.input_status_label = ctk.CTkLabel(
            bottom, textvariable=self.input_status_var, font=FONT_BODY,
            text_color=MUTED, anchor="w", justify="left", wraplength=380,
        )
        self.input_status_label.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            bottom, text="选择文件夹", width=92, height=30, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._browse_input,
        
                font=FONT_SMALL,).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            bottom, text="清空", width=54, height=30, corner_radius=9,
            fg_color="transparent", hover_color="#2a1622", text_color=DANGER,
            border_width=1, border_color="#64283a", command=self._clear_input,
        
                font=FONT_SMALL,).grid(row=0, column=2, padx=(6, 0))

        scope_row = ctk.CTkFrame(card, fg_color="transparent")
        scope_row.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))
        scope_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            scope_row, text="处理范围", font=FONT_SMALL_BOLD,
            text_color=MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.scope_button = ctk.CTkSegmentedButton(
            scope_row,
            values=list(self.scope_labels.values()),
            variable=self.scope_var,
            command=self._on_scope_change,
            height=30,
            corner_radius=9,
            fg_color="#0b1526",
            selected_color=ACCENT_DARK,
            selected_hover_color="#0f766e",
            unselected_color="#1b2b46",
            unselected_hover_color="#284261",
            text_color=TEXT,
            font=FONT_SMALL,
        )
        self.scope_button.grid(row=0, column=1, sticky="ew", padx=(10, 0))

    def _build_output_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 9))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text="输出文件夹", font=FONT_SECTION, text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=10)
        self.output_entry = ctk.CTkEntry(
            card, textvariable=self.output_var, height=34, corner_radius=9,
            fg_color=CARD_ALT, border_color=BORDER, text_color=TEXT,
        
                font=FONT_BODY,)
        self.output_entry.grid(row=0, column=1, sticky="ew", pady=7)
        ctk.CTkButton(
            card, text="选择…", width=76, height=34, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._browse_output,
        
                font=FONT_SMALL,).grid(row=0, column=2, padx=(8, 14))

    def _build_lut_card(self, parent) -> None:
        card = self._card(parent)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 9))
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 1))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="色彩管理", font=FONT_SECTION, text_color=TEXT,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.lut_count_label = ctk.CTkLabel(
            head, text="", font=FONT_SMALL_BOLD, text_color=ACCENT,
        )
        self.lut_count_label.grid(row=0, column=1, sticky="e")
        self.lut_status_label = ctk.CTkLabel(
            card, textvariable=self.lut_status_var, font=FONT_MONO,
            text_color=OK, anchor="w", justify="left", wraplength=545,
        )
        self.lut_status_label.grid(row=1, column=0, sticky="ew", padx=16)
        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 2))
        mode_row.grid_columnconfigure(0, weight=1)
        self.color_mode_button = ctk.CTkSegmentedButton(
            mode_row, values=["色彩还原", "调色"], variable=self.color_mode_var,
            command=self._on_color_mode_change, height=34, corner_radius=9,
            fg_color="#0b1526", selected_color=ACCENT_DARK,
            selected_hover_color="#0f766e", unselected_color="#1b2b46",
            unselected_hover_color="#284261", text_color=TEXT, font=FONT_BODY_BOLD,
        )
        self.color_mode_button.grid(row=0, column=0, sticky="ew")
        self.lut_meta_label = ctk.CTkLabel(
            card, textvariable=self.lut_meta_var, font=FONT_SMALL,
            text_color=MUTED, anchor="w", justify="left", wraplength=540,
        )
        self.lut_meta_label.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 0))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="w", padx=10, pady=(7, 8))
        self.browse_lut_button = ctk.CTkButton(
            buttons, text="浏览/选择LUT", width=118, height=30, corner_radius=9,
            fg_color=ACCENT_DARK, hover_color="#0f766e", text_color=TEXT,
            font=FONT_SMALL_BOLD, command=self._open_lut_library,
        )
        self.browse_lut_button.pack(side="left", padx=(4, 7))
        self.browse_buttons = {"all": self.browse_lut_button}
        self.import_lut_button = ctk.CTkButton(
            buttons, text="导入 .cube", width=92, height=30, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._choose_lut, font=FONT_SMALL,
        )
        self.import_lut_button.pack(side="left", padx=0)
        self.sync_lut_button = ctk.CTkButton(
            buttons, text="同步DJI官方LUT库", width=140, height=30, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._update_lut_library, font=FONT_SMALL,
        )
        self.sync_lut_button.pack(side="left")
        ctk.CTkButton(
            buttons, text="打开目录", width=86, height=30, corner_radius=9,
            fg_color="transparent", hover_color="#1b2b46", text_color=MUTED,
            border_width=1, border_color=BORDER, command=self._open_luts,
            font=FONT_SMALL,
        ).pack(side="left", padx=7)

        strength_row = ctk.CTkFrame(card, fg_color="transparent")
        self.strength_row = strength_row
        strength_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))
        strength_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            strength_row, text="风格强度", font=FONT_SMALL_BOLD,
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.strength_slider = ctk.CTkSlider(
            strength_row, from_=0, to=100, number_of_steps=100,
            variable=self.lut_strength_var, command=self._on_strength_change,
            height=16, progress_color=ACCENT_DARK, button_color=ACCENT,
            button_hover_color="#5eead4", fg_color="#1b2b46",
        )
        self.strength_slider.grid(row=0, column=1, sticky="ew", padx=(10, 8))
        self.strength_slider.bind("<ButtonRelease-1>", self._commit_strength)
        self.strength_value_label = ctk.CTkLabel(
            strength_row, text=f"{self.lut_strength_var.get()}%",
            font=FONT_SMALL_BOLD, text_color=ACCENT, width=38,
        )
        self.strength_value_label.grid(row=0, column=2, sticky="e")
        self._build_quick_card(card)

    def _build_quick_card(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color="transparent")
        self.quick_card = card
        card.grid(row=6, column=0, sticky="ew", padx=0, pady=(0, 2))
        card.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 2))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="快速调色", font=FONT_SECTION, text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            head, text="一键推荐", width=88, height=28, corner_radius=8,
            fg_color=ACCENT_DARK, hover_color="#0f766e", text_color=TEXT,
            font=FONT_SMALL_BOLD, command=self._recommend_one_click,
        ).grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            head, text="预览", width=58, height=28, corner_radius=8,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            font=FONT_SMALL, command=self._open_preview_dialog,
        ).grid(row=0, column=2, sticky="e", padx=(6, 0))
        ctk.CTkButton(
            head, text="撤销上一步", width=94, height=28, corner_radius=8,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            font=FONT_SMALL, command=self._undo_lut,
        ).grid(row=0, column=3, sticky="e", padx=(6, 0))
        ctk.CTkLabel(
            card, textvariable=self.template_status_var, font=FONT_SMALL,
            text_color=MUTED, anchor="w", justify="left", wraplength=540,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        templates = ctk.CTkFrame(card, fg_color="transparent")
        templates.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 9))
        for index in range(4):
            templates.grid_columnconfigure(index, weight=1)
        for index, template in enumerate(TEMPLATES):
            ctk.CTkButton(
                templates, text=template.label, height=30, corner_radius=8,
                fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
                font=FONT_SMALL,
                command=lambda item=template: self._apply_template(item),
            ).grid(row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3)

    def _on_mode_change(self, label: str) -> None:
        self.simple_mode = label == "简易模式"
        self.config.ui_mode = "simple" if self.simple_mode else "pro"
        try:
            save_config(self.config)
        except Exception:
            pass
        self._apply_mode_visibility()
        self._append_log("INFO", f"界面模式：{label}")

    def _apply_mode_visibility(self) -> None:
        if not hasattr(self, "settings_card") or not hasattr(self, "quick_card"):
            return
        if self.simple_mode:
            self.settings_card.grid_remove()
        else:
            self.settings_card.grid()
        self._apply_color_mode_visibility()

    def _current_lut_state(self) -> tuple[str, int]:
        return self.lut_path_var.get(), int(self.lut_strength_var.get())

    def _push_lut_history(self) -> None:
        if self._restoring_lut:
            return
        current = self._current_lut_state()
        if self._lut_history and self._lut_history[-1] == current:
            return
        self._lut_history.append(current)
        self._lut_history = self._lut_history[-50:]

    def _restore_lut_state(self, state: tuple[str, int]) -> None:
        path, strength = state
        self._restoring_lut = True
        try:
            self.lut_path_var.set(path)
            self.lut_strength_var.set(int(strength))
            try:
                self.strength_slider.set(int(strength))
            except Exception:
                pass
            self.strength_value_label.configure(text=f"{int(strength)}%")
            self.config.lut_strength = float(strength) / 100.0
            self._refresh_lut_library()
            self._refresh_lut_label()
        finally:
            self._restoring_lut = False

    def _undo_lut(self) -> None:
        if not self._lut_history:
            self.status_var.set("没有可撤销的调色操作")
            return
        state = self._lut_history.pop()
        self._restore_lut_state(state)
        self.status_var.set("已撤销上一步调色操作")

    def _on_strength_change(self, value) -> None:
        amount = int(round(float(value)))
        if not self._restoring_lut and self._strength_before is None:
            self._strength_before = self._current_lut_state()
        self.lut_strength_var.set(amount)
        if hasattr(self, "strength_value_label"):
            self.strength_value_label.configure(text=f"{amount}%")
        self.config.lut_strength = amount / 100.0

    def _commit_strength(self, _event=None) -> None:
        if self._strength_before is None:
            return
        before = self._strength_before
        self._strength_before = None
        if before != self._current_lut_state():
            self._lut_history.append(before)
            self._lut_history = self._lut_history[-50:]

    def _apply_template(self, template: StyleTemplate) -> None:
        if not template.path.exists():
            messagebox.showerror(
                "模板不可用",
                "模板 LUT 不存在：" + chr(10) + str(template.path),
            )
            return
        self._push_lut_history()
        self.color_mode_var.set("调色")
        self.lut_path_var.set(str(template.path))
        percent = int(round(template.strength * 100))
        self._set_strength(percent)
        self._refresh_lut_library()
        self._refresh_lut_label()
        self._apply_color_mode_visibility()
        self.template_status_var.set(f"已应用：{template.label} · {template.description}")
        self._append_log("INFO", f"快速模板：{template.label}（强度 {percent}%）")
        self.status_var.set(f"已应用模板：{template.label}")

    def _open_preview_dialog(self) -> None:
        path = project_path(self.lut_path_var.get())
        if not path.exists():
            messagebox.showerror("预览失败", "当前 LUT 文件不存在，请重新选择。")
            return
        try:
            lut = CubeLUT.from_file(path)
        except Exception as exc:
            messagebox.showerror("预览失败", f"无法读取当前 LUT：{exc}")
            return
        sources: list[Path] = []
        for job in self._all_job_dicts():
            raw = str(job.get("source") or "").strip()
            if raw and Path(raw).is_file():
                sources.append(Path(raw))
        for item in self.selected_files:
            if item.is_file():
                sources.append(item)
        if self.input_path and self.input_path.is_file():
            sources.append(self.input_path)
        seen = set()
        sources = [p for p in sources if not (str(p.resolve()) in seen or seen.add(str(p.resolve())))]
        try:
            PreviewDialog(
                self.root, lut, self.lut_strength_var, sources,
                on_strength=self._on_strength_change,
                on_commit=self._commit_strength,
            )
        except Exception as exc:
            messagebox.showerror("预览失败", str(exc))

    def _recommend_one_click(self) -> None:
        paths = list(self.selected_files)
        if not paths and self.input_path:
            if self.input_path.is_file():
                paths = [self.input_path]
            elif self.input_path.is_dir():
                try:
                    first = next((p for p in self.input_path.rglob("*") if p.is_file()), None)
                    if first:
                        paths = [first]
                except OSError:
                    pass
        template, reason = recommend_template(paths)
        self._apply_template(template)
        messagebox.showinfo(
            "一键推荐",
            reason + chr(10) * 2 + f"已应用模板：{template.label}",
        )

    def _build_settings_card(self, parent) -> None:
        card = self._card(parent)
        self.settings_card = card
        card.grid(row=3, column=0, sticky="ew", pady=(0, 9))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text="处理设置", font=FONT_SECTION, text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(8, 2))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", padx=16, pady=2)
        row1.grid_columnconfigure(2, weight=1)
        ctk.CTkSwitch(
            row1, text="递归子目录", variable=self.recursive_var,
            font=FONT_BODY, text_color=TEXT, progress_color=ACCENT_DARK,
            button_color=ACCENT, button_hover_color="#5eead4",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            row1, text="输出格式", font=FONT_BODY, text_color=MUTED,
        ).grid(row=0, column=1, sticky="e", padx=(18, 8))
        ctk.CTkOptionMenu(
            row1, values=list(self.profile_labels.values()), variable=self.output_profile_var,
            height=30, corner_radius=8, fg_color="#1b2b46", button_color="#284261",
            button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL,
        ).grid(row=0, column=2, sticky="ew")

        quality_row = ctk.CTkFrame(card, fg_color="transparent")
        quality_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))
        quality_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            quality_row, text="质量预设", font=FONT_BODY, text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(
            quality_row, values=list(self.quality_preset_labels.values()),
            variable=self.quality_preset_var, height=30, corner_radius=8,
            fg_color="#1b2b46", button_color="#284261", button_hover_color=ACCENT_DARK,
            text_color=TEXT, font=FONT_SMALL, command=self._on_quality_preset_change,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ctk.CTkLabel(
            quality_row, text="自动映射 CRF / CPU preset / GPU 码率", font=FONT_SMALL,
            text_color=MUTED,
        ).grid(row=0, column=2, sticky="e", padx=(10, 0))

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 2))
        row2.grid_columnconfigure(1, weight=1)
        row2.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(row2, text="JPEG 质量", font=FONT_BODY, text_color=MUTED).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkSlider(
            row2, from_=60, to=100, number_of_steps=40,
            variable=self.quality_var, command=self._on_quality_change,
            height=16, progress_color=ACCENT_DARK, button_color=ACCENT,
            button_hover_color="#5eead4", fg_color="#1b2b46",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.quality_value_label = ctk.CTkLabel(
            row2, text=str(self.quality_var.get()), font=FONT_BODY_BOLD,
            text_color=ACCENT, width=28,
        )
        self.quality_value_label.grid(row=0, column=2, padx=(0, 18))
        ctk.CTkLabel(row2, text="视频 CRF", font=FONT_BODY, text_color=MUTED).grid(
            row=0, column=3, sticky="w"
        )
        ctk.CTkSlider(
            row2, from_=12, to=35, number_of_steps=23,
            variable=self.crf_var, command=self._on_crf_change,
            height=16, progress_color=ACCENT_DARK, button_color=ACCENT,
            button_hover_color="#5eead4", fg_color="#1b2b46",
        ).grid(row=0, column=4, sticky="ew", padx=(8, 8))
        self.crf_value_label = ctk.CTkLabel(
            row2, text=str(self.crf_var.get()), font=FONT_BODY_BOLD,
            text_color=ACCENT, width=28,
        )
        self.crf_value_label.grid(row=0, column=5)

        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.grid(row=4, column=0, sticky="ew", padx=16, pady=(5, 2))
        row3.grid_columnconfigure(4, weight=1)
        ctk.CTkLabel(row3, text="编码器", font=FONT_BODY, text_color=MUTED).grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        ctk.CTkOptionMenu(
            row3, values=list(self.encoder_labels.values()), variable=self.encoder_pref_var,
            width=135, height=30, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL,
        ).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ctk.CTkLabel(row3, text="视频并发", font=FONT_BODY, text_color=MUTED).grid(
            row=0, column=2, sticky="w", padx=(0, 5)
        )
        ctk.CTkOptionMenu(
            row3, values=self.worker_values, variable=self.video_workers_var,
            width=68, height=30, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL,
        ).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ctk.CTkLabel(row3, text="照片并发", font=FONT_BODY, text_color=MUTED).grid(
            row=0, column=4, sticky="e", padx=(0, 5)
        )
        ctk.CTkOptionMenu(
            row3, values=self.worker_values, variable=self.photo_workers_var,
            width=68, height=30, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL,
        ).grid(row=0, column=5, sticky="e")

    def _build_aux_card(self, parent) -> None:
        card = self._card(parent)
        self.aux_card = card
        card.grid(row=4, column=0, sticky="ew", pady=(0, 9))
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card, text="常用开关", font=FONT_SECTION, text_color=TEXT,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 2))
        ctk.CTkSwitch(
            card, text="监听输入文件夹", variable=self.watch_var,
            font=FONT_BODY, text_color=TEXT, progress_color=ACCENT_DARK,
            button_color=ACCENT, button_hover_color="#5eead4",
            command=self._on_watch_toggle,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=3)
        ctk.CTkSwitch(
            card, text="匿名诊断", variable=self.telemetry_var,
            font=FONT_BODY, text_color=TEXT, progress_color=ACCENT_DARK,
            button_color=ACCENT, button_hover_color="#5eead4",
        ).grid(row=1, column=1, sticky="w", padx=16, pady=3)
        ctk.CTkSwitch(
            card, text="启动时检查更新", variable=self.auto_update_var,
            font=FONT_BODY, text_color=TEXT, progress_color=ACCENT_DARK,
            button_color=ACCENT, button_hover_color="#5eead4",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(3, 8))
        ctk.CTkSwitch(
            card, text="自动同步 LUT", variable=self.auto_lut_update_var,
            font=FONT_BODY, text_color=TEXT, progress_color=ACCENT_DARK,
            button_color=ACCENT, button_hover_color="#5eead4",
        ).grid(row=2, column=1, sticky="w", padx=16, pady=(3, 8))

    def _build_actions(self, parent, row: int = 4) -> None:
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=row, column=0, sticky="ew", padx=10, pady=(4, 5))
        actions.grid_columnconfigure(0, weight=1)
        self.start_btn = ctk.CTkButton(
            actions, text="开始批处理", height=38, corner_radius=11,
            font=FONT_SECTION, fg_color=ACCENT_DARK,
            hover_color="#0f766e", text_color=TEXT, command=self._start,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew")
        self.cancel_btn = ctk.CTkButton(
            actions, text="取消", width=82, height=38, corner_radius=11,
            font=FONT_BODY_BOLD, fg_color="#2a1622",
            hover_color="#3b1c2b", text_color=DANGER,
            border_width=1, border_color="#64283a",
            state="disabled", command=self._cancel,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(
            actions, text="打开输出目录", width=110, height=38, corner_radius=11,
            font=FONT_BODY, fg_color="#1b2b46", hover_color="#284261",
            text_color=TEXT, command=self._open_output,
        ).grid(row=0, column=2)

    def _build_progress_card(self, parent, row: int = 5) -> None:
        card = self._card(parent)
        card.grid(row=row, column=0, sticky="ew", padx=10, pady=(0, 5))
        card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 2))
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top, textvariable=self.status_var, font=FONT_BODY,
            text_color=MUTED, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            top, textvariable=self.progress_text_var, font=FONT_BODY_BOLD,
            text_color=ACCENT, width=46,
        ).grid(row=0, column=1, sticky="e")
        self.progressbar = ctk.CTkProgressBar(
            card, height=8, corner_radius=4, progress_color=ACCENT,
            fg_color="#1b2b46",
        )
        self.progressbar.grid(row=1, column=0, sticky="ew", padx=16)
        self.progressbar.set(0)
        ctk.CTkLabel(
            card, textvariable=self.counts_var, font=FONT_BODY,
            text_color=TEXT, anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(6, 8))

    def _build_log_panel(self, parent) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.tabs = ctk.CTkTabview(
            parent, fg_color="transparent", corner_radius=12,
            segmented_button_selected_color=ACCENT_DARK,
            segmented_button_selected_hover_color="#0f766e",
            segmented_button_unselected_color="#1b2b46",
            segmented_button_unselected_hover_color="#284261",
            text_color=TEXT,
        )
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        queue_tab = self.tabs.add("任务队列")
        log_tab = self.tabs.add("运行日志")
        queue_tab.grid_rowconfigure(1, weight=1)
        queue_tab.grid_columnconfigure(0, weight=1)
        log_tab.grid_rowconfigure(1, weight=1)
        log_tab.grid_columnconfigure(0, weight=1)

        queue_actions = ctk.CTkFrame(queue_tab, fg_color="transparent")
        queue_actions.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
        ctk.CTkButton(
            queue_actions, text="重试失败", width=88, height=30, corner_radius=8,
            fg_color="#3b1c2b", hover_color="#64283a", text_color=DANGER,
            border_width=1, border_color="#64283a", command=self._retry_failed,
        
                font=FONT_SMALL,).pack(side="left")
        ctk.CTkButton(
            queue_actions, text="清空已完成", width=94, height=30, corner_radius=8,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._clear_finished_jobs,
        
                font=FONT_SMALL,).pack(side="left", padx=6)
        ctk.CTkButton(
            queue_actions, text="打开报告目录", width=104, height=30, corner_radius=8,
            fg_color="transparent", hover_color="#1b2b46", text_color=MUTED,
            border_width=1, border_color=BORDER, command=self._open_reports,
        
                font=FONT_SMALL,).pack(side="right")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Queue.Treeview", background=CARD_ALT, fieldbackground=CARD_ALT,
            foreground="#cbd5e1", borderwidth=0, rowheight=31,
            font=FONT_SMALL,
        )
        style.configure(
            "Queue.Treeview.Heading", background="#1b2b46", foreground=TEXT,
            borderwidth=0, font=FONT_SMALL_BOLD,
        )
        style.map("Queue.Treeview", background=[("selected", "#164e63")])
        table_frame = ctk.CTkFrame(queue_tab, fg_color=CARD_ALT, corner_radius=10)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 6))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        columns = ("file", "status", "progress", "duration", "encoder", "note")
        self.job_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Queue.Treeview", selectmode="browse",
        )
        headings = {
            "file": "文件", "status": "状态", "progress": "进度",
            "duration": "耗时", "encoder": "编码", "note": "备注 / 错误",
        }
        widths = {"file": 220, "status": 74, "progress": 58, "duration": 70, "encoder": 130, "note": 195}
        for col in columns:
            self.job_tree.heading(col, text=headings[col])
            self.job_tree.column(col, width=widths[col], anchor="w",
                                 stretch=(col in {"file", "note"}))
        self.job_tree.tag_configure("success", foreground=OK)
        self.job_tree.tag_configure("failed", foreground=DANGER)
        self.job_tree.tag_configure("running", foreground=ACCENT)
        self.job_tree.tag_configure("cancelled", foreground=WARN)
        self.job_tree.tag_configure("skipped", foreground=MUTED)
        self.job_tree.tag_configure("import_failed", foreground=DANGER)
        self.job_tree.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=4)
        self.job_tree.bind("<Button-3>", self._show_job_context_menu)
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.job_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=4, padx=(0, 4))
        self.job_tree.configure(yscrollcommand=scroll.set)

        log_head = ctk.CTkFrame(log_tab, fg_color="transparent")
        log_head.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
        log_head.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            log_head, text="打开日志目录", width=104, height=30, corner_radius=8,
            fg_color="transparent", hover_color="#1b2b46", text_color=MUTED,
            border_width=1, border_color=BORDER, command=self._open_logs,
        
                font=FONT_SMALL,).grid(row=0, column=1, sticky="e")
        self.log_text = ctk.CTkTextbox(
            log_tab, fg_color=CARD_ALT, text_color="#cbd5e1",
            font=FONT_MONO, corner_radius=10, border_width=0,
            wrap="word", state="disabled",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 6))

        ctk.CTkLabel(
            parent,
            text="作者：Hu080608   ·   本地离线处理   ·   日志 / 缓存 / 临时文件 / 报告均在软件目录内",
            font=FONT_SMALL, text_color=MUTED,
        ).grid(row=3, column=0, pady=(0, 10))

    def _maximize_window(self) -> None:
        try:
            self.root.update_idletasks()
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
            except Exception:
                pass

    def _update_license_badge(self) -> None:
        button = getattr(self, "license_button", None)
        if button is None:
            return
        if self.license_manager is None:
            button.configure(text="开发模式", text_color=MUTED, fg_color="#1b2b46")
            return
        status = self.license_manager.status()
        button.configure(text=self.license_manager.license_summary())
        if status.kind == "commercial":
            button.configure(text_color=ACCENT)
        elif status.kind == "trial" and (status.days_left or 0) <= 2:
            button.configure(text_color=WARN)
        elif not status.can_run:
            button.configure(text_color=DANGER)
        else:
            button.configure(text_color=ACCENT)

    def _open_license_dialog(self) -> None:
        if self.license_manager is None:
            return
        status = self.license_manager.evaluate()
        dialog = LicenseDialog(self.root, self.license_manager, status)
        self.root.wait_window(dialog)
        self._update_license_badge()
        if dialog.result:
            self._license_locked = False

    def _license_tick(self) -> None:
        if self.license_manager:
            status = self.license_manager.evaluate()
            self._update_license_badge()
            if status.is_trial and (status.days_left or 0) <= 2 and not self._license_warning_shown:
                self._license_warning_shown = True
                messagebox.showwarning(
                    "试用即将到期",
                    f"7 天免费试用剩余 {status.days_left} 天。到期后可联系作者购买买断授权；"
                    "已生成的素材、配置和报告不会被删除。",
                )
            if not status.can_run and not self._license_locked:
                self._license_locked = True
                messagebox.showwarning("授权不可用", status.message)
            self.root.after(60000, self._license_tick)

    def _open_help(self) -> None:
        win = ctk.CTkToplevel(self.root)
        win.title("使用说明 — DJI D-Log M Batch Grader")
        win.geometry("820x640")
        win.minsize(620, 480)
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(win, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="使用说明", font=(FONT_UI, 24, "bold"), text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head, text="作者：Hu080608 · 本地离线处理 · 默认 LUT 与自定义 LUT 分开管理",
            font=FONT_BODY, text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        text = ctk.CTkTextbox(
            win, fg_color=CARD_ALT, text_color="#cbd5e1", font=FONT_BODY,
            corner_radius=10, border_width=0, wrap="word",
        )
        text.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        text.insert("1.0", self._help_content())
        text.configure(state="disabled")
        ctk.CTkButton(
            win, text="关闭", width=90, height=32, corner_radius=9,
            fg_color=ACCENT_DARK, hover_color="#0f766e", text_color=TEXT,
            command=win.destroy,
        
                font=FONT_SMALL,).grid(row=2, column=0, pady=(0, 16))

    def _help_content(self) -> str:
        return """
DJI D-Log M Batch Grader 使用说明
作者：Hu080608

一、最快开始（4 步）
1. 把照片、视频或整个文件夹拖到左上拖拽区域。
2. 选择输出文件夹（默认软件目录下 output/）。
3. 简易模式可直接点击“快速调色”模板或“一键推荐”；专业模式可打开“浏览LUT库”，进入后按官方/热门网络/自定义筛选。
4. 用“风格强度”调整效果强弱，再点击“开始批处理”。

二、支持的输入
照片：JPG/JPEG、PNG、TIF/TIFF、HEIC（可选依赖）。
RAW：DNG/CR2/CR3/NEF/NRW/ARW/SRF/SR2/RAF/RW2/ORF/PEF/SRW 等 LibRaw 常见格式，输出 16-bit TIFF。
视频：MP4、MOV、M4V。
.SRT 字幕文件会自动忽略，不计入失败。
处理范围：只处理视频 / 视频 + RAW / 全部处理，默认全部处理；范围外文件跳过并计数。

三、输出格式
H.264 MP4 8-bit：兼容优先。
H.265/HEVC MP4 8-bit：体积更小。
H.265/HEVC MP4 10-bit：保留更多暗部与天空渐变。
ProRes 422 HQ MOV 10-bit：剪辑母版。

四、质量预设
极致画质 / 高质量 / 标准 / 极速会自动映射 CRF、CPU preset 和 GPU 码率。
手动拖动 CRF 会切换为“自定义”。

五、简易模式与专业模式
右上角可切换模式。简易模式显示快速模板、一键推荐、风格强度和导出；专业模式保留 LUT、RAW、编码、并发和高级设置。
所有模板和风格强度最终都通过同一套 LUT 引擎处理，不削弱专业能力。

六、LUT 库
默认 LUT 库内置 113 个 3D LUT：55 个 DJI 官方 LUT（25 个设备/系列）和 58 个“热门网络 LUT”风格。
程序默认每 24 小时检查一次 DJI 官方目录，发现新机型/LUT 会自动下载补充；
也可以点击“同步DJI官方LUT库”手动检查。
点击“浏览LUT库”后，可在弹窗内按官方、热门网络、自定义类型以及设备、类别筛选，并支持鼠标滚轮。
来源统一分为“默认”和“自定义”；“热门网络 LUT”属于默认内置分区，只有用户导入的 LUT 归为“自定义”。
也可以点击“导入 .cube”加载自己的 LUT。调色模式还提供“预览”，可对比默认样片或队列素材的前后效果。

七、任务队列
文件导入后会立即显示为“待处理”。
状态流转：待处理 → 处理中 → 成功 / 失败。
取消显示为“已取消”，输出已存在显示为“跳过”，导入无效显示“导入失败”。
失败文件可点击“重试失败”只重新处理失败项。
每次启动自动清空任务队列；只清空队列，不删除配置、报告和历史记录。
右键单个任务项提供“开始 / 重试 / 取消 / 删除”；删除仅移除队列项，不删除源文件；批处理运行中不可操作。
报告自动写入 reports/ 目录（JSON + CSV）。
批次结束和日志会显示“本次处理总耗时：时:分:秒”。

八、音频
优先复制原始音频；目标容器不兼容时自动回退 AAC/PCM。
多音轨、章节、元数据尽可能保留。

九、监听文件夹
开启“监听输入文件夹”后，新文件会自动入队；
当前批次忙完会自动处理下一批。

十、试用与授权
软件可免费从 GitHub Releases 下载，首次启动自动开始 7 天免费试用，无需授权。
试用期间功能全部可用，输出不加水印；到期后停止新建任务，但不会删除已有文件。
试用到期后可复制机器码，添加作者 QQ：3643791089 购买买断授权。
右上角“授权信息”可复制机器码、导入授权或查看剩余时间。

十一、隐私与诊断
素材全程本地处理，不上传。
只有配置 telemetry_endpoint 并开启“匿名诊断”时才会上传匿名错误信息。

十二、应用更新
应用更新只从 GitHub Releases 检查。
确认更新后主界面会关闭，并打开独立更新进度页，持续显示下载、校验、解压、安装和启动新版本的状态。
更新包通过 SHA-256 校验后才安装，并保留用户配置、自定义 LUT、授权、输出和日志。

十三、取消与退出
取消会终止当前 FFmpeg 并清理当前半成品。
已完成文件会保留。
""".strip()

    def _handle_callback_exception(self, exc_type, exc, tb) -> None:
        try:
            record_exception(
                exc_type, exc, tb,
                enabled=bool(self.telemetry_var.get()),
                endpoint=str(self.config.telemetry_endpoint or ""),
            )
        except Exception:
            pass
        messagebox.showerror("程序异常", f"{exc_type.__name__}: {exc}\n\n诊断信息已写入 logs/diagnostics/")

    def _check_updates(self, manual: bool = True) -> None:
        if self.worker and self.worker.is_alive():
            if manual:
                messagebox.showinfo("任务进行中", "当前批处理仍在进行，请完成或取消后再检查更新。")
            return
        if manual:
            self._append_log("INFO", "正在从 GitHub Releases 检查更新…")
        def _worker():
            try:
                info = check_for_update()
                self.events.put(("update", info, manual))
            except Exception as exc:
                self.events.put(("update_error", str(exc), manual))
        threading.Thread(target=_worker, daemon=True).start()

    def _download_update(self, info) -> None:
        """Start the independent updater window and close the main window."""
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "当前批处理仍在进行，请完成或取消后再更新。")
            return
        if not messagebox.askyesno(
            "开始更新",
            f"将更新到 v{info.version}。更新期间主界面会关闭，"
            "并显示独立的更新进度窗口。" + chr(10) * 2
            + "是否继续？",
        ):
            return
        try:
            launch_updater(info)
        except Exception as exc:
            messagebox.showerror("更新启动失败", str(exc))
            return
        self._append_log("INFO", f"已启动独立更新程序，准备更新到 v{info.version}")
        self.closing = True
        self._stop_watcher()
        self.root.withdraw()
        self.root.after(200, self.root.destroy)

    def _append_log(self, level: str, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{level}] {message}" + chr(10))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_queue_view(self) -> None:
        try:
            children = self.job_tree.get_children()
            if children:
                self.job_tree.delete(*children)
        except tk.TclError:
            pass
        self.job_rows.clear()
        self.current_jobs.clear()

    def _status_text(self, status: str) -> str:
        return JOB_STATUS_LABELS.get(status, status)

    def _all_job_dicts(self) -> list[dict]:
        by_id: dict[int, dict] = {}
        for job in self.last_jobs:
            try:
                by_id[int(job.get("job_id"))] = dict(job)
            except (TypeError, ValueError):
                continue
        for key, job in self.current_jobs.items():
            by_id[int(key)] = dict(job)
        return [by_id[key] for key in sorted(by_id)]

    def _update_queue_counts(self) -> None:
        jobs = self._all_job_dicts()
        counts = {key: 0 for key in JOB_STATUS_LABELS}
        for job in jobs:
            status = str(job.get("status") or "pending")
            counts[status] = counts.get(status, 0) + 1
        self.counts_var.set(
            f"待处理 {counts.get('pending', 0)}   成功 {counts.get('success', 0)}   "
            f"失败 {counts.get('failed', 0)}   跳过 {counts.get('skipped', 0)}   "
            f"总计 {len(jobs)}   总耗时 {self._last_batch_duration_text}"
        )

    def _clear_queue_on_open(self) -> None:
        """Every application start begins with an empty visible queue."""
        try:
            self.queue_store.save_state([], status="empty", strict=True)
        except Exception as exc:
            self._append_log("WARN", f"写入空队列状态失败：{exc}")
        self.current_jobs.clear()
        self.last_jobs = []
        self.job_rows.clear()
        self._clear_queue_view()
        self.input_path = None
        self.selected_files = []
        self._update_input_status()
        self._last_batch_duration_text = "—"
        self.progressbar.set(0)
        self.progress_text_var.set("0%")
        self.counts_var.set("待处理 0   成功 0   失败 0   跳过 0   总计 0   总耗时 —")
        self.status_var.set("就绪 · 队列已清空")
        self._append_log("INFO", "启动时已清空任务队列；配置、报告和历史记录未删除。")

    def _change_job_status(self, job_id: int, new_status: str) -> None:
        if new_status not in JOB_STATUS_LABELS or new_status == "import_failed":
            raise ValueError(f"不支持的任务状态：{new_status}")
        if self.worker and self.worker.is_alive():
            raise RuntimeError("批处理正在运行，不能修改任务状态")
        jobs = self._all_job_dicts()
        target_index = next(
            (index for index, job in enumerate(jobs) if int(job.get("job_id", -1)) == job_id),
            None,
        )
        if target_index is None:
            raise RuntimeError("任务项已被移除，无法修改")
        old_job = self.current_jobs.get(job_id)
        if old_job is None:
            raise RuntimeError("任务项已被移除，无法修改")
        current_status = str(old_job.get("status") or "pending")
        if current_status == "running":
            raise RuntimeError("任务正在处理中，不能修改状态")
        if current_status == new_status:
            raise RuntimeError("已经是当前状态")

        updated = dict(old_job)
        updated["status"] = new_status
        updated["error"] = ""
        if new_status == "pending":
            updated["progress"] = 0.0
            updated["started_at"] = ""
            updated["finished_at"] = ""
            updated["duration_sec"] = None
        elif new_status == "running":
            updated["progress"] = 0.0
            updated["started_at"] = now_iso()
            updated["finished_at"] = ""
            updated["duration_sec"] = None
        else:
            updated["progress"] = 1.0
            if not updated.get("finished_at"):
                updated["finished_at"] = now_iso()
            if new_status in {"failed", "cancelled", "skipped"}:
                updated["error"] = f"手动修改状态：{JOB_STATUS_LABELS[new_status]}"

        jobs[target_index] = updated
        try:
            self.queue_store.save_state(
                [JobRecord.from_dict(job) for job in jobs],
                status="manual",
                strict=True,
            )
        except Exception as exc:
            raise RuntimeError(f"状态保存失败，原状态已保留：{exc}") from exc

        self.last_jobs = jobs
        self._apply_job_event(updated)
        self._update_queue_counts()
        self._append_log(
            "INFO",
            f"手动修改任务状态：{updated.get('relative') or job_id} "
            f"{self._status_text(current_status)} → {JOB_STATUS_LABELS[new_status]}",
        )
        self.status_var.set(
            f"任务状态已修改：{updated.get('relative') or job_id} → "
            f"{JOB_STATUS_LABELS[new_status]}"
        )

    def _show_job_context_menu(self, event) -> None:
        iid = self.job_tree.identify_row(event.y)
        if not iid:
            if not self.current_jobs:
                self.status_var.set("队列为空，无法修改任务状态")
            return
        try:
            job_id = int(iid)
        except ValueError:
            return
        job = self.current_jobs.get(job_id)
        if job is None:
            return
        self.job_tree.selection_set(iid)
        current_status = str(job.get("status") or "pending")
        busy = bool(self.worker and self.worker.is_alive()) or current_status == "running"
        menu = tk.Menu(
            self.root, tearoff=0, bg=CARD, fg=TEXT,
            activebackground=ACCENT_DARK, activeforeground=TEXT,
            disabledforeground=MUTED, font=(FONT_UI, 13),
        )
        menu.add_command(
            label=f"当前状态：{self._status_text(current_status)}",
            state="disabled",
        )
        menu.add_separator()
        if busy:
            menu.add_command(label="任务处理中，操作不可用", state="disabled")
        else:
            menu.add_command(
                label="开始",
                command=lambda: self._start_job_from_menu(job_id, retry=False),
            )
            menu.add_command(
                label="重试",
                command=lambda: self._start_job_from_menu(job_id, retry=True),
            )
            menu.add_command(
                label="取消",
                state="disabled" if current_status == "cancelled" else "normal",
                command=lambda: self._cancel_job_from_menu(job_id),
            )
            menu.add_command(
                label="删除",
                command=lambda: self._delete_job_from_menu(job_id),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _job_source(self, job_id: int) -> Path | None:
        job = self.current_jobs.get(job_id)
        if not job:
            return None
        raw = str(job.get("source") or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        return path if path.exists() and path.is_file() else None

    def _start_job_from_menu(self, job_id: int, *, retry: bool) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "请等待当前批处理结束后再操作。")
            return
        job = self.current_jobs.get(job_id)
        if not job:
            messagebox.showwarning("任务不存在", "该任务项已不存在，可能已被清空。")
            return
        source = self._job_source(job_id)
        if source is None:
            messagebox.showwarning(
                "无法开始",
                "该任务没有可用的源文件路径，无法单独开始处理。"
                + chr(10) * 2
                + "请重新导入素材。",
            )
            return
        self.input_path = source.parent.resolve()
        self.selected_files = [source.resolve()]
        self._update_input_status()
        self._append_log(
            "INFO",
            f"{'重试' if retry else '开始'}单项任务：{source.name}",
        )
        self._start()

    def _cancel_job_from_menu(self, job_id: int) -> None:
        try:
            self._change_job_status(job_id, "cancelled")
        except Exception as exc:
            messagebox.showerror("取消失败", str(exc))

    def _delete_job_from_menu(self, job_id: int) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "批处理进行中，不能删除任务项。")
            return
        job = self.current_jobs.get(job_id)
        if not job:
            messagebox.showwarning("任务不存在", "该任务项已不存在。")
            return
        if not messagebox.askyesno(
            "删除任务项",
            f"从队列中删除“{job.get('relative') or job_id}”？"
            + chr(10) * 2
            + "只移除队列项，不会删除源文件、输出或历史报告。",
        ):
            return
        jobs = [item for item in self._all_job_dicts() if int(item.get("job_id", -1)) != job_id]
        try:
            self.queue_store.save_state(
                [JobRecord.from_dict(item) for item in jobs],
                status="manual",
                strict=True,
            )
        except Exception as exc:
            messagebox.showerror("删除失败", f"队列状态保存失败，原状态已保留：{exc}")
            return
        self.last_jobs = jobs
        self.current_jobs.pop(job_id, None)
        self.job_rows.discard(job_id)
        try:
            if self.job_tree.exists(str(job_id)):
                self.job_tree.delete(str(job_id))
        except tk.TclError:
            pass
        self._update_queue_counts()
        self._append_log("INFO", f"已从队列删除：{job.get('relative') or job_id}")
        self.status_var.set("已删除任务项" if jobs else "队列已清空")

    def _manual_status_from_menu(self, job_id: int, status: str) -> None:
        try:
            self._change_job_status(job_id, status)
        except Exception as exc:
            messagebox.showerror("状态修改失败", str(exc))

    @staticmethod
    def _format_duration(seconds) -> str:
        if seconds is None:
            return "—"
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return "—"
        if value < 1:
            return f"{value * 1000:.0f}ms"
        if value < 60:
            return f"{value:.1f}s"
        minutes = int(value // 60)
        remainder = value - minutes * 60
        return f"{minutes}m {remainder:.0f}s"

    def _job_values(self, job: dict) -> tuple:
        error = str(job.get("error") or "")
        encoder = str(job.get("encoder") or "")
        if job.get("audio_mode"):
            encoder += f" / {job['audio_mode']}"
        return (
            job.get("relative") or Path(str(job.get("source", ""))).name,
            self._status_text(str(job.get("status", ""))),
            f"{float(job.get('progress') or 0) * 100:.0f}%",
            self._format_duration(job.get("duration_sec")),
            encoder,
            error.replace(chr(10), " ")[:120],
        )

    def _apply_job_event(self, job: dict) -> None:
        job_id = int(job.get("job_id", -1))
        if job_id < 0:
            return
        self.current_jobs[job_id] = job
        iid = str(job_id)
        values = self._job_values(job)
        tag = str(job.get("status", "pending"))
        if self.job_tree.exists(iid):
            self.job_tree.item(iid, values=values, tags=(tag,))
        else:
            self.job_tree.insert("", "end", iid=iid, values=values, tags=(tag,))
        self.job_rows.add(job_id)
        if job.get("status") in {"running", "success", "failed", "cancelled", "import_failed"}:
            try:
                self.job_tree.see(iid)
            except tk.TclError:
                pass

    def _preview_output_name(self, source: Path) -> str:
        profile = get_output_profile(self.profile_key_by_label.get(self.output_profile_var.get(), "h264_mp4"))
        ext = source.suffix.lower()
        if ext in {".mp4", ".mov", ".m4v"}:
            out_ext = profile.extension
        elif ext in {".heic", ".heif"}:
            out_ext = ".jpg"
        elif ext in RAW_EXTS:
            out_ext = ".tif"
        else:
            out_ext = ext
        return f"{source.stem}{self.config.output_suffix}{out_ext}"

    def _show_import_preview_limited(self, files: list[Path], base_dir: Path) -> None:
        ordered = sorted(files, key=lambda p: str(p).casefold())
        preview = ordered[:MAX_PREVIEW_FILES]
        self._show_import_preview(preview, base_dir)
        if len(ordered) > len(preview):
            self._append_log(
                "INFO",
                f"共扫描到 {len(ordered)} 个媒体文件；任务队列仅预览前 {len(preview)} 个，"
                "批处理仍会处理全部文件。",
            )
            self.counts_var.set(
                f"待处理 {len(ordered)}   成功 0   失败 0   跳过 0   总计 {len(ordered)}"
                f"（仅预览前 {len(preview)} 个）"
            )
            self.status_var.set(f"已扫描 {len(ordered)} 个文件，等待开始")

    def _show_import_preview(self, files: list[Path], base_dir: Path) -> None:
        self.last_jobs = []
        self._clear_queue_view()
        for index, source in enumerate(sorted(files, key=lambda p: str(p).casefold())):
            try:
                rel = source.resolve().relative_to(base_dir.resolve()).as_posix()
            except ValueError:
                rel = source.name
            job = {
                "job_id": index, "source": str(source), "relative": rel,
                "output": "", "kind": "video" if source.suffix.lower() in {".mp4", ".mov", ".m4v"} else "photo",
                "status": "pending", "progress": 0.0, "encoder": "", "audio_mode": "",
                "attempts": 0, "error": "",
            }
            self._apply_job_event(job)
        self.counts_var.set(f"待处理 {len(files)}   成功 0   失败 0   跳过 0   总计 {len(files)}")
        self.status_var.set(f"已导入 {len(files)} 个文件，等待开始")

    def _show_import_failure(self, reason: str) -> None:
        self.last_jobs = []
        self._clear_queue_view()
        self._apply_job_event({
            "job_id": 0, "source": "", "relative": "导入失败", "output": "",
            "kind": "", "status": "import_failed", "progress": 0.0,
            "encoder": "", "audio_mode": "", "attempts": 0, "error": reason,
        })
        self.counts_var.set("待处理 0   成功 0   失败 0   跳过 0   总计 0")
        self.status_var.set("导入失败：没有有效照片或视频")

    def _scan_import_folder(self, folder: Path, token: int, recursive: bool, excluded: Path, scope: str) -> None:
        try:
            if not folder.exists() or not folder.is_dir():
                self.events.put(("preview_import_done", token, [], folder, "输入文件夹不存在"))
                return
            files: list[Path] = []
            discovered = 0

            def on_walk_error(_error) -> None:
                return

            if recursive:
                walker = os.walk(folder, topdown=True, onerror=on_walk_error, followlinks=False)
            else:
                try:
                    names = sorted(
                        name for name in os.listdir(folder)
                        if (folder / name).is_file()
                    )
                except OSError as exc:
                    self.events.put(("preview_import_done", token, [], folder, str(exc)))
                    return
                walker = [(str(folder), [], names)]

            for root, dirs, names in walker:
                root_path = Path(root)
                dirs[:] = sorted(
                    [
                        name for name in dirs
                        if not (root_path / name).resolve().is_relative_to(excluded)
                    ],
                    key=str.casefold,
                )
                for name in sorted(names, key=str.casefold):
                    path = root_path / name
                    try:
                        if not path.is_file():
                            continue
                        resolved = path.resolve()
                        if resolved.is_relative_to(excluded):
                            continue
                        ext = resolved.suffix.lower()
                        if ext in IGNORED_EXTS or ext not in SUPPORTED_EXTS:
                            continue
                        if not is_file_in_scope(resolved, scope):
                            continue
                        files.append(resolved)
                        discovered += 1
                        if discovered % 500 == 0:
                            self.events.put(("scan_progress", token, discovered, folder))
                    except OSError:
                        continue
            self.events.put(("preview_import_done", token, sorted(files, key=lambda p: str(p).casefold()), folder, ""))
        except Exception as exc:
            self.events.put(("preview_import_done", token, [], folder, str(exc)))

    def _handle_import_preview_done(self, token: int, files: list[Path], folder: Path, error: str) -> None:
        if token != self._import_token:
            return
        if error:
            self._show_import_failure(error)
            self._append_log("ERROR", f"扫描输入文件夹失败：{error}")
        elif files:
            self.selected_files = []
            self._show_import_preview_limited(files, folder)
            self._append_log("INFO", f"已导入文件夹，等待处理文件 {len(files)} 个：{folder}")
        else:
            self._show_import_failure(
                "没有找到当前处理范围内可处理的文件。支持 JPG/PNG/TIFF/HEIC、"
                "常见 RAW（DNG/CR2/NEF/ARW 等）和 MP4/MOV/M4V；.SRT 会自动忽略。"
            )
            self._append_log("WARN", f"输入文件夹没有有效媒体文件：{folder}")

    def _load_last_queue(self) -> None:
        try:
            _status, jobs = self.queue_store.load_state()
            if not jobs:
                return
            if _status in {"prepared", "running"}:
                for job in jobs:
                    if job.status in {"pending", "running"}:
                        job.status = "failed"
                        job.error = "上次程序退出导致任务中断，可点击“重试失败”。"
                self.queue_store.save_state(jobs, status="interrupted")
            self.last_jobs = [job.to_dict() for job in jobs]
            self._clear_queue_view()
            for job in self.last_jobs:
                self._apply_job_event(job)
            failed = sum(1 for job in self.last_jobs if job.get("status") == "failed")
            self._append_log("INFO", f"已加载上次队列记录：{len(self.last_jobs)} 个任务，失败 {failed} 个。")
        except Exception as exc:
            self._append_log("WARN", f"读取上次队列记录失败：{exc}")

    def _retry_failed(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "请等待当前批处理结束后再重试失败项。")
            return
        jobs = self.last_jobs or list(self.current_jobs.values())
        failed = [
            Path(str(job.get("source")))
            for job in jobs
            if job.get("status") == "failed" and Path(str(job.get("source", ""))).exists()
        ]
        if not failed:
            messagebox.showinfo("没有失败项", "当前队列中没有可重试的失败文件。")
            return
        parents = [p.parent.resolve() for p in failed]
        try:
            common = Path(os.path.commonpath([str(p) for p in parents]))
        except ValueError:
            common = parents[0]
        self.input_path = common
        self.selected_files = sorted(failed, key=lambda p: str(p).casefold())
        self._update_input_status()
        self._show_import_preview(self.selected_files, common)
        self._append_log("INFO", f"准备重试 {len(failed)} 个失败文件。")
        self._start()

    def _clear_finished_jobs(self) -> None:
        keep = [
            job for job in (self.last_jobs or list(self.current_jobs.values()))
            if job.get("status") not in {"success", "skipped", "cancelled"}
        ]
        self.last_jobs = keep
        self._clear_queue_view()
        for job in keep:
            self._apply_job_event(job)
        self._append_log("INFO", "已清理成功/跳过/已取消任务，保留失败项。")

    def _open_reports(self) -> None:
        self._open_path(REPORT_DIR)


    def _on_watch_toggle(self) -> None:
        if self.watch_var.get():
            self._restart_watcher()
            if self.watcher:
                self._append_log("INFO", f"已开启监听：{self.input_path}")
        else:
            self._stop_watcher()
            self.watch_pending.clear()
            self._append_log("INFO", "已关闭监听输入文件夹。")

    def _stop_watcher(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

    def _restart_watcher(self) -> None:
        self._stop_watcher()
        if not self.watch_var.get() or not self.input_path or not self.input_path.is_dir():
            return
        output_dir = project_path(self.output_var.get() or "output")
        self.watcher = FolderWatcher(
            self.input_path,
            recursive=bool(self.recursive_var.get()),
            interval_seconds=float(self.config.watch_interval_seconds),
            output_queue=self.watch_queue,
            exclude_dirs=[output_dir],
            scope=self._current_scope(),
        )
        self.watcher.start()

    def _schedule_watch_poll(self) -> None:
        self.root.after(250, self._poll_watch_queue)

    def _poll_watch_queue(self) -> None:
        try:
            while True:
                new_files = self.watch_queue.get_nowait()
                self.watch_pending.extend(new_files)
                self._append_log("INFO", f"监听发现 {len(new_files)} 个新文件，已加入待处理队列。")
        except queue.Empty:
            pass
        except Exception as exc:
            self._append_log("WARN", f"监听文件夹处理失败：{exc}")
        if self.watch_pending and not (self.worker and self.worker.is_alive()):
            self._start_watch_batch()
        self._schedule_watch_poll()

    def _start_watch_batch(self) -> None:
        pending = [p for p in self.watch_pending if p.exists()]
        self.watch_pending.clear()
        if not pending:
            return
        try:
            common = Path(os.path.commonpath([str(p.parent.resolve()) for p in pending]))
        except ValueError:
            common = pending[0].parent.resolve()
        self.input_path = common
        self.selected_files = sorted(pending, key=lambda p: str(p).casefold())
        self._update_input_status()
        self._show_import_preview(self.selected_files, common)
        self._append_log("INFO", f"自动处理监听到的 {len(pending)} 个文件。")
        self._start()

    def _on_quality_preset_change(self, label: str) -> None:
        self.quality_preset_var.set(label)
        key = self.quality_preset_key_by_label.get(label, "custom")
        if key == "custom":
            return
        preset = QUALITY_PRESETS[key]
        self._applying_preset = True
        try:
            if preset.get("crf") is not None:
                self.crf_var.set(int(preset["crf"]))
                self.crf_value_label.configure(text=str(self.crf_var.get()))
        finally:
            self._applying_preset = False
        self._append_log(
            "INFO",
            f"质量预设：{label}（CRF {preset['crf']} / {preset['preset']} / GPU {preset['hardware_bitrate']}）",
        )

    def _on_quality_change(self, value) -> None:
        self.quality_var.set(int(float(value)))
        self.quality_value_label.configure(text=str(int(float(value))))

    def _on_crf_change(self, value) -> None:
        self.crf_var.set(int(float(value)))
        self.crf_value_label.configure(text=str(int(float(value))))
        if not self._applying_preset:
            self.quality_preset_var.set(self.quality_preset_labels.get("custom", "自定义"))

    def _current_scope(self) -> str:
        return self.scope_key_by_label.get(self.scope_var.get(), DEFAULT_SCOPE)

    def _on_scope_change(self, label: str) -> None:
        scope = self.scope_key_by_label.get(label, DEFAULT_SCOPE)
        self.config.import_scope = scope
        self._append_log("INFO", f"处理范围切换为：{SCOPE_LABELS[scope]}")
        self._update_input_status()
        if self.selected_files:
            preview = [p for p in self.selected_files if is_file_in_scope(p, scope)]
            if preview:
                self._show_import_preview(preview, self.input_path or preview[0].parent)
                self.status_var.set(f"已导入 {len(preview)} 个文件，等待开始")
            else:
                self._show_import_failure("当前处理范围下没有可处理文件。")
            self._restart_watcher()
            return
        if self.input_path and not (self.worker and self.worker.is_alive()):
            self._set_input_folder(self.input_path)
        else:
            self._restart_watcher()

    def _update_input_status(self) -> None:
        if self.selected_files:
            scope = self._current_scope()
            supported = [p for p in self.selected_files if p.suffix.lower() in SUPPORTED_EXTS]
            in_scope = [p for p in supported if is_file_in_scope(p, scope)]
            out_of_scope = len(supported) - len(in_scope)
            unsupported = len(self.selected_files) - len(supported)
            names = "、".join(p.name for p in in_scope[:3])
            if len(in_scope) > 3:
                names += f" 等 {len(in_scope)} 个文件"
            extra = f"（当前范围可处理 {len(in_scope)}，范围外 {out_of_scope}，不支持 {unsupported}）"
            self.input_status_var.set(f"已拖入 {len(self.selected_files)} 个文件{extra}：{names}")
        elif self.input_path:
            self.input_status_var.set(f"文件夹：{self.input_path}")
        else:
            self.input_status_var.set("尚未选择素材，可拖拽文件 / 文件夹到窗口")

    def _set_input_folder(self, folder: Path) -> None:
        self.input_path = folder.resolve()
        self.selected_files = []
        self._update_input_status()
        self._append_log("INFO", f"输入文件夹：{self.input_path}")
        self._restart_watcher()
        if not (self.worker and self.worker.is_alive()):
            self._import_token += 1
            token = self._import_token
            self.last_jobs = []
            self._clear_queue_view()
            self._apply_job_event({
                "job_id": 0, "source": "", "relative": "正在扫描输入文件夹…",
                "output": "", "kind": "", "status": "pending",
                "progress": 0.0, "encoder": "", "audio_mode": "",
                "attempts": 0, "error": "",
            })
            self.status_var.set("正在扫描输入文件夹…")
            recursive = bool(self.recursive_var.get())
            excluded = project_path(self.output_var.get() or "output").resolve()
            threading.Thread(
                target=self._scan_import_folder,
                args=(self.input_path, token, recursive, excluded, self._current_scope()),
                daemon=True,
            ).start()

    def _clear_input(self) -> None:
        self._stop_watcher()
        self.watch_pending.clear()
        self._import_token += 1
        self.input_path = None
        self.selected_files = []
        self._clear_queue_view()
        self.last_jobs = []
        self._update_input_status()
        self.counts_var.set("待处理 0   成功 0   失败 0   跳过 0   总计 0")
        self.status_var.set("就绪 · 请选择或拖入素材")

    def _on_files_dropped(self, paths: list[Path]) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "当前批处理仍在进行，请等待结束或点击取消后再导入新素材。")
            return
        existing = [Path(p) for p in paths if Path(p).exists()]
        if not existing:
            self._show_import_failure("没有识别到有效的文件或文件夹。")
            messagebox.showwarning("拖拽失败", "没有识别到有效的文件或文件夹。")
            return
        directories = [p for p in existing if p.is_dir()]
        files = [p for p in existing if p.is_file()]
        if directories:
            if len(directories) > 1:
                self._append_log("WARN", "一次拖入多个文件夹时只使用第一个文件夹。")
            self._set_input_folder(directories[0])
            if files:
                self._append_log("WARN", "文件夹和文件同时拖入时，已优先使用文件夹。")
            self.status_var.set(f"已选择文件夹：{directories[0].name}")
            return
        if not files:
            self._show_import_failure("拖入内容中没有文件。")
            messagebox.showwarning("拖拽失败", "拖入内容中没有文件。")
            return
        ignored = [p for p in files if p.suffix.lower() in IGNORED_EXTS]
        if ignored:
            files = [p for p in files if p.suffix.lower() not in IGNORED_EXTS]
            self._append_log("INFO", f"已自动忽略 {len(ignored)} 个 .SRT 字幕文件")
        if not files:
            self._show_import_failure("拖入内容只有 .SRT 字幕文件，已全部忽略；没有可处理的照片或视频。")
            messagebox.showinfo("没有可处理文件", "拖入内容只有 .SRT 字幕文件，已全部忽略。")
            return
        parents = [p.parent.resolve() for p in files]
        try:
            common = Path(os.path.commonpath([str(p) for p in parents]))
        except ValueError:
            common = parents[0]
        self.input_path = common
        self.selected_files = sorted(files, key=lambda p: str(p).casefold())
        self._update_input_status()
        scope = self._current_scope()
        supported = [p for p in self.selected_files if p.suffix.lower() in SUPPORTED_EXTS]
        in_scope = [p for p in supported if is_file_in_scope(p, scope)]
        out_of_scope = [p for p in supported if not is_file_in_scope(p, scope)]
        self._append_log(
            "INFO",
            f"拖入 {len(self.selected_files)} 个文件，其中支持格式 {len(supported)} 个，"
            f"当前处理范围可处理 {len(in_scope)} 个，公共上级目录：{common}",
        )
        if out_of_scope:
            self._append_log(
                "INFO",
                f"当前处理范围（{SCOPE_LABELS[scope]}）跳过 {len(out_of_scope)} 个文件："
                + "、".join(p.name for p in out_of_scope[:8])
                + (" 等" if len(out_of_scope) > 8 else ""),
            )
        if in_scope:
            self._show_import_preview_limited(in_scope, common)
        else:
            self._show_import_failure("当前处理范围内没有可处理的照片或视频格式。")
        self.status_var.set(f"当前范围已导入 {len(in_scope)} 个文件，等待开始")
        self._restart_watcher()

    def _browse_input(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("任务进行中", "当前批处理仍在进行，请等待结束或点击取消后再导入新素材。")
            return
        initial = self.input_path if self.input_path and self.input_path.exists() else PROJECT_ROOT
        chosen = filedialog.askdirectory(title="选择输入文件夹", initialdir=str(initial))
        if chosen:
            self._set_input_folder(Path(chosen).resolve())
            self.status_var.set(f"已选择文件夹：{Path(chosen).name}")

    def _browse_output(self) -> None:
        initial = project_path(self.output_var.get() or "output")
        chosen = filedialog.askdirectory(title="选择输出文件夹", initialdir=str(initial))
        if chosen:
            self.output_var.set(chosen)
            self._restart_watcher()

    def _open_luts(self) -> None:
        selected = project_path(self.lut_path_var.get())
        self._open_path(selected.parent if selected.parent.exists() else LUT_DIR)

    def _open_output(self) -> None:
        self._open_path(project_path(self.output_var.get() or "output"))

    def _open_logs(self) -> None:
        self._open_path(LOG_DIR)

    def _open_path(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("无法打开目录", f"{path}\n{exc}")

    def _refresh_lut_label(self) -> None:
        selected = project_path(self.lut_path_var.get())
        entry = next((e for e in self.lut_entries.values() if e.path.resolve() == selected), None)
        tag = entry.origin if entry is not None else "自定义"
        if selected.exists():
            self.lut_status_var.set(f"[{tag}] {selected.name}   ✓")
            self.lut_status_label.configure(text_color=OK)
        else:
            self.lut_status_var.set(
                f"[{tag}] 未找到：{selected.name}\n"
                f"路径：{selected}" + chr(10) + "可点击“浏览官方LUT库”“浏览网络热门LUT库”或“导入 .cube”重新选择"
            )
            self.lut_status_label.configure(text_color=DANGER)

    def _refresh_lut_library(self) -> None:
        try:
            entries, default_path = scan_lut_library()
        except Exception as exc:
            self._append_log("WARN", f"扫描 LUT 库失败：{exc}")
            return
        entries = sorted(entries, key=lambda e: (e.device.casefold(), e.category.casefold(), e.name.casefold()))
        self.lut_entries = {entry.label: entry for entry in entries}
        self.lut_count_label.configure(text=f"默认库 + 自定义：{len(entries)} 个")
        current = project_path(self.lut_path_var.get())
        match = next((entry for entry in entries if entry.path.resolve() == current), None)
        if match:
            if match.origin == "默认":
                self.lut_meta_var.set("")
                self.lut_meta_label.grid_remove()
            else:
                detail = f"[{match.origin}] {match.device} / {match.category}"
                if match.profile:
                    detail += f" / {match.profile}"
                if match.description:
                    detail += f" · {match.description}"
                self.lut_meta_var.set(detail)
                self.lut_meta_label.grid()
        elif current.exists():
            self.lut_meta_var.set("自定义 LUT（未在 manifest 中登记）")
            self.lut_meta_label.grid()
        else:
            self.lut_meta_var.set("LUT 文件不存在，请重新选择。")

    def _apply_lut_entry(self, entry) -> None:
        self._push_lut_history()
        self.lut_path_var.set(str(entry.path))
        if self._is_official_lut_path(entry.path):
            self.color_mode_var.set("色彩还原")
            self._set_strength(100)
        else:
            self.color_mode_var.set("调色")
        self._refresh_lut_library()
        self._refresh_lut_label()
        self._apply_color_mode_visibility()
        detail = f"已选择 LUT：{entry.device} / {entry.category} / {entry.name}"
        if entry.profile:
            detail += f"（{entry.profile}）"
        self._append_log("INFO", detail)

    def _update_lut_library(self, manual: bool = True) -> None:
        if self._lut_update_thread and self._lut_update_thread.is_alive():
            if manual:
                messagebox.showinfo("LUT 同步", "正在检查 DJI 官方 LUT 目录，请稍候。")
            return
        if manual:
            self._append_log("INFO", "正在检查 DJI 官方 LUT 更新…")
        def _worker():
            try:
                result = check_and_update_luts()
                self.events.put(("lut_update_done", result, manual))
            except Exception as exc:
                self.events.put(("lut_update_error", str(exc), manual))
        self._lut_update_thread = threading.Thread(target=_worker, daemon=True)
        self._lut_update_thread.start()

    def _open_lut_library(self) -> None:
        if not self.lut_entries:
            self._refresh_lut_library()
        entries = list(self.lut_entries.values())
        if not entries:
            messagebox.showinfo("LUT 库", "当前没有可用的 LUT。")
            return
        current = project_path(self.lut_path_var.get())
        LutLibraryDialog(
            self.root,
            entries,
            current,
            self._apply_lut_entry,
            title="LUT 库",
            subtitle="进入后可按官方 / 热门网络 / 自定义、设备和类别筛选",
        )

    def _confirm_lut(self, candidate: LutCandidate) -> bool:
        return messagebox.askyesno(
            "确认自动匹配 LUT",
            f"未找到精确文件名，但发现：\n\n{candidate.path.name}\n\n"
            f"原因：{candidate.reason}\n\n是否使用该 LUT？",
        )

    def _choose_lut(self) -> None:
        initial = project_path(self.lut_path_var.get()).parent
        if not initial.exists():
            initial = LUT_DIR
        chosen = filedialog.askopenfilename(
            title="选择 3D LUT 文件",
            initialdir=str(initial),
            filetypes=[("Cube 3D LUT", "*.cube"), ("所有文件", "*.*")],
        )
        if not chosen:
            return
        source = Path(chosen).expanduser().resolve()
        try:
            lut = CubeLUT.from_file(source)
            local_path, copied = import_lut_into_project(source)
        except LutError as exc:
            messagebox.showerror("LUT 错误", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("LUT 错误", f"无法读取 LUT：\n{source}\n{exc}")
            return
        self._push_lut_history()
        self.lut_path_var.set(str(local_path))
        self.color_mode_var.set("调色")
        self._refresh_lut_library()
        self._refresh_lut_label()
        self._apply_color_mode_visibility()
        self._append_log("INFO", f"已选择 LUT：{local_path}（{lut.size}^3）")
        if copied:
            self._append_log("INFO", "外部 LUT 已复制到项目内 luts/custom/")
        messagebox.showinfo(
            "LUT 已切换",
            f"当前 LUT：\n{local_path.name}\n\nLUT 尺寸：{lut.size}^3\n"
            "开始批处理时会保存为当前配置。",
        )

    # ------------------------------------------------------------- workflow
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if self.license_manager is not None:
            license_status = self.license_manager.evaluate()
            self._update_license_badge()
            if not license_status.can_run:
                self._license_locked = True
                self._open_license_dialog()
                license_status = self.license_manager.evaluate()
                if not license_status.can_run:
                    return
        if self.input_path is None:
            messagebox.showerror("缺少输入", "请拖拽素材或点击“选择文件夹”。")
            return
        input_dir = self.input_path.resolve()
        if not input_dir.is_dir():
            messagebox.showerror("输入错误", f"输入文件夹不存在：\n{input_dir}")
            return
        output_dir = project_path(self.output_var.get().strip() or "output")
        if input_dir == output_dir:
            messagebox.showerror("路径错误", "输入文件夹和输出文件夹不能相同。")
            return

        cfg = AppConfig(**self.config.__dict__)
        cfg.recursive = bool(self.recursive_var.get())
        cfg.import_scope = self._current_scope()
        cfg.lut_strength = self.lut_strength_var.get() / 100.0
        cfg.ui_mode = "simple" if self.simple_mode else "pro"
        cfg.output_profile = self.profile_key_by_label.get(
            self.output_profile_var.get(), self.config.output_profile
        )
        preset_key = self.quality_preset_key_by_label.get(self.quality_preset_var.get(), "custom")
        cfg.quality_preset = preset_key
        if preset_key != "custom":
            preset = QUALITY_PRESETS[preset_key]
            cfg.video_crf = int(preset["crf"])
            cfg.video_preset = str(preset["preset"])
            cfg.hardware_bitrate = str(preset["hardware_bitrate"])
        cfg.encoder_preference = self.encoder_key_by_label.get(
            self.encoder_pref_var.get(), "auto"
        )
        cfg.video_workers = 0 if self.video_workers_var.get() == "自动" else int(self.video_workers_var.get())
        cfg.photo_workers = 0 if self.photo_workers_var.get() == "自动" else int(self.photo_workers_var.get())
        cfg.jpeg_quality = int(self.quality_var.get())
        cfg.video_crf = int(self.crf_var.get())
        cfg.watch_enabled = bool(self.watch_var.get())
        cfg.telemetry_enabled = bool(self.telemetry_var.get())
        cfg.auto_check_updates = bool(self.auto_update_var.get())
        cfg.auto_update_luts = bool(self.auto_lut_update_var.get())
        # Input selection is intentionally session-only and never persisted.
        cfg.input_dir = ""
        cfg.output_dir = str(output_dir)
        problems = cfg.validate()
        if problems:
            messagebox.showerror("配置错误", "\n".join(problems))
            return

        selected_lut = project_path(self.lut_path_var.get())
        if not selected_lut.exists():
            messagebox.showerror(
                "LUT 错误",
                f"当前选择的 LUT 不存在：\n{selected_lut}\n\n"
                "请点击“浏览官方LUT库”“浏览网络热门LUT库”或“导入 .cube”重新选择。",
            )
            return
        try:
            lut_path, exact = resolve_lut(
                selected_lut, confirm=self._confirm_lut, assume_yes=False
            )
            lut = CubeLUT.from_file(lut_path)
            lut_path, copied = import_lut_into_project(lut_path)
        except LutError as exc:
            messagebox.showerror("LUT 错误", str(exc))
            return
        try:
            cfg.lut_file = lut_path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            cfg.lut_file = str(lut_path)
        try:
            save_config(cfg)
            self.config = cfg
        except Exception as exc:
            self._append_log("WARN", f"保存配置失败：{exc}")
        if copied:
            self._append_log("INFO", f"外部 LUT 已复制到项目内：{lut_path}")
        if not exact:
            self._append_log("WARN", f"已确认使用自动匹配的 LUT：{lut_path}")

        selected_files = list(self.selected_files)
        self.last_jobs = []
        self._clear_queue_view()
        self.cancel_event.clear()
        self.done = False
        self._set_running(True)
        self.progressbar.set(0)
        self.progress_text_var.set("0%")
        self.counts_var.set("成功 0   失败 0   跳过 0   总计 0")
        self.status_var.set("正在启动…")
        try:
            self.tabs.set("任务队列")
        except Exception:
            pass
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._append_log("INFO", f"输入目录：{input_dir}")
        if selected_files:
            self._append_log("INFO", f"本次仅处理拖入的 {len(selected_files)} 个文件")
        self._append_log("INFO", f"输出目录：{output_dir}")
        self._append_log("INFO", f"LUT：{lut_path}（{lut.size}^3）")

        self.worker = threading.Thread(
            target=self._worker_main,
            args=(input_dir, output_dir, lut, cfg, selected_files),
            daemon=True,
        )
        self.worker.start()
        self._schedule_poll()

    def _worker_main(
        self,
        input_dir: Path,
        output_dir: Path,
        lut: CubeLUT,
        cfg: AppConfig,
        selected_files: list[Path],
    ) -> None:
        log = AppLogger(callback=lambda level, msg: self.events.put(("log", level, msg)))
        self.log_window = log
        try:
            print_banner(log)
            log.info(f"加载 LUT：{lut.path}")
            log.info(f"LUT 尺寸：{lut.size}^3")
            processor = BatchProcessor(
                input_dir=input_dir,
                output_dir=output_dir,
                lut=lut,
                config=cfg,
                logger=log,
                cancel_callback=self.cancel_event.is_set,
                selected_files=selected_files or None,
                job_callback=lambda job: self.events.put(("job", job)),
                progress_callback=lambda frac, detail, result: self.events.put(
                    ("progress", frac, detail, result.success, result.failed,
                     result.skipped_unsupported, result.total)
                ),
            )
            result = processor.run()
            self.events.put(("done", result))
        except Exception as exc:
            log.exception("批处理发生严重错误", exc)
            try:
                record_exception(
                    type(exc), exc, exc.__traceback__,
                    enabled=bool(self.telemetry_var.get()),
                    endpoint=str(self.config.telemetry_endpoint or ""),
                )
            except Exception:
                pass
            self.events.put(("fatal", str(exc)))
        finally:
            log.close()

    def _set_running(self, running: bool) -> None:
        self.start_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _cancel(self) -> None:
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self.status_var.set("正在取消… 当前文件完成后停止")
            self._append_log("WARN", "用户点击取消，正在停止…")

    def _schedule_drop_poll(self) -> None:
        self.root.after(150, self._poll_drop_queue)

    def _poll_drop_queue(self) -> None:
        try:
            while True:
                paths = self.drop_queue.get_nowait()
                self._on_files_dropped(paths)
        except queue.Empty:
            pass
        except Exception as exc:
            self._append_log("ERROR", f"处理拖拽文件失败：{exc}")
        self._schedule_drop_poll()

    def _schedule_poll(self) -> None:
        if not self.poll_scheduled:
            self.poll_scheduled = True
            self.root.after(100, self._poll_events)

    def _poll_events(self) -> None:
        self.poll_scheduled = False
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1], event[2])
                elif kind == "job":
                    self._apply_job_event(event[1])
                elif kind == "preview_import_done":
                    self._handle_import_preview_done(event[1], event[2], event[3], event[4])
                elif kind == "scan_progress":
                    _, token, count, folder = event
                    if token == self._import_token:
                        self.status_var.set(f"正在扫描输入文件夹…已发现 {count} 个媒体文件")
                elif kind == "progress":
                    _, frac, detail, success, failed, unsupported, total = event
                    self.progressbar.set(frac)
                    self.progress_text_var.set(f"{frac * 100:.0f}%")
                    self.status_var.set(detail)
                    self.counts_var.set(
                        f"成功 {success}   失败 {failed}   跳过 {unsupported}   总计 {total}"
                    )
                elif kind == "done":
                    result: BatchResult = event[1]
                    self._finish(result)
                elif kind == "update":
                    info, manual = event[1], bool(event[2])
                    if info is None:
                        if manual:
                            messagebox.showinfo("检查更新", f"当前已是最新版本 v{__version__}。")
                        else:
                            self._append_log("INFO", f"GitHub Releases 检查完成，当前 v{__version__} 已是最新。")
                    else:
                        notes = extract_update_summary(str(info.notes or ""))
                        text = "发现新版本 v" + str(info.version) + "。" + chr(10) * 2
                        if notes:
                            text += "本次更新：" + chr(10) + notes + chr(10) * 2
                        text += "是否进入独立更新进度页并安装？"
                        if messagebox.askyesno("发现新版本", text):
                            self._download_update(info)
                elif kind == "update_error":
                    self._append_log("WARN", f"GitHub Releases 检查失败：{event[1]}")
                    if bool(event[2]):
                        messagebox.showwarning("检查更新失败", str(event[1]))
                elif kind == "lut_update_done":
                    result, manual = event[1], bool(event[2])
                    self._refresh_lut_library()
                    if result.new_files:
                        self._append_log("INFO", f"LUT 库同步完成：新增 {result.new_files} 个文件，设备 {', '.join(result.new_devices) or '无'}")
                        messagebox.showinfo(
                            "LUT 库已同步",
                            f"已从 DJI 官方目录新增 {result.new_files} 个 LUT。" + chr(10) +
                            f"新增设备：{', '.join(result.new_devices) or '现有设备补充'}",
                        )
                    elif manual:
                        detail = result.skipped_reason or "未发现需要新增的 LUT"
                        if result.errors:
                            detail += chr(10) + chr(10).join(result.errors[:4])
                        messagebox.showinfo("LUT 同步", detail)
                    elif result.errors:
                        self._append_log("WARN", f"LUT 库同步失败：{result.errors[0]}")
                    elif not manual:
                        self._append_log("INFO", "LUT 库自动检查完成：已是最新。")
                elif kind == "lut_update_error":
                    self._append_log("WARN", f"LUT 库同步失败：{event[1]}")
                    if bool(event[2]):
                        messagebox.showwarning("LUT 同步失败", str(event[1]))
                elif kind == "fatal":
                    self.done = True
                    self.status_var.set("发生错误")
                    self._set_running(False)
                    messagebox.showerror("批处理失败", event[1])
                    if self.closing:
                        self.root.destroy()
        except queue.Empty:
            pass
        if not self.done:
            self._schedule_poll()

    def _finish(self, result: BatchResult) -> None:
        self.done = True
        self._set_running(False)
        self.last_jobs = [job.to_dict() for job in result.jobs]
        if not result.cancelled:
            self.progressbar.set(1.0)
            self.progress_text_var.set("100%")
        self.status_var.set("已取消" if result.cancelled else "已完成")
        if result.report_json:
            self._append_log("INFO", f"本次报告：{result.report_json}")
        elapsed = format_duration_hms(getattr(result, "duration_sec", None))
        self._last_batch_duration_text = elapsed
        self.counts_var.set(
            f"成功 {result.success}   失败 {result.failed}   "
            f"跳过范围 {result.skipped_scope}   跳过不支持 {result.skipped_unsupported}   "
            f"总计 {result.total}   总耗时 {elapsed}"
        )
        if result.cancelled:
            messagebox.showwarning("已取消", "批处理已取消。之前已完成的文件会保留。")
        elif result.failed:
            detail = "\n".join(result.failures[:8])
            messagebox.showwarning(
                "部分失败",
                f"成功 {result.success}，失败 {result.failed}。\n\n{detail}\n\n请查看日志。",
            )
        else:
            messagebox.showinfo(
                "完成",
                f"处理完成：成功 {result.success}，失败 {result.failed}，"
                f"跳过不支持 {result.skipped_unsupported}。\n\n作者：Hu080608",
            )
        if self.watch_pending and not result.cancelled and not self.closing:
            self.root.after(500, self._start_watch_batch)
        if self.closing:
            self.root.destroy()

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("退出", "批处理仍在进行，取消并退出？"):
                return
            self.closing = True
            self.cancel_event.set()
            self.status_var.set("正在取消并退出…")
            return
        self._stop_watcher()
        for target in self.drop_targets:
            try:
                target.close()
            except Exception:
                pass
        self.root.destroy()


def launch_gui() -> None:
    configure_environment()
    cfg = load_config()
    install_exception_hooks(cfg.telemetry_enabled, cfg.telemetry_endpoint)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    root = ctk.CTk()
    manager = LicenseManager()
    root.update_idletasks()

    status = manager.evaluate()
    if not status.can_run:
        root.update()
        dialog = LicenseDialog(root, manager, status)
        root.wait_window(dialog)
        status = manager.evaluate()
        if not status.can_run:
            root.destroy()
            return

    GraderGUI(root, license_manager=manager)
    if status.is_new:
        root.after(500, lambda: messagebox.showinfo(
            "7 天免费试用已开始",
            "已开始 7 天免费试用。试用期间功能全部可用，输出不加水印。"
            + chr(10) * 2
            + f"机器码：{manager.machine_code}" + chr(10)
            + "试用到期后可添加作者 QQ：3643791089 购买买断授权。",
            parent=root,
        ))
    elif status.is_trial and (status.days_left or 0) <= 2:
        root.after(500, lambda: messagebox.showwarning(
            "试用即将到期",
            f"7 天免费试用剩余 {status.days_left} 天。到期后可添加作者 QQ：3643791089 购买买断授权，"
            "已生成的文件和配置不会被删除。",
            parent=root,
        ))
    root.mainloop()

