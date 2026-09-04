"""文件名校验测试：非法字符 / 保留名 / 忽略大小写语义。"""

from rename_file.core.validate import (
    has_conflict,
    is_case_only_rename,
    is_filename_valid,
    names_equal,
)


def test_valid_names():
    assert is_filename_valid("a.txt")
    assert is_filename_valid("报告 最终_v2.docx")


def test_invalid_chars():
    for ch in '<>:"/\\|?*':
        assert not is_filename_valid(f"bad{ch}name.txt")


def test_reserved_names_case_insensitive():
    assert not is_filename_valid("CON")
    assert not is_filename_valid("con.txt")
    assert not is_filename_valid("Com1.docx")
    assert is_filename_valid("constant.txt")  # 仅前缀相同不算保留名


def test_empty_or_blank_invalid():
    assert not is_filename_valid("")
    assert not is_filename_valid("   ")


def test_names_equal_ignores_case():
    assert names_equal("Readme.txt", "readme.txt")
    assert not names_equal("Readme.txt", "readme.md")


def test_case_only_rename():
    assert is_case_only_rename("readme.txt", "Readme.txt")
    assert not is_case_only_rename("readme.txt", "readme.txt")     # 没变
    assert not is_case_only_rename("readme.txt", "other.txt")      # 不止大小写变化


def test_has_conflict_excludes_self():
    occupied = ["readme.txt", "other.txt"]
    # 仅大小写变化：排除自身后不算冲突
    assert not has_conflict("Readme.txt", occupied, self_name="readme.txt")
    # 其他文件占用还原名：冲突
    assert has_conflict("other.txt", occupied, self_name="readme.txt")
