"""Scrollable, searchable LUT library picker."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from .lut_library import LutEntry

BG = "#080f1c"
CARD = "#111c31"
CARD_ALT = "#0b1526"
BORDER = "#203452"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
ACCENT = "#2dd4bf"
ACCENT_DARK = "#0d9488"
FONT_UI = "Microsoft YaHei UI"
FONT_DIALOG_TITLE = (FONT_UI, 24, "bold")
FONT_BODY = (FONT_UI, 13)
FONT_BODY_BOLD = (FONT_UI, 13, "bold")
FONT_SMALL = (FONT_UI, 12)
FONT_SMALL_BOLD = (FONT_UI, 12, "bold")


class LutLibraryDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        entries: list[LutEntry],
        current_path: Path | None,
        on_select: Callable[[LutEntry], None],
    ):
        super().__init__(master)
        self.entries = sorted(entries, key=lambda e: (e.device.casefold(), e.category.casefold(), e.name.casefold()))
        self.current_path = current_path.resolve() if current_path else None
        self.on_select = on_select
        self.filtered: list[LutEntry] = []
        self.row_entries: dict[str, LutEntry] = {}
        self.title("LUT 库 — 按设备筛选")
        self.geometry("900x620")
        self.minsize(720, 480)
        self.configure(fg_color=BG)
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text="DJI LUT 库", font=FONT_DIALOG_TITLE, text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header, text="滚动查看 / 搜索 / 按设备筛选，双击可直接使用",
            font=FONT_BODY, text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.count_label = ctk.CTkLabel(
            header, text="", font=FONT_BODY_BOLD, text_color=ACCENT,
        )
        self.count_label.grid(row=0, column=1, rowspan=2, sticky="e")

        filters = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        filters.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        filters.grid_columnconfigure(3, weight=1)
        self.device_var = tk.StringVar(value="全部设备")
        self.category_var = tk.StringVar(value="全部类别")
        self.source_var = tk.StringVar(value="全部来源")
        self.search_var = tk.StringVar(value="")
        self.device_menu = ctk.CTkOptionMenu(
            filters, values=["全部设备"], variable=self.device_var,
            width=160, height=32, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL, command=lambda _v: self._apply_filter(),
        )
        self.device_menu.grid(row=0, column=0, padx=(12, 6), pady=10)
        self.category_menu = ctk.CTkOptionMenu(
            filters, values=["全部类别"], variable=self.category_var,
            width=130, height=32, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL, command=lambda _v: self._apply_filter(),
        )
        self.category_menu.grid(row=0, column=1, padx=6, pady=10)
        self.source_menu = ctk.CTkOptionMenu(
            filters, values=["全部来源", "默认", "自定义"], variable=self.source_var,
            width=108, height=32, corner_radius=8, fg_color="#1b2b46",
            button_color="#284261", button_hover_color=ACCENT_DARK, text_color=TEXT,
            font=FONT_SMALL, command=lambda _v: self._apply_filter(),
        )
        self.source_menu.grid(row=0, column=2, padx=6, pady=10)
        search = ctk.CTkEntry(
            filters, textvariable=self.search_var, placeholder_text="搜索设备 / LUT 名称 / 风格",
            height=32, corner_radius=8, fg_color=CARD_ALT, border_color=BORDER,
            text_color=TEXT, font=FONT_SMALL,
        )
        search.grid(row=0, column=3, sticky="ew", padx=6, pady=10)
        self.search_var.trace_add("write", lambda *_args: self._apply_filter())
        ctk.CTkButton(
            filters, text="重置", width=62, height=32, corner_radius=8,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self._reset_filters,
        
                font=FONT_SMALL,).grid(row=0, column=4, padx=(6, 12), pady=10)

        table_frame = ctk.CTkFrame(self, fg_color=CARD_ALT, corner_radius=10)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 8))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Lut.Treeview", background=CARD_ALT, fieldbackground=CARD_ALT,
            foreground="#cbd5e1", borderwidth=0, rowheight=32, font=FONT_SMALL,
        )
        style.configure(
            "Lut.Treeview.Heading", background="#1b2b46", foreground=TEXT,
            borderwidth=0, font=FONT_SMALL_BOLD,
        )
        style.map("Lut.Treeview", background=[("selected", "#164e63")])
        columns = ("origin", "device", "category", "name", "profile")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Lut.Treeview", selectmode="browse",
        )
        headings = {"origin": "来源", "device": "设备 / 系列", "category": "类别", "name": "LUT 名称", "profile": "输入色彩"}
        widths = {"origin": 58, "device": 170, "category": 110, "name": 360, "profile": 82}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w", stretch=(col == "name"))
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=6)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.empty_label = ctk.CTkLabel(
            table_frame, text="当前筛选下没有 LUT。" + chr(10) + "默认库包含 83 个 LUT（55 个 DJI 官方 + 28 个热门网络风格）；自定义 LUT 请通过“导入 .cube”添加。", font=FONT_SMALL,
            text_color=MUTED, justify="center",
        )
        self.tree.bind("<<TreeviewSelect>>", self._on_selection)
        self.tree.bind("<Double-1>", lambda _e: self._use_selected())
        self.tree.bind("<Return>", lambda _e: self._use_selected())
        self.tree.bind("<MouseWheel>", self._on_mousewheel)
        self.tree.bind("<Button-4>", lambda _e: self.tree.yview_scroll(-3, "units"))
        self.tree.bind("<Button-5>", lambda _e: self.tree.yview_scroll(3, "units"))

        footer = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))
        footer.grid_columnconfigure(0, weight=1)
        self.description = ctk.CTkLabel(
            footer, text="选择一条 LUT 查看说明。", font=FONT_SMALL,
            text_color=MUTED, anchor="w", justify="left", wraplength=560,
        )
        self.description.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 10))
        ctk.CTkButton(
            footer, text="取消", width=78, height=34, corner_radius=9,
            fg_color="#1b2b46", hover_color="#284261", text_color=TEXT,
            command=self.destroy,
        
                font=FONT_SMALL,).grid(row=0, column=1, padx=6, pady=10)
        ctk.CTkButton(
            footer, text="使用此 LUT", width=116, height=34, corner_radius=9,
            fg_color=ACCENT_DARK, hover_color="#0f766e", text_color=TEXT,
            font=FONT_BODY_BOLD, command=self._use_selected,
        ).grid(row=0, column=2, padx=(0, 12), pady=10)

        self._build_filter_values()
        self._apply_filter()

    def _build_filter_values(self) -> None:
        devices = sorted({e.device for e in self.entries}, key=str.casefold)
        categories = sorted({e.category for e in self.entries}, key=str.casefold)
        self.device_menu.configure(values=["全部设备"] + devices)
        self.category_menu.configure(values=["全部类别"] + categories)

    def _reset_filters(self) -> None:
        self.device_var.set("全部设备")
        self.category_var.set("全部类别")
        self.source_var.set("全部来源")
        self.search_var.set("")
        self._apply_filter()

    def _apply_filter(self) -> None:
        device = self.device_var.get()
        category = self.category_var.get()
        source = self.source_var.get()
        query = self.search_var.get().strip().casefold()
        self.filtered = []
        for entry in self.entries:
            if device != "全部设备" and entry.device != device:
                continue
            if category != "全部类别" and entry.category != category:
                continue
            if source != "全部来源" and entry.origin != source:
                continue
            haystack = f"{entry.origin} {entry.device} {entry.category} {entry.name} {entry.profile} {entry.description}".casefold()
            if query and query not in haystack:
                continue
            self.filtered.append(entry)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.row_entries.clear()
        for index, entry in enumerate(self.filtered):
            iid = str(index)
            self.row_entries[iid] = entry
            self.tree.insert(
                "", "end", iid=iid,
                values=(entry.origin, entry.device, entry.category, entry.name, entry.profile or "—"),
            )
        self.count_label.configure(text=f"{len(self.filtered)} / {len(self.entries)} 个 LUT")
        if self.filtered:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")
        if self.current_path:
            for iid, entry in self.row_entries.items():
                if entry.path.resolve() == self.current_path:
                    self.tree.selection_set(iid)
                    self.tree.see(iid)
                    self._on_selection()
                    break

    def _on_selection(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        entry = self.row_entries.get(selection[0])
        if not entry:
            return
        text = f"[{entry.origin}] {entry.device} / {entry.category} / {entry.name}"
        if entry.description:
            text += chr(10) + entry.description
        self.description.configure(text=text)

    def _on_mousewheel(self, event) -> None:
        delta = -1 if event.delta > 0 else 1
        self.tree.yview_scroll(delta * 3, "units")

    def _use_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        entry = self.row_entries.get(selection[0])
        if not entry:
            return
        self.on_select(entry)
        self.destroy()
