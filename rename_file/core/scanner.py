"""文件扫描：目录 + 通配符过滤 + 正则过滤 + 递归开关（行为与旧版 main.py 一致）。"""

import re
from pathlib import Path


def scan_files(directory: str | Path, pattern: str = "*",
               regex_pattern: str = ".*", recursive: bool = False) -> list[Path]:
    """扫描目录下匹配的文件（只返回文件，不含目录）。"""
    dir_path = Path(directory)
    search = dir_path.rglob(pattern) if recursive else dir_path.glob(pattern)

    files: list[Path] = []
    for path in search:
        if not path.is_file():
            continue
        if regex_pattern and regex_pattern != ".*":
            try:
                if not re.match(regex_pattern, path.name):
                    continue
            except re.error:
                pass  # 非法正则：与旧版一致，视为不过滤
        files.append(path)
    return files
