from pathlib import Path

from conf import BASE_DIR

# 确保 cookies 目录存在，供各平台上传脚本使用
Path(BASE_DIR / "cookies").mkdir(exist_ok=True)

