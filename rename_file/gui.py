"""tkinter GUI：目录/过滤/规则/预览/执行 + 撤销面板（任意跳选 + 确认预览）。

布局对应 design/prototype.html 已确认的面板结构：
- 左列：文件选择、修改规则、预览表、执行按钮
- 右列：撤销面板（操作历史 + 选中撤销 + 撤销最近一次）

确认弹窗（执行确认 / 撤销还原预览）封装在 ask_execute_confirm /
show_undo_confirm 两个方法里，便于自动化验证时覆写。
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from rename_file.core import (
    RULE_TYPE_BY_LABEL,
    RULE_TYPE_LABELS,
    HistoryStore,
    LogWriteError,
    apply_undo,
    build_preview,
    execute,
    find_tmp_residue,
    normalize_rule,
    plan_undo,
    scan_files,
)

PREVIEW_STATUS_LABELS = {
    "ok": "有效",
    "same": "无变化",
    "invalid": "无效",
    "conflict": "冲突",
}
UNDO_STATE_LABELS = {
    "ok": "可还原",
    "conflict": "冲突跳过（还原名已被占用）",
    "missing": "跳过（已被后续操作改名或删除）",
}


def rule_summary(rule: dict) -> str:
    """规则摘要（历史面板展示用）：如「正则替换: ^IMG_ → 2023_」。"""
    label = RULE_TYPE_LABELS[rule["type"]]
    params = rule.get("params") or {}
    if rule["type"] in ("replace", "regex"):
        return f"{label}: {params.get('find', '')} → {params.get('replace', '')}"
    return f"{label}: {params.get('text', '')}"


class RenameApp:
    """主窗口。逻辑全部委托 core，本类只做 UI 编排。"""

    def __init__(self, root: tk.Tk, store: HistoryStore | None = None):
        self.root = root
        self.store = store or HistoryStore()
        self.files: list[Path] = []
        self.preview = []
        self._ops: list[dict] = []          # 历史面板行 ↔ 操作日志
        self.root.title("批量文件名修改工具")
        self.root.geometry("1100x700")
        self._build_ui()
        self.refresh_history()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="both", expand=True)

        # -- 文件选择
        file_box = ttk.LabelFrame(left, text="文件选择", padding=6)
        file_box.pack(fill="x")
        row1 = ttk.Frame(file_box)
        row1.pack(fill="x")
        self.dir_var = tk.StringVar(value=str(Path.cwd()))
        ttk.Entry(row1, textvariable=self.dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="浏览…", command=self.on_browse).pack(side="left", padx=4)
        ttk.Button(row1, text="扫描文件", command=self.on_scan).pack(side="left")

        row2 = ttk.Frame(file_box)
        row2.pack(fill="x", pady=(4, 0))
        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="递归搜索子目录", variable=self.recursive_var).pack(side="left")
        ttk.Label(row2, text="文件过滤:").pack(side="left", padx=(12, 2))
        self.filter_var = tk.StringVar(value="*")
        ttk.Entry(row2, textvariable=self.filter_var, width=10).pack(side="left")
        ttk.Label(row2, text="正则模式:").pack(side="left", padx=(12, 2))
        self.regex_var = tk.StringVar(value=".*")
        ttk.Entry(row2, textvariable=self.regex_var, width=10).pack(side="left")
        self.count_var = tk.StringVar(value="0 个文件")
        ttk.Label(row2, textvariable=self.count_var).pack(side="left", padx=12)

        # -- 修改规则
        rule_box = ttk.LabelFrame(left, text="修改规则", padding=6)
        rule_box.pack(fill="x", pady=6)
        rrow = ttk.Frame(rule_box)
        rrow.pack(fill="x")
        ttk.Label(rrow, text="规则类型:").pack(side="left")
        self.rule_type_var = tk.StringVar(value=RULE_TYPE_LABELS["prefix"])
        type_box = ttk.Combobox(rrow, textvariable=self.rule_type_var, state="readonly",
                                values=list(RULE_TYPE_LABELS.values()), width=12)
        type_box.pack(side="left", padx=4)
        type_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_rule_params())
        self.rule_params_frame = ttk.Frame(rrow)
        self.rule_params_frame.pack(side="left", fill="x", expand=True)
        self.case_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rule_box, text="大小写敏感（对替换/正则生效）",
                        variable=self.case_var).pack(side="left")
        ttk.Button(rule_box, text="预览修改", command=self.on_preview).pack(side="right")

        # -- 预览
        prev_box = ttk.LabelFrame(left, text="预览", padding=6)
        prev_box.pack(fill="both", expand=True, pady=6)
        self.preview_tree = ttk.Treeview(prev_box, columns=("old", "new", "status"),
                                         show="headings", height=12)
        for col, text, width in (("old", "原文件名", 240), ("new", "新文件名", 240),
                                 ("status", "状态", 160)):
            self.preview_tree.heading(col, text=text)
            self.preview_tree.column(col, width=width, anchor="w")
        self.preview_tree.pack(fill="both", expand=True)
        btns = ttk.Frame(left)
        btns.pack(fill="x")
        self.exec_btn = ttk.Button(btns, text="执行修改", command=self.on_execute,
                                   state="disabled")
        self.exec_btn.pack(side="left")
        ttk.Button(btns, text="清空预览", command=self.on_clear_preview).pack(side="left", padx=6)

        # -- 撤销面板（右列）
        right = ttk.LabelFrame(main, text="撤销面板（任意跳选 · 需确认）", padding=6)
        right.pack(side="right", fill="y", padx=(8, 0))
        self.history_tree = ttk.Treeview(right, columns=("rule", "count", "state", "time"),
                                         show="headings", height=18, selectmode="browse")
        for col, text, width in (("rule", "规则", 150), ("count", "文件数", 46),
                                 ("state", "状态", 64), ("time", "时间", 105)):
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, anchor="w")
        self.history_tree.pack(fill="both", expand=True)
        self.undo_btn = ttk.Button(right, text="撤销选中操作", command=self.on_undo_selected,
                                   state="disabled")
        self.undo_btn.pack(fill="x", pady=(4, 0))
        ttk.Button(right, text="撤销最近一次", command=self.on_undo_latest).pack(fill="x", pady=2)
        hist_dir = str(self.store.directory)
        ttk.Label(right, text=f"日志目录: {hist_dir}", wraplength=310,
                  foreground="#666666").pack(fill="x", pady=(4, 0))

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
            ttk.Label(self.rule_params_frame, text="查找:").pack(side="left")
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["find"],
                      width=14).pack(side="left", padx=2)
            ttk.Label(self.rule_params_frame, text="替换为:").pack(side="left", padx=(6, 0))
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["replace"],
                      width=14).pack(side="left", padx=2)
        else:
            label = "前缀内容:" if rtype == "prefix" else "后缀内容:"
            ttk.Label(self.rule_params_frame, text=label).pack(side="left")
            ttk.Entry(self.rule_params_frame, textvariable=self._rule_param_vars["text"],
                      width=22).pack(side="left", padx=2)

    def _current_rule(self) -> dict:
        rtype = RULE_TYPE_BY_LABEL[self.rule_type_var.get()]
        if rtype in ("replace", "regex"):
            params = {"find": self._rule_param_vars["find"].get(),
                      "replace": self._rule_param_vars["replace"].get()}
        else:
            params = {"text": self._rule_param_vars["text"].get()}
        return normalize_rule(rtype, params, self.case_var.get())

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

    def on_preview(self):
        if not self.files:
            messagebox.showwarning("提示", "请先扫描文件")
            return
        self.preview = build_preview(self.files, self._current_rule())
        self.preview_tree.delete(*self.preview_tree.get_children())
        for e in self.preview:
            status = PREVIEW_STATUS_LABELS[e.status]
            if e.status == "ok" and e.case_only:
                status += " · 两步法"
            new_name = "—" if e.status == "same" else e.new_name
            self.preview_tree.insert("", "end", values=(e.old_name, new_name, status))
        has_valid = any(e.status == "ok" for e in self.preview)
        self.exec_btn.configure(state="normal" if has_valid else "disabled")

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
        self.on_clear_preview()
        self.refresh_history()

    # -------------------------------------------------------------- 撤销面板
    def refresh_history(self):
        self._ops = self.store.list_ops()
        self.history_tree.delete(*self.history_tree.get_children())
        for op in self._ops:
            if op.get("undone"):
                state = "已撤销"
            elif self.store.is_undoable(op):
                state = "可撤销"
            else:
                state = "超出窗口"
            self.history_tree.insert(
                "", "end",
                values=(op["op_id"], rule_summary(op["rule"]), op["file_count"],
                        state, op["created_at"].replace("T", " ")))
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
        dialog.transient(self.root)
        dialog.geometry("640x420")
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("cur", "restore", "state"),
                            show="headings")
        for col, text, width in (("cur", "当前名", 200), ("restore", "还原为", 200),
                                 ("state", "状态", 200)):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        for item in plan:
            entry = item["entry"]
            tree.insert("", "end", values=(
                entry["to"], entry["from"], UNDO_STATE_LABELS[item["state"]]))
        ttk.Label(frame, foreground="#666666", wraplength=600, text=(
            "「跳过」条目绝不覆盖；全部条目都被跳过时本次撤销不成立（操作保持可撤销）。")).pack(
            fill="x", pady=(6, 0))

        choice = {"confirm": False}

        def confirm():
            choice["confirm"] = True
            dialog.destroy()

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="确认撤销", command=confirm).pack(side="right", padx=(0, 8))
        dialog.grab_set()
        self.root.wait_window(dialog)
        return choice["confirm"]


def main():
    root = tk.Tk()
    RenameApp(root)
    root.mainloop()
