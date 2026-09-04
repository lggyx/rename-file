"""撤销引擎：还原判定 + 逐条回退。

对应 design/flowcharts.md §3 / §6 的已验证规则：
- 任意跳选：任一 applied 操作可单独撤销，不能假设其输出文件仍在原位，
  每条还原前必须实时判定（to 存在、from 空闲）。
- 两步法：case_only 条目的撤销同样走 临时名 中转，中途失败回滚。
- 0 条还原 → 撤销不成立：不标记 undone，操作保持可撤销。
  否则操作被标记已撤销但文件卡在中间状态，原名将永远无法通过撤销找回。
- 冲突绝不覆盖：还原名被占用时跳过并留痕。
"""

from datetime import datetime
from pathlib import Path

from .history import HistoryStore
from .validate import names_equal

TMP_PREFIX = "__rename_tmp_"

UNDO_STATE_OK = "ok"
UNDO_STATE_CONFLICT = "conflict"    # 还原名被其他文件占用
UNDO_STATE_MISSING = "missing"      # 输出文件已不存在（被后续操作改名/删除）


def _dir_names(directory: Path) -> list[str]:
    return [p.name for p in directory.iterdir()]


def _entry_state(entry: dict, names: list[str]) -> str:
    """单条还原判定（names 为当前目录文件名快照）。

    - case_only：from/to 忽略大小写时是同一个名字，只要该文件还在即可还原；
    - 其他：要求 e.to 仍存在（要改回去的那个文件得在），且 e.from 名字空闲。
    """
    to_present = any(names_equal(n, entry["to"]) for n in names)
    if entry.get("case_only"):
        return UNDO_STATE_OK if to_present else UNDO_STATE_MISSING
    from_free = not any(names_equal(n, entry["from"]) for n in names)
    if not to_present:
        return UNDO_STATE_MISSING
    return UNDO_STATE_OK if from_free else UNDO_STATE_CONFLICT


def plan_undo(op: dict) -> list[dict]:
    """还原预览：逐条判定，返回 [{"entry": entry, "state": state}]（保持日志顺序）。

    UI 层据此渲染确认弹窗；实际回退以 apply_undo 的实时判定为准。
    """
    base = Path(op["base_dir"])
    names = _dir_names(base) if base.exists() else []
    plan = []
    for entry in op["entries"]:
        if entry["status"] != "ok":
            plan.append({"entry": entry, "state": UNDO_STATE_MISSING})
            continue
        plan.append({"entry": entry, "state": _entry_state(entry, names)})
    return plan


def apply_undo(op: dict, store: HistoryStore) -> dict:
    """执行撤销（倒序回退），返回 {"restored", "skipped", "undone", "op"}。

    undone 为 False 表示撤销不成立（0 条还原）：op 保持 applied、可再次撤销。
    """
    base = Path(op["base_dir"])
    if not base.exists():
        skipped = [{"from": e["from"], "reason": "目标目录不存在"}
                   for e in op["entries"] if e["status"] == "ok"]
        return {"restored": 0, "skipped": skipped, "undone": False, "op": op}

    names = _dir_names(base)
    restored = 0
    skipped: list[dict] = []

    for entry in reversed([e for e in op["entries"] if e["status"] == "ok"]):
        state = _entry_state(entry, names)
        if state != UNDO_STATE_OK:
            reason = ("还原名已被占用，跳过" if state == UNDO_STATE_CONFLICT
                      else f"当前找不到 {entry['to']}（已被后续操作改名或删除），跳过")
            skipped.append({"from": entry["from"], "reason": reason})
            continue

        target = base / entry["to"]
        try:
            if entry.get("case_only"):
                tmp = base / entry["via_tmp"]
                target.rename(tmp)
                try:
                    tmp.rename(base / entry["from"])
                except OSError:
                    tmp.rename(target)  # 第二步失败：回滚第一步
                    raise
            else:
                target.rename(base / entry["from"])
        except OSError as exc:
            skipped.append({"from": entry["from"], "reason": f"还原失败：{exc}"})
            continue

        # 维护目录名快照：to 消失、from 出现
        names = [n for n in names if not names_equal(n, entry["to"])]
        names.append(entry["from"])
        restored += 1

    if restored == 0:
        # 撤销不成立：不消费这次撤销，操作保持可撤销
        return {"restored": 0, "skipped": skipped, "undone": False, "op": op}

    op["undone"] = True
    op["undone_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    op["undo_result"] = {"restored": restored, "skipped": skipped}
    store.write_op(op)
    return {"restored": restored, "skipped": skipped, "undone": True, "op": op}


def find_tmp_residue(directory: Path | str) -> list[Path]:
    """扫描两步法中途崩溃残留的临时名文件（__rename_tmp_*），供启动时提示。"""
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir()
                  if p.is_file() and p.name.startswith(TMP_PREFIX))
