"""撤销引擎测试：还原判定 / 两步法回退 / 0 条还原不成立 / 冲突不覆盖。"""


from rename_file.core.engine import build_preview, execute
from rename_file.core.history import HistoryStore
from rename_file.core.rules import normalize_rule
from rename_file.core.undo import apply_undo, find_tmp_residue, plan_undo


def touch(parent, name, content="x"):
    p = parent / name
    p.write_text(content, encoding="utf-8")
    return p


def names_in(directory):
    return {p.name for p in directory.iterdir()}


def run_op(tmp_path, history_dir, files, rule):
    """辅助：对 files 执行一次重命名，返回 (result, store)。"""
    store = HistoryStore(history_dir)
    preview = build_preview([tmp_path / f for f in files], rule)
    result = execute(preview, store=store, base_dir=tmp_path, rule=rule)
    assert result["failed_count"] == 0
    return result, store


def test_undo_restores_names(tmp_path, history_dir):
    touch(tmp_path, "IMG_0001.jpg")
    touch(tmp_path, "IMG_0002.jpg")
    rule = normalize_rule("regex", find=r"^IMG_", replace="2023_")
    result, store = run_op(tmp_path, history_dir, ["IMG_0001.jpg", "IMG_0002.jpg"], rule)

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 2 and undo["undone"] is True
    assert names_in(tmp_path) == {"IMG_0001.jpg", "IMG_0002.jpg"}
    op = store.list_ops()[0]
    assert op["undone"] is True
    assert op["undo_result"]["restored"] == 2
    assert op["undo_result"]["skipped"] == []


def test_undo_case_only_two_step(tmp_path, history_dir):
    touch(tmp_path, "readme.txt")
    rule = normalize_rule("replace", find="readme", replace="Readme")
    result, store = run_op(tmp_path, history_dir, ["readme.txt"], rule)
    assert names_in(tmp_path) == {"Readme.txt"}

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 1
    assert names_in(tmp_path) == {"readme.txt"}  # 还原为原始大小写，无临时名残留


def test_undo_zero_restored_is_not_consumed(tmp_path, history_dir):
    """纠缠场景：Op1 的输出已被 Op2 改名，跳选撤 Op1 → 0 条还原 → 撤销不成立。"""
    touch(tmp_path, "notes.txt")
    op1, store = run_op(tmp_path, history_dir, ["notes.txt"],
                        normalize_rule("replace", find="notes", replace="memo"))
    op2, _ = run_op(tmp_path, history_dir, ["memo.txt"],
                    normalize_rule("replace", find="memo", replace="archived_memo"))
    assert names_in(tmp_path) == {"archived_memo.txt"}

    undo1 = apply_undo(op1["op"], store)

    assert undo1["restored"] == 0 and undo1["undone"] is False
    assert undo1["op"]["undone"] is False                # 操作保持可撤销
    assert len(store.undoable_ops()) == 2                # 两个操作都还能撤
    assert names_in(tmp_path) == {"archived_memo.txt"}   # 文件没被动过

    # 按正确顺序：先撤 Op2，再撤 Op1 → notes.txt 完整找回
    undo2 = apply_undo(op2["op"], store)
    assert undo2["restored"] == 1 and names_in(tmp_path) == {"memo.txt"}
    undo1b = apply_undo(op1["op"], store)
    assert undo1b["restored"] == 1 and undo1b["undone"] is True
    assert names_in(tmp_path) == {"notes.txt"}


def test_undo_conflict_never_overwrites(tmp_path, history_dir):
    touch(tmp_path, "a.txt")
    rule = normalize_rule("prefix", text="x_")
    result, store = run_op(tmp_path, history_dir, ["a.txt"], rule)
    assert names_in(tmp_path) == {"x_a.txt"}

    # 撤销前：另一个文件占住了还原名 a.txt（且原 x_a.txt 也在）
    touch(tmp_path, "a.txt", content="别的文件")
    other = touch(tmp_path, "other_marker", content="")

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 0
    assert undo["skipped"][0]["reason"].startswith("还原名已被占用")
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "别的文件"  # 绝不覆盖
    assert other.exists()


def test_undo_partial_restore_marks_undone_with_skipped(tmp_path, history_dir):
    touch(tmp_path, "a.txt")
    touch(tmp_path, "b.txt")
    rule = normalize_rule("regex", find=r"^([ab])", replace=r"z_\1")
    result, store = run_op(tmp_path, history_dir, ["a.txt", "b.txt"], rule)
    assert names_in(tmp_path) == {"z_a.txt", "z_b.txt"}

    # 撤销前：外部新文件占住了 b 的还原名 → 该条跳过，a 正常还原
    touch(tmp_path, "b.txt", content="外来文件")

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 1 and undo["undone"] is True
    assert undo["skipped"][0]["from"] == "b.txt"
    assert (tmp_path / "a.txt").exists()                          # a 已还原
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "外来文件"  # 外来文件未被覆盖
    assert (tmp_path / "z_b.txt").read_text(encoding="utf-8") == "x"      # b 保持在改名后状态
    op = store.list_ops()[0]
    assert op["undo_result"]["restored"] == 1
    assert op["undo_result"]["skipped"][0]["from"] == "b.txt"


def test_undo_ignores_failed_entries(tmp_path, history_dir):
    """执行时 failed 的条目根本没改名，撤销不应碰它。"""
    f1 = touch(tmp_path, "IMG_0001.jpg")
    f2 = touch(tmp_path, "IMG_0002.jpg")
    store = HistoryStore(history_dir)
    rule = normalize_rule("regex", find=r"^IMG_", replace="2023_")
    preview = build_preview([f1, f2], rule)
    (tmp_path / "2023_0001.jpg").mkdir()  # 制造运行时失败
    result = execute(preview, store=store, base_dir=tmp_path, rule=rule)
    assert result["failed_count"] == 1

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 1                 # 只有成功的 0002 被还原
    assert (tmp_path / "IMG_0001.jpg").exists()  # failed 条目保持原名
    assert (tmp_path / "IMG_0002.jpg").exists()  # 0002 已被还原回原名


def test_plan_undo_states(tmp_path, history_dir):
    touch(tmp_path, "notes.txt")
    op1, _ = run_op(tmp_path, history_dir, ["notes.txt"],
                    normalize_rule("replace", find="notes", replace="memo"))
    op2, _ = run_op(tmp_path, history_dir, ["memo.txt"],
                    normalize_rule("replace", find="memo", replace="archived_memo"))

    # Op1 的输出 memo.txt 已不存在 → missing；Op2 可还原 → ok
    plan1 = {p["entry"]["from"]: p["state"] for p in plan_undo(op1["op"])}
    plan2 = {p["entry"]["from"]: p["state"] for p in plan_undo(op2["op"])}
    assert plan1["notes.txt"] == "missing"
    assert plan2["memo.txt"] == "ok"


def test_undo_target_dir_missing(tmp_path, history_dir):
    import shutil
    work = tmp_path / "work"
    work.mkdir()
    touch(work, "a.txt")
    result, store = run_op(work, history_dir, ["a.txt"],
                           normalize_rule("prefix", text="x_"))
    shutil.rmtree(work)  # 目录整个被删

    undo = apply_undo(result["op"], store)

    assert undo["restored"] == 0 and undo["undone"] is False
    assert undo["skipped"][0]["reason"] == "目标目录不存在"


def test_find_tmp_residue(tmp_path):
    assert find_tmp_residue(tmp_path) == []
    residue = tmp_path / "__rename_tmp_op_x_Readme.txt"
    residue.write_text("x", encoding="utf-8")
    (tmp_path / "normal.txt").write_text("x", encoding="utf-8")
    found = find_tmp_residue(tmp_path)
    assert found == [residue]
