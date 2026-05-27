# 🎯 抖音神秘人猎人

**实时监听抖音直播间，抓取"神秘人"真实身份**

神秘人是抖音直播间里隐藏真实昵称的观众/弹幕发送者。本工具自动识别他们的真实身份，并支持 Web 可视化界面实时查看。

## ✨ 功能

- 🎯 **自动识别神秘人** — 实时抓取直播间神秘人的真实昵称
- 🌐 **Web 可视化界面** — 手机浏览器/电脑即可访问，实时查看
- 💬 **弹幕监听** — 直播间弹幕、礼物、进场记录
- 📦 **轻量部署** — 手机 Termux 可跑，或部署到云服务器
- 🔗 **外网访问** — 支持 Serveo 隧道，随时随地查看

## 🚀 快速启动

### 环境要求

- Python 3.7+
- Node.js 18+

### 安装

```bash
pip install -r requirements.txt
npm install
```

### 配置

复制抖音登录后的 cookie 到 `.env` 文件中（需两个 cookie）：

| 变量 | 获取地址 |
|------|---------|
| `DY_COOKIES` | `www.douyin.com` 的登录 cookie |
| `DY_LIVE_COOKIES` | `live.douyin.com` 的登录 cookie |

> 浏览器 F12 → 网络 → 任意请求 → 复制 Cookie 头

### 运行 Web 界面

```bash
python web_listener.py
```

访问 `http://手机IP:5000` 即可打开神秘人猎人面板。

### 命令行监听

```bash
# 监听指定直播间
python hunt_mystery.py <直播间ID>

# 连接直播间 WebSocket
python connect_direct.py <直播间ID>
```

## 🐳 Docker 部署

```bash
docker build -t douyin-mystery-hunter .
docker run -d -p 5000:5000 --env-file .env douyin-mystery-hunter
```

## 🗺️ 项目结构

```
├── web_listener.py       # Flask Web 界面（核心）
├── hunt_mystery.py       # 神秘人识别脚本
├── connect_direct.py     # 直播间直连监听
├── hunt_file.py          # 文件版神秘人识别
├── scan_room_users.py    # 直播间用户扫描
├── utils/                # 工具模块
│   ├── common_util.py    # 通用工具 + cookie 加载
│   ├── dy_util.py        # 抖音签名生成
│   └── cookie_util.py    # cookie 管理
├── builder/              # 抖音 API 构建器
├── static/               # protobuf 定义 + JS 签名
├── dy_live/              # 直播间 WebSocket
└── Dockerfile            # 容器部署配置
```

## 📝 说明

- 本项目基于 [Douyin_Spider](https://github.com/cvv-cat/Douyin_Spider) 二次开发，专注神秘人识别场景
- cookie 有效期有限，失效后需重新获取
- 仅供学习与技术研究使用
