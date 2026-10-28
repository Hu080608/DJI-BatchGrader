"""Live before/after preview for the current LUT and strength."""
from __future__ import annotations

import io
import subprocess
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from .ffmpeg_tools import find_ffmpeg
from .lut import CubeLUT
from .paths import PROJECT_ROOT, child_environment

BG = "#080f1c"
CARD = "#111c31"
CARD_ALT = "#0b1526"
BORDER = "#203452"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#2dd4bf"
ACCENT_DARK = "#0d9488"
FONT_UI = "Microsoft YaHei UI"
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}


def _video_frame(path: Path) -> Image.Image:
    ffmpeg = find_ffmpeg()
    cmd = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-ss", "0.5", "-i", str(path), "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    cp = subprocess.run(
        cmd, capture_output=True, env=child_environment(),
        cwd=str(PROJECT_ROOT), timeout=30,
    )
    if cp.returncode != 0 or not cp.stdout:
        raise RuntimeError(cp.stderr.decode("utf-8", errors="replace")[-500:])
    return Image.open(io.BytesIO(cp.stdout)).convert("RGB")


class PreviewDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        lut: CubeLUT,
        strength_var,
        paths: list[Path],
        *,
        on_strength=None,
        on_commit=None,
    ):
        super().__init__(master)
        self.lut = lut
        self.strength_var = strength_var
        self.on_strength = on_strength
        self.on_commit = on_commit
        self.paths = [Path(p) for p in paths if Path(p).exists()]
        self.current_path: Path | None = None
        self.original: Image.Image | None = None
        self._original_photo = None
        self._graded_photo = None
        self.title("调色预览")
        self.geometry("1120x620")
        self.minsize(900, 520)
        self.configure(fg_color=BG)
        self.transient(master)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="调色预览", font=(FONT_UI, 25, "bold"), text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="拖动风格强度，右侧效果实时更新", font=(FONT_UI, 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        controls = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        controls.grid(row=1, column=0, sticky="ew", padx=22, pady=8)
        controls.grid_columnconfigure(1, weight=1)
        self.source_map = {"默认示例": PROJECT_ROOT / "assets" / "preview_sample.jpg"}
        for path in self.paths[:40]:
            label = path.name
            if label in self.source_map:
                label = f"{path.stem} · {path.parent.name}"
            self.source_map[label] = path
        ctk.CTkLabel(
            controls, text="预览素材", font=(FONT_UI, 12), text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=12)
        self.source_var = ctk.StringVar(value="默认示例")
        self.source_menu = ctk.CTkOptionMenu(
            controls, values=list(self.source_map), variable=self.source_var,
            width=300, height=32, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK,
            text_color=TEXT, font=(FONT_UI, 12), command=self._on_source_change,
        )
        self.source_menu.grid(row=0, column=1, sticky="w", padx=8, pady=12)
        ctk.CTkButton(
            controls, text="浏览文件", width=88, height=32, corner_radius=8,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            font=(FONT_UI, 12), command=self._browse_source,
        ).grid(row=0, column=2, padx=8, pady=12)
        ctk.CTkLabel(
            controls, text="原图 / 调色效果", font=(FONT_UI, 11), text_color=MUTED,
        ).grid(row=0, column=3, padx=14, pady=12)

        images = ctk.CTkFrame(self, fg_color="transparent")
        images.grid(row=2, column=0, sticky="nsew", padx=22)
        images.grid_columnconfigure(0, weight=1)
        images.grid_columnconfigure(1, weight=1)
        images.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(images, text="原始画面", font=(FONT_UI, 13, "bold"), text_color=MUTED).grid(row=0, column=0, pady=(4, 4))
        ctk.CTkLabel(images, text="调色效果", font=(FONT_UI, 13, "bold"), text_color=ACCENT).grid(row=0, column=1, pady=(4, 4))
        self.original_label = ctk.CTkLabel(images, text="", fg_color=CARD_ALT, corner_radius=10)
        self.original_label.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.graded_label = ctk.CTkLabel(images, text="", fg_color=CARD_ALT, corner_radius=10)
        self.graded_label.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        footer = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        footer.grid(row=3, column=0, sticky="ew", padx=22, pady=(8, 18))
        footer.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(footer, text="风格强度", font=(FONT_UI, 12, "bold"), text_color=TEXT).grid(row=0, column=0, padx=14, pady=14)
        self.slider = ctk.CTkSlider(
            footer, from_=0, to=100, number_of_steps=100,
            variable=self.strength_var, command=self._on_slider,
            height=18, progress_color=ACCENT_DARK, button_color=ACCENT,
            button_hover_color="#5eead4", fg_color="#1b2b46",
        )
        self.slider.grid(row=0, column=1, sticky="ew", padx=8)
        self.slider.bind("<ButtonRelease-1>", self._commit)
        self.percent_label = ctk.CTkLabel(footer, text=f"{self.strength_var.get()}%", width=48, font=(FONT_UI, 13, "bold"), text_color=ACCENT)
        self.percent_label.grid(row=0, column=2, padx=(8, 12))
        self.status_label = ctk.CTkLabel(self, text="", font=(FONT_UI, 11), text_color=MUTED)
        self.status_label.grid(row=4, column=0, sticky="w", padx=24, pady=(0, 10))

        self._load_path(self.source_map["默认示例"])

    def _on_source_change(self, label: str) -> None:
        path = self.source_map.get(label)
        if path:
            self._load_path(path)

    def _browse_source(self) -> None:
        chosen = filedialog.askopenfilename(
            title="选择预览素材",
            filetypes=[
                ("图片/视频", "*.jpg *.jpeg *.png *.tif *.tiff *.heic *.heif *.mp4 *.mov *.m4v"),
                ("所有文件", "*.*"),
            ],
        )
        if not chosen:
            return
        path = Path(chosen)
        self.source_map[path.name] = path
        self.source_menu.configure(values=list(self.source_map))
        self.source_var.set(path.name)
        self._load_path(path)

    def _load_path(self, path: Path) -> None:
        try:
            if path.suffix.lower() in VIDEO_EXTS:
                image = _video_frame(path)
            else:
                with Image.open(path) as opened:
                    image = opened.convert("RGB")
            image.thumbnail((480, 320))
            self.original = image.copy()
            self.current_path = path
            self._render()
            self.status_label.configure(text=f"预览：{path.name}")
        except Exception as exc:
            self.status_label.configure(text=f"无法加载预览：{exc}")

    def _on_slider(self, value) -> None:
        percent = int(round(float(value)))
        self.percent_label.configure(text=f"{percent}%")
        if self.on_strength:
            self.on_strength(percent)
        self._render()

    def _commit(self, _event=None) -> None:
        if self.on_commit:
            self.on_commit()

    def _render(self) -> None:
        if self.original is None:
            return
        effect = self.original.copy().filter(
            self.lut.blended(int(self.strength_var.get()) / 100.0).pillow_filter()
        )
        self._original_photo = ctk.CTkImage(
            light_image=self.original, dark_image=self.original, size=self.original.size
        )
        self._graded_photo = ctk.CTkImage(
            light_image=effect, dark_image=effect, size=effect.size
        )
        self.original_label.configure(image=self._original_photo)
        self.graded_label.configure(image=self._graded_photo)
