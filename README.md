# 🎯 抖音神秘人猎人

> 实时监听抖音直播间，自动识别"神秘人"真实身份
>
> 部署于 **Linux 云服务器**，通过 **Cloudflare Tunnel** 随时外网访问
> 支持 Web 可视化面板、多房间同时监听、互动记录追溯

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

> V2 改进：采用 **OR 筛选 + API 确认** 双重校验，防止普通用户改昵称冒充神秘人

---

## ✨ 功能特性

### 🎯 核心功能

- **自动识别神秘人** — WebSocket 实时监听，自动检测匿名用户
- **真实身份查询** — 通过抖音 API 查询神秘人的真实昵称、抖音号、粉丝数、IP 属地
- **OR 筛选 + API 确认** — 先按昵称模式筛出"疑似神秘人"，再调 API 确认真实身份
- **多房间监听** — 同时监听多个直播间（默认上限 3 个，可调整），各自独立连接
- **两种显示模式** — 🎯 **神秘人模式**：仅展示跨会话的神秘人卡片；📋 **全部模式**：记录当前会话所有进入/弹幕/送礼用户（默认最近2小时，可查看全量）
- **私密直播支持** — 自动检测私密直播，送礼时通过 API 获取真实昵称/粉丝数/IP/主页
- **身份合并** — 同一用户不同显示名自动合并，不同用户同名 display 不会误合
- **互动记录追溯** — 每条聊天/送礼内容自动存储，卡片右上角点击展开查看详情
- **多种输入格式** — 支持抖音号、主页链接、直播间链接三种方式输入
- **实时 Web 面板** — 手机/电脑浏览器即可访问，暗色主题

### 🔧 进阶功能

- **🎯/📋 模式切换** — 状态栏点击切换神秘人/全部模式
- **历史记录** — 神秘人页记录跨会话的历史马甲，带 ✅/⏳ 时效标记
- **♻️ 页面刷新自动恢复** — 刷新后自动检测活跃房间并恢复连接
- **🔗 Cloudflare Tunnel** — 外网穿透，无需公网 IP
- **🏠 房间标签** — 多房间时每个卡片左上角显示带颜色的房间名
- **systemd 自启** — 服务器重启自动拉起服务

---

## 🏗️ 架构

```
用户浏览器（手机/电脑）
    ↓ HTTPS
[Cloudflare Tunnel]            ← 外网穿透，无需公网 IP
    ↓
nginx（反向代理，可选）
    ↓
Flask Web 服务（端口 5000）
    ├─ GET  /                    → 前端页面（暗色主题）
    ├─ POST /api/resolve         → 解析抖音号/链接 → {room_id, nickname}
    ├─ POST /api/start           → 启动 WebSocket 监听
    ├─ POST /api/stop            → 停止指定房间
    ├─ POST /api/stop_all        → 停止所有监听
    ├─ GET  /api/status          → 查询监听器状态
    ├─ GET  /api/history/:id     → 指定房间历史神秘人
    ├─ GET  /api/history_all/:id → 跨会话历史记录（含马甲合并）
    ├─ GET  /api/all_records/:id → 全部用户记录（支持 ?hours=2）
    ├─ GET  /api/interactions/:room/:uid → 互动详情
    ├─ GET  /api/rooms           → 活跃直播间列表
    └─ GET  /stream/:id          → SSE 实时推送
```

### 数据流

```
抖音直播间 WebSocket
    ↓ protobuf 消息流
RoomListener（每个直播间一个独立实例）
    ├─ 神秘人 → SSE 实时推送到浏览器
    ├─ 互动记录 → 写入 SQLite（interaction_log 表）
    └─ 全部用户 → 写入 SQLite → 前端"刷新"读取
Queue（事件队列）
    ↓ SSE 推送
浏览器前端（实时渲染卡片）
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
git clone https://github.com/my-jxy/douyin-mystery-hunter.git
cd douyin-mystery-hunter

# Python 虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# JS 依赖（用于签名）
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
>
> 确保 Cookie 中包含 `sessionid`、`odin_tt`、`uid_tt`、`ttwid` 等关键字段

---

## 💻 使用方式

### 启动 Web 面板

```bash
cd douyin-mystery-hunter
source venv/bin/activate
python3 web_listener.py
```

访问 `http://localhost:5000` 即可。

### systemd 开机自启（推荐服务器部署）

```ini
# /etc/systemd/system/douyin-hunter.service
[Unit]
Description=Douyin Mystery Hunter Web Panel
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/douyin-mystery-hunter
ExecStart=/home/admin/douyin-mystery-hunter/venv/bin/python web_listener.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now douyin-hunter
```

### 外网访问：Cloudflare Tunnel

```bash
# 安装 cloudflared
# 参见 https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

# 登录并创建隧道
cloudflared tunnel create my-tunnel

# 配置 DNS
cloudflared tunnel route dns my-tunnel my.domain.com

# 配置文件 ~/.cloudflared/config.yml：
# tunnel: <tunnel-id>
# credentials-file: /home/admin/.cloudflared/<tunnel-id>.json
# ingress:
#   - hostname: my.domain.com
#     service: http://localhost:5000
#   - service: http_status:404

# 启动
cloudflared tunnel run my-tunnel
```

> 也可使用 trycloudflare 快速暴露（无需注册）：
> ```bash
> cloudflared tunnel --url http://localhost:5000
> ```

### 输入格式支持

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

### 多房间监听

- 默认同时监听 **3 个** 直播间，可在 `web_listener.py` 搜索 `MAX_ROOMS` 修改
- 每个房间独立 WebSocket 连接，互不影响
- 用户卡片左上角带颜色标签区分房间来源
- 颜色分配：红 → 蓝 → 绿，按加入顺序循环

---

## 🗺️ 项目结构

```
├── web_listener.py          # 🌐 Flask Web 面板（核心入口，含前端 HTML + SQLite）
├── hunt_mystery.py          # 🔍 命令行神秘人识别
├── connect_direct.py        # 🔗 直播间直连（简化版）
├── connect_live.py          # 📡 WebSocket 直连封装
├── scan_room_users.py       # 👥 直播间用户扫描
├── parse_proto.py           # 🔧 protobuf 解析工具
├── check_history.py         # 📜 历史记录检查
├── debug_search.py          # 🐛 搜索调试
│
├── utils/                   # 🛠️ 工具模块
│   ├── common_util.py       #   通用工具 + cookie 加载
│   ├── dy_util.py           #   抖音签名生成
│   ├── cookie_util.py       #   cookie 管理
│   └── data_util.py         #   数据处理
│
├── builder/                 # 🏗️ 抖音 API 构建器
│   ├── header.py            #   请求头
│   ├── params.py            #   请求参数
│   ├── auth.py              #   认证模块
│   └── proto.py             #   protobuf 构建
│
├── static/                  # 📦 静态文件
│   ├── Live.proto / Live_pb2.py
│   ├── dy_ab.js / dy_live_sign.js
│   └── anime.min.js
│
├── dy_live/server.py        # 📡 WebSocket 连接服务
├── dy_apis/                 # 🔌 抖音 API 封装
├── .env                     # 🔑 配置文件（已 gitignore）
├── requirements.txt         # 📋 Python 依赖
└── mystery_history.db       # 💾 SQLite 数据文件（自动创建）
```

---

## 🔍 核心工作流程

### 神秘人检测流程

```
WebSocket 消息流
    ↓ 解析每条消息的 user 信息
    ↓ 检测三种匿名模式
    ├─ display_name 以 "神秘人" 开头且长度 > 3
    ├─ display_name 匹配 "dou" + 数字
    └─ mystery_man >= 2
    ↓ 命中疑似神秘人 → 调用 API lookup_user 查询
    ├─ API 昵称 == 脱敏名 display → 降级为普通用户
    └─ 不同或无结果 → 真神秘人，推送 SSE
    ↓ SSE 实时推送到浏览器
```

### 全部用户模式

```
开启"全部"模式
    ↓ 每次进入/弹幕/送礼写入 SQLite
    ↓ 互动内容自动存储到 interaction_log 表
    ↓ 前端"刷新" → GET /api/all_records/:id?hours=2
    └─ 默认最近 2 小时，点击"查看全部历史数据"显示全量
```

---

## ⚙️ Web 面板详解

### 状态栏

```
🟢 监听中  |  1/3房  |  🎯神秘人  📋全部
```

- 🟢 监听中 / 🟡 重连中 / 🔴 已断开
- N/M 房 — 当前活跃房间数/上限
- 🎯 神秘人 / 📋 全部 — 模式切换

### 神秘人卡片（🎯 模式）

```
┌─────────────────────────────────┐
│ 🏠 房间名 🏅Lv.8    ▼ 3条互动    │  ← 右上角可点击展开互动详情
│ 真实昵称                         │
│ ⏳ 历史马甲1  ⏳ 历史马甲2        │
│ 🆔 xxxxxx                       │
│ 📊 粉丝1234 作品56  🌍 浙江      │
│ 🚪3次 💬2条 🎁1个               │
│ ──── 互动详情 ────               │  ← 点击展开后显示
│ 💬 今天好开心                     │
│ 🎁 小心心 x1                     │
└─────────────────────────────────┘
```

每个神秘人卡片底部有 **🔗 主页** 链接，点击在新标签打开抖音主页。

### 全部用户卡片（📋 模式）

```
┌─────────────────────────────────┐
│ 🏠 房间名 普通         ▼ 39条互动 │  ← 右上角有互动才显示
│ 遮罩昵称                         │
│ 🆔 xxxxxx                       │
│ 🚪5次 💬3条 🎁0个               │
│ ──── 互动详情 ────               │  ← 点击展开（显示最近50条）
│ 💬 在吗？                        │
│ 🎁 人气票 x10                    │
└─────────────────────────────────┘
```

> 全部用户默认仅显示最近 2 小时数据。点击底部 **📋 查看全部历史数据** 可查看该直播间所有历史记录。

### WebSocket 自动重连

- 抖音 WebSocket 会频繁断开（约几分钟一次）
- 断线后 5 秒自动重连，不丢失监听状态
- 前端 5 秒防抖，不闪屏

---

## ☁️ 推荐部署：Linux 云服务器 + Cloudflare Tunnel

这也是本项目当前的实际运行环境。

| 组件 | 方案 |
|------|------|
| 服务器 | 阿里云 ECS / 腾讯云轻量（新用户约 ¥9/月起） |
| 系统 | Ubuntu 24.04 / Debian 12 |
| 外网访问 | Cloudflare Tunnel（免费，无需公网 IP） |
| 进程管理 | systemd 自启 |
| 数据库 | SQLite（单文件，零运维） |

### 部署要点

```bash
# 1. 安装依赖
apt install python3 python3-venv nodejs npm git

# 2. 克隆项目
git clone https://github.com/my-jxy/douyin-mystery-hunter.git
cd douyin-mystery-hunter

# 3. 配置虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
npm install

# 4. 配置 .env（抖音 Cookie）
nano .env

# 5. 配置 systemd 服务（见上方）
sudo systemctl enable --now douyin-hunter

# 6. 配置 Cloudflare Tunnel
# 确认 cloudflared 已安装并配置好隧道
cloudflared tunnel run my-tunnel
```

---

## ⚠️ 已知限制

1. **同时监听上限默认为 3 个**，可在 `web_listener.py` 中搜索 `MAX_ROOMS` 修改。每个直播间约 20-30MB 内存
2. **Cookie 会过期** — 需定期重新获取
3. **榜一/排行榜不显示** — Web 面板过滤了排行榜消息
4. **匿名模式下财富等级始终为 0** — 抖音隐藏，非 bug
5. **API 有风控** — 连续大量查询会被限制（限流 + 缓存已缓解）
6. **私密直播无法获取用户真实身份** — 抖音全量脱敏，仅展示遮罩昵称

---

## 📝 更新日志

| 日期 | 内容 |
|------|------|
| 2026-06-14 | 互动记录存储 + 点击展开详情；全部页按钮移到右上角；README 适配 Linux + Cloudflare Tunnel |
| 2026-06-11 | V3 更新：私密直播送礼追踪真实身份；全部页统一红/灰风格；合并逻辑防误合 |
| 2026-05-28 | 新增隧道排障章节 |
| 2026-05-27 | 代码公开托管至 Gitee + GitHub |
| 2026-05-25 | 新增 Web 面板，支持多房间监听、SSE 实时推送、自动重连 |

---

## 🔧 隧道排障（Cloudflare Tunnel）

如果外网无法访问，先检查隧道状态：

```bash
# 查看隧道进程
ps aux | grep cloudflared | grep -v grep

# 检查隧道运行状态
cloudflared tunnel list

# 查看最近日志
journalctl -u cloudflared --no-pager -n 30

# 本地测试服务是否正常
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000

# 重新启动隧道
sudo systemctl restart cloudflared

# 或者使用 trycloudflare 快速排查（临时隧道）
cloudflared tunnel --url http://localhost:5000
```

### 常见问题

- **502 错误**：隧道连通但 Flask 挂了 → `systemctl restart douyin-hunter`
- **Tunnel 状态显示 DOWN**：认证凭证失效 → 重新 `cloudflared tunnel login`
- **域名无法访问**：DNS 未正确指向 → 确保域名 CNAME 指向隧道 ID
