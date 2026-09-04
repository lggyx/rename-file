# -*- coding: utf-8 -*-
"""CLI 测试：dry-run / apply / undo / --list / 参数解析 / 退出码。

直接调用 cli.main(argv)，不走子进程；文件系统用 tmp_path 沙箱，
日志目录经 --history-dir 注入，绝不碰真实 %APPDATA%。
"""

import pytest

from rename_file.cli import main


def touch(parent, name, content="x"):
    p = parent / name
    p.write_text(content, encoding="utf-8")
    return p


def names_in(directory):
    return {p.name for p in directory.iterdir()}


@pytest.fixture
def sandbox(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    return work


def test_dry_run_previews_without_touching(sandbox, tmp_path, capsys):
    touch(sandbox, "IMG_0001.jpg")
    hist = tmp_path / "history"
    code = main(["--dry-run", "--dir", str(sandbox), "--history-dir", str(hist),
                 "--rule", "regex", r"^IMG_", "2023_"])
    out = capsys.readouterr().out
    assert code == 0
    assert "预览 1 条有效变更" in out
    assert names_in(sandbox) == {"IMG_0001.jpg"}          # 文件没动
    assert not hist.exists() or not list(hist.glob("op_*.json"))  # 日志没写


def test_apply_renames_and_writes_log(sandbox, tmp_path, capsys):
    touch(sandbox, "IMG_0001.jpg")
    hist = tmp_path / "history"
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(hist),
                 "--rule", "regex", r"^IMG_", "2023_"])
    out = capsys.readouterr().out
    assert code == 0
    assert names_in(sandbox) == {"2023_0001.jpg"}
    assert "撤销日志:" in out
    assert list(hist.glob("op_*.json")), "日志必须落盘"


def test_apply_with_no_valid_changes_exits_zero(sandbox, tmp_path, capsys):
    touch(sandbox, "a.txt")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                 "--rule", "regex", r"^zzz", "x"])
    out = capsys.readouterr().out
    assert code == 0
    assert "没有有效变更" in out
    assert names_in(sandbox) == {"a.txt"}


def test_apply_partial_failure_exits_one(sandbox, tmp_path):
    """Windows 下重命名被占用的文件会失败：一条留痕、其余正常、退出码 1。"""
    f1 = touch(sandbox, "IMG_0001.jpg")
    touch(sandbox, "IMG_0002.jpg")
    with open(f1, "rb") as lock:  # 打开的句柄（无 FILE_SHARE_DELETE）阻塞重命名
        code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                     "--rule", "regex", r"^IMG_", "2023_"])
    assert code == 1
    assert (sandbox / "IMG_0001.jpg").exists()   # 被占用的失败留痕、原文件未动
    assert (sandbox / "2023_0002.jpg").exists()  # 其余条目正常完成


def test_undo_restores(tmp_path, capsys):
    sandbox = tmp_path / "work"
    sandbox.mkdir()
    hist = tmp_path / "history"
    touch(sandbox, "IMG_0001.jpg")
    assert main(["--apply", "--dir", str(sandbox), "--history-dir", str(hist),
                 "--rule", "regex", r"^IMG_", "2023_"]) == 0
    code = main(["--undo", "--history-dir", str(hist)])
    out = capsys.readouterr().out
    assert code == 0
    assert "已还原 1 个文件" in out
    assert names_in(sandbox) == {"IMG_0001.jpg"}


def test_undo_list_and_empty(sandbox, tmp_path, capsys):
    hist = tmp_path / "history"
    assert main(["--undo", "--list", "--history-dir", str(hist)]) == 0
    assert "当前没有可撤销的操作" in capsys.readouterr().out

    touch(sandbox, "a.txt")
    main(["--apply", "--dir", str(sandbox), "--history-dir", str(hist),
          "--rule", "prefix", "x_"])
    code = main(["--undo", "--list", "--history-dir", str(hist)])
    out = capsys.readouterr().out
    assert code == 0
    assert "可撤销 1 项" in out
    assert "前缀添加: x_" in out


def test_undo_without_undoable_exits_one(tmp_path, capsys):
    code = main(["--undo", "--history-dir", str(tmp_path / "h")])
    assert code == 1


def test_undo_twice_restores_fully(tmp_path, capsys):
    """链式改名（notes→memo→archived）经两次 --undo 完整找回原名。

    「跳撤较早操作 → 撤销不成立」的场景由 core 测试覆盖，
    CLI 的 --undo 永远撤最新一条。
    """
    sandbox = tmp_path / "work"
    sandbox.mkdir()
    hist = tmp_path / "history"
    touch(sandbox, "notes.txt")
    main(["--apply", "--dir", str(sandbox), "--history-dir", str(hist),
          "--rule", "replace", "notes", "memo"])
    main(["--apply", "--dir", str(sandbox), "--history-dir", str(hist),
          "--rule", "replace", "memo", "archived_memo"])
    assert names_in(sandbox) == {"archived_memo.txt"}

    assert main(["--undo", "--history-dir", str(hist)]) == 0
    code = main(["--undo", "--history-dir", str(hist)])
    out = capsys.readouterr().out
    assert code == 0 and "已还原 1 个文件" in out
    assert names_in(sandbox) == {"notes.txt"}


def test_chinese_rule_label_accepted(sandbox, tmp_path):
    touch(sandbox, "IMG_0001.jpg")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                 "--rule", "正则替换", r"^IMG_", "2023_"])
    assert code == 0
    assert names_in(sandbox) == {"2023_0001.jpg"}


def test_unknown_rule_type_exits_one(sandbox, tmp_path, capsys):
    touch(sandbox, "a.txt")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                 "--rule", "nope", "x"])
    assert code == 1
    assert "未知规则类型" in capsys.readouterr().out


def test_wrong_param_count_exits_one(sandbox, tmp_path, capsys):
    touch(sandbox, "a.txt")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                 "--rule", "prefix"])
    assert code == 1
    assert "需要 1 个参数" in capsys.readouterr().out


def test_missing_rule_for_apply_exits_one(sandbox, tmp_path, capsys):
    touch(sandbox, "a.txt")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h")])
    assert code == 1
    assert "--rule" in capsys.readouterr().out


def test_missing_mode_exits_two(sandbox):
    with pytest.raises(SystemExit) as exc:
        main(["--dir", str(sandbox)])
    assert exc.value.code == 2


def test_missing_dir_exits_one(tmp_path, capsys):
    code = main(["--apply", "--dir", str(tmp_path / "nope"),
                 "--history-dir", str(tmp_path / "h"),
                 "--rule", "prefix", "x_"])
    assert code == 1


def test_no_case_sensitive_flag(sandbox, tmp_path):
    touch(sandbox, "IMG_0001.jpg")
    code = main(["--apply", "--dir", str(sandbox), "--history-dir", str(tmp_path / "h"),
                 "--rule", "replace", "img", "pic", "--no-case-sensitive"])
    out_code = code
    assert out_code == 0
    assert names_in(sandbox) == {"pic_0001.jpg"}
