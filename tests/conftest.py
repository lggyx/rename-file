"""pytest 共享 fixture：history 目录一律注入独立临时目录，绝不碰真实 %APPDATA%，
也不会混进各测试自己的 tmp_path 文件沙箱。"""

import pytest


@pytest.fixture
def history_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("history")
