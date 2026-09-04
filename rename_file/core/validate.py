"""文件名合法性与冲突检查。

Windows 语义：文件名比较一律忽略大小写（readme.txt 与 Readme.txt 是同一个名字），
仅大小写变化的重命名（a.txt → A.txt）不视为冲突，由执行/撤销层走两步法。
"""

import os

INVALID_CHARS = '<>:"/\\|?*'

RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_filename_valid(name: str) -> bool:
    """检查文件名在 Windows 上是否合法（非法字符 / 保留名）。"""
    if not name or not name.strip():
        return False
    if any(ch in name for ch in INVALID_CHARS):
        return False
    stem = os.path.splitext(name)[0].upper()
    return stem not in RESERVED_NAMES


def names_equal(a: str, b: str) -> bool:
    """文件名比较：Windows 大小写不敏感，统一按 lower 比较。"""
    return a.lower() == b.lower()


def is_case_only_rename(old: str, new: str) -> bool:
    """仅大小写变化的重命名（a.txt → A.txt），执行/撤销都需要两步法。"""
    return old != new and old.lower() == new.lower()


def has_conflict(target: str, occupied, self_name: str | None = None) -> bool:
    """target 是否被 occupied 中"另一个文件"占用（忽略大小写）。

    self_name 用于排除自身：仅大小写变化的改名不算冲突。
    """
    for name in occupied:
        if self_name is not None and names_equal(name, self_name):
            continue
        if names_equal(name, target):
            return True
    return False
