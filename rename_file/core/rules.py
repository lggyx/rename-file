"""规则引擎：四类重命名规则的应用逻辑（纯函数，无 UI / IO 依赖）。"""

import os
import re

RULE_PREFIX = "prefix"
RULE_SUFFIX = "suffix"
RULE_REPLACE = "replace"
RULE_REGEX = "regex"

# 内部 id ↔ UI 中文标签（GUI / CLI 层复用，避免散落字面量）
RULE_TYPE_LABELS = {
    RULE_PREFIX: "前缀添加",
    RULE_SUFFIX: "后缀添加",
    RULE_REPLACE: "字符串替换",
    RULE_REGEX: "正则替换",
}
RULE_TYPE_BY_LABEL = {label: rid for rid, label in RULE_TYPE_LABELS.items()}


def normalize_rule(rule_type: str, params: dict | None = None,
                   case_sensitive: bool = True, **param_kwargs) -> dict:
    """构造规则 dict，统一入口避免各处散落字面量。

    参数两种传法等价：normalize_rule("replace", {"find": "a"}) 或
    normalize_rule("replace", find="a")；case_sensitive 永远是顶层控制键。
    """
    if rule_type not in RULE_TYPE_LABELS:
        raise ValueError(f"未知规则类型: {rule_type!r}")
    merged = {**(params or {}), **param_kwargs}
    return {
        "type": rule_type,
        "params": merged,
        "case_sensitive": bool(case_sensitive),
    }


def apply_rule(filename: str, rule: dict) -> str:
    """对单个文件名应用规则，返回新文件名（不校验合法性，非法正则返回原名）。"""
    rtype = rule["type"]
    params = rule.get("params") or {}
    case_sensitive = rule.get("case_sensitive", True)

    if rtype == RULE_PREFIX:
        return params.get("text", "") + filename

    if rtype == RULE_SUFFIX:
        # 后缀加在扩展名之前（与旧版 main.py 行为一致）
        text = params.get("text", "")
        name, ext = os.path.splitext(filename)
        return name + text + ext

    if rtype == RULE_REPLACE:
        find = params.get("find", "")
        replace = params.get("replace", "")
        if not find:
            return filename
        if case_sensitive:
            return filename.replace(find, replace)
        # 忽略大小写：按字面量转义后走正则
        pattern = re.compile(re.escape(find), re.IGNORECASE)
        return pattern.sub(replace, filename)

    if rtype == RULE_REGEX:
        find = params.get("find", "")
        replace = params.get("replace", "")
        if not find:
            return filename
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.sub(find, replace, filename, flags=flags)
        except re.error:
            # 非法正则：与旧版行为一致，返回原名
            return filename

    return filename
