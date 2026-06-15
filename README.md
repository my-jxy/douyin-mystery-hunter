# 🎯 抖音神秘人猎人 v2.0

> 实时监听抖音直播间，自动识别"神秘人"真实身份
>
> 部署于 **Linux 云服务器**，通过 **Cloudflare Tunnel** 随时外网访问
> 支持 Web 可视化面板、多房间同时监听、互动记录追溯

---

## 🆕 v2.0 重构

**核心架构变更：数据模型从「房间中心」改为「用户中心」**

- PK 从 `(room_id, sec_uid, display)` 改为 `(sec_uid, display)`——同一用户跨房间自动合并，不再需要事后跨房间查询
- 新增 `last_room_id` / `seen_room_ids` 字段追踪用户出现过的房间
- 删除 ~200 行重复的跨房间合并代码
- 无 `sec_uid` 的匿名用户不再入库（私密房打码昵称无价值）

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
- **多房间监听** — 同时监听多个直播间（默认上限 3 个，可调整）
- **两种显示模式** — 🎯 **神秘人模式**：仅展示神秘人卡片；📋 **全部模式**：记录所有进入/弹幕/送礼用户；📜 **历史模式**：跨会话持久化记录
- **私密直播支持** — 送礼时通过 API 获取真实身份
- **互动记录追溯** — 聊天/送礼内容自动存储，点击展开查看
- **多种输入格式** — 支持抖音号、主页链接、直播间链接
- **实时 Web 面板** — 暗色主题，手机/电脑浏览器即可访问

### 🔧 进阶功能

- **马甲历史** — 同一用户的历史 `神秘人`/`dou` 马甲在卡片内显示，带时效标记
- **♻️ 页面刷新自动恢复** — 刷新后自动检测活跃房间并恢复连接
- **🔗 Cloudflare Tunnel** — 外网穿透，无需公网 IP
- **systemd 自启** — 服务器重启自动拉起服务

---

## 🏗️ 架构

```
用户浏览器（手机/电脑）
    ↓ HTTPS
[Cloudflare Tunnel]
    ↓
nginx（反向代理）
    ↓
Flask Web 服务（端口 5000）
    ├─ GET  /                    → 前端页面
    ├─ POST /api/resolve         → 解析抖音号/链接
    ├─ POST /api/start           → 启动 WebSocket 监听
    ├─ POST /api/stop            → 停止指定房间
    ├─ POST /api/stop_all        → 停止所有监听
    ├─ GET  /api/status          → 查询监听器状态
    ├─ GET  /api/history_all     → 指定房间历史记录
    ├─ GET  /api/history_all_all → 全部历史记录
    ├─ GET  /api/all_records/:id → 全部用户记录
    ├─ GET  /api/interactions    → 互动详情
    ├─ GET  /api/history_rooms   → 历史房间列表
    └─ GET  /stream/:id          → SSE 实时推送
```

### 数据模型（v2.0）

```
mystery_records  — 主表，PK=(sec_uid, display)，同一用户一条记录
    ├─ last_room_id    最近出现的房间
    ├─ seen_room_ids   出现过的所有房间（逗号分隔）
    └─ display_names  保留所有历史马甲

interaction_log  — 互动明细（聊天/送礼），按 (room_id, sec_uid) 查询
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

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
npm install
```

### 配置抖音 Cookie

在项目根目录创建 `.env` 文件：

```env
DY_COOKIES='从 www.douyin.com 获取的完整 cookie'
DY_LIVE_COOKIES='从 live.douyin.com 获取的完整 cookie'
```

---

## 💻 使用方式

### 启动 Web 面板

```bash
cd douyin-mystery-hunter
source venv/bin/activate
python3 web_listener.py
```

访问 `http://localhost:5000`

### systemd 开机自启

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
cloudflared tunnel create my-tunnel
cloudflared tunnel route dns my-tunnel my.domain.com

# ~/.cloudflared/config.yml：
# tunnel: <tunnel-id>
# credentials-file: /home/admin/.cloudflared/<tunnel-id>.json
# ingress:
#   - hostname: my.domain.com
#     service: http://localhost:5000
#   - service: http_status:404

cloudflared tunnel run my-tunnel
```

---

## 🗺️ 项目结构

```
├── web_listener.py          # 🌐 Flask Web 面板（核心入口）
├── utils/                   # 🛠️ 工具模块
│   ├── common_util.py       #   通用工具 + cookie 加载
│   ├── dy_util.py           #   抖音签名生成
│   ├── cookie_util.py       #   cookie 管理
│   └── data_util.py         #   数据处理
├── builder/                 # 🏗️ 抖音 API 构建器
│   ├── header.py            #   请求头
│   ├── params.py            #   请求参数
│   ├── auth.py              #   认证模块
│   └── proto.py             #   protobuf 构建
├── static/                  # 📦 静态文件
│   ├── Live.proto / Live_pb2.py
│   ├── dy_ab.js / dy_live_sign.js
│   └── anime.min.js
├── dy_apis/                 # 🔌 抖音 API 封装
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🔍 核心工作流程

```
WebSocket 消息流
    ↓ 解析每条消息的 user 信息
    ↓ 检测三种匿名模式
    ├─ display_name 以 "神秘人" 开头且长度 > 3
    ├─ display_name 匹配 "dou" + 数字
    └─ mystery_man >= 2
    ↓ 命中 → 调用 API lookup_user 查询真实身份
    ↓ sec_uid 相同 → 自动合并，替换旧马甲
    ↓ SSE 实时推送到浏览器
```

---

## ⚙️ Web 面板详解

### 状态栏

```
🟢 监听中  |  1/3房  |  🎯神秘人  📋全部  📜历史
```

### 神秘人卡片

```
┌─────────────────────────────────┐
│ 🏠 房间名 🏅Lv.8      ▼ 3条互动   │
│ 真实昵称                          │
│ ✅ 神秘人XXXX 有效  ⏳ douXXXX    │
│ 🆔 douyin_id                     │
│ 📊 粉丝1234 作品56  🌍 浙江       │
│ 🔗 主页                          │
└─────────────────────────────────┘
```

---

## ⚠️ 已知限制

1. **同时监听上限默认为 3 个**，搜索 `MAX_ROOMS` 修改
2. **Cookie 会过期** — 需定期重新获取
3. **私密直播无法获取未送礼用户身份** — 抖音全量脱敏
4. **API 有风控** — 连续大量查询会被限制（限流 + 缓存已缓解）

---

## 📝 更新日志

| 日期 | 内容 |
|------|------|
| 2026-06-15 | **v2.0** 重构：PK 从房间中心改为用户中心，删除跨房间合并逻辑，匿名用户不入库 |
| 2026-06-14 | 互动记录存储 + 点击展开详情；全部页按钮移到右上角 |
| 2026-06-11 | V3 更新：私密直播送礼追踪真实身份；全部页统一风格 |
| 2026-05-28 | 新增隧道排障章节 |
| 2026-05-27 | 代码公开托管至 GitHub |
| 2026-05-25 | 新增 Web 面板，支持多房间监听、SSE 实时推送 |
