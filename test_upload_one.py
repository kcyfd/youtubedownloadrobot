# -*- coding: utf-8 -*-
"""
单独测试上传一个视频到抖音是否成功。
用法：
  python test_upload_one.py                    # 使用 youtube_downloads 下第一个有 .info.json 的 mp4
  python test_upload_one.py  <视频路径或文件名>  # 指定视频
"""
import asyncio
import sys
from pathlib import Path

from conf import BASE_DIR
from uploaddy import get_title_and_tags_from_info_json
from uploader.douyin_uploader.main import DouYinVideo, douyin_setup


def main():
    video_dir = Path(BASE_DIR) / "youtube_downloads"
    account_file = Path(BASE_DIR) / "cookies" / "douyin_uploader" / "account.json"

    if not account_file.exists():
        print(f"账号文件不存在: {account_file}")
        return 1

    # 确定要测试的视频
    if len(sys.argv) >= 2:
        arg = Path(sys.argv[1])
        if arg.is_absolute():
            file_path = arg
        else:
            file_path = (video_dir / arg).resolve()
        if not file_path.exists():
            print(f"文件不存在: {file_path}")
            return 1
        if file_path.suffix.lower() != ".mp4":
            print("请指定 .mp4 文件")
            return 1
    else:
        all_mp4 = sorted(video_dir.glob("*.mp4"))
        file_path = None
        for f in all_mp4:
            if f.with_suffix(".info.json").exists():
                file_path = f
                break
        if file_path is None:
            print(f"在 {video_dir} 下未找到带 .info.json 的 mp4 视频")
            return 1

    info_result = get_title_and_tags_from_info_json(file_path)
    if info_result is None:
        print(f"缺少或无效的同名 .info.json: {file_path.name}")
        return 1
    title, tags = info_result

    print(f"测试视频: {file_path.name}")
    print(f"标题: {title}")
    print(f"话题数: {len(tags)}")
    print("正在检查登录状态...")
    ok = asyncio.run(douyin_setup(str(account_file), handle=True, check_cookie=True))
    if not ok:
        print("Cookie 无效或未登录，请先完成登录。")
        return 1

    print("开始上传...")
    app = DouYinVideo(title, file_path, tags, 0, str(account_file))
    try:
        success = asyncio.run(app.main())
    except Exception as e:
        print(f"上传异常: {e}")
        return 1

    if success:
        print("\n>>> 上传成功")
        return 0
    print("\n>>> 上传失败（未写入已上传记录，可重试）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
