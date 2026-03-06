# -*- coding: utf-8 -*-
"""
简单邮件发送测试脚本。

使用前请先在 conf.py 中正确配置：
- EMAIL_NOTIFY_ENABLED = True
- EMAIL_SMTP_HOST / EMAIL_SMTP_PORT / EMAIL_USE_TLS
- EMAIL_USERNAME / EMAIL_PASSWORD / EMAIL_FROM / EMAIL_TO

运行示例：
    python test_email.py
    python test_email.py "自定义主题" "自定义正文"
"""
import sys

from uploaddy import configure_logging  # 复用上传脚本的日志配置
from uploaddy import _send_email       # 复用内部发送函数


def main():
    configure_logging()

    if len(sys.argv) >= 2:
        subject = sys.argv[1]
    else:
        subject = "uploaddy 邮件发送测试"

    if len(sys.argv) >= 3:
        body = sys.argv[2]
    else:
        body = "这是一封来自 test_email.py 的测试邮件。\n如果你看到这封邮件，说明邮件配置正常工作。"

    ok = _send_email(subject, body)
    if ok:
        print("邮件发送成功。")
    else:
        print("邮件发送失败，请检查日志输出与 conf.py 配置。")


if __name__ == "__main__":
    main()

