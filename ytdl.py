"""简单的 YouTube 视频下载脚本：传入 URL，下载为 mp4；文件名繁体转简体，并生成同名 .info.json（含标题、标签）。"""
import os
import sys
import json
import re

def _to_simplified(s):
    """繁体转简体。未安装 zhconv 时返回原文。"""
    try:
        import zhconv
        return zhconv.convert(s or "", "zh-cn")
    except ImportError:
        return s or ""

# 复用 ytrobot 的代理预置（在 import yt_dlp 前）
def _load_config_early():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('proxy')
    except Exception:
        return None

def _install_socks5_proxy(proxy_url):
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
        socket.socket = socks.socksocket
    except ImportError:
        print("使用 SOCKS5 代理需要安装 PySocks：pip install PySocks")
        sys.exit(1)
    except Exception as e:
        print(f"警告：SOCKS5 代理设置失败（{e}）")

_install_socks5_proxy(_load_config_early())

import yt_dlp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'youtube_downloads')


def load_config():
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
    except Exception:
        return {}


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
        print(f"写入 info.json 失败: {e}")


def download(url, output_dir=OUTPUT_DIR, proxy_url=None, cookies_from_browser=None):
    """下载 YouTube 视频，保存为 mp4；标题繁体转简体（用于文件名和 info.json），并生成同名 .info.json。"""
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',  # 合并音视频时输出为 MP4
        'js_runtimes': {'node': {}},
    }
    if proxy_url:
        ydl_opts['proxy'] = proxy_url
    if cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_from_browser.strip().lower(),)

    try:
        print(f"正在下载: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            print("下载失败: 无法获取视频信息")
            return False
        # 标题繁体转简体，使文件名和 info.json 均使用简体
        orig_title = info.get('title') or ''
        info['title'] = _to_simplified(orig_title)
        if info['title'] != orig_title:
            print(f"标题已转为简体: {info['title']}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.process_ie_result(info, download=True)
            filepath = ydl.prepare_filename(info)
        if not os.path.isfile(filepath):
            filepath = re.sub(r'\.webm$', '.mp4', filepath)
        if not os.path.isfile(filepath):
            print(f"警告: 未找到输出文件 {filepath}")
            stem = os.path.splitext(os.path.basename(filepath))[0]
            _write_info_json(stem, info, output_dir)
            return False
        base = os.path.splitext(os.path.basename(filepath))[0]
        print(f"下载完成: {filepath}")
        _write_info_json(base, info, output_dir)
        return True
    except Exception as e:
        print(f"下载失败: {e}")
    return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python ytdl.py <youtube_url>")
        print("示例: python ytdl.py https://www.youtube.com/watch?v=xxxxx")
        sys.exit(1)

    url = sys.argv[1].strip()
    if not url:
        print("请提供有效的 YouTube URL")
        sys.exit(1)

    config = load_config()
    if config.get('proxy') and not config['proxy'].strip().lower().startswith('socks5://'):
        os.environ['HTTP_PROXY'] = config['proxy']
        os.environ['HTTPS_PROXY'] = config['proxy']

    ok = download(url, proxy_url=config.get('proxy'), cookies_from_browser=config.get('cookies_from_browser'))
    sys.exit(0 if ok else 1)
