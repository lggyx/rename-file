#!/usr/bin/env python3
"""批量文件名修改工具入口：启动 tkinter GUI。

GUI 层在 rename_file/gui.py，业务逻辑在 rename_file/core/（GUI/CLI 共用）。
"""

from rename_file.gui import main

if __name__ == "__main__":
    main()
