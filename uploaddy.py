# -*- coding: utf-8 -*-
"""
自动上传抖音视频：只上传未记录的视频，上传成功后写入记录，下次不再重复上传。

本版本基于 social-auto-upload 项目的 uploaddy.py，
并适配为直接读取本项目 `youtube_downloads` 目录下的 mp4 和同名 .info.json。
"""
import asyncio
import json
import logging
import random
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta

from conf import BASE_DIR
from uploader.douyin_uploader.main import douyin_setup, DouYinVideo


LOGGER = logging.getLogger("uploaddy")


def configure_logging(log_file=None):
    """配置日志：输出到控制台和滚动日志文件。"""
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.INFO)
    if log_file is None:
        logs_dir = Path(BASE_DIR) / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "uploaddy.log"
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(console_handler)
    LOGGER.propagate = False


# 已上传记录文件（存绝对路径，避免重复上传）
RECORD_DIR = Path(BASE_DIR) / "data"
RECORD_FILE = RECORD_DIR / "douyin_uploaded.json"

# 上传间隔随机范围（小时）
INTERVAL_MIN_HOURS = 0.5
INTERVAL_MAX_HOURS = 8.0


def load_douyin_config():
    """从 config.json 读取抖音上传相关配置。"""
    config_path = Path(BASE_DIR) / "config.json"
    default_max_per_24h = 10
    if not config_path.exists():
        return {"douyin_max_uploads_per_24h": default_max_per_24h}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        max_per_24h = data.get("douyin_max_uploads_per_24h", default_max_per_24h)
        if not isinstance(max_per_24h, int) or max_per_24h < 1:
            max_per_24h = default_max_per_24h
        return {"douyin_max_uploads_per_24h": max_per_24h}
    except (json.JSONDecodeError, IOError, TypeError):
        return {"douyin_max_uploads_per_24h": default_max_per_24h}


def load_uploaded_records():
    """加载完整上传记录列表。"""
    if not RECORD_FILE.exists():
        return []
    try:
        with open(RECORD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    if not isinstance(data, list):
        return []
    if not data:
        return []
    if isinstance(data[0], dict):
        return data
    records = []
    for path in data:
        if path:
            records.append({"path": path, "uploaded_at": None})
    return records


def load_uploaded_set():
    """加载已上传记录，返回「已上传绝对路径」集合。"""
    records = load_uploaded_records()
    return {item["path"] for item in records if item.get("path")}


def _parse_uploaded_at(record):
    ts = record.get("uploaded_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _count_uploads_in_last_24h(records, ref_time: datetime) -> int:
    cutoff = ref_time - timedelta(hours=24)
    count = 0
    for rec in records:
        t = _parse_uploaded_at(rec)
        if t and t >= cutoff:
            count += 1
    return count


def _get_last_upload_time(records):
    times = []
    for rec in records:
        t = _parse_uploaded_at(rec)
        if t:
            times.append(t)
    if not times:
        return None
    return max(times)


def get_title_and_tags_from_info_json(video_path: Path):
    """
    从与视频同名的 .info.json 读取 title 和 tags。
    格式示例：{"title": "...", "tags": ["A", "B", "C"]}
    返回 (title, tags) 或 None（文件不存在或格式错误）。
    """
    info_path = video_path.with_suffix(".info.json")
    if not info_path.exists():
        return None
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        title = data.get("title") or ""
        tags_raw = data.get("tags")
        if tags_raw is None:
            tags = []
        elif isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags = []
        return title, tags
    except (json.JSONDecodeError, IOError, TypeError):
        return None


def save_uploaded_record(path: str, uploaded_at: datetime | None = None):
    """追加一条上传成功记录并写回文件。"""
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    if RECORD_FILE.exists():
        try:
            with open(RECORD_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, IOError):
            records = []
    if not isinstance(records, list):
        records = []
    uploaded_time = uploaded_at or datetime.now()
    records.append(
        {
            "path": path,
            "uploaded_at": uploaded_time.isoformat(),
        }
    )
    with open(RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def main():
    configure_logging()

    # 与 ytrobot / ytdl 统一：直接使用 youtube_downloads 目录
    video_dir = Path(BASE_DIR) / "youtube_downloads"
    account_file = Path(BASE_DIR) / "cookies" / "douyin_uploader" / "account.json"

    if not account_file.exists():
        LOGGER.error("账号文件不存在: %s", account_file)
        return

    uploaded_records = load_uploaded_records()
    uploaded_set = {item["path"] for item in uploaded_records if item.get("path")}
    all_mp4 = sorted(video_dir.glob("*.mp4"))
    to_upload = [f for f in all_mp4 if str(f.resolve()) not in uploaded_set]

    if not to_upload:
        LOGGER.info("没有需要上传的新视频（已记录的都视为已上传）。")
        return

    douyin_config = load_douyin_config()
    max_uploads_per_24h = douyin_config["douyin_max_uploads_per_24h"]

    # 启动时先检查 24 小时上传配额
    now = datetime.now()
    uploads_24h = _count_uploads_in_last_24h(uploaded_records, now)
    if uploads_24h >= max_uploads_per_24h:
        LOGGER.info(
            "过去24小时内已上传 %s 个视频，已达到上限 %s 个，本次不再上传。",
            uploads_24h,
            max_uploads_per_24h,
        )
        return

    LOGGER.info(
        "共 %s 个视频，已上传 %s 个，本次待上传 %s 个。",
        len(all_mp4),
        len(uploaded_set),
        len(to_upload),
    )
    LOGGER.info(
        "24 小时上限：%s 个，上传间隔：%s～%s 小时随机。",
        max_uploads_per_24h,
        INTERVAL_MIN_HOURS,
        INTERVAL_MAX_HOURS,
    )

    # handle=True：若 cookie 不存在或失效，将自动打开浏览器让你登录一次
    ok = asyncio.run(douyin_setup(str(account_file), handle=True))
    if not ok:
        LOGGER.error("Cookie 无效或未登录，请先运行登录流程。")
        return

    # 0 表示立即发布，不设置定时
    for file_path in to_upload:
        # 每个视频前检查 24 小时配额与随机间隔（0.5～8 小时）
        while True:
            now = datetime.now()
            uploads_24h = _count_uploads_in_last_24h(uploaded_records, now)
            if uploads_24h >= max_uploads_per_24h:
                LOGGER.info(
                    "过去24小时内已上传 %s 个视频，已达到上限 %s 个，停止本次上传。",
                    uploads_24h,
                    max_uploads_per_24h,
                )
                return

            last_time = _get_last_upload_time(uploaded_records)
            if last_time is not None:
                interval_hours = random.uniform(INTERVAL_MIN_HOURS, INTERVAL_MAX_HOURS)
                min_next_time = last_time + timedelta(hours=interval_hours)
                if now < min_next_time:
                    wait_seconds = (min_next_time - now).total_seconds()
                    wait_hours = wait_seconds / 3600
                    LOGGER.info(
                        "距上次上传未满 %.1f 小时，将等待约 %.1f 小时后再上传下一个视频...",
                        interval_hours,
                        wait_hours,
                    )
                    time.sleep(wait_seconds)
                    continue
            break

        abs_path = str(file_path.resolve())
        info_result = get_title_and_tags_from_info_json(file_path)
        if info_result is None:
            LOGGER.warning("跳过（缺少或无效的同名 .info.json）：%s", file_path.name)
            continue
        title, tags = info_result

        LOGGER.info("视频：%s", file_path.name)
        LOGGER.info("    标题：%s", title)
        LOGGER.info("    Hashtag：%s", tags)

        app = DouYinVideo(title, file_path, tags, 0, account_file)
        try:
            asyncio.run(app.main())
        except Exception as e:
            LOGGER.error("上传失败 %s: %s", file_path.name, e)
            # 上传失败不写入记录，下次运行会重试该视频
            continue

        # 仅在上传成功时记录，避免失败视频被误判为已上传
        now = datetime.now()
        save_uploaded_record(abs_path, uploaded_at=now)
        uploaded_records.append({"path": abs_path, "uploaded_at": now.isoformat()})
        LOGGER.info("已记录，下次将不再上传：%s", file_path.name)

    LOGGER.info("本次上传流程结束。")


if __name__ == "__main__":
    main()

