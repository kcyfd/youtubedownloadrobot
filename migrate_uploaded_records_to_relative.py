# -*- coding: utf-8 -*-
"""
临时脚本：将 data/douyin_uploaded.json 中的 path 从绝对路径迁移为相对 BASE_DIR 的相对路径。
运行一次即可，完成后可删除本脚本。
"""
import json
from pathlib import Path

from conf import BASE_DIR

RECORD_DIR = Path(BASE_DIR) / "data"
RECORD_FILE = RECORD_DIR / "douyin_uploaded.json"


def path_to_relative(path_str: str) -> str:
    base = Path(BASE_DIR).resolve()
    p = Path(path_str).resolve()
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def main():
    if not RECORD_FILE.exists():
        print(f"记录文件不存在: {RECORD_FILE}")
        return
    with open(RECORD_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)
    if not isinstance(records, list):
        print("记录格式异常，未迁移")
        return
    migrated = []
    for item in records:
        if isinstance(item, dict):
            path = item.get("path") or ""
            uploaded_at = item.get("uploaded_at")
        elif isinstance(item, str) and item:
            path, uploaded_at = item, None
        else:
            continue
        if path and Path(path).is_absolute():
            path = path_to_relative(path)
        migrated.append({"path": path, "uploaded_at": uploaded_at})
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(migrated, f, ensure_ascii=False, indent=2)
    print(f"已迁移 {len(migrated)} 条记录，路径已改为相对路径: {RECORD_FILE}")


if __name__ == "__main__":
    main()
