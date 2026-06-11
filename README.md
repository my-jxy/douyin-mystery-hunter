# 🎯 抖音神秘人猎人

> 实时监听抖音直播间，自动识别"神秘人"真实身份
>
> 支持 Web 可视化面板、直播间同时监听（支持自定义上限）、多种输入格式

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
- **OR 筛选 + API 确认** — 先按昵称模式筛出"疑似神秘人"，再调 API 确认真实身份；API 查到昵称和脱敏名一致时降级为普通用户
- **多房间监听** — 同时监听多个不同直播间（默认上限 3 个，可调整），每个房间独立连接
- **两种显示模式** — 🎯 **神秘人模式**：仅展示神秘人卡片；📋 **全部模式**：记录直播间所有进入/弹幕/送礼用户
- **私密直播支持** — 自动检测私密直播，送礼时通过 API 获取真实昵称/粉丝数/IP/主页，缓存后后续进房弹幕自动补全
- **身份合并** — 同一用户的不同等级记录通过 extra+display 双重校验合并，不同用户同名 display 不会误合
- **多种输入格式** — 支持抖音号、主页链接、直播间链接三种方式输入
- **实时 Web 面板** — 手机浏览器即可访问
- **弹幕/礼物记录** — 神秘人发送的弹幕和赠送的礼物自动记录、折叠展示

### 🔧 进阶功能

- **🎯/📋 模式切换** — 状态栏点击切换神秘人模式/全部模式，全部模式下点击"刷新"同步最新数据
- **♻️ 页面刷新自动恢复** — 刷新页面后自动检测活跃房间并恢复连接
- **🔗 外网穿透** — 支持 Serveo 隧道，出门在外也能访问
- **🏠 房间标签** — 多房间时每个用户卡片左上角显示带颜色的房间名
- **🐳 Docker 部署** — 支持容器化运行

---

## 🏗️ 架构

```
用户浏览器（手机/电脑）
    ↓ HTTPS
[SSH 隧道 / Cloudflare Tunnel]
    ↓
Flask Web 服务（端口 5000 ~ 5002）
    ├─ GET  /                  → 前端页面（暗色主题）
    ├─ POST /api/resolve       → 解析抖音号/链接 → {room_id, nickname}
    ├─ POST /api/start         → 启动 WebSocket 监听
    ├─ POST /api/stop          → 停止指定房间监听
    ├─ POST /api/stop_all      → 停止所有监听
    ├─ GET  /api/status        → 查询所有监听器状态
    ├─ GET  /api/history/:id   → 获取指定房间历史神秘人
    ├─ GET  /api/all_records/:id → 获取全部用户记录（从磁盘读取）
    ├─ POST /api/toggle_record_all → 切换全部用户录制模式
    └─ GET  /stream/:id        → SSE 实时推送（神秘人/弹幕/礼物）
```

### 数据流

```
抖音直播间 WebSocket
    ↓ protobuf 消息流
RoomListener（每个直播间一个独立实例）
    ├─ 神秘人 → SSE 实时推送到浏览器
    └─ 普通用户（全部模式）→ 写入磁盘 JSONL → 前端点"刷新"读取
Queue（事件队列）
    ↓ SSE 推送
浏览器前端（实时渲染神秘人/全部用户卡片）
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
# 克隆仓库（GitHub 优先）
git clone https://github.com/my-jxy/douyin-mystery-hunter.git
cd douyin-mystery-hunter
# 或从 Gitee 镜像克隆
# git clone https://gitee.com/my-jy/douyin-mystery-hunter.git
# cd douyin-mystery-hunter

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
>
> ⚠️ **Cookie 缺失或不完整时，无法获取礼物数据**。神秘人送礼时如果收不到礼物信息（`WebcastGiftMessage`），将无法通过礼物记录追踪神秘人。确保 Cookie 中包含 `sessionid`、`odin_tt`、`uid_tt`、`ttwid` 等关键字段。

---

## 💻 使用方式

### 方式一：Web 面板（推荐）

启动 Flask Web 服务：

```bash
python3 web_listener.py
```

访问 `http://localhost:5000` 即可打开 Web 面板。

如果需要外网访问（比如出门在外），配合 SSH 隧道或 Cloudflare Tunnel：

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
| **停止监听** | 点击"停止"按钮，多房间时弹出选择弹窗 |
| **切换模式** | 状态栏点击 🎯 神秘人 或 📋 全部 切换显示模式 |
| **刷新数据** | 全部模式下点击"刷新"同步最新记录 |
| **查看互动** | 点击卡片底部的 `▼ N 条互动` 展开弹幕/礼物记录 |
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

- 默认同时监听 **3 个** 直播间，可修改代码调整上限
- 每个房间独立 WebSocket 连接，互不影响
- 用户卡片左上角带颜色标签区分房间来源
- 颜色分配：红 → 蓝 → 绿，按加入顺序循环
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
├── web_listener.py          # 🌐 Flask Web 面板（核心入口，含前端 HTML）
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
├── package.json             # 📦 JS 依赖
└── data/                    # 💾 全部用户记录磁盘存储（自动创建/删除）
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

### 场景 C：神秘人检测流程（V2 改进）

```
WebSocket 消息流
    ↓ 解析每条消息的 user 信息
    ↓ 检测三种匿名模式
    ├─ display_name 以 "神秘人" 开头且长度 > 3
    ├─ display_name 匹配 "dou" + 数字
    └─ mystery_man >= 2
    ↓ 命中疑似神秘人 → 调用 API lookup_user 查询真实信息
    ├─ API 返回的昵称 == 脱敏名 display → 普通用户改的名，降级为普通用户
    └─ API 无结果或昵称不同 → 真神秘人，推送 SSE
    ↓ SSE 推送到浏览器
```

### 全部用户模式

```
WebSocket 消息流
    ↓ 开启"全部"模式时，每次进入/弹幕/送礼都写入磁盘 JSONL
    ↓ 前端点击"刷新" → GET /api/all_records/:id
    ↓ 从磁盘读取最近 500 条 → 按用户聚合渲染
    └─ 私密直播自动识别 → 用 real_name + consume_level + badge_level 组合 key
```

### API 防风控

- **限流**：API 调用间隔 ≥ 0.3 秒，防止触发抖音风控
- **缓存**：同一用户只查一次，失败的也缓存
- **轻量认证**：仅用 ttwid + 空 msToken，不加 a_bogus 签名

---

## ⚙️ Web 面板功能详解

### 状态栏

```
🟢 监听中  |  1/3房  |  🎯神秘人  📋全部
```

- **状态指示** — 🟢 监听中 / 🟡 重连中 / 🔴 已断开
- **N/M 房** — 当前活跃房间数/上限
- **🎯 神秘人 / 📋 全部** — 模式切换按钮，点击切换

### 神秘人卡片

```
┌─────────────────────────────────┐
│ 🏠 房间名（颜色标签） 🏅Lv.8    │
│ 真实昵称                         │
│ 🆔 xxxxxx                       │
│ 📊 粉丝1234 作品56               │
│ 🌍 IP属地: 浙江                  │
│ 🚪3次 💬2条 🎁1个               │
│ ▼ 3条互动（点击展开）             │
└─────────────────────────────────┘
```

统计项：🚪进入次数 💬弹幕条数 🎁礼物个数

### 全部用户卡片（全部模式）

```
┌─────────────────────────────────┐
│ 🏠 房间名（颜色标签） 普通        │
│ 遮罩昵称                         │
│ 🆔 xxxxxx                       │
│ 🚪5次 💬3条 🎁0个               │
│ ▼ 8条互动（点击展开）             │
└─────────────────────────────────┘
```

### 停止弹窗

多房间时点击"停止"弹出选择弹窗：
- 每个房间显示名称 + 红色"停止"按钮
- 底部"全部停止"一键停止所有
- 点击"取消"关闭弹窗

### 私密直播检测

自动检测私密直播（sec_uid 为空 + unique_id='?'）：
- 神秘人页：用 display + consume_level + badge_level 组合 key，防止同名遮罩用户合并
- 全部页：用 real_name + consume_level + badge_level 组合 key，正确聚合
- 判定逻辑不影响正常直播

### WebSocket 自动重连

- 抖音 WebSocket 会频繁断开（约几分钟一次）
- 断线后 5 秒自动重连，不丢失监听状态
- 前端 5 秒防抖，不闪屏

### 页面刷新自动恢复

刷新页面后自动：
1. 查询 `/api/status` 获取活跃房间列表
2. 为每个房间重新连接 SSE
3. 拉取全量历史神秘人数据
4. 自动恢复监听状态

---

## 🐳 Docker 部署

```bash
docker build -t douyin-mystery-hunter .
docker run -d -p 5000:5000 --env-file .env --restart unless-stopped douyin-mystery-hunter
```

---

## 💻 支持平台

本项目最初在 **Android (Termux)** 上开发并运行，代码兼容主流操作系统。

| 平台 | 环境配置 | 隧道支持 | 注意事项 |
|------|---------|---------|---------|
| **Android (Termux)** 🏠 | Python + Node.js 通过 pkg 安装 | Serveo / localhost.run | ✅ 原生支持；⚠️ Clash TUN 模式会拦截 SSH 隧道，需关掉或加直连规则 |
| **Linux** | 系统包管理器安装 Python/Node | Serveo / localhost.run / ngrok | ✅ 全功能支持；推荐 systemd 管理进程 |
| **Windows** | 安装 Python + Node.js（官网下载） | Serveo / localhost.run / ngrok | ✅ ngrok 可用；路径用反斜杠；PowerShell 管理后台进程 |
| **macOS** | Homebrew 安装 Python/Node | Serveo / localhost.run / ngrok | ✅ 全功能支持 |
| **Docker** (任意平台) | 无需手动装依赖 | 宿主机提供隧道 | ✅ 环境隔离，一键部署 |

> 💡 **建议**：如果只是想临时用用，手机 Termux 就够了。如果需要 24 小时稳定运行，推荐部署到 Linux 云服务器或 Windows 电脑。

内网穿透用于在外网访问本地的 Web 面板。

### Serveo.net（推荐）

```bash
ssh -o StrictHostKeyChecking=no -R mybb:80:localhost:5000 serveo.net
```

支持固定子域名，访问 `https://mybb.serveousercontent.com` 即可。稳定可靠，推荐使用。

### localhost.run（备选）

```bash
ssh -o StrictHostKeyChecking=no -R 80:localhost:5000 nokey@localhost.run
```

免注册零配置，但每次重启域名会变化。

### ngrok

如果你在 Windows/Linux/Mac 上运行，也可以用 ngrok 做内网穿透：

```bash
ngrok http 5000
```

> ⚠️ ngrok 官方 Python 包（pyngrok）不支持 Android 系统，因此 Termux 上无法使用。Windows/Linux/Mac 上完全正常。

---

## ☁️ 推荐：部署到云服务器

手机本地运行依赖 Termux 进程不中断，网络也受限制。建议有条件的话部署到云服务器上，24 小时在线，不受手机影响。

### 推荐云平台

| 平台 | 说明 |
|------|------|
| **阿里云轻量** | 新用户 1 个月免费，后续约 ¥9/月起 |
| **腾讯云轻量** | 新用户 1 个月免费，后续约 ¥10/月起 |
| **Railway** | 海外平台，免费 $5 额度/月，但注册需信用卡 |

> 国内平台（阿里云/腾讯云）支持支付宝付款，无需信用卡。

### 部署要点

- 云服务器上只需装 Python + Node.js + Git
- `git clone` 项目，装依赖，配 `.env`，跑起来就行
- 自带公网 IP，无需额外配置隧道

---

## ⚠️ 已知限制

1. **同时监听上限默认为 3 个**，可在 `web_listener.py` 中搜索 `MAX_ROOMS` 修改

   性能参考：每个直播间约消耗 20-30MB 内存，CPU 几乎无占用，普通手机可开 5-8 个，云服务器/电脑可开 10-20 个
2. **Cookie 会过期** — 需定期重新获取
3. **榜一/排行榜不显示** — Web 面板过滤了排行榜消息
4. **匿名模式下财富等级始终为 0** — 抖音隐藏，非 bug
5. **API 有风控** — 连续大量查询会被限制（限流 + 缓存已缓解）
6. **私密直播无法获取用户真实身份** — 抖音全量脱敏，仅展示遮罩昵称 + 等级组合

---

## 📝 更新日志

| 日期 | 内容 |
|------|------|
| 2026-06-11 | V3 更新：私密直播送礼追踪真实身份；全部页卡片统一红/灰风格；合并逻辑防误合；修复uid问号、JSONL残留等细节 |
| 2026-05-28 | 新增隧道排障章节 |
| 2026-05-27 | 代码公开托管至 Gitee + GitHub，完善文档 |
| 2026-05-25 | 新增 Web 面板，支持多房间监听、SSE 实时推送、自动重连、同步功能 |

---

## 🔧 隧道排障（Serveo）

如果 Web 页面无法访问，先检查隧道：

```bash
# 检查隧道进程
ps aux | grep serveo | grep -v grep

# 测试公网
curl -s -o /dev/null -w "%{http_code}" https://mybb.serveousercontent.com

# 如果返回 502 或连不通：
pkill -f "serveo.net"       # 杀光所有旧隧道
sleep 5                      # 等服务端清理残留映射
# 重新建立隧道
nohup ssh -o StrictHostKeyChecking=no \
  -R mybb:80:localhost:5000 serveo.net > /dev/null 2>&1 &
```

**常见问题：**
- `remote forward failure for: listen port 80` → **旧隧道残留**，清干净重试即可（见上）
- 502 → 隧道连上了但本地服务没起来，检查 `python3 web_listener.py` 是否在跑
- 200 但显示空白 → 浏览器缓存，强制刷新

---

## 📄 许可

基于 [Douyin_Spider](https://github.com/cvv-cat/Douyin_Spider) 二次开发，专注神秘人识别场景。仅供学习与技术研究使用。
