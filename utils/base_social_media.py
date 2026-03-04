from pathlib import Path
from typing import List

from conf import BASE_DIR

SOCIAL_MEDIA_DOUYIN = "douyin"
SOCIAL_MEDIA_TENCENT = "tencent"
SOCIAL_MEDIA_TIKTOK = "tiktok"
SOCIAL_MEDIA_BILIBILI = "bilibili"
SOCIAL_MEDIA_KUAISHOU = "kuaishou"


def get_supported_social_media() -> List[str]:
    return [SOCIAL_MEDIA_DOUYIN, SOCIAL_MEDIA_TENCENT, SOCIAL_MEDIA_TIKTOK, SOCIAL_MEDIA_KUAISHOU]


def get_cli_action() -> List[str]:
    return ["upload", "login", "watch"]


async def set_init_script(context):
    """
    为 Playwright 上下文设置初始脚本。

    这里保留与原项目相同的接口，但不强制依赖 stealth.min.js，
    仅直接返回 context，后续如需更强的反检测能力，可在 BASE_DIR/utils 下
    放置 stealth.min.js 并调用 context.add_init_script。
    """
    stealth_js_path = Path(BASE_DIR / "utils/stealth.min.js")
    if stealth_js_path.exists():
        await context.add_init_script(path=stealth_js_path)
    return context

