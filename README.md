# ytrobot — 订阅频道热门视频自动下载

从你的 YouTube 订阅频道中，按「最近 7 天播放量最高」和「总播放量最高」筛选视频，并用 yt-dlp 自动下载，避免重复下载。

## 功能概览

- **OAuth 登录**：使用 Google OAuth 读取你的订阅列表（只读权限）
- **智能筛选**：对每个订阅频道取最近若干条视频，选出「一周内播放最高」和「总播放最高」各一条
- **自动下载**：用 yt-dlp 下载，标题可转为简体，并生成同名 `.info.json`
- **去重记录**：已下载视频写入 `downloaded_videos.json`，下次运行自动跳过
- **代理支持**：支持 SOCKS5（需 PySocks）及 HTTP/HTTPS 代理；OAuth 刷新/首次授权时会临时直连 Google

## 环境要求

- Python 3.7+（本项目实际在 Anaconda 创建的 Python 3.12 虚拟环境中测试通过）
- Node.js（用于 yt-dlp 的 `js_runtimes=node`，未安装时通常也能正常工作）

## 安装依赖

```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 yt-dlp
```

使用 SOCKS5 代理时还需：

```bash
pip install PySocks
```

可选（标题繁体转简体）：

```bash
pip install zhconv
```

## 配置

### 1. Google OAuth 客户端

1. 打开 [Google Cloud 控制台](https://console.cloud.google.com/)
2. 创建或选择项目 → 启用 **YouTube Data API v3**
3. 凭据 → 创建凭据 → OAuth 2.0 客户端 ID → 应用类型选「桌面应用」
4. 下载 JSON，重命名为 `client_secret.json`，放在脚本同目录

### 2. 首次授权

首次运行会打开浏览器，用你的 Google 账号登录并授权。授权完成后会生成 `token.json`


### 3. config.json

在脚本同目录创建 `config.json`，例如：

```json
{
  "proxy": "socks5://127.0.0.1:10809",
  "cookies_from_browser": "firefox"
}
```

- **proxy**：代理地址。`socks5://...` 会在程序启动时通过 PySocks 全局生效；其他类型会设置 `HTTP_PROXY`/`HTTPS_PROXY`（仅对部分库有效）。
- **cookies_from_browser**：从浏览器读取 Cookie 供 yt-dlp 使用，如 `chrome`、`firefox` 等，按 yt-dlp 文档填写。注：运行程序时对应浏览器要关闭，因为cookie会被锁定。所以建议用不常用的如friefoxw做为专门下载视频用。

## 目录与文件说明

| 文件/目录 | 说明 |
|-----------|------|
| `ytrobot.py` | 主程序 |
| `config.json` | 代理、cookies_from_browser 等配置 |
| `client_secret.json` | Google OAuth 客户端密钥（需自行创建） |
| `token.json` | OAuth 令牌（首次授权后生成） |
| `youtube_tokens.json` | 可由 gettoken 等工具生成，与 token.json 二选一 |
| `downloaded_videos.json` | 已下载视频记录（id、标题、播放量、时间、文件名） |
| `youtube_downloads/` | 默认下载目录（可在调用时修改） |
| `ytrobot.log` | 日志（按天滚动，保留 7 天） |

## 运行方式

```bash
python ytrobot.py
```
![自动下载视频流程](./doc/自动下载视频.png)

流程简述：

1. 读取 `config.json`，设置代理并检查连通性（仅 SOCKS5 会做连接测试）
2. 使用 `token.json` 或 `youtube_tokens.json` 获取 OAuth 凭据，必要时刷新或启动本地授权（端口 8080）
3. 拉取订阅列表（最多 `MAX_SUBSCRIPTIONS` 个频道），每个频道取最近 `VIDEOS_PER_CHANNEL` 条视频
4. 为每个频道计算「最近 7 天播放最高」和「总播放最高」，去重后得到待下载列表
5. 跳过已在 `downloaded_videos.json` 中的视频，用 yt-dlp 下载到 `youtube_downloads/`
6. 下载成功后追加一条记录到 `downloaded_videos.json`

## 程序内常量（可改）

在 `ytrobot.py` 顶部可调整：

- `MAX_SUBSCRIPTIONS`：最多使用多少个订阅频道（默认 30）
- `VIDEOS_PER_CHANNEL`：每个频道取最近多少条视频参与筛选（默认 5）

## 常见问题

- **8080 端口被占用**：关闭占用 8080 的其他程序，或只保留一个 ytrobot 运行实例，避免多次授权导致 state 混乱。
- **代理下 OAuth 失败**：程序在刷新 token 和首次授权时会暂时关闭代理直连 Google；若仍失败，可检查本机直连 Google 是否正常。
- **代理连接失败**：确认代理软件已开启，且 `config.json` 中的端口（如 10809）与代理的 SOCKS5 端口一致。
- **下载失败**：可配置 `cookies_from_browser`，或检查 yt-dlp 与 YouTube 的访问策略（如地区、登录状态）。

## 许可证

按项目仓库约定使用。
