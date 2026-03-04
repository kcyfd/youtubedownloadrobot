from pathlib import Path
from sys import stdout

from loguru import logger

from conf import BASE_DIR


def log_formatter(record: dict) -> str:
    colors = {
        "TRACE": "#cfe2f3",
        "INFO": "#9cbfdd",
        "DEBUG": "#8598ea",
        "WARNING": "#dcad5a",
        "SUCCESS": "#3dd08d",
        "ERROR": "#ae2c2c",
    }
    color = colors.get(record["level"].name, "#b3cfe7")
    return (
        f"<fg #70acde>{{time:YYYY-MM-DD HH:mm:ss}}</fg #70acde> | "
        f"<fg {color}>{{level}}</fg {color}>: <light-white>{{message}}</light-white>\n"
    )


def create_logger(log_name: str, file_path: str):
    def filter_record(record):
        return record["extra"].get("business_name") == log_name

    Path(BASE_DIR / file_path).parent.mkdir(exist_ok=True)
    logger.add(
        Path(BASE_DIR / file_path),
        filter=filter_record,
        level="INFO",
        rotation="10 MB",
        retention="10 days",
        backtrace=True,
        diagnose=True,
    )
    return logger.bind(business_name=log_name)


# 控制台输出
logger.remove()
logger.add(stdout, colorize=True, format=log_formatter)

# 各平台独立 logger（目前项目只用到 douyin，保留其余以便扩展）
douyin_logger = create_logger("douyin", "logs/douyin.log")
tencent_logger = create_logger("tencent", "logs/tencent.log")
xhs_logger = create_logger("xhs", "logs/xhs.log")
tiktok_logger = create_logger("tiktok", "logs/tiktok.log")
bilibili_logger = create_logger("bilibili", "logs/bilibili.log")
kuaishou_logger = create_logger("kuaishou", "logs/kuaishou.log")
baijiahao_logger = create_logger("baijiahao", "logs/baijiahao.log")
xiaohongshu_logger = create_logger("xiaohongshu", "logs/xiaohongshu.log")

