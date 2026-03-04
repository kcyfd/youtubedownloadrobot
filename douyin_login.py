# -*- coding: utf-8 -*-
"""
手动登录抖音创作者中心以生成/更新 cookies：

运行：
    python douyin_login.py

会自动打开浏览器，你在新窗口中扫码或账号密码登录，
登录成功后关闭 Playwright 的调试面板，即可在：
    cookies/douyin_uploader/account.json
生成/更新登录状态。
"""
import asyncio
from pathlib import Path

from conf import BASE_DIR
from uploader.douyin_uploader.main import douyin_setup


def main():
    account_file = Path(BASE_DIR) / "cookies" / "douyin_uploader" / "account.json"
    account_file.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"[*] 将使用浏览器登录抖音创作者中心，生成/更新 cookie 文件：\n"
        f"    {account_file}\n"
    )
    # handle=True 表示在 cookie 不存在或失效时自动打开浏览器登录
    ok = asyncio.run(douyin_setup(str(account_file), handle=True))
    if ok:
        print("[+] 登录流程结束，已生成/更新 account.json。")
    else:
        print("[!] 登录流程未完成或失败，请重试。")


if __name__ == "__main__":
    main()

