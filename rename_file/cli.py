"""rename-cli：批量文件名修改工具的命令行入口。

与 GUI 共用同一个 core（规则引擎 / 日志存储 / 撤销引擎），业务逻辑零重复。

用法示例：
    rename-cli --dry-run --dir D:/photos --filter "*.jpg" --rule regex "^IMG_" "2023_"
    rename-cli --apply --dir D:/photos --rule regex "^IMG_" "2023_"
    rename-cli --undo
    rename-cli --undo --list

约定：
- --dry-run 只预览：不修改文件、不写撤销日志
- --apply 执行并写撤销日志；日志写失败则中止（可撤销性优先）
- --undo 撤销最近一次；0 条还原时撤销不成立（退出码 1，操作保持可撤销）
- 退出码：0 成功 / 1 运行失败（含部分失败）/ 2 参数错误
"""

import argparse
import sys
from pathlib import Path

from rename_file.core import (
    RULE_TYPE_BY_LABEL,
    RULE_TYPE_LABELS,
    STATUS_LABELS,
    HistoryStore,
    LogWriteError,
    apply_undo,
    build_preview,
    execute,
    normalize_rule,
    rule_summary,
    scan_files,
)

RULE_PARAM_COUNTS = {"prefix": 1, "suffix": 1, "replace": 2, "regex": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rename-cli",
        description="批量文件名修改工具 CLI（与 GUI 共用同一 core）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  rename-cli --dry-run --dir D:/photos --rule regex '^IMG_' '2023_'\n"
            "  rename-cli --apply --dir D:/photos --rule regex '^IMG_' '2023_'\n"
            "  rename-cli --undo\n"
            "  rename-cli --undo --list\n"
        ),
    )
    parser.add_argument("--dir", default=".", help="目标目录（默认当前目录）")
    parser.add_argument("--filter", default="*", help="通配符过滤（默认 *）")
    parser.add_argument("--regex-filter", default=".*",
                        help="文件名正则过滤（默认 .*，非法正则视为不过滤）")
    parser.add_argument("--recursive", action="store_true", help="递归搜索子目录")
    parser.add_argument("--rule", nargs="+", metavar=("TYPE", "PARAM"),
                        help=("规则类型 + 参数：prefix/suffix 后接 1 个文本参数；"
                              "replace/regex 后接 2 个（查找 替换为）。"
                              f"类型可用英文 id 或中文标签（{'/'.join(RULE_TYPE_LABELS.values())}）"))
    parser.add_argument("--no-case-sensitive", dest="case_sensitive",
                        action="store_false",
                        help="忽略大小写（仅对 replace/regex 生效，默认大小写敏感）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="仅预览：不修改文件、不写撤销日志")
    mode.add_argument("--apply", action="store_true",
                      help="执行重命名并写撤销日志")
    mode.add_argument("--undo", action="store_true",
                      help="撤销最近一次可撤销操作")
    parser.add_argument("--list", action="store_true",
                        help="与 --undo 连用：列出可撤销的操作栈")
    parser.add_argument("--history-dir", default=None,
                        help=argparse.SUPPRESS)  # 测试/自动化注入用
    return parser


def parse_rule(rule_args: list[str] | None, case_sensitive: bool) -> dict:
    """解析 --rule TYPE PARAM...；类型/参数个数不合法时抛 ValueError。"""
    if not rule_args:
        raise ValueError("--dry-run/--apply 需要 --rule 规则")
    rtype = rule_args[0]
    if rtype in RULE_TYPE_BY_LABEL:
        rtype = RULE_TYPE_BY_LABEL[rtype]
    rest = rule_args[1:]
    expected = RULE_PARAM_COUNTS.get(rtype)
    if expected is None:
        raise ValueError(f"未知规则类型: {rule_args[0]!r}"
                         f"（可选: prefix/suffix/replace/regex 或中文标签）")
    if len(rest) != expected:
        raise ValueError(f"规则 {rtype} 需要 {expected} 个参数，收到 {len(rest)} 个")
    if expected == 1:
        return normalize_rule(rtype, {"text": rest[0]}, case_sensitive)
    return normalize_rule(rtype, {"find": rest[0], "replace": rest[1]}, case_sensitive)


def _print_preview(preview) -> None:
    for e in preview:
        new_name = "—" if e.status == "same" else e.new_name
        note = " · 两步法" if (e.status == "ok" and e.case_only) else ""
        print(f"  {e.old_name}  →  {new_name}  [{STATUS_LABELS[e.status]}{note}]")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = HistoryStore(args.history_dir) if args.history_dir else HistoryStore()

    # ---- 撤销模式
    if args.undo:
        if not args.list:
            ops = store.undoable_ops()
            if not ops:
                print("当前没有可撤销的操作")
                return 1
            op = ops[0]
            result = apply_undo(op, store)
            if not result["undone"]:
                print("撤销不成立：该操作的输出文件已被后续操作改名或占用，"
                      "请先撤销对应的后续操作（--undo --list 查看）。")
                return 1
            print(f"已还原 {result['restored']} 个文件（{op['op_id']}）")
            for s in result["skipped"]:
                print(f"  跳过: {s['reason']}")
            return 0
        ops = store.undoable_ops()
        if not ops:
            print("当前没有可撤销的操作")
            return 0
        print(f"可撤销 {len(ops)} 项（新 → 旧）：")
        for i, op in enumerate(ops, 1):
            print(f"  {i}. {op['op_id']}  {rule_summary(op['rule'])}"
                  f"  {op['file_count']} 个文件  {op['created_at']}")
        return 0

    # ---- 预览 / 执行模式
    if not (args.dry_run or args.apply):
        parser.error("需要指定模式：--dry-run / --apply / --undo")
    try:
        rule = parse_rule(args.rule, args.case_sensitive)
    except ValueError as exc:
        print(f"错误: {exc}")
        return 1

    directory = Path(args.dir)
    if not directory.exists():
        print(f"错误: 目录不存在 {directory}")
        return 1

    files = scan_files(directory, args.filter, args.regex_filter, args.recursive)
    preview = build_preview(files, rule)
    valid = [e for e in preview if e.status == "ok"]
    _print_preview(preview)

    if not valid:
        print(f"共 {len(preview)} 项，没有有效变更。")
        return 0
    print(f"预览 {len(valid)} 条有效变更。")

    if args.dry_run:
        print("--dry-run：未修改任何文件、未写撤销日志。")
        return 0

    try:
        result = execute(preview, store=store, base_dir=directory,
                         recursive=args.recursive, rule=rule)
    except LogWriteError as exc:
        print(f"执行中止: {exc}")
        return 1
    print(f"已重命名 {result['ok_count']} 个文件，失败 {result['failed_count']} 个。")
    print(f"撤销日志: {store.path_for(result['op']['op_id'])}")
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
