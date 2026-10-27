"""Activation / trial-expiry dialog."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ._license_guard import LicenseManager, LicenseStatus

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
PURCHASE_QQ = "3643791089"


class LicenseDialog(ctk.CTkToplevel):
    def __init__(self, master, manager: LicenseManager, status: LicenseStatus):
        super().__init__(master)
        self.manager = manager
        self.status = status
        self.result = False
        self.title("软件授权")
        self.geometry("700x560")
        self.minsize(620, 480)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="软件授权", font=(FONT_UI, 24, "bold"), text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head, text="下载即可开始 7 天免费试用；到期后购买买断授权，导入 license.json 继续使用。",
            font=(FONT_UI, 12), text_color=MUTED, justify="left", wraplength=600,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        status_card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        status_card.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        status_card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            status_card, text="当前状态", font=(FONT_UI, 12), text_color=MUTED,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.status_label = ctk.CTkLabel(
            status_card, text=status.message, font=(FONT_UI, 13, "bold"),
            text_color=DANGER if not status.can_run else ACCENT, anchor="w",
        )
        self.status_label.grid(row=0, column=1, sticky="ew", padx=(8, 14), pady=(12, 4))
        ctk.CTkLabel(
            status_card, text="机器码", font=(FONT_UI, 12), text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(4, 12))
        machine = ctk.CTkEntry(
            status_card, font=(FONT_UI, 13), height=30, fg_color=CARD_ALT,
            border_color=BORDER, text_color=TEXT,
        )
        machine.grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=(4, 12))
        machine.insert(0, manager.machine_code)
        machine.configure(state="readonly")
        self.machine_text = manager.machine_code

        help_card = ctk.CTkFrame(self, fg_color=CARD_ALT, corner_radius=12)
        help_card.grid(row=2, column=0, sticky="nsew", padx=24, pady=8)
        help_card.grid_columnconfigure(0, weight=1)
        rules = chr(10).join([
            "免费试用",
            "• 首次启动自动开始 7 天免费试用，无需注册或授权。",
            "• 试用期间所有核心功能可用，输出不加水印。",
            "• 试用到期后停止新建任务，不删除已有素材、配置和报告。",
            "",
            "购买买断授权",
            "• 试用到期后，复制机器码并添加作者 QQ 购买。",
            "• 每份授权绑定当前设备，不能在其他电脑直接使用。",
            "• 收到 license.json 后点击下方“导入许可证”。",
            "• 买断授权不设到期日；如需换机，请联系作者重新签发。",
        ])
        ctk.CTkLabel(
            help_card, text=rules, font=(FONT_UI, 12), text_color="#cbd5e1",
            justify="left", anchor="nw", wraplength=620,
        ).grid(row=0, column=0, sticky="nsew", padx=16, pady=14)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 18))
        actions.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            actions, text="复制机器码", width=104, height=34, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._copy_machine,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            actions, text="复制作者 QQ", width=104, height=34, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._copy_qq,
        ).grid(row=0, column=1, padx=6)
        ctk.CTkButton(
            actions, text="导入许可证", width=112, height=34, corner_radius=9,
            fg_color=ACCENT_DARK, hover_color="#0f766e", text_color=TEXT,
            command=self._import_license,
        ).grid(row=0, column=2, padx=6)
        ctk.CTkButton(
            actions, text="退出", width=72, height=34, corner_radius=9,
            fg_color="transparent", hover_color="#2a1622", text_color=DANGER,
            border_width=1, border_color="#64283a", command=self.destroy,
        ).grid(row=0, column=3, padx=(6, 0))

    def _copy_machine(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self.machine_text)
            messagebox.showinfo("已复制", "机器码已复制到剪贴板。", parent=self)
        except Exception as exc:
            messagebox.showerror("复制失败", str(exc), parent=self)

    def _copy_qq(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(PURCHASE_QQ)
            messagebox.showinfo("作者 QQ", f"购买/续费请添加作者 QQ：{PURCHASE_QQ}", parent=self)
        except Exception as exc:
            messagebox.showerror("复制失败", str(exc), parent=self)

    def _import_license(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="选择授权文件",
            filetypes=[("授权文件", "*.json"), ("所有文件", "*.*")],
        )
        if not chosen:
            return
        try:
            status = self.manager.activate_license_file(Path(chosen))
        except Exception as exc:
            messagebox.showerror("授权失败", str(exc), parent=self)
            return
        self.result = True
        messagebox.showinfo("授权成功", status.message, parent=self)
        self.destroy()
