# 🎯 抖音神秘人猎人

> 实时监听抖音直播间，自动识别"神秘人"真实身份
>
> 支持 Web 可视化面板、最多 3 个直播间同时监听、多种输入格式

---

## 📖 什么是神秘人？

抖音直播间里，部分观众会以**匿名身份**出现——昵称显示为 `神秘人XXXXX` 或 `dou` + 数字，无法直接看出是谁。

本工具通过 WebSocket 直连抖音直播间，解析 protobuf 消息流，自动检测并查询这些匿名用户的**真实昵称**，实时展示在 Web 面板上。

识别三种匿名模式：

| 模式 | 特征 |
|------|------|
| 🎭 经典匿名 | 显示名 `神秘人XXXXX` |
| 🆕 dou 匿名 | 显示名 `dou` + 数字 |
| 🔒 深度匿名 | protobuf 中 `mystery_man >= 2` |

---

## ✨ 功能特性

### 🎯 核心功能

- **自动识别神秘人** — WebSocket 实时监听，自动检测匿名用户
- **真实身份查询** — 通过抖音 API 查询神秘人的真实昵称、抖音号、粉丝数、IP 属地
- **多房间监听** — 同时监听 **最多 3 个** 不同直播间，每个房间独立连接
- **多种输入格式** — 支持抖音号、主页链接、直播间链接三种方式输入
- **实时 Web 面板** — 手机浏览器即可访问，零 AI Token 消耗
- **弹幕/礼物记录** — 神秘人发送的弹幕和赠送的礼物自动记录、折叠展示

### 🔧 进阶功能

- **🔄 手动同步** — 点击状态栏"同步"按钮，增量拉取服务端所有神秘人数据
- **🤖 自动同步** — 每 30 秒后台自动同步，多标签页数据保持一致
- **♻️ 页面刷新自动恢复** — 刷新页面后自动检测活跃房间并恢复连接
- **🔗 外网穿透** — 支持 Serveo 隧道，出门在外也能访问
- **🏠 房间标签** — 多房间时每个神秘人卡片左上角显示带颜色的房间名
- **🐳 Docker 部署** — 支持容器化运行

---

## 🏗️ 架构

```
用户浏览器（手机/电脑）
    ↓ HTTPS
SSH 隧道（Serveo.net / localhost.run）
    ↓
Flask Web 服务（手机 Termux / 云服务器，端口 5000）
    ├─ GET  /                → 前端页面（暗色主题）
    ├─ POST /api/resolve     → 解析抖音号/链接 → {room_id, nickname}
    ├─ POST /api/start       → 启动 WebSocket 监听
    ├─ POST /api/stop        → 停止指定房间监听
    ├─ POST /api/stop_all    → 停止所有监听
    ├─ GET  /api/status      → 查询所有监听器状态
    ├─ GET  /api/history/:id → 获取指定房间历史神秘人
    └─ GET  /stream/:id      → SSE 实时推送（神秘人/弹幕/礼物）
```

### 数据流

```
抖音直播间 WebSocket
    ↓ protobuf 消息流
RoomListener（每个直播间一个独立实例）
    ↓ 解析 → 神秘人检测 → API 查询真实身份
Queue（事件队列）
    ↓ SSE 推送
浏览器前端（实时渲染神秘人卡片）
```

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.7+ |
| Node.js | 18+（用于 JS 签名） |

### 安装

```bash
# 克隆仓库
git clone git@gitee.com:my-jy/douyin-spider.git
cd douyin-spider

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 JS 依赖（用于签名）
npm install
```

### 配置抖音 Cookie

1. 浏览器打开 `www.douyin.com` 并登录
2. F12 → 网络 → 任意请求 → 复制 Cookie 头
3. 同样在 `live.douyin.com` 获取直播间 Cookie

在项目根目录创建 `.env` 文件：

```env
DY_COOKIES='从 www.douyin.com 获取的完整 cookie'
DY_LIVE_COOKIES='从 live.douyin.com 获取的完整 cookie'
```

> ⚠️ Cookie 会过期，失效时需要重新获取

---

## 💻 使用方式

### 方式一：Web 面板（推荐）

启动 Flask Web 服务：

```bash
python3 web_listener.py
```

访问 `http://localhost:5000` 即可打开 Web 面板。

如果需要外网访问（比如出门在外），配合 SSH 隧道：

```bash
# Serveo.net（固定子域名，推荐）
ssh -o StrictHostKeyChecking=no -R mybb:80:localhost:5000 serveo.net
# 访问 https://mybb.serveousercontent.com

# 或 localhost.run（免注册，每次域名变化）
ssh -o StrictHostKeyChecking=no -R 80:localhost:5000 nokey@localhost.run
```

#### Web 面板使用说明

| 操作 | 说明 |
|------|------|
| **输入直播间** | 在输入框粘贴抖音号、主页链接或直播间链接，点击"监听" |
| **停止监听** | 点击房间标签上的 ✕ 按钮，停止该房间 |
| **手动同步** | 点击状态栏右侧 🔄 按钮，拉取最新数据 |
| **查看弹幕** | 点击神秘人卡片底部的 `▼ N 条互动` 展开 |
| **查看主页** | 点击神秘人昵称，在新标签页打开抖音主页 |

#### 输入格式支持

```
# 直播间链接
https://live.douyin.com/7643362348794776355

# 主播主页链接
https://www.douyin.com/user/MS4wLjABAAAA...

# 抖音号（unique_id）
81066441269

# 仅直播间 ID
7643362348794776355
```

#### 多房间监听

- 最多同时监听 **3 个** 直播间
- 每个房间独立 WebSocket 连接，互不影响
- 神秘人卡片左上角带颜色标签区分房间来源
- 颜色分配：红 `#fe2c55` → 蓝 `#5ac8fa` → 绿 `#34c759`
- 重复输入已监听的房间会提示"⚠️ 已在监听"

### 方式二：命令行模式

```bash
# 监听指定直播间
python3 hunt_mystery.py <直播间ID>

# 后台运行，输出到日志文件
python3 -u hunt_mystery.py <直播间ID> >> ~/douyin_monitor.log 2>&1 &

# 查看结果
tail -20 ~/douyin_monitor.log

# 直连模式（简化版）
python3 connect_direct.py <直播间ID>
```

### 方式三：Docker

```bash
docker build -t douyin-mystery-hunter .
docker run -d -p 5000:5000 --env-file .env douyin-mystery-hunter
```

---

## 🗺️ 项目结构

```
├── web_listener.py          # 🌐 Flask Web 面板（核心入口）
├── hunt_mystery.py          # 🔍 神秘人识别主脚本（命令行）
├── connect_direct.py        # 🔗 直播间直连监听（简化版）
├── hunt_file.py             # 📄 文件版神秘人识别
├── scan_room_users.py       # 👥 直播间用户扫描
├── scan_types.py            # 📋 直播间消息类型枚举
├── parse_proto.py           # 🔧 protobuf 解析工具
├── check_history.py         # 📜 历史记录检查
├── debug_search.py          # 🐛 搜索调试工具
│
├── utils/                   # 🛠️ 工具模块
│   ├── common_util.py       #   通用工具 + cookie 加载
│   ├── dy_util.py           #   抖音签名生成
│   ├── cookie_util.py       #   cookie 管理
│   └── data_util.py         #   数据处理
│
├── builder/                 # 🏗️ 抖音 API 构建器
│   ├── header.py            #   请求头构建
│   ├── params.py            #   请求参数
│   ├── auth.py              #   认证模块
│   └── proto.py             #   protobuf 构建
│
├── static/                  # 📦 静态文件
│   ├── Live.proto           #   直播间 protobuf 定义
│   ├── Live_pb2.py          #   编译后的 protobuf
│   ├── dy_ab.js             #   JS 反爬签名
│   └── dy_live_sign.js      #   直播间签名
│
├── dy_live/                 # 📡 直播间 WebSocket
│   └── server.py            #   WebSocket 服务
│
├── dy_apis/                 # 🔌 抖音 API 封装
│
├── .env                     # 🔑 配置文件（已 gitignore）
├── requirements.txt         # 📋 Python 依赖
├── Dockerfile               # 🐳 容器部署
└── package.json             # 📦 JS 依赖
```

---

## 🔍 核心工作流程

### 场景 A：输入直播间链接

```
live.douyin.com/xxxxxxxx
    → 提取 room_id
    → 直连抖音 WebSocket
    → 监听消息流
```

### 场景 B：输入主播抖音号/主页链接

```
抖音号 / 主页链接
    → v2 API 查询用户信息（拿 sec_uid）
    → profile API 查直播状态（live_status + room_id）
    → 有 room_id → 连 WebSocket
    → 无直播 → 提示"主播未开播"
```

### 场景 C：神秘人检测流程

```
WebSocket 消息流
    ↓ 解析每条消息的 user 信息
    ↓ 检测三种匿名模式
    ├─ display_name 以 "神秘人" 开头且长度 > 3
    ├─ display_name 匹配 "dou" + 数字
    └─ mystery_man >= 2
    ↓ 命中 → 提取 sec_uid
    ↓ 轻量 API 查询真实昵称（lookup_user）
    ↓ 缓存结果（同一 sec_uid 只查一次）
    ↓ SSE 推送到浏览器
```

### API 防风控

- **限流**：API 调用间隔 ≥ 0.3 秒
- **缓存**：同一用户只查一次，失败的也缓存
- **轻量认证**：仅用 ttwid + 空 msToken，不加 a_bogus

---

## ⚙️ Web 面板功能详解

### 状态栏

```
🎯 神秘人: 12  |  🏠 房间 A (3)  🏠 房间 B (7)  |  🟢 已连接  |  🔄 同步
```

- **神秘人: N** — 所有房间汇总的不重复神秘人总数
- **房间标签** — 每个房间的名称和该房间的神秘人数量
- **状态指示** — 🟢 已连接 / 🟡 重连中 / 🔴 已断开
- **🔄 同步** — 增量拉取所有房间最新数据

### 神秘人卡片

每个神秘人显示：

```
┌─────────────────────────────────┐
│ 🏠 房间名（颜色标签）              │
│ 真实昵称 🏅 Lv.30                │
│ 抖音号: xxxxxx  |  粉丝 1234     │
│ IP属地: 浙江                      │
│ ▼ 3 条互动（点击展开）             │
│   💬 弹幕: 来了来了               │
│   🎁 送了 1 个小心心             │
└─────────────────────────────────┘
```

### WebSocket 自动重连

- 抖音 WebSocket 会频繁断开（约几分钟一次）
- 断线后 5 秒自动重连，不丢失监听状态
- 前端 5 秒防抖，不闪屏

### 页面刷新自动恢复

刷新页面后自动：
1. 查询 `/api/status` 获取活跃房间列表
2. 为每个房间重新连接 SSE
3. 拉取全量历史神秘人数据
4. 恢复 30 秒自动同步定时器

---

## 🐳 Docker 部署

### 构建镜像

```bash
docker build -t douyin-mystery-hunter .
```

### 运行容器

```bash
docker run -d \
  -p 5000:5000 \
  --env-file .env \
  --restart unless-stopped \
  douyin-mystery-hunter
```

### Dockerfile 说明

基于 `python:3.10-slim`，自动安装 Node.js 20，暴露 5000 端口。

---

## ☁️ 云服务器部署

### 推荐配置

| 平台 | 最低配置 | 月费 |
|------|---------|------|
| 阿里云轻量 | 1核1G/20G SSD/1M | ~¥9/月 |
| 腾讯云轻量 | 1核1G/50G SSD/1M | ~¥10/月 |
| Railway | 容器托管 | 免费$5额度/月 |

### 部署步骤

```bash
# 1. 安装依赖
apt update && apt install -y python3 python3-pip nodejs git
pip install -r requirements.txt
npm install

# 2. 克隆代码
git clone git@gitee.com:my-jy/douyin-spider.git
cd douyin-spider

# 3. 配置 .env（上传或手动创建）
nano .env

# 4. 启动
python3 web_listener.py
```

---

## 🔧 隧道方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Serveo.net** 🔥 | 支持固定子域名，稳定 | 需要 SSH，有时被 Clash 拦截 | ⭐⭐⭐⭐⭐ |
| **localhost.run** | 免注册，零配置 | 每次重启域名变化 | ⭐⭐⭐⭐ |
| **Cloudflare Tunnel** | 固定域名，走 HTTPS | 需要装 cloudflared | ⭐⭐⭐⭐ |

---

## ⚠️ 已知限制

1. **最多同时监听 3 个直播间** — 后端硬限制
2. **Cookie 有效期** — 抖音 cookie 会过期，需重新获取
3. **榜一/排行榜不显示** — Web 面板过滤了排行榜消息（用户要求去掉刷屏）
4. **匿名模式下财富等级为 0** — 抖音隐藏，非 bug
5. **pyngrok 不支持 Android** — Termux 无法使用 ngrok
6. **API 风控** — 连续大量查询可能触发抖音风控（限流 + 缓存已缓解）

---

## 📝 更新日志

| 日期 | 内容 |
|------|------|
| 2026-05-25 | Web 面板上线，支持多房间监听、SSE 实时推送、自动重连、同步功能 |
| 2026-05-27 | 代码托管至 Gitee，完善文档 |

---

## 📄 许可

本项目基于 [Douyin_Spider](https://github.com/cvv-cat/Douyin_Spider) 二次开发，专注神秘人识别场景。

仅供学习与技术研究使用。
