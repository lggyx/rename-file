"""日志存储测试：读写往返 / 排序 / 可撤销窗口 / 损坏容错。"""

import json

from rename_file.core.history import HistoryStore, default_history_dir


def make_op(op_id, undone=False):
    return {
        "version": 1, "op_id": op_id, "created_at": "2026-09-04T00:00:00+08:00",
        "base_dir": "D:/demo", "recursive": False,
        "rule": {"type": "prefix", "params": {"text": "x"}, "case_sensitive": True},
        "file_count": 1,
        "entries": [{"from": "a.txt", "to": "xa.txt", "status": "ok",
                     "error": None, "case_only": False, "via_tmp": None}],
        "undone": undone, "undone_at": None, "undo_result": None,
    }


def test_write_and_list_roundtrip(tmp_path):
    store = HistoryStore(tmp_path)
    store.write_op(make_op("op_20260904_000001"))
    ops = store.list_ops()
    assert len(ops) == 1
    assert ops[0]["op_id"] == "op_20260904_000001"
    assert (tmp_path / "op_20260904_000001.json").exists()


def test_list_sorted_newest_first(tmp_path):
    store = HistoryStore(tmp_path)
    store.write_op(make_op("op_20260904_000001"))
    store.write_op(make_op("op_20260904_000003"))
    store.write_op(make_op("op_20260904_000002"))
    assert [o["op_id"] for o in store.list_ops()] == [
        "op_20260904_000003", "op_20260904_000002", "op_20260904_000001"]


def test_undoable_window_keeps_recent_ten(tmp_path):
    store = HistoryStore(tmp_path)
    for i in range(1, 13):
        store.write_op(make_op(f"op_20260904_{i:06d}"))
    assert len(store.applied_ops()) == 12
    undoable = store.undoable_ops()
    assert len(undoable) == 10
    # 窗口 = 最新的 10 份（最旧的 2 份被挤出）
    assert undoable[-1]["op_id"] == "op_20260904_000003"
    assert not store.is_undoable(make_op("op_20260904_000001"))
    assert store.is_undoable(make_op("op_20260904_000005"))


def test_undone_ops_excluded_from_window(tmp_path):
    store = HistoryStore(tmp_path)
    for i in range(1, 12):
        store.write_op(make_op(f"op_20260904_{i:06d}"))
    # 把最新的标记为已撤销：它让出窗口名额，最旧的 000001 重新进入窗口
    newest = make_op("op_20260904_000011", undone=True)
    store.write_op(newest)
    undoable_ids = [o["op_id"] for o in store.undoable_ops()]
    assert "op_20260904_000011" not in undoable_ids
    assert "op_20260904_000001" in undoable_ids


def test_corrupt_file_skipped(tmp_path):
    store = HistoryStore(tmp_path)
    store.write_op(make_op("op_20260904_000001"))
    (tmp_path / "op_20260904_000009.json").write_text("{broken", encoding="utf-8")
    assert [o["op_id"] for o in store.list_ops()] == ["op_20260904_000001"]


def test_new_op_id_unique_within_same_second(tmp_path):
    store = HistoryStore(tmp_path)
    first = store.new_op_id()
    second = store.new_op_id()
    assert first != second
    assert second.startswith(first.rsplit("-", 1)[0])


def test_default_dir_uses_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", r"D:\AppData\Roaming")
    d = default_history_dir()
    assert str(d).startswith(r"D:\AppData\Roaming")
    assert d.name == "history"


def test_overwrite_preserves_single_file(tmp_path):
    store = HistoryStore(tmp_path)
    store.write_op(make_op("op_20260904_000001"))
    op = make_op("op_20260904_000001", undone=True)
    store.write_op(op)
    files = list(tmp_path.glob("op_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["undone"] is True
