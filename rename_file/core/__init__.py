"""core：与 UI 无关的全部业务逻辑（GUI / CLI 共用，业务逻辑零重复）。

模块划分：
- rules    规则引擎：四类规则的应用逻辑（纯函数）
- validate 文件名合法性与冲突检查（Windows 语义，比较一律忽略大小写）
- scanner  文件扫描：目录 + 通配符 + 正则 + 递归
- history  撤销日志存储：%APPDATA%/rename-file/history/op_*.json
- engine   执行引擎：预览构建与批量重命名（日志先行，两步法）
- undo     撤销引擎：还原判定 + 逐条回退（任意跳选，0 条还原时撤销不成立）
"""

from rename_file.core.engine import (
    STATUS_CONFLICT,
    STATUS_FAILED,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_SAME,
    LogWriteError,
    PreviewEntry,
    build_preview,
    execute,
)
from rename_file.core.history import LOG_VERSION, HistoryStore, default_history_dir
from rename_file.core.rules import (
    RULE_REGEX,
    RULE_REPLACE,
    RULE_SUFFIX,
    RULE_TYPE_LABELS,
    apply_rule,
    normalize_rule,
)
from rename_file.core.scanner import scan_files
from rename_file.core.undo import apply_undo, find_tmp_residue, plan_undo
from rename_file.core.validate import (
    INVALID_CHARS,
    RESERVED_NAMES,
    has_conflict,
    is_case_only_rename,
    is_filename_valid,
    names_equal,
)

__all__ = [
    "INVALID_CHARS",
    "LOG_VERSION",
    "RESERVED_NAMES",
    "RULE_REGEX",
    "RULE_REPLACE",
    "RULE_SUFFIX",
    "RULE_TYPE_LABELS",
    "STATUS_CONFLICT",
    "STATUS_FAILED",
    "STATUS_INVALID",
    "STATUS_OK",
    "STATUS_SAME",
    "HistoryStore",
    "LogWriteError",
    "PreviewEntry",
    "apply_rule",
    "apply_undo",
    "build_preview",
    "default_history_dir",
    "execute",
    "find_tmp_residue",
    "has_conflict",
    "is_case_only_rename",
    "is_filename_valid",
    "names_equal",
    "normalize_rule",
    "plan_undo",
    "scan_files",
]
