"""Dark standalone update progress window."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .core import (
    UpdateEngine,
    UpdateRequest,
    UpdateState,
    format_bytes,
    format_eta,
    launch_old_app,
)

BG = "#080f1c"
CARD = "#111c31"
CARD_ALT = "#0b1526"
BORDER = "#203452"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#2dd4bf"
ACCENT_DARK = "#0d9488"
DANGER = "#fb7185"
FONT_UI = "Microsoft YaHei UI"


class UpdateProgressWindow:
    def __init__(self, root: tk.Tk, request: UpdateRequest, request_path: Path):
        self.root = root
        self.request = request
        self.request_path = Path(request_path)
        self.states: queue.Queue[UpdateState] = queue.Queue()
        self.engine = UpdateEngine(request, request_path, on_state=self.states.put)
        self.running = False
        self.failed = False
        self.completed = False
        self.worker: threading.Thread | None = None
        self.dots = 0

        root.title("DJI D-Log M 正在更新")
        root.geometry("780x560")
        root.minsize(700, 520)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            root.eval("tk::PlaceWindow . center")
        except Exception:
            pass

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Updater.Horizontal.TProgressbar",
            troughcolor=CARD_ALT,
            background=ACCENT,
            bordercolor=BORDER,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=18,
        )

        self._build_ui()
        self.root.after(100, self._poll)
        self.root.after(300, self._start)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=36, pady=30)

        tk.Label(
            outer, text="正在更新",
            bg=BG, fg=TEXT, font=(FONT_UI, 27, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text=f"DJI D-Log M Batch Grader  {self.request.current_version}  →  {self.request.version}",
            bg=BG, fg=MUTED, font=(FONT_UI, 12), anchor="w",
        ).pack(fill="x", pady=(5, 20))

        card = tk.Frame(outer, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=22, pady=20)

        self.stage_label = tk.Label(
            inner, text="准备更新…", bg=CARD, fg=TEXT,
            font=(FONT_UI, 17, "bold"), anchor="w",
        )
        self.stage_label.pack(fill="x")
        self.detail_label = tk.Label(
            inner, text="正在准备更新文件", bg=CARD, fg=MUTED,
            font=(FONT_UI, 11), anchor="w", justify="left", wraplength=650,
        )
        self.detail_label.pack(fill="x", pady=(5, 15))

        self.progress = ttk.Progressbar(
            inner, style="Updater.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", maximum=100, value=0,
        )
        self.progress.pack(fill="x")
        self.percent_label = tk.Label(
            inner, text="0%", bg=CARD, fg=ACCENT,
            font=(FONT_UI, 24, "bold"), anchor="e",
        )
        self.percent_label.pack(fill="x", pady=(8, 4))
        self.metrics_label = tk.Label(
            inner, text="", bg=CARD, fg=MUTED,
            font=(FONT_UI, 10), anchor="w",
        )
        self.metrics_label.pack(fill="x")

        self.busy_label = tk.Label(
            outer, text="", bg=BG, fg=MUTED,
            font=(FONT_UI, 10), anchor="w",
        )
        self.busy_label.pack(fill="x", pady=(12, 0))

        self.error_frame = tk.Frame(outer, bg="#2a1622", highlightthickness=1, highlightbackground="#64283a")
        self.error_label = tk.Label(
            self.error_frame, text="", bg="#2a1622", fg=DANGER,
            font=(FONT_UI, 11), anchor="w", justify="left", wraplength=650,
        )
        self.error_label.pack(fill="x", padx=14, pady=(12, 6))
        actions = tk.Frame(self.error_frame, bg="#2a1622")
        actions.pack(fill="x", padx=14, pady=(0, 12))
        self.retry_button = tk.Button(
            actions, text="重试", command=self._retry,
            bg=ACCENT_DARK, fg=TEXT, activebackground="#0f766e",
            activeforeground=TEXT, relief="flat", padx=18, pady=7,
            font=(FONT_UI, 10, "bold"),
        )
        self.retry_button.pack(side="left")
        self.exit_button = tk.Button(
            actions, text="退出并打开旧版本", command=self._exit_to_app,
            bg="#1b2b46", fg=TEXT, activebackground="#284261",
            activeforeground=TEXT, relief="flat", padx=18, pady=7,
            font=(FONT_UI, 10),
        )
        self.exit_button.pack(side="left", padx=(8, 0))

        self.footer = tk.Label(
            outer,
            text="更新期间请勿关闭此窗口。下载中断后重试会自动续传。",
            bg=BG, fg=MUTED, font=(FONT_UI, 9), anchor="w",
        )
        self.footer.pack(fill="x", pady=(14, 0))

    def _start(self) -> None:
        if self.running:
            return
        self.failed = False
        self.completed = False
        self.running = True
        self.error_frame.pack_forget()
        self.progress.configure(value=0)
        self.percent_label.configure(text="0%")
        self.stage_label.configure(text="准备更新…")
        self.detail_label.configure(text="正在准备更新文件")
        self.metrics_label.configure(text="")
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()
        self._animate()

    def _run_worker(self) -> None:
        try:
            self.engine.run()
        except Exception:
            pass

    def _poll(self) -> None:
        try:
            while True:
                state = self.states.get_nowait()
                self._apply_state(state)
        except queue.Empty:
            pass
        if not self.completed:
            self.root.after(100, self._poll)

    def _apply_state(self, state: UpdateState) -> None:
        self.progress.configure(value=state.percent)
        self.percent_label.configure(text=f"{state.percent:.0f}%")
        self.stage_label.configure(text=state.message)
        if state.stage == "failed":
            self.running = False
            self.failed = True
            self.stage_label.configure(text="更新失败")
            self.detail_label.configure(text="更新没有完成，当前软件文件可能仍保持旧版本。")
            self.metrics_label.configure(text="")
            self.error_label.configure(text=state.error or "未知错误")
            self.error_frame.pack(fill="x", pady=(14, 0), before=self.footer)
            self.busy_label.configure(text="")
            self.footer.configure(text="可以重试；如果仍然失败，请退出后手动打开软件。")
            return

        self.detail_label.configure(text=state.message)
        if state.total_bytes > 0:
            if state.stage == "downloading":
                speed = format_bytes(state.speed_bps) + "/s" if state.speed_bps else "计算中"
                self.metrics_label.configure(
                    text=f"{format_bytes(state.downloaded_bytes)} / {format_bytes(state.total_bytes)}"
                    f"   ·   速度 {speed}   ·   预计剩余 {format_eta(state.eta_seconds)}"
                )
            else:
                self.metrics_label.configure(
                    text=f"{format_bytes(state.downloaded_bytes)} / {format_bytes(state.total_bytes)}"
                )
        else:
            self.metrics_label.configure(text="")

        if state.stage == "completed":
            self.completed = True
            self.running = False
            self.progress.configure(value=100)
            self.percent_label.configure(text="100%")
            self.stage_label.configure(text="更新完成")
            self.detail_label.configure(text="新版本已启动，本更新窗口即将关闭。")
            self.metrics_label.configure(text="")
            self.footer.configure(text="")
            self.root.after(700, self.root.destroy)

    def _animate(self) -> None:
        if not self.running or self.failed:
            return
        self.dots = (self.dots + 1) % 4
        dots = "." * self.dots
        current = self.stage_label.cget("text").rstrip(".")
        self.busy_label.configure(text=f"更新进程运行中{dots}")
        self.root.after(450, self._animate)

    def _retry(self) -> None:
        if self.running:
            return
        self.error_frame.pack_forget()
        self.busy_label.configure(text="")
        self._start()

    def _exit_to_app(self) -> None:
        try:
            launch_old_app(Path(self.request.app_root))
        finally:
            self.root.destroy()

    def _on_close(self) -> None:
        if self.running:
            messagebox.showinfo("更新进行中", "更新尚未完成，请不要关闭更新窗口。", parent=self.root)
            return
        self._exit_to_app()


def run_updater(request_path: Path) -> int:
    request = UpdateRequest.from_file(request_path)
    root = tk.Tk()
    UpdateProgressWindow(root, request, request_path)
    root.mainloop()
    return 0
