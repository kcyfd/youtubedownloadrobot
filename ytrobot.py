import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
import logging
from logging.handlers import TimedRotatingFileHandler

def _load_config_early():
    """在 import 前仅读取 config.json 中的 proxy，用于设置 SOCKS5。"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('proxy')
    except Exception:
        return None

# 保存原始 socket，供 OAuth 时临时恢复直连（避免 SOCKS5 导致 token 请求失败）
_original_socket = None
_socks_socket = None

# 在导入会发起网络请求的库之前设置 SOCKS5，否则 Google API 不会走代理
def _install_socks5_proxy(proxy_url):
    global _original_socket, _socks_socket
    if not proxy_url or not str(proxy_url).strip().lower().startswith('socks5://'):
        return
    try:
        from urllib.parse import urlparse
        import socks
        p = urlparse(str(proxy_url).strip())
        host = p.hostname or '127.0.0.1'
        port = p.port or 1080
        socks.set_default_proxy(socks.SOCKS5, host, port)
        import socket
        _original_socket = socket.socket
        _socks_socket = socks.socksocket
        socket.socket = socks.socksocket
    except ImportError:
        print("使用 SOCKS5 代理需要安装 PySocks，请执行：pip install PySocks")
        sys.exit(1)
    except Exception as e:
        print(f"警告：SOCKS5 代理设置失败（{e}）")

_install_socks5_proxy(_load_config_early())

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp

# 程序内写死
JS_RUNTIMES = 'node'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(SCRIPT_DIR, 'client_secret.json')
TOKEN_FILE = os.path.join(SCRIPT_DIR, 'token.json')
YOUTUBE_TOKENS_FILE = os.path.join(SCRIPT_DIR, 'youtube_tokens.json')  # gettoken.py 生成
DOWNLOADED_IDS_FILE = os.path.join(SCRIPT_DIR, 'downloaded_videos.json')
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
# 从订阅频道中取最近视频时：最多取多少订阅、每频道取多少条
MAX_SUBSCRIPTIONS = 30
VIDEOS_PER_CHANNEL = 5
# 只下载小于此大小的视频（字节），默认 1GB
MAX_VIDEO_SIZE_BYTES = 1024 ** 3


LOGGER = logging.getLogger("ytrobot")


def configure_logging(log_file=None):
    """配置日志：输出到控制台和滚动日志文件。"""
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.INFO)
    if log_file is None:
        logs_dir = os.path.join(SCRIPT_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, "ytrobot.log")
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 每天生成一个新的日志文件，保留最近 7 天
    file_handler = TimedRotatingFileHandler(
        log_file,
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

def apply_proxy(proxy_url):
    """设置环境变量（仅对部分库有效；SOCKS5 已在上方通过 socket 生效）"""
    if proxy_url and not (proxy_url.strip().lower().startswith('socks5://')):
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['HTTPS_PROXY'] = proxy_url

def check_proxy_connectivity(proxy_url, test_host='www.google.com', test_port=443, timeout=10):
    """检查通过代理能否连上外网（仅 SOCKS5）。返回 True=可用，False=不可用。"""
    if not proxy_url or not proxy_url.strip().lower().startswith('socks5://'):
        return True
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((test_host, test_port))
        s.close()
        print("代理连接正常")
        return True
    except OSError as e:
        err = str(e)
        if '10061' in err or 'Connection refused' in err or 'ConnectionRefusedError' in err:
            print("代理连接失败：本机无法连上代理端口（连接被拒绝）")
            print("  → 请确认代理软件已启动，且 SOCKS5 端口为 10809。")
        elif '10060' in err or 'timed out' in err.lower():
            print("代理连接超时：能连上代理但无法访问外网，或代理未响应。")
            print("  → 请确认代理软件里已开启「系统代理」或对应 SOCKS5 端口，且规则允许访问 Google。")
        else:
            print(f"代理连接异常：{e}")
        return False

def _credentials_from_youtube_tokens():
    """从 gettoken.py 生成的 youtube_tokens.json + client_secret.json 构建 Credentials。"""
    from google.oauth2.credentials import Credentials
    if not os.path.isfile(YOUTUBE_TOKENS_FILE):
        return None
    try:
        with open(YOUTUBE_TOKENS_FILE, 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        with open(CLIENT_SECRET_FILE, 'r', encoding='utf-8') as f:
            client_data = json.load(f)
        client_config = client_data.get('installed') or client_data.get('web')
        if not client_config:
            return None
        info = {
            'token': tokens.get('access_token'),
            'refresh_token': tokens.get('refresh_token'),
            'token_uri': client_config['token_uri'],
            'client_id': client_config['client_id'],
            'client_secret': client_config['client_secret'],
        }
        return Credentials.from_authorized_user_info(info, SCOPES)
    except Exception:
        return None

def get_oauth_credentials(client_secret_path=CLIENT_SECRET_FILE, token_path=TOKEN_FILE):
    """使用 token.json 或 gettoken 生成的 youtube_tokens.json 完成授权，返回 credentials。"""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    creds = None
    proxy_env_keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
    if os.path.isfile(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            pass
    if not creds and os.path.isfile(YOUTUBE_TOKENS_FILE):
        creds = _credentials_from_youtube_tokens()
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # 刷新 token 时暂时禁用代理（环境变量 + SOCKS5），直连 Google 避免 RemoteDisconnected
            saved_env = {k: os.environ.get(k) for k in proxy_env_keys if k in os.environ}
            for k in proxy_env_keys:
                os.environ.pop(k, None)
            import socket as _socket_mod
            if _socks_socket is not None:
                _socket_mod.socket = _original_socket
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
            finally:
                if _socks_socket is not None:
                    _socket_mod.socket = _socks_socket
                for k, v in saved_env.items():
                    if v is not None:
                        os.environ[k] = v
        if not creds:
            if not os.path.isfile(client_secret_path):
                print(f'未找到 {client_secret_path}，请从 Google Cloud 控制台下载 OAuth 客户端密钥。')
                return None
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            # 首次授权时临时移除代理（环境变量 + SOCKS5），直连 Google 避免 RemoteDisconnected
            saved_env = {k: os.environ.get(k) for k in proxy_env_keys if k in os.environ}
            for k in proxy_env_keys:
                os.environ.pop(k, None)
            import socket as _socket_mod
            if _socks_socket is not None:
                _socket_mod.socket = _original_socket
            try:
                from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
            except ImportError:
                MismatchingStateError = None
            try:
                # 固定端口 8080，避免多次运行导致回调 state 混乱；若端口被占用请关闭其他 ytrobot 窗口
                # 若授权页提示 redirect_uri 不匹配，请在 Google 控制台为该 OAuth 客户端添加：http://localhost:8080/
                creds = flow.run_local_server(port=8080)
            except OSError as e:
                if "address already in use" in str(e).lower() or "10048" in str(e):
                    print("本机 8080 端口已被占用，请关闭其他正在运行的 ytrobot 窗口后再试。")
                raise
            except Exception as e:
                if MismatchingStateError and type(e) is MismatchingStateError:
                    print("授权 state 不匹配。请只运行一次本脚本，在浏览器中只打开一次授权页并完成登录，不要刷新或重复打开链接。然后重新执行：python ytrobot.py")
                    return None
                raise
            finally:
                if _socks_socket is not None:
                    _socket_mod.socket = _socks_socket
                for k, v in saved_env.items():
                    if v is not None:
                        os.environ[k] = v
        with open(token_path, 'w', encoding='utf-8') as f:
            f.write(creds.to_json())
    return creds

def get_youtube_service_oauth(credentials, timeout=60):
    """用 OAuth credentials 创建 YouTube 服务（用于读订阅等需登录的接口）"""
    try:
        import socket
        socket.setdefaulttimeout(timeout)
        return build('youtube', 'v3', credentials=credentials)
    except Exception as e:
        print(f"创建 API 服务失败：{e}")
        return None


def load_downloaded_ids(path=DOWNLOADED_IDS_FILE):
    """从本地 JSON 文件加载已下载视频 ID 集合（新格式：对象数组，仅取其中的 id 字段）。"""
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return set()

    ids = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                vid = item.get('id')
                if vid:
                    ids.add(str(vid))
            elif isinstance(item, str):
                # 如果你手动写了字符串 ID，也一并考虑
                ids.add(item)
    return ids


def append_download_record(video_info, path=DOWNLOADED_IDS_FILE, filename=None):
    """为单个已下载视频追加一条记录到 JSON 文件。

    记录格式：
    {
      "id": "视频ID",
      "title": "标题",
      "view_count": 12345,
      "downloaded_at": "ISO 时间",
      "filename": "本地保存的文件名"
    }
    """
    records = []
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                records = data
        except Exception:
            records = []

    rec = {
        'id': str(video_info.get('id', '')),
        'title': video_info.get('title', ''),
        'view_count': video_info.get('view_count'),
        'downloaded_at': datetime.now(timezone.utc).isoformat(),
        'filename': filename if filename else '',
    }
    records.append(rec)

    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        LOGGER.error("保存下载记录失败：%s", e)

def get_most_viewed_from_subscriptions(youtube, days=7, excluded_ids=None):
    """从当前账户的订阅频道中，为每个频道找出：
    1）最近 N 天内播放量最高的视频；
    2）总播放量最高的视频（限于抓取到的最近 VIDEOS_PER_CHANNEL 条）。

    返回一个待下载的视频信息列表，每个元素是 dict：
    {id, url, title, view_count, published_at, channel_id, channel_title}

    :param youtube: 已授权的 YouTube API 客户端
    :param days: 最近多少天内的视频视为「一周内」范围（默认 7 天）
    :param excluded_ids: 需要排除的视频 ID 集合（例如已下载过的）
    """
    try:
        if excluded_ids is None:
            excluded_ids = set()
        else:
            excluded_ids = set(str(x) for x in excluded_ids)
        now = datetime.now(timezone.utc)
        since_time = now - timedelta(days=days)

        # 1. 我的订阅列表 -> 频道 ID & 名称
        sub_res = youtube.subscriptions().list(
            part='snippet',
            mine=True,
            maxResults=MAX_SUBSCRIPTIONS,
            order='relevance'
        ).execute()
        items = sub_res.get('items') or []
        if not items:
            LOGGER.info("未找到订阅的频道，请先在 YouTube 订阅一些频道。")
            return []
        channel_ids = []
        channel_titles = {}
        for it in items:
            snippet = it.get('snippet', {}) or {}
            cid = snippet.get('resourceId', {}).get('channelId')
            if not cid:
                continue
            channel_ids.append(cid)
            channel_titles[cid] = snippet.get('title') or cid

        if not channel_ids:
            LOGGER.info("未找到有效的订阅频道。")
            return []

        # 2. 各频道的「上传」播放列表 ID
        channels_res = youtube.channels().list(
            id=','.join(channel_ids),
            part='contentDetails'
        ).execute()
        upload_playlists = {}  # channel_id -> uploads playlist id
        for ch in channels_res.get('items') or []:
            cid = ch.get('id')
            upl = ch.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
            if cid and upl:
                upload_playlists[cid] = upl
        if not upload_playlists:
            LOGGER.info("无法获取订阅频道的上传列表。")
            return []

        # 3. 每个播放列表取最近几条视频 ID，并建立 video -> channel 映射
        channel_video_ids = {}  # channel_id -> [video_id]
        video_to_channel = {}   # video_id -> channel_id
        for cid, pl_id in upload_playlists.items():
            pl_res = youtube.playlistItems().list(
                playlistId=pl_id,
                part='contentDetails',
                maxResults=VIDEOS_PER_CHANNEL
            ).execute()
            for it in pl_res.get('items') or []:
                vid = it.get('contentDetails', {}).get('videoId')
                if vid:
                    channel_video_ids.setdefault(cid, []).append(vid)
                    video_to_channel[vid] = cid

        if not video_to_channel:
            LOGGER.info("订阅频道下暂无视频。")
            return []

        all_video_ids = list(video_to_channel.keys())

        # 4. 批量取视频详情，为每个频道计算「一周内最高」和「总播放最高」
        per_channel = {}  # channel_id -> {'weekly_best': {...}, 'all_time_best': {...}}
        for i in range(0, len(all_video_ids), 50):
            batch = all_video_ids[i:i + 50]
            vid_res = youtube.videos().list(
                id=','.join(batch),
                part='statistics,snippet'
            ).execute()
            for it in vid_res.get('items') or []:
                vid = it.get('id')
                if not vid or vid in excluded_ids:
                    continue
                cid = video_to_channel.get(vid)
                if not cid:
                    continue
                snippet = it.get('snippet', {}) or {}
                stats = it.get('statistics', {}) or {}
                published_at = snippet.get('publishedAt')
                try:
                    published_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00')) if published_at else None
                except Exception:
                    published_dt = None
                try:
                    view_count = int(stats.get('viewCount', 0))
                except Exception:
                    view_count = 0

                info = {
                    'id': vid,
                    'url': f"https://www.youtube.com/watch?v={vid}",
                    'title': snippet.get('title', ''),
                    'view_count': view_count,
                    'published_at': published_at,
                    'channel_id': cid,
                    'channel_title': channel_titles.get(cid, cid),
                }
                ch_info = per_channel.setdefault(cid, {'weekly_best': None, 'all_time_best': None})

                # 总播放最高（不限制时间）
                if ch_info['all_time_best'] is None or view_count > ch_info['all_time_best']['view_count']:
                    ch_info['all_time_best'] = info

                # 一周内最高（仅在时间范围内才参与）
                if published_dt and published_dt >= since_time:
                    if ch_info['weekly_best'] is None or view_count > ch_info['weekly_best']['view_count']:
                        ch_info['weekly_best'] = info

        # 5. 组装最终需要下载的列表：每频道最多 2 条（去重）
        downloads = []
        added_ids = set()
        for cid, ch_info in per_channel.items():
            ch_title = channel_titles.get(cid, cid)
            for label, v in (
                (f"最近 {days} 天内播放量最高", ch_info.get('weekly_best')),
                ("总播放量最高（最近抓取的视频中）", ch_info.get('all_time_best')),
            ):
                if not v:
                    continue
                vid = v['id']
                if not vid or vid in excluded_ids or vid in added_ids:
                    continue
                downloads.append(v)
                added_ids.add(vid)
                LOGGER.info("频道：%s", ch_title)
                LOGGER.info("类型：%s", label)
                LOGGER.info("标题：%s", v['title'])
                LOGGER.info("播放量：%s 次", f"{int(v['view_count']):,}")
                LOGGER.info("链接：%s", v['url'])

        if not downloads:
            LOGGER.info("没有需要下载的频道视频（可能都已下载过或不在时间范围内）。")

        return downloads
    except HttpError as e:
        LOGGER.error("获取订阅列表失败（HTTP）：%s", e)
        return []
    except Exception as e:
        LOGGER.error("获取订阅列表失败：%s", e)
        return []

def _to_simplified(s):
    """繁体转简体。未安装 zhconv 时返回原文。"""
    try:
        import zhconv
        return zhconv.convert(s or "", "zh-cn")
    except ImportError:
        return s or ""


def _write_info_json(path_stem, info, output_dir):
    """生成与视频同名的 .info.json，写入标题、标签等。"""
    data = {
        'title': info.get('title'),
        'tags': info.get('tags') or [],
    }
    info_path = os.path.join(output_dir, path_stem + '.info.json')
    try:
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        LOGGER.warning("写入 info.json 失败：%s", e)


def download_video(video_url, output_dir='./youtube_downloads', proxy_url=None, cookies_from_browser=None):
    """用 yt-dlp 下载视频（不指定 format，由 yt-dlp 自动选最高画质）。
    标题繁体转简体（用于文件名和 info.json），并生成同名 .info.json。
    成功时返回 (True, 实际保存的文件名)，失败时返回 (False, None)。
    """
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'js_runtimes': {JS_RUNTIMES: {}},
    }
    if proxy_url:
        ydl_opts['proxy'] = proxy_url
    if cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser.strip().lower(),)

    try:
        LOGGER.info("开始下载：%s", video_url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        if not info:
            LOGGER.error("下载失败：无法获取视频信息")
            return False, None
        # 只下载小于 1GB 的视频（yt-dlp 可能返回 filesize 或 filesize_approx）
        size = info.get('filesize') or info.get('filesize_approx')
        if size is not None and size > MAX_VIDEO_SIZE_BYTES:
            LOGGER.info("跳过（体积 %.1f MB > %d MB）：%s", size / (1024 * 1024), MAX_VIDEO_SIZE_BYTES // (1024 * 1024), info.get('title', video_url))
            return False, None
        orig_title = info.get('title') or ''
        info['title'] = _to_simplified(orig_title)
        if info['title'] != orig_title:
            LOGGER.info("标题已转为简体：%s", info['title'])
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.process_ie_result(info, download=True)
            filepath = ydl.prepare_filename(info)
        if not os.path.isfile(filepath):
            filepath = re.sub(r'\.webm$', '.mp4', filepath)
        if not os.path.isfile(filepath):
            LOGGER.warning("未找到输出文件：%s", filepath)
            stem = os.path.splitext(os.path.basename(filepath))[0]
            _write_info_json(stem, info, output_dir)
            return False, None
        base = os.path.splitext(os.path.basename(filepath))[0]
        _write_info_json(base, info, output_dir)
        filename = os.path.basename(filepath)
        LOGGER.info("下载完成，文件保存至：%s", output_dir)
        return True, filename
    except Exception as e:
        LOGGER.error("下载失败：%s", e)
        return False, None

def load_config(config_path=None):
    """从 JSON 配置文件加载参数。返回 dict：proxy、cookies_from_browser。"""
    if config_path is None:
        config_path = os.path.join(SCRIPT_DIR, 'config.json')
    if not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            'proxy': data.get('proxy'),
            'cookies_from_browser': data.get('cookies_from_browser') or data.get('cookies-from-browser'),
        }
    except Exception as e:
        LOGGER.error("读取配置文件失败（%s）：%s", config_path, e)
        return {}

if __name__ == '__main__':
    configure_logging()
    LOGGER.info("==== ytrobot 启动 ====")

    config = load_config()
    apply_proxy(config.get('proxy'))
    if config.get('proxy') and not check_proxy_connectivity(config.get('proxy')):
        exit(1)

    creds = get_oauth_credentials()
    if not creds:
        exit(1)
    youtube_service = get_youtube_service_oauth(creds)
    if not youtube_service:
        exit(1)

    downloaded_ids = load_downloaded_ids()
    videos_to_download = get_most_viewed_from_subscriptions(
        youtube_service,
        days=7,
        excluded_ids=downloaded_ids
    )
    if not videos_to_download:
        # 已在函数内部打印原因，例如没有新视频或请求失败
        exit(0)

    for v in videos_to_download:
        video_id = v.get('id')
        if video_id and video_id in downloaded_ids:
            # 双重保险：正常情况下在函数中已排除
            print(f"该视频已记录为已下载，跳过：{v.get('title', '')} ({video_id})")
            continue
        ok, filename = download_video(
            v['url'],
            proxy_url=config.get('proxy'),
            cookies_from_browser=config.get('cookies_from_browser')
        )
        if ok and video_id:
            # 仅下载成功时才记录，失败的不写入，下次运行可重试
            vid_str = str(video_id)
            downloaded_ids.add(vid_str)
            append_download_record(v, path=DOWNLOADED_IDS_FILE, filename=filename)