"""扫描器测试：通配符 / 正则 / 递归。"""

from rename_file.core.scanner import scan_files


def make_tree(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.jpg").write_text("x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("x")
    return sub


def test_glob_filter(tmp_path):
    make_tree(tmp_path)
    names = {p.name for p in scan_files(tmp_path, pattern="*.txt")}
    assert names == {"a.txt"}


def test_regex_filter(tmp_path):
    make_tree(tmp_path)
    names = {p.name for p in scan_files(tmp_path, regex_pattern=r"^[ab]")}
    assert names == {"a.txt", "b.jpg"}


def test_recursive(tmp_path):
    make_tree(tmp_path)
    names = {p.name for p in scan_files(tmp_path, recursive=True)}
    assert names == {"a.txt", "b.jpg", "c.txt"}


def test_directories_excluded(tmp_path):
    make_tree(tmp_path)
    names = {p.name for p in scan_files(tmp_path, recursive=True)}
    assert "sub" not in names


def test_invalid_regex_treated_as_no_filter(tmp_path):
    make_tree(tmp_path)
    names = {p.name for p in scan_files(tmp_path, regex_pattern="([")}
    assert names == {"a.txt", "b.jpg"}
