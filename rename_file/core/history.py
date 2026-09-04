"""撤销日志存储：每次「执行修改」写一份 JSON 到 history 目录。

- 默认目录 %APPDATA%/rename-file/history/（跨工作目录，不污染用户目标目录）
- 可撤销窗口：最近 MAX_UNDOABLE 份 applied 状态的日志
- 已撤销（undone）与被挤出窗口（expired）的日志归档保留、可追溯
"""

import json
import os
from datetime import datetime
from pathlib import Path

LOG_VERSION = 1


def default_history_dir() -> Path:
    """%APPDATA%/rename-file/history；无 APPDATA 环境变量时退回 ~/.rename-file/history。"""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".rename-file"
    return base / "rename-file" / "history"


class HistoryStore:
    """history 目录的读写封装；目录可注入（测试用 tmp_path）。"""

    MAX_UNDOABLE = 10

    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else default_history_dir()
        self._generated_ids: set[str] = set()

    def new_op_id(self) -> str:
        """生成 op_YYYYMMDD_HHMMSS（本地时区）；重复（同秒或已落盘）时追加 -NN 序号保证唯一。"""
        ids = {op["op_id"] for op in self.list_ops()} | self._generated_ids
        base = datetime.now().astimezone().strftime("op_%Y%m%d_%H%M%S")
        op_id = base
        n = 1
        while op_id in ids:
            n += 1
            op_id = f"{base}-{n:02d}"
        self._generated_ids.add(op_id)
        return op_id

    def path_for(self, op_id: str) -> Path:
        return self.directory / f"{op_id}.json"

    def write_op(self, op: dict) -> Path:
        """写入一份操作日志（整体覆盖）。

        先写临时文件再 replace，保证不会留下半截 JSON。
        写失败抛 OSError，由调用方决定中止（engine 据此保证可撤销性）。
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(op["op_id"])
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(op, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def list_ops(self) -> list[dict]:
        """读取全部日志，按 op_id 降序（新 → 旧）；损坏文件跳过不抛错。"""
        ops: list[dict] = []
        if not self.directory.exists():
            return ops
        for path in self.directory.glob("op_*.json"):
            try:
                op = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(op, dict) and "op_id" in op:
                ops.append(op)
        ops.sort(key=lambda o: o["op_id"], reverse=True)
        return ops

    def applied_ops(self) -> list[dict]:
        """未撤销的全部操作，新 → 旧。"""
        return [op for op in self.list_ops() if not op.get("undone")]

    def undoable_ops(self) -> list[dict]:
        """可撤销窗口内的操作（最近 MAX_UNDOABLE 份 applied），新 → 旧。"""
        return self.applied_ops()[: self.MAX_UNDOABLE]

    def is_undoable(self, op: dict) -> bool:
        """该操作当前是否仍在可撤销窗口内。"""
        return any(o["op_id"] == op["op_id"] for o in self.undoable_ops())
