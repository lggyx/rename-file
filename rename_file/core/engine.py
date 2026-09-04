"""执行引擎：预览构建与批量重命名。

核心保证（对应 design/flowcharts.md §2）：
- 日志先行：撤销日志写入成功后才开始改名；写失败抛 LogWriteError 中止，
  此时未改动任何文件（可撤销性优先于执行）。
- 两步法：仅大小写变化的改名走 原名 → 临时名 → 目标名，中途失败自动回滚。
- 失败留痕：单条运行时失败记入 entries.status = failed 并继续其余条目。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .history import LOG_VERSION, HistoryStore
from .rules import apply_rule
from .validate import is_case_only_rename, is_filename_valid, names_equal

STATUS_OK = "ok"            # 有效：预览通过且执行成功
STATUS_SAME = "same"        # 无变化
STATUS_INVALID = "invalid"  # 无效：非法字符 / 保留名
STATUS_CONFLICT = "conflict"  # 冲突：目标名被其他文件占用
STATUS_FAILED = "failed"    # 预览有效但执行时失败（运行时留痕）


class LogWriteError(RuntimeError):
    """撤销日志写入失败（目录不可写等）。此时未改动任何文件。"""


@dataclass
class PreviewEntry:
    path: Path
    old_name: str
    new_name: str
    status: str                  # ok / same / invalid / conflict
    case_only: bool = False      # 仅大小写变化，执行需两步法


def build_preview(files: list[Path], rule: dict) -> list[PreviewEntry]:
    """逐条应用规则并判定状态。

    冲突按"同目录"判定，忽略大小写，且增量认领目标名：
    两个文件改出同一个新名时，后者判冲突。
    """
    entries: list[PreviewEntry] = []
    occupied: dict[Path, set[str]] = {}  # 父目录 → 现有文件名 ∪ 已认领的目标名

    for path in files:
        old_name = path.name
        new_name = apply_rule(old_name, rule)
        case_only = is_case_only_rename(old_name, new_name)

        if new_name == old_name:
            status = STATUS_SAME
        elif not is_filename_valid(new_name):
            status = STATUS_INVALID
        else:
            seen = occupied.get(path.parent)
            if seen is None:
                seen = occupied[path.parent] = {p.name for p in path.parent.iterdir()}
            conflict = any(
                names_equal(n, new_name)
                for n in seen
                if not names_equal(n, old_name)  # 排除自身（case-only 改名不算冲突）
            )
            status = STATUS_CONFLICT if conflict else STATUS_OK
            if not conflict:
                seen.add(new_name)  # 认领目标名

        entries.append(PreviewEntry(path, old_name, new_name, status, case_only))

    return entries


def _build_op(preview: list[PreviewEntry], *, op_id: str, base_dir: str,
              recursive: bool, rule: dict) -> tuple[dict, list[PreviewEntry]]:
    """由有效条目构造操作日志（entries 与 PreviewEntry 按位对应）。"""
    valid = [e for e in preview if e.status == STATUS_OK]
    entries = [
        {
            "from": e.old_name,
            "to": e.new_name,
            "status": STATUS_OK,
            "error": None,
            "case_only": e.case_only,
            "via_tmp": f"__rename_tmp_{op_id}_{e.new_name}" if e.case_only else None,
        }
        for e in valid
    ]
    op = {
        "version": LOG_VERSION,
        "op_id": op_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_dir": str(base_dir),
        "recursive": bool(recursive),
        "rule": rule,
        "file_count": len(entries),
        "entries": entries,
        "undone": False,
        "undone_at": None,
        "undo_result": None,
    }
    return op, valid


def execute(preview: list[PreviewEntry], *, store: HistoryStore,
            base_dir: str | Path, recursive: bool = False, rule: dict) -> dict:
    """执行全部「有效」条目并写撤销日志。

    返回 {"op": op|None, "ok_count": int, "failed_count": int}。
    没有有效条目时直接返回，不写日志、不改文件。
    """
    valid = [e for e in preview if e.status == STATUS_OK]
    if not valid:
        return {"op": None, "ok_count": 0, "failed_count": 0}

    op, _ = _build_op(preview, op_id=store.new_op_id(),
                      base_dir=str(base_dir), recursive=recursive, rule=rule)

    # 日志先行：写失败则中止，未改动任何文件
    try:
        store.write_op(op)
    except OSError as exc:
        raise LogWriteError(f"撤销日志写入失败（{exc}），已中止执行以保证可撤销性") from exc

    ok_count = failed_count = 0
    for e, entry in zip(valid, op["entries"]):
        target = e.path.parent / entry["to"]
        try:
            if entry["case_only"]:
                tmp = e.path.parent / entry["via_tmp"]
                e.path.rename(tmp)
                try:
                    tmp.rename(target)
                except OSError:
                    tmp.rename(e.path)  # 第二步失败：回滚第一步，不留临时名
                    raise
            else:
                e.path.rename(target)
            ok_count += 1
        except OSError as exc:
            # 运行时失败（文件被占用 / 权限 / 目标被外部占用）：留痕并继续
            entry["status"] = STATUS_FAILED
            entry["error"] = str(exc)
            failed_count += 1

    store.write_op(op)  # 回写最终状态（ok / failed）
    return {"op": op, "ok_count": ok_count, "failed_count": failed_count}
