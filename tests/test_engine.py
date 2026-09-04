"""执行引擎测试：预览状态判定 / 两步法 / 日志先行 / 失败留痕。"""

import json

import pytest

from rename_file.core.engine import (
    LogWriteError,
    build_preview,
    execute,
)
from rename_file.core.history import HistoryStore
from rename_file.core.rules import normalize_rule


def touch(parent, name, content="x"):
    p = parent / name
    p.write_text(content, encoding="utf-8")
    return p


def names_in(directory):
    return {p.name for p in directory.iterdir()}


def test_preview_statuses(tmp_path):
    touch(tmp_path, "IMG_0001.jpg")
    touch(tmp_path, "keep.txt")
    touch(tmp_path, "IMG_0001.jpg.bak")  # 改名后会与 IMG_0001.jpg 冲突
    rule = normalize_rule("replace", find="IMG_", replace="NEW_")
    preview = build_preview([tmp_path / "IMG_0001.jpg", tmp_path / "keep.txt"],
                            rule)
    by_old = {e.old_name: e for e in preview}
    assert by_old["IMG_0001.jpg"].status == "ok"
    assert by_old["keep.txt"].status == "same"


def test_preview_conflict_is_case_insensitive(tmp_path):
    touch(tmp_path, "readme.txt")
    touch(tmp_path, "other.txt")
    # other.txt → README.TXT：与现有 readme.txt 忽略大小写同名 → 冲突
    rule = normalize_rule("regex", find=r"^other", replace="README")
    preview = build_preview([tmp_path / "other.txt"], rule)
    assert preview[0].status == "conflict"


def test_preview_case_only_self_not_conflict(tmp_path):
    touch(tmp_path, "readme.txt")
    rule = normalize_rule("replace", find="readme", replace="Readme")
    preview = build_preview([tmp_path / "readme.txt"], rule)
    assert preview[0].status == "ok"
    assert preview[0].case_only is True


def test_preview_incremental_claim(tmp_path):
    a = touch(tmp_path, "a1.txt")
    b = touch(tmp_path, "a2.txt")
    # 两个文件改出同一个新名 "same.txt"：后者冲突
    rule = normalize_rule("regex", find=r"^a\d", replace="same")
    preview = build_preview([a, b], rule)
    statuses = {e.old_name: e.status for e in preview}
    assert statuses["a1.txt"] == "ok"
    assert statuses["a2.txt"] == "conflict"


def test_preview_invalid_name(tmp_path):
    f = touch(tmp_path, "a.txt")
    rule = normalize_rule("regex", find="^a", replace="CON")  # 保留名
    preview = build_preview([f], rule)
    assert preview[0].status == "invalid"


def test_execute_renames_and_writes_log(tmp_path, history_dir):
    touch(tmp_path, "IMG_0001.jpg")
    touch(tmp_path, "IMG_0002.jpg")
    store = HistoryStore(history_dir)
    rule = normalize_rule("regex", find=r"^IMG_", replace="2023_")
    preview = build_preview([tmp_path / "IMG_0001.jpg", tmp_path / "IMG_0002.jpg"], rule)

    result = execute(preview, store=store, base_dir=tmp_path, rule=rule)

    assert result["ok_count"] == 2 and result["failed_count"] == 0
    assert names_in(tmp_path) == {"2023_0001.jpg", "2023_0002.jpg"}
    op = result["op"]
    assert op["undone"] is False
    assert op["file_count"] == 2
    assert all(e["status"] == "ok" for e in op["entries"])
    # 日志确实落盘且可读回
    stored = store.list_ops()
    assert len(stored) == 1 and stored[0]["op_id"] == op["op_id"]


def test_execute_case_only_two_step(tmp_path, history_dir):
    touch(tmp_path, "readme.txt")
    store = HistoryStore(history_dir)
    rule = normalize_rule("replace", find="readme", replace="Readme")
    preview = build_preview([tmp_path / "readme.txt"], rule)

    result = execute(preview, store=store, base_dir=tmp_path, rule=rule)

    assert result["ok_count"] == 1
    assert names_in(tmp_path) == {"Readme.txt"}  # 不残留临时名
    entry = result["op"]["entries"][0]
    assert entry["case_only"] is True
    assert entry["via_tmp"].startswith("__rename_tmp_")


def test_execute_log_write_failure_aborts_everything(tmp_path, history_dir):
    touch(tmp_path, "a.txt")
    # 让 history 目录路径指向一个"文件"，制造写入失败
    blocked = history_dir / "blocked"
    blocked.write_text("not a dir", encoding="utf-8")
    store = HistoryStore(blocked)
    rule = normalize_rule("prefix", text="x_")
    preview = build_preview([tmp_path / "a.txt"], rule)

    with pytest.raises(LogWriteError):
        execute(preview, store=store, base_dir=tmp_path, rule=rule)

    # 未改动任何文件、未留下半截日志
    assert names_in(tmp_path) == {"a.txt"}


def test_execute_runtime_failure_marked_and_others_proceed(tmp_path, history_dir):
    f1 = touch(tmp_path, "IMG_0001.jpg")
    f2 = touch(tmp_path, "IMG_0002.jpg")
    store = HistoryStore(history_dir)
    rule = normalize_rule("regex", find=r"^IMG_", replace="2023_")
    preview = build_preview([f1, f2], rule)

    # 预览之后、执行之前：在磁盘上放一个同名"目录"，让 2023_0001.jpg 的改名失败
    # （目录不会作为文件被扫描，预览时看不到它）
    (tmp_path / "2023_0001.jpg").mkdir()

    result = execute(preview, store=store, base_dir=tmp_path, rule=rule)

    assert result["ok_count"] == 1 and result["failed_count"] == 1
    entry = result["op"]["entries"][0]
    assert entry["status"] == "failed"
    assert entry["error"]
    assert (tmp_path / "IMG_0001.jpg").exists()          # 失败条目原文件没动
    assert (tmp_path / "2023_0002.jpg").exists()         # 其余条目正常完成
    # 失败状态已回写到落盘日志
    stored = store.list_ops()[0]
    assert stored["entries"][0]["status"] == "failed"
    assert stored["entries"][1]["status"] == "ok"


def test_execute_empty_preview_writes_nothing(tmp_path, history_dir):
    store = HistoryStore(history_dir)
    rule = normalize_rule("prefix", text="x_")
    result = execute([], store=store, base_dir=tmp_path, rule=rule)
    assert result["op"] is None
    assert list(history_dir.glob("op_*.json")) == []


def test_log_schema_fields(tmp_path, history_dir):
    touch(tmp_path, "readme.txt")
    store = HistoryStore(history_dir)
    rule = normalize_rule("replace", find="readme", replace="Readme")
    result = execute(build_preview([tmp_path / "readme.txt"], rule),
                     store=store, base_dir=tmp_path, rule=rule)
    op = json.loads((history_dir / f"{result['op']['op_id']}.json").read_text(encoding="utf-8"))
    for key in ("version", "op_id", "created_at", "base_dir", "recursive",
                "rule", "file_count", "entries", "undone", "undone_at", "undo_result"):
        assert key in op
