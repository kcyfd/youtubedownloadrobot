import json
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.resolve()

# 抖音等上传使用的本地浏览器路径（按需修改）
LOCAL_CHROME_PATH = ""

# 是否无头运行浏览器（True 为无界面，False 为有界面）
LOCAL_CHROME_HEADLESS = False

# 邮件提醒配置从 email_config.json 读取（不存在或缺项时使用下列默认值）
_email_config_path = BASE_DIR / "email_config.json"
_email = {}
if _email_config_path.exists():
    try:
        with open(_email_config_path, "r", encoding="utf-8") as f:
            _email = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

EMAIL_NOTIFY_ENABLED = _email.get("EMAIL_NOTIFY_ENABLED", False)
EMAIL_SMTP_HOST = _email.get("EMAIL_SMTP_HOST", "")
EMAIL_SMTP_PORT = int(_email.get("EMAIL_SMTP_PORT", 0)) or 465
EMAIL_USE_TLS = _email.get("EMAIL_USE_TLS", False)
EMAIL_USERNAME = _email.get("EMAIL_USERNAME", "")
EMAIL_PASSWORD = _email.get("EMAIL_PASSWORD", "")
