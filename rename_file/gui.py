"""tkinter GUI：目录/过滤/规则/预览/执行 + 撤销面板（任意跳选 + 确认预览）。

视觉风格与 lggyx.vercel.app 统一：深色 ink 底 (#0a0a0a)、卡片 #161616、
白 8% 细边框、紫蓝渐变主按钮 (#7a5cff → #5b8cff)、emerald/amber 状态色。

布局：
- 顶栏：标题 + 动态状态
- 左列：文件选择、修改规则、预览表、执行按钮
- 右列：撤销面板（操作历史 + 选中撤销 + 撤销最近一次）

确认弹窗（执行确认 / 撤销还原预览）封装在 ask_execute_confirm /
show_undo_confirm 两个方法里，便于自动化验证时覆写。
"""

import math
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from rename_file.core import (
    RULE_TYPE_BY_LABEL,
    RULE_TYPE_LABELS,
    STATUS_LABELS,
    UNDO_STATE_LABELS,
    HistoryStore,
    LogWriteError,
    apply_undo,
    build_preview,
    execute,
    find_tmp_residue,
    normalize_rule,
    plan_undo,
    rule_summary,
    scan_files,
)

# ------------------------------------------------------------- 设计系统变量
BG = "#0a0a0a"        # 窗口底（站内 --color-ink）
CARD = "#161616"      # 卡片（--color-card）
CARD2 = "#1d1d1d"     # 输入框 / 次级表面（--color-card-2）
BORDER = "#2a2a2e"    # ~white 8% 边框
TEXT = "#f2f2f5"      # 主文字（white/95）
DIM = "#a3a3af"       # 次级文字（white/60）
FAINT = "#70707c"     # 弱文字（white/40）
ACCENT = "#6d4aff"    # 强调紫
GRAD_FROM = "#7a5cff"  # 渐变起
GRAD_TO = "#5b8cff"    # 渐变止
EMERALD = "#34d399"   # 成功 / 状态点
AMBER = "#fcd34d"     # 冲突提醒
RED = "#f87171"       # 无效 / 错误

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 11)
FONT_MONO = ("Consolas", 9)

def _lerp_hex(a: str, b: str, t: float) -> str:
    a, b = a.lstrip("#"), b.lstrip("#")
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg_, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    return f"#{round(ar + (br - ar) * t):02x}{round(ag + (bg_ - ag) * t):02x}{round(ab + (bb - ab) * t):02x}"


class GradientButton(tk.Canvas):
    """紫蓝渐变圆角按钮（站点 CTA 风格）；tkinter 无原生圆角/渐变，手绘实现。"""

    def __init__(self, master, text, command=None, width=None, height=34,
                 radius=9, font=FONT_BOLD, state="normal"):
        measure_font = tkfont.Font(family=font[0], size=font[1])
        w = width or measure_font.measure(text) + 36
        super().__init__(master, width=w, height=height, bg=CARD,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text = text
        self._command = command
        self._btn_w, self._btn_h, self._r = w, height, radius  # 注意 _w 是 tkinter 保留属性
        self._enabled = state != "disabled"
        self._hover = False
        self._draw()
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))

    def _corner_inset(self, x: int) -> int:
        r = self._r
        if x < r:
            dx = r - x - 0.5
        elif x > self._btn_w - 1 - r:
            dx = r - (self._btn_w - 1 - x) + 0.5
        else:
            return 0
        dx = max(dx, 0.0)
        return int(r - math.sqrt(max(r * r - dx * dx, 0.0)))

    def _draw(self):
        self.delete("all")
        c1 = _lerp_hex(GRAD_FROM, "#ffffff", 0.14) if self._hover else GRAD_FROM
        c2 = _lerp_hex(GRAD_TO, "#ffffff", 0.14) if self._hover else GRAD_TO
        if not self._enabled:
            c1 = c2 = "#31313a"
        for x in range(self._btn_w):
            inset = self._corner_inset(x)
            color = _lerp_hex(c1, c2, x / max(self._btn_w - 1, 1))
            self.create_line(x, inset, x, self._btn_h - 1 - inset, fill=color)
        self.create_text(self._btn_w // 2, self._btn_h // 2, text=self._text,
                         fill=TEXT if self._enabled else FAINT, font=FONT_BOLD)

    def _set_hover(self, on: bool):
        if self._enabled:
            self._hover = on
            self._draw()

    def _on_click(self, _event):
        if self._enabled and self._command:
            self._command()

    # 兼容 ttk 风格的状态查询/设置（自动化验证用）
    def configure(self, **kw):
        if "state" in kw:
            self._enabled = kw["state"] != "disabled"
            self.configure(cursor="hand2" if self._enabled else "arrow")
            self._draw()
        else:
            super().configure(**kw)

    def instate(self, statespec) -> bool:
        disabled = not self._enabled
        return disabled if statespec == ["disabled"] else not disabled


class FlatButton(tk.Button):
    """次级按钮：深色扁平 + hover 提亮（站点 white/6% ghost 按钮）。"""

    def __init__(self, master, **kw):
        super().__init__(master, relief="flat", bd=0, bg=CARD2, fg=TEXT,
                         activebackground=BORDER, activeforeground=TEXT,
                         disabledforeground=FAINT, font=FONT,
                         cursor="hand2", padx=14, pady=6, **kw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e):
        if str(self["state"]) != "disabled":
            self.configure(bg="#26262b")

    def _on_leave(self, _e):
        self.configure(bg=CARD2)

    def instate(self, statespec) -> bool:
        disabled = str(self["state"]) == "disabled"
        return disabled if statespec == ["disabled"] else not disabled


def _setup_style(root: tk.Tk):
    """clam 主题深色化 + 组件样式（对应站点设计变量）。"""
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=BG,
                    focuscolor=CARD, selectbackground=ACCENT,
                    selectforeground="#ffffff", font=FONT)

    style.configure("Card.TFrame", background=CARD)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Dim.TLabel", background=CARD, foreground=DIM)
    style.configure("Faint.TLabel", background=CARD, foreground=FAINT,
                    font=FONT_SMALL)
    style.configure("Title.TLabel", background=BG, foreground=TEXT, font=FONT_BOLD)
    style.configure("Sub.TLabel", background=BG, foreground=FAINT, font=FONT_SMALL)
    style.configure("Status.TLabel", background=BG, foreground=DIM, font=FONT_SMALL)

    style.configure("TEntry", fieldbackground=CARD2, background=CARD2,
                    foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=5)
    style.map("TEntry", bordercolor=[("focus", ACCENT)],
              lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

    style.configure("TCombobox", fieldbackground=CARD2, background=CARD2,
                    foreground=TEXT, arrowcolor=DIM, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=4)
    style.map("TCombobox", bordercolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", CARD2)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", CARD2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", FONT)

    style.configure("TCheckbutton", background=CARD, foreground=DIM,
                    focuscolor=CARD, indicatorcolor=CARD2, indicatorrelief="flat")
    style.map("TCheckbutton",
              indicatorcolor=[("selected", ACCENT)],
              foreground=[("active", TEXT)],
              background=[("active", CARD)])

    style.configure("Treeview", background="#101013", fieldbackground="#101013",
                    foreground=TEXT, rowheight=30, borderwidth=0, font=FONT)
    style.map("Treeview",
              background=[("selected", "#332a63")],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=CARD, foreground=FAINT,
                    relief="flat", borderwidth=0, padding=(8, 7), font=FONT_SMALL)
    style.map("Treeview.Heading", background=[("active", CARD)])

    style.configure("Vertical.TScrollbar", background=CARD2, troughcolor="#101013",
                    bordercolor="#101013", arrowcolor=FAINT, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BORDER)])


def _enable_dark_titlebar(root: tk.Tk):
    """Windows 深色标题栏（DWMWA_USE_IMMERSIVE_DARK_MODE），失败静默跳过。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        for attr in (20, 19):  # 20 = Win20H1+，19 = 旧版回退
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(ctypes.c_int(1)), 4) == 0:
                break
    except (OSError, AttributeError):
        return  # 非 Windows/DWM 不可用：保持系统默认标题栏


class RenameApp:
    """主窗口。逻辑全部委托 core，本类只做 UI 编排。"""

    def __init__(self, root: tk.Tk, store: HistoryStore | None = None):
        self.root = root
        self.store = store or HistoryStore()
        self.files: list[Path] = []
        self.preview = []
        self._ops: list[dict] = []          # 历史面板行 ↔ 操作日志
        self.root.title("批量文件名修改工具")
        self.root.geometry("1140x790")
        self.root.configure(bg=BG)
        _setup_style(self.root)
        self._build_ui()
        _enable_dark_titlebar(self.root)
        self.refresh_history()

    # ------------------------------------------------------------------ UI
    def _card(self, parent, title: str) -> ttk.Frame:
        """站点风格卡片：#161616 底 + 白 8% 细边 + 弱色小标题。"""
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1)
        card.pack(fill="x", pady=(0, 10))
        inner = ttk.Frame(card, style="Card.TFrame", padding=(14, 10, 14, 12))
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title, style="Faint.TLabel").pack(anchor="w")
        return inner

    def _build_ui(self):
        # 顶栏：标题 + 状态
        header = ttk.Frame(self.root, style="TFrame", padding=(2, 0, 2, 10))
        header.pack(fill="x")
        head_row = ttk.Frame(header, style="TFrame")
        head_row.pack(fill="x")
        tk.Label(head_row, text="批量文件名修改工具", bg=BG, fg=TEXT,
                 font=FONT_BOLD).pack(side="left")
        status_row = ttk.Frame(head_row, style="TFrame")
        status_row.pack(side="right")
        self.status_dot = tk.Canvas(status_row, width=8, height=8, bg=BG,
                                    highlightthickness=0)
        self.status_dot.create_oval(1, 1, 7, 7, fill=EMERALD, outline="")
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_var = tk.StringVar(value="就绪 — 选择目录开始")
        tk.Label(status_row, textvariable=self.status_var, bg=BG, fg=DIM,
                 font=FONT_SMALL).pack(side="left")
        tk.Label(header, text="B U L K   R E N A M E   ·   U N D O   R E A D Y",
                 bg=BG, fg=FAINT, font=FONT_SMALL).pack(anchor="w")

        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, style="TFrame")
        left.pack(side="left", fill="both", expand=True)

        # -- 文件选择
        file_card = self._card(left, "文 件 选 择")
        row1 = ttk.Frame(file_card, style="Card.TFrame")
        row1.pack(fill="x")
        self.dir_var = tk.StringVar(value=str(Path.cwd()))
        ttk.Entry(row1, textvariable=self.dir_var, font=FONT_MONO).pack(
            side="left", fill="x", expand=True)
        FlatButton(row1, text="浏览…", command=self.on_browse).pack(side="left", padx=4)
        FlatButton(row1, text="扫描文件", command=self.on_scan).pack(side="left")

        row2 = ttk.Frame(file_card, style="Card.TFrame")
        row2.pack(fill="x", pady=(8, 0))
        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="递归搜索子目录",
                        variable=self.recursive_var).pack(side="left")
        ttk.Label(row2, text="文件过滤:", style="Dim.TLabel").pack(side="left", padx=(14, 2))
        self.filter_var = tk.StringVar(value="*")
        ttk.Entry(row2, textvariable=self.filter_var, width=9).pack(side="left")
        ttk.Label(row2, text="正则模式:", style="Dim.TLabel").pack(side="left", padx=(14, 2))
        self.regex_var = tk.StringVar(value=".*")
        ttk.Entry(row2, textvariable=self.regex_var, width=9).pack(side="left")
        self.count_var = tk.StringVar(value="0 个文件")
        ttk.Label(row2, textvariable=self.count_var, style="Dim.TLabel").pack(
            side="left", padx=14)

        # -- 修改规则
        rule_card = self._card(left, "修 改 规 则")
        rrow = ttk.Frame(rule_card, style="Card.TFrame")
        rrow.pack(fill="x")
        ttk.Label(rrow, text="规则类型:", style="Dim.TLabel").pack(side="left")
        self.rule_type_var = tk.StringVar(value=RULE_TYPE_LABELS["prefix"])
        type_box = ttk.Combobox(rrow, textvariable=self.rule_type_var, state="readonly",
                                values=list(RULE_TYPE_LABELS.values()), width=11,
                                font=FONT)
        type_box.pack(side="left", padx=6)
        type_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_rule_params())
        self.rule_params_frame = ttk.Frame(rrow, style="Card.TFrame")
        self.rule_params_frame.pack(side="left", fill="x", expand=True)
        self.case_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rule_card, text="大小写敏感（对替换/正则生效）",
                        variable=self.case_var).pack(side="left")
        GradientButton(rule_card, text="预览修改", command=self.on_preview).pack(
            side="right")

        # -- 预览
        prev_card = self._card(left, "预 览")
        prev_wrap = ttk.Frame(prev_card, style="Card.TFrame")
        prev_wrap.pack(fill="both", expand=True)
        self.preview_tree = ttk.Treeview(prev_wrap, columns=("old", "new", "status"),
                                         show="headings", height=10)
        for col, text, width in (("old", "原文件名", 250), ("new", "新文件名", 250),
                                 ("status", "状态", 150)):
            self.preview_tree.heading(col, text=text)
            self.preview_tree.column(col, width=width, anchor="w")
        self.preview_tree.pack(side="left", fill="both", expand=True)
        prev_scroll = ttk.Scrollbar(prev_wrap, orient="vertical",
                                    command=self.preview_tree.yview)
        prev_scroll.pack(side="left", fill="y")
        self.preview_tree.configure(yscrollcommand=prev_scroll.set)
        # 按状态标色（有效保持默认白，无变化弱化，冲突琥珀，无效红）
        self.preview_tree.tag_configure("same", foreground=FAINT)
        self.preview_tree.tag_configure("conflict", foreground=AMBER)
        self.preview_tree.tag_configure("invalid", foreground=RED)

        btns = ttk.Frame(left, style="TFrame")
        btns.pack(fill="x", pady=(2, 0))
        self.exec_btn = GradientButton(btns, text="执行修改", command=self.on_execute,
                                       state="disabled")
        self.exec_btn.pack(side="left")
        FlatButton(btns, text="清空预览", command=self.on_clear_preview).pack(
            side="left", padx=8)

        # -- 撤销面板（右列）
        undo_card = tk.Frame(body, bg=CARD, highlightbackground=BORDER,
                             highlightthickness=1)
        undo_card.pack(side="right", fill="y", padx=(10, 0))
        undo_inner = ttk.Frame(undo_card, style="Card.TFrame", padding=(12, 10))
        undo_inner.pack(fill="both", expand=True)
        ttk.Label(undo_inner, text="撤 销 面 板", style="Faint.TLabel").pack(anchor="w")
        ttk.Label(undo_inner, text="任意跳选 · 需确认", style="Dim.TLabel").pack(anchor="w")
        hist_wrap = ttk.Frame(undo_inner, style="Card.TFrame")
        hist_wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.history_tree = ttk.Treeview(hist_wrap, columns=("rule", "count", "state"),
                                         show="headings", height=17,
                                         selectmode="browse")
        for col, text, width in (("rule", "规则", 148), ("count", "文件数", 44),
                                 ("state", "状态", 60)):
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.pack(side="left", fill="both", expand=True)
        hist_scroll = ttk.Scrollbar(hist_wrap, orient="vertical",
                                    command=self.history_tree.yview)
        hist_scroll.pack(side="left", fill="y")
        self.history_tree.configure(yscrollcommand=hist_scroll.set)
        self.history_tree.tag_configure("undone", foreground=FAINT)

        self.undo_btn = GradientButton(undo_inner, text="撤销选中操作",
                                       command=self.on_undo_selected, state="disabled")
        self.undo_btn.pack(fill="x", pady=(8, 2))
        FlatButton(undo_inner, text="撤销最近一次",
                   command=self.on_undo_latest).pack(fill="x")
        ttk.Label(undo_inner, text=f"日志目录: {self.store.directory}",
                  style="Faint.TLabel", wraplength=300, font=FONT_MONO).pack(
            fill="x", pady=(6, 0))

        self._rule_param_vars: dict[str, tk.StringVar] = {}
        self._refresh_rule_params()

    def _refresh_rule_params(self):
        """按规则类型重建参数输入行（前缀/后缀文本框 或 查找/替换两个输入框）。"""
        for child in self.rule_params_frame.winfo_children():
            child.destroy()
        self._rule_param_vars = {"text": tk.StringVar(), "find": tk.StringVar(),
                                 "replace": tk.StringVar()}
        rtype = RULE_TYPE_BY_LABEL[self.rule_type_var.get()]
        if rtype in ("replace", "regex"):
            ttk.Label(self.rule_params_frame, text="查找:",
                      style="Dim.TLabel").pack(side="left")
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["find"],
                      width=13).pack(side="left", padx=3)
            ttk.Label(self.rule_params_frame, text="替换为:",
                      style="Dim.TLabel").pack(side="left", padx=(8, 0))
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["replace"],
                      width=13).pack(side="left", padx=3)
        else:
            label = "前缀内容:" if rtype == "prefix" else "后缀内容:"
            ttk.Label(self.rule_params_frame, text=label,
                      style="Dim.TLabel").pack(side="left")
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["text"],
                      width=20).pack(side="left", padx=3)

    def _current_rule(self) -> dict:
        rtype = RULE_TYPE_BY_LABEL[self.rule_type_var.get()]
        if rtype in ("replace", "regex"):
            params = {"find": self._rule_param_vars["find"].get(),
                      "replace": self._rule_param_vars["replace"].get()}
        else:
            params = {"text": self._rule_param_vars["text"].get()}
        return normalize_rule(rtype, params, self.case_var.get())

    def _set_status(self, text: str):
        self.status_var.set(text)

    # -------------------------------------------------------------- 事件处理
    def on_browse(self):
        chosen = filedialog.askdirectory(parent=self.root, title="选择要处理的目录")
        if chosen:
            self.dir_var.set(chosen)

    def on_scan(self):
        directory = self.dir_var.get().strip()
        if not directory or not Path(directory).exists():
            messagebox.showerror("错误", "请选择有效的目录")
            return
        residue = find_tmp_residue(directory)
        if residue:
            shown = "\n".join(p.name for p in residue[:5])
            more = f"\n… 共 {len(residue)} 个" if len(residue) > 5 else ""
            messagebox.showwarning(
                "发现残留临时文件",
                "两步法中途崩溃可能残留了临时名文件（可安全删除）：\n" + shown + more)
        self.files = scan_files(directory, self.filter_var.get().strip() or "*",
                                self.regex_var.get().strip() or ".*",
                                self.recursive_var.get())
        self.count_var.set(f"{len(self.files)} 个文件")
        self._set_status(f"已扫描 {len(self.files)} 个文件")

    def on_preview(self):
        if not self.files:
            messagebox.showwarning("提示", "请先扫描文件")
            return
        self.preview = build_preview(self.files, self._current_rule())
        self.preview_tree.delete(*self.preview_tree.get_children())
        for e in self.preview:
            status = STATUS_LABELS[e.status]
            if e.status == "ok" and e.case_only:
                status += " · 两步法"
            new_name = "—" if e.status == "same" else e.new_name
            self.preview_tree.insert("", "end",
                                     values=(e.old_name, new_name, status),
                                     tags=(e.status,))
        has_valid = any(e.status == "ok" for e in self.preview)
        self.exec_btn.configure(state="normal" if has_valid else "disabled")
        self._set_status(f"预览完成 — {sum(e.status == 'ok' for e in self.preview)} 条有效变更")

    def on_clear_preview(self):
        self.preview = []
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.exec_btn.configure(state="disabled")

    def on_execute(self):
        valid = [e for e in self.preview if e.status == "ok"]
        if not valid:
            return
        if not self.ask_execute_confirm(len(valid)):
            return
        try:
            result = execute(self.preview, store=self.store,
                             base_dir=self.dir_var.get(),
                             recursive=self.recursive_var.get(),
                             rule=self._current_rule())
        except LogWriteError as exc:
            self._set_status("执行中止 — 撤销日志写入失败")
            messagebox.showerror("执行中止", str(exc))
            return
        skipped_note = ""
        failed = [e for e in result["op"]["entries"] if e["status"] == "failed"]
        if failed:
            skipped_note = f"\n失败 {len(failed)} 条已留痕（其余条目正常）。"
        messagebox.showinfo(
            "操作完成",
            f"成功 {result['ok_count']} 个，失败 {result['failed_count']} 个。{skipped_note}\n\n"
            "已记录撤销日志，可在右侧撤销面板回退。")
        self._set_status(f"已执行 {result['op']['op_id']} — 可撤销")
        self.on_clear_preview()
        self.refresh_history()

    # -------------------------------------------------------------- 撤销面板
    def refresh_history(self):
        self._ops = self.store.list_ops()
        self.history_tree.delete(*self.history_tree.get_children())
        for op in self._ops:
            if op.get("undone"):
                state, tag = "已撤销", "undone"
            elif self.store.is_undoable(op):
                state, tag = "可撤销", ""
            else:
                state, tag = "超出窗口", "undone"
            self.history_tree.insert(
                "", "end",
                values=(op["op_id"].replace("op_", ""), rule_summary(op["rule"]),
                        op["file_count"], state),
                tags=(tag,))
        has_undoable = bool(self.store.undoable_ops())
        self.undo_btn.configure(state="normal" if has_undoable else "disabled")

    def _selected_op(self) -> dict | None:
        selection = self.history_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择一条操作记录")
            return None
        return self._ops[self.history_tree.index(selection[0])]

    def on_undo_selected(self):
        op = self._selected_op()
        if op is None:
            return
        if op.get("undone"):
            messagebox.showinfo("提示", "该操作已撤销（归档保留，不可再次撤销）")
            return
        if not self.store.is_undoable(op):
            messagebox.showinfo("提示", "该操作已超出可撤销窗口（最近 10 次之外）")
            return
        self._undo_flow(op)

    def on_undo_latest(self):
        ops = self.store.undoable_ops()
        if not ops:
            messagebox.showinfo("提示", "当前没有可撤销的操作")
            return
        self._undo_flow(ops[0])

    def _undo_flow(self, op: dict):
        plan = plan_undo(op)
        if not self.show_undo_confirm(op, plan):
            return
        result = apply_undo(op, self.store)
        if not result["undone"]:
            self._set_status("撤销不成立 — 先撤销其后续操作")
            messagebox.showwarning(
                "撤销不成立",
                "没有任何条目被还原：该操作的输出文件已被后续操作改名或占用。\n"
                "请先撤销对应的后续操作，再撤销本操作。")
        else:
            skipped = result["skipped"]
            msg = f"已还原 {result['restored']} 个文件。"
            if skipped:
                msg += (f"\n\n跳过 {len(skipped)} 条（绝不覆盖）：\n"
                        + "\n".join(f"· {s['reason']}" for s in skipped[:5]))
            messagebox.showinfo("撤销完成", msg)
            self._set_status(f"已撤销 {op['op_id']} — 还原 {result['restored']} 个")
        self.refresh_history()
        self.on_clear_preview()  # 旧预览已过期

    # ------------------------------------------------------- 可覆写的确认弹窗
    def ask_execute_confirm(self, count: int) -> bool:
        return messagebox.askyesno(
            "确认操作",
            f"确定要重命名 {count} 个文件吗？\n\n操作将记录撤销日志，可回退。")

    def show_undo_confirm(self, op: dict, plan: list[dict]) -> bool:
        """模态还原预览：逐条展示还原判定，确认才执行。"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"撤销预览：{op['op_id']}")
        dialog.configure(bg=CARD)
        dialog.transient(self.root)
        dialog.geometry("680x430")
        frame = ttk.Frame(dialog, style="Card.TFrame", padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"撤销预览 · {op['op_id']}",
                  style="Card.TLabel", font=FONT_BOLD).pack(anchor="w")
        ttk.Label(frame, text="「跳过」条目绝不覆盖；全部被跳过时本次撤销不成立（操作保持可撤销）。",
                  style="Faint.TLabel").pack(anchor="w", pady=(2, 8))
        wrap = ttk.Frame(frame, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=("cur", "restore", "state"), show="headings")
        for col, text, width in (("cur", "当前名", 210), ("restore", "还原为", 210),
                                 ("state", "状态", 210)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        scroll.pack(side="left", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        for item in plan:
            entry = item["entry"]
            tree.insert("", "end", values=(
                entry["to"], entry["from"], UNDO_STATE_LABELS[item["state"]]))

        choice = {"confirm": False}

        def confirm():
            choice["confirm"] = True
            dialog.destroy()

        actions = ttk.Frame(frame, style="Card.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        GradientButton(actions, text="确认撤销", command=confirm).pack(side="right")
        FlatButton(actions, text="取消", command=dialog.destroy).pack(
            side="right", padx=(0, 8))
        dialog.grab_set()
        self.root.wait_window(dialog)
        return choice["confirm"]


def main():
    root = tk.Tk()
    RenameApp(root)
    root.mainloop()
