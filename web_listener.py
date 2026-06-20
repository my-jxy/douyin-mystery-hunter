"""抖音神秘人猎人 - Web 版 🎯
Flask Web 服务，手机浏览器访问，实时监听直播神秘人。
"""
import sys, os, time, gzip, json, threading, queue, re, requests, urllib3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder
from utils.dy_util import generate_signature
from dy_apis.douyin_api import DouyinAPI
from urllib.parse import urlencode
from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2

from flask import Flask, Response, request, jsonify, render_template

app = Flask(__name__)

# ========== 工具函数 ==========
GENDER_MAP = {0: '未设置', 1: '男', 2: '女'}
_TTWID = cu.dy_live_auth.cookie.get('ttwid', '')
_user_info_cache = {}
_level_cache = {}
_last_api_call = 0  # 限流时间戳
_record_all_enabled = True  # 全局录制开关：True=记录所有用户，False=仅记录神秘人（默认开启，监听即记录）
_private_name_cache = {}  # (room_id:display) -> real_nickname, 私密直播间送礼拿到真实名后缓存

# ========== SQLite 持久化 ==========
import sqlite3
_DB_PATH = '/home/admin/douyin-mystery-hunter/mystery_history.db'

def _init_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mystery_records (
            sec_uid TEXT NOT NULL,
            display TEXT,
            real_name TEXT DEFAULT '',
            nickname TEXT DEFAULT '',
            extra TEXT DEFAULT '{}',
            last_room_id TEXT DEFAULT '',
            seen_room_ids TEXT DEFAULT '',
            first_seen INTEGER DEFAULT 0,
            last_seen INTEGER DEFAULT 0,
            enter_count INTEGER DEFAULT 0,
            gift_count INTEGER DEFAULT 0,
            chat_count INTEGER DEFAULT 0,
            is_regular INTEGER DEFAULT 0,
            PRIMARY KEY (sec_uid, display)
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_mr_last_room ON mystery_records(last_room_id)
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS display_names (
            sec_uid TEXT NOT NULL,
            display TEXT NOT NULL,
            seen_count INTEGER DEFAULT 1,
            first_seen INTEGER DEFAULT 0,
            last_seen INTEGER DEFAULT 0,
            PRIMARY KEY (sec_uid, display)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS interaction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            sec_uid TEXT NOT NULL,
            display TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT DEFAULT '',
            gift_count INTEGER DEFAULT 1,
            timestamp INTEGER NOT NULL
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_interaction_log
        ON interaction_log(sec_uid, timestamp)
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS room_search_history (
            input_text TEXT PRIMARY KEY,
            nickname TEXT NOT NULL DEFAULT '',
            room_id TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

_init_db()

def _save_mystery_record(room_id, sec_uid, display, real_name, extra, event_type, timestamp=None, is_regular=0, room_nickname=None, is_private=False):
    """保存或更新记录。无 sec_uid 的匿名用户不存储"""
    if not sec_uid:
        return
    # 私密房：即使神秘人也标为普通用户，不进历史页
    if is_private:
        is_regular = 1
    if timestamp is None:
        timestamp = int(time.time())
    if extra and isinstance(extra, dict) and extra.get('nickname'):
        if not real_name or real_name == display:
            real_name = extra['nickname']
    try:
        extra = dict(extra or {})
        if room_nickname:
            extra['room_nickname'] = room_nickname
        conn = sqlite3.connect(_DB_PATH)
        
        if sec_uid:
            # 收集同一 sec_uid 所有旧记录的累积数据
            old_rows = conn.execute(
                'SELECT real_name, extra, seen_room_ids, enter_count, gift_count, chat_count FROM mystery_records WHERE sec_uid=?',
                (sec_uid,)
            ).fetchall()
            
            merged_seen = set()
            merged_enter = 0
            merged_gift = 0
            merged_chat = 0
            best_real_name = real_name
            merged_extra = dict(extra)
            for old in old_rows:
                if old[2]:
                    for rid in old[2].split(','):
                        if rid:
                            merged_seen.add(rid)
                merged_enter += old[3] or 0
                merged_gift += old[4] or 0
                merged_chat += old[5] or 0
                old_rn = (old[0] or '').strip()
                if old_rn and not old_rn.startswith('dou') and not old_rn.startswith('神秘人'):
                    if (not best_real_name) or best_real_name.startswith('dou') or best_real_name.startswith('神秘人'):
                        best_real_name = real_name = old_rn
                if old[1]:
                    try:
                        old_extra = json.loads(old[1]) if isinstance(old[1], str) else old[1]
                        for k, v in old_extra.items():
                            if not merged_extra.get(k):
                                merged_extra[k] = v
                    except:
                        pass
            
            # 删掉所有旧记录
            conn.execute('DELETE FROM mystery_records WHERE sec_uid=?', (sec_uid,))
            
            real_name = best_real_name or real_name
            extra = merged_extra
            enter_count = merged_enter
            gift_count = merged_gift
            chat_count = merged_chat
            seen_room_ids = merged_seen
        else:
            # 匿名用户：按 display 处理，不跨 display 合并
            enter_count = 0
            gift_count = 0
            chat_count = 0
            seen_room_ids = set()
        
        if room_id:
            seen_room_ids.add(str(room_id))
        seen_room_ids_str = ','.join(sorted(seen_room_ids))
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else '{}'
        
        # 按事件类型累加本次计数
        add_enter = 1 if event_type == 'enter' else 0
        add_gift = 1 if event_type == 'gift' else 0
        add_chat = 1 if event_type == 'chat' else 0
        
        conn.execute('''
            INSERT INTO mystery_records (sec_uid, display, real_name, extra, last_room_id, seen_room_ids,
                first_seen, last_seen, is_regular, enter_count, gift_count, chat_count, nickname)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sec_uid or '', display or '', real_name, extra_json,
              str(room_id) if room_id else '', seen_room_ids_str,
              timestamp, timestamp, is_regular,
              enter_count + add_enter, gift_count + add_gift, chat_count + add_chat,
              room_nickname or ''))
        
        # display_name 记录：私密房跳过（马甲无编号无意义）
        if not is_private:
            conn.execute('''
                INSERT INTO display_names (sec_uid, display, first_seen, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sec_uid, display) DO UPDATE SET
                    seen_count = seen_count + 1,
                    last_seen = MAX(last_seen, ?)
            ''', (sec_uid or '', display or '', timestamp, timestamp, timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] _save_mystery_record 失败: {e}", flush=True)

def _save_interaction(room_id, sec_uid, display, i_type, content='', gift_count=1, timestamp=None):
    """保存单条互动记录（聊天/送礼）"""
    if not room_id or not sec_uid:
        return
    if timestamp is None:
        timestamp = int(time.time())
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.execute('''
            INSERT INTO interaction_log (room_id, sec_uid, display, type, content, gift_count, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, sec_uid, display, i_type, content, gift_count, timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] interaction save error: {e}", flush=True)

def _load_room_history(room_id):
    """加载某个直播间所有历史记录（仅神秘人）"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # 查询该房间出现过的所有神秘人（seen_room_ids 包含 room_id）
        cur = conn.execute('''
            SELECT * FROM mystery_records
            WHERE is_regular = 0
            ORDER BY last_seen DESC
        ''')
        all_rows = [dict(r) for r in cur.fetchall()]
        
        # 过滤：seen_room_ids 包含该 room_id
        rows = []
        for r in all_rows:
            seen = (r.get('seen_room_ids') or '').split(',')
            if str(room_id) in seen:
                rows.append(r)
        
        # 拉取所有相关的 display_names
        if rows:
            all_sec_uids = list(set(r['sec_uid'] for r in rows if r.get('sec_uid')))
            placeholders = ','.join('?' * len(all_sec_uids)) if all_sec_uids else "'none'"
            cur2 = conn.execute(f'''
                SELECT sec_uid, display, last_seen, seen_count
                FROM display_names
                WHERE sec_uid IN ({placeholders})
            ''', all_sec_uids if all_sec_uids else [])
            dn_rows = cur2.fetchall()
        else:
            dn_rows = []
        
        conn.close()
        
        # 按 sec_uid 分组，合并 display_names
        display_map = {}
        for d in dn_rows:
            key = d['sec_uid']
            if key not in display_map:
                display_map[key] = []
            display_map[key].append({'display': d['display'], 'last_seen': d['last_seen'], 'seen_count': d['seen_count']})
        
        merged = {}
        for row in rows:
            key = row['sec_uid']
            if key not in merged:
                row['displays'] = sorted(display_map.get(key, []), key=lambda x: x['last_seen'], reverse=True)
                if row.get('extra'):
                    try:
                        row['extra'] = json.loads(row['extra'])
                    except:
                        row['extra'] = {}
                row['is_current'] = False
                merged[key] = row
            else:
                existing = merged[key]
                if (row.get('last_seen') or 0) > (existing.get('last_seen') or 0):
                    existing['last_seen'] = row['last_seen']
        
        result = list(merged.values())
        for item in result:
            ex = item.get('extra')
            if isinstance(ex, dict) and ex.get('room_nickname'):
                item['room_nickname'] = ex['room_nickname']
        result.sort(key=lambda x: x.get('last_seen', 0) or 0, reverse=True)
        return result
    except Exception as e:
        print(f"[DB] load error: {e}", flush=True)
        return []

def gender_str(g):
    return GENDER_MAP.get(g, '未知')

def user_id_str(user):
    return (getattr(user, 'unique_id', '') or
            getattr(user, 'display_id', '') or
            str(user.short_id or '?'))

def get_badge_level(user):
    try:
        for badge in user.badge_image_list:
            c = badge.content if hasattr(badge, 'content') else None
            if c and hasattr(c, 'level') and c.level:
                sec_uid = getattr(user, 'sec_uid', None)
                if sec_uid: _level_cache[sec_uid] = c.level
                return c.level
    except: pass
    sec_uid = getattr(user, 'sec_uid', None)
    if sec_uid and sec_uid in _level_cache:
        return _level_cache[sec_uid]
    return 0

def lookup_user(sec_uid):
    global _last_api_call
    if sec_uid in _user_info_cache: return _user_info_cache[sec_uid]
    if not sec_uid or len(sec_uid) < 10: return {}
    for attempt in range(3):
        try:
            # 限流：两次API调用至少间隔0.3秒
            elapsed = time.time() - _last_api_call
            if elapsed < 0.3:
                time.sleep(0.3 - elapsed)
            _last_api_call = time.time()
            params = {'device_platform': 'webapp', 'aid': '6383',
                      'sec_user_id': sec_uid, 'version_code': '170400', 'msToken': ''}
            headers = {'User-Agent': 'Mozilla/5.0 ... Chrome/116.0.0.0',
                       'Referer': f'https://www.douyin.com/user/{sec_uid}'}
            resp = requests.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
                                params=params, headers=headers,
                                cookies={'ttwid': _TTWID}, verify=False, timeout=8)
            j = resp.json()
            if j.get('status_code') == 0 and 'user' in j:
                u = j['user']
                info = {'nickname': u.get('nickname','?'),
                        'unique_id': u.get('unique_id') or u.get('short_id','?'),
                        'ip_location': u.get('ip_location',''),
                        'follower_count': u.get('follower_count',0),
                        'following_count': u.get('following_count',0),
                        'total_favorited': u.get('total_favorited',0),
                        'aweme_count': u.get('aweme_count',0),
                        'signature': (u.get('signature') or '')[:100]}
                _user_info_cache[sec_uid] = info
                return info
            else:
                raise Exception(f"status_code={j.get('status_code')}")
        except Exception as e:
            print(f"[WARN] lookup_user 第{attempt+1}次失败({sec_uid}): {e}", flush=True)
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
    # 查询失败不缓存空结果，下次重试
    return {}

def is_real_mystery_user(user):
    display = (user.desensitized_nickname or '').strip()
    real_name = (user.nickname or '').strip()
    mystery_man = getattr(user, 'mystery_man', 0)
    is_masked = display.startswith('神秘人') and len(display) > 3
    is_dou_mystery = ((display.startswith('dou') and len(display) > 5) or
                      (real_name.startswith('dou') and len(real_name) > 5))
    is_deep = mystery_man >= 2
    return is_masked or is_dou_mystery or is_deep, display, real_name, mystery_man

def get_room_id_by_douyin_id(douyin_id):
    """通过抖音号/链接获取 room_id"""
    # 抖音号（纯数字或字母数字组合）→ 用旧版v2 API查
    if re.match(r'^[a-zA-Z0-9_]+$', douyin_id) and not douyin_id.startswith('http'):
        try:
            _auth_cookies = dict(cu.dy_live_auth.cookie)
            resp = requests.get('https://www.douyin.com/web/api/v2/user/info/',
                params={'unique_id': douyin_id},
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                         'Referer': 'https://www.douyin.com/'},
                cookies=_auth_cookies, verify=False, timeout=10)
            j = resp.json()
            if j.get('status_code') == 0 and 'user_info' in j:
                sec_uid = j['user_info']['sec_uid']
                nickname = j['user_info']['nickname']
                # 查直播状态
                resp2 = requests.get('https://www.douyin.com/aweme/v1/web/user/profile/other/',
                    params={'device_platform': 'webapp', 'aid': '6383',
                            'sec_user_id': sec_uid, 'version_code': '170400', 'msToken': ''},
                    headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
                             'Referer': f'https://www.douyin.com/user/{sec_uid}'},
                    cookies={'ttwid': _TTWID}, verify=False, timeout=10)
                j2 = resp2.json()
                if j2.get('status_code') == 0 and 'user' in j2:
                    u = j2['user']
                    return {'success': True, 'nickname': nickname,
                            'room_id': str(u.get('room_id', 0)),
                            'live_status': u.get('live_status', 0),
                            'sec_uid': sec_uid}
        except: pass
        return {'success': False, 'error': '查询失败，请检查抖音号是否存在'}
    # v.douyin.com 短链接
    match = re.search(r'v\.douyin\.com/(\w+)', douyin_id)
    if match:
        try:
            resp = requests.head(f'https://{match.group(0)}', allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            url = resp.url
            rid = re.search(r'/(\d+)\??', url)
            if rid: return {'success': True, 'room_id': rid.group(1), 'type': 'live', 'live_status': 1}
            # 可能是用户主页 → 提取 sec_uid 查直播状态
            sec = re.search(r'sec_uid=([^&]+)', url)
            if sec:
                sec_uid = sec.group(1)
                try:
                    _auth_cookies = dict(cu.dy_live_auth.cookie)
                    resp2 = requests.get(
                        'https://www.douyin.com/aweme/v1/web/user/profile/other/',
                        params={'device_platform': 'webapp', 'aid': '6383',
                                'sec_user_id': sec_uid, 'version_code': '170400', 'msToken': ''},
                        headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
                                 'Referer': f'https://www.douyin.com/user/{sec_uid}'},
                        cookies={'ttwid': _TTWID}, verify=False, timeout=10)
                    j2 = resp2.json()
                    if j2.get('status_code') == 0 and 'user' in j2:
                        u = j2['user']
                        return {'success': True, 'nickname': u.get('nickname', ''),
                                'room_id': str(u.get('room_id', 0)),
                                'live_status': u.get('live_status', 0),
                                'sec_uid': sec_uid}
                except: pass
                return {'success': True, 'sec_uid': sec_uid, 'live_status': 0,
                        'room_id': '0', 'nickname': ''}
        except: pass
    # 直接是数字→当做room_id
    if douyin_id.isdigit():
        return {'success': True, 'room_id': douyin_id, 'type': 'room'}
    return {'success': False, 'error': '无法解析链接或抖音号'}

# ========== 房间监听器 ==========
listeners = {}

class RoomListener:
    def __init__(self, room_id, nickname='', sec_uid=''):
        self.room_id = room_id
        self.nickname = nickname
        self.sec_uid = sec_uid
        self.events = queue.Queue()
        self.running = False
        self.thread = None
        self.ws = None
        self.mystery_count = 0
        self.recent_mysteries = []
        self._mystery_seq = 0
        self.is_private = False  # 是否为隐私直播间（sec_uid 为空即匿名模式）
        self.last_msg_time = time.time()  # 最后收到消息的时间，用于下播检测

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.running = False
        if self.ws:
            try: self.ws.close()
            except: pass

    def send_event(self, event_type, data):
        self.events.put({'type': event_type, 'data': data, 'time': time.time()})

    def _write_all_user(self, info):
        try:
            # 写入 SQLite
            extra = info.get('extra') or {}
            if info.get('unique_id') and not extra.get('unique_id'):
                extra['unique_id'] = info['unique_id']
            _save_mystery_record(
                info.get('room_id', self.room_id),
                info.get('sec_uid', '') or '',
                info.get('display', '') or '',
                info.get('real_name', '') or extra.get('nickname', '') or '',
                extra,
                info.get('event_type', 'enter'),
                is_regular=1,
                room_nickname=self.nickname
            )
        except:
            pass

    def _run(self):
        # ====== 匿名模式检测（在 WS 连接之前，只检测一次） ======
        if not self.is_private:
            try:
                _resp = requests.get(f'https://live.douyin.com/{self.room_id}',
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    cookies=cu.dy_live_auth.cookie, verify=False, timeout=10)
                if 'live_room_mode' in _resp.text and ':1' in _resp.text.split('live_room_mode')[1][:20]:
                    self.is_private = True
                    self.send_event('room_anonymous', {
                        'message': '当前为匿名模式直播间，仅能通过<b>礼物</b>获取用户真实身份。<br>识别到的用户请点击上方 <b>「📋全部」</b> 按钮查看，不会存入「📜历史」。'
                    })
                    print(f"[匿名] 房间 {self.room_id} 为匿名模式，仅处理礼物", flush=True)
            except Exception as e:
                print(f"[匿名检测] {self.room_id} 失败: {e}", flush=True)

        reconnect_attempts = 0
        max_reconnects = 5
        while self.running and reconnect_attempts < max_reconnects:
            try:
                user_unique_id = cu.dy_live_auth.cookie.get('uid', '7638929563125138984')
                auth = cu.dy_live_auth

                # ====== 先调 get_webcast_detail 拿真实 cursor + internalExt ======
                try:
                    _ws_init = DouyinAPI.get_webcast_detail(
                        auth, str(user_unique_id), self.room_id,
                        f"https://live.douyin.com/{self.room_id}"
                    )
                    _init_frame = Live_pb2.LiveResponse()
                    _init_frame.ParseFromString(_ws_init)
                    _cursor = str(_init_frame.cursor)
                    _internal_ext = _init_frame.internalExt
                except Exception as e:
                    print(f"[WARN] get_webcast_detail failed: {e}, using defaults")
                    _cursor = '-1'
                    _internal_ext = ''

                sig = generate_signature(self.room_id, user_unique_id)

                params = Params()
                (params.add_param('app_name','douyin_web').add_param('version_code','180800')
                 .add_param('webcast_sdk_version','1.0.15').add_param('update_version_code','1.0.15')
                 .add_param('compress','gzip').add_param('device_platform','web')
                 .add_param('cookie_enabled','true').add_param('screen_width','1707')
                 .add_param('screen_height','960').add_param('browser_language','zh-CN')
                 .add_param('browser_platform','Win32').add_param('browser_name','Mozilla')
                 .add_param('browser_version',HeaderBuilder.ua.split('Mozilla/')[-1])
                 .add_param('browser_online','true').add_param('tz_name','Etc/GMT-8')
                 .add_param('cursor', _cursor).add_param('host','https://live.douyin.com')
                 .add_param('aid','6383').add_param('live_id','1').add_param('did_rule','3')
                 .add_param('endpoint','live_pc').add_param('support_wrds','1')
                 .add_param('user_unique_id',user_unique_id).add_param('im_path','/webcast/im/fetch/')
                 .add_param('identity','audience').add_param('need_persist_msg_count','15')
                 .add_param('insert_task_id','').add_param('live_reason','')
                 .add_param('room_id',self.room_id).add_param('heartbeatDuration','0')
                 .add_param('signature',sig))
                if _internal_ext:
                    params.add_param('internal_ext', _internal_ext)

                wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"

                def on_message(ws, message):
                    try:
                        frame = Live_pb2.PushFrame()
                        frame.ParseFromString(message)
                        origin_bytes = gzip.decompress(frame.payload)
                        response = Live_pb2.LiveResponse()
                        response.ParseFromString(origin_bytes)

                        if response.needAck:
                            s = Live_pb2.PushFrame()
                            s.payloadType = "ack"
                            s.payload = response.internalExt.encode('utf-8')
                            s.logId = frame.logId
                            ws.send(s.SerializeToString(), opcode=0x02)

                        for item in response.messagesList:
                            self.last_msg_time = time.time()
                            if item.method == 'WebcastMemberMessage':
                                # 匿名模式：跳过进入事件，只等礼物
                                if self.is_private:
                                    continue
                                msg = Live_pb2.MemberMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                # 私密直播间：先查缓存（不管是不是神秘人，只要sec_uid为空就查）
                                extra = None
                                if not user.sec_uid:
                                    self.is_private = True
                                    cached = _private_name_cache.get(f"{self.room_id}:{display}")
                                    if cached:
                                        print(f"[CACHE] 缓存命中: {display} -> {cached.get('nickname','?')}", flush=True)
                                        extra = cached
                                    else:
                                        print(f"[CACHE] 缓存未命中(enter): {self.room_id}:{display}", flush=True)
                                if is_mystery:
                                    if not extra:
                                        extra = lookup_user(user.sec_uid)
                                    if extra and extra.get('nickname') and extra['nickname'] == display:
                                        is_mystery = False
                                if is_mystery:
                                    self._mystery_seq += 1
                                    badge_lv = get_badge_level(user)
                                    uid = user_id_str(user) or (extra.get('unique_id','') if extra else '')
                                    info = {'display': display, 'real_name': real_name,
                                            'unique_id': uid, 'sec_uid': user.sec_uid,
                                            'gender': gender_str(user.gender),
                                            'consume_level': user.consume_diamond_level,
                                            'badge_level': badge_lv, 'mystery_man': mm,
                                            'mystery_seq': self._mystery_seq,
                                            'is_regular': False}
                                    self.mystery_count += 1
                                    self.recent_mysteries.append(info)
                                    if extra:
                                        if extra.get('nickname') and extra['nickname'] != real_name:
                                            info['real_name'] = extra['nickname']
                                        info['extra'] = extra
                                    # 私密房无身份 → 不推送不保存
                                    has_id = bool(user.sec_uid) or (extra and extra.get('sec_uid'))
                                    if has_id or not self.is_private:
                                        _save_mystery_record(self.room_id, user.sec_uid or '', display, info['real_name'], extra, 'enter', room_nickname=self.nickname, is_private=self.is_private)
                                        info['room_id'] = self.room_id
                                        info['room_nickname'] = self.nickname
                                        self.send_event('mystery_enter', info)
                                elif _record_all_enabled:
                                    # 私密直播间：用缓存补全真实名
                                    if extra and extra.get('nickname'):
                                        real_name = extra['nickname']
                                    info = {'display': display, 'real_name': real_name,    
                                            'unique_id': user_id_str(user), 'sec_uid': user.sec_uid,
                                            'gender': gender_str(user.gender),
                                            'consume_level': user.consume_diamond_level,
                                            'badge_level': get_badge_level(user), 'mystery_man': mm,
                                            'is_regular': True, 'event_type': 'enter'}
                                    if extra:
                                        info['extra'] = extra
                                    info['room_id'] = self.room_id
                                    info['room_nickname'] = self.nickname
                                    self._write_all_user(info)
                                    self.send_event('mystery_enter', info)

                            elif item.method == 'WebcastChatMessage':
                                # 匿名模式：跳过聊天事件，只等礼物
                                if self.is_private:
                                    continue
                                msg = Live_pb2.ChatMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                # 私密直播间：先查缓存
                                extra = None
                                if not user.sec_uid:
                                    self.is_private = True
                                    cached = _private_name_cache.get(f"{self.room_id}:{display}")
                                    if cached:
                                        print(f"[CACHE] 缓存命中(chat): {display} -> {cached.get('nickname','?')}", flush=True)
                                        extra = cached
                                    else:
                                        print(f"[CACHE] 缓存未命中(chat): {self.room_id}:{display}", flush=True)
                                if is_mystery:
                                    if not extra:
                                        extra = lookup_user(user.sec_uid)
                                    if extra and extra.get('nickname') and extra['nickname'] == display:
                                        is_mystery = False
                                if is_mystery:
                                    badge_lv = get_badge_level(user)
                                    uid = user_id_str(user) or (extra.get('unique_id','') if extra else '')
                                    chat_info = {
                                        'display': display, 'real_name': real_name,
                                        'content': msg.content, 'sec_uid': user.sec_uid,
                                        'badge_level': badge_lv,
                                        'consume_level': user.consume_diamond_level,
                                        'unique_id': uid,
                                        'mystery_man': mm,
                                        'is_regular': False}
                                    if extra:
                                        if extra.get('nickname') and extra['nickname'] != real_name:
                                            chat_info['real_name'] = extra['nickname']
                                        chat_info['extra'] = extra
                                    # 私密房无身份 → 不推送不保存
                                    has_id = bool(user.sec_uid) or (extra and extra.get('sec_uid'))
                                    if has_id or not self.is_private:
                                        chat_info['room_id'] = self.room_id
                                        chat_info['room_nickname'] = self.nickname
                                        _save_mystery_record(self.room_id, user.sec_uid or '', display, real_name, extra, 'chat', room_nickname=self.nickname, is_private=self.is_private)
                                        _save_interaction(self.room_id, user.sec_uid or '', display, 'chat', content=msg.content)
                                        self.send_event('mystery_chat', chat_info)
                                elif _record_all_enabled:
                                    # 私密直播间：用缓存补全真实名
                                    if extra and extra.get('nickname'):
                                        chat_real_name = extra['nickname']
                                    else:
                                        chat_real_name = real_name
                                    chat_info = {
                                        'display': display, 'real_name': chat_real_name,
                                        'content': msg.content, 'sec_uid': user.sec_uid,
                                        'badge_level': get_badge_level(user),
                                        'consume_level': user.consume_diamond_level,
                                        'unique_id': user_id_str(user),
                                        'is_regular': True, 'event_type': 'chat'}
                                    if extra:
                                        chat_info['extra'] = extra
                                    chat_info['room_id'] = self.room_id
                                    chat_info['room_nickname'] = self.nickname
                                    self._write_all_user(chat_info)
                                    _save_interaction(self.room_id, user.sec_uid or '', display, 'chat', content=msg.content)
                                    self.send_event('mystery_chat', chat_info)

                            elif item.method == 'WebcastGiftMessage':
                                try:
                                    msg = Live_pb2.GiftMessage()
                                    msg.ParseFromString(item.payload)
                                    user = msg.user
                                    is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                    # 仅隐私直播间：送礼时查 API 获取真实名
                                    extra = None
                                    if self.is_private and user.sec_uid:
                                        extra = lookup_user(user.sec_uid)
                                        if extra and extra.get('nickname'):
                                            print(f"[CACHE] 缓存写入: room={self.room_id} display={display} -> {extra.get('nickname','?')}", flush=True)
                                            if extra.get('nickname') != real_name:
                                                real_name = extra['nickname']
                                            extra['sec_uid'] = user.sec_uid
                                            _private_name_cache[f"{self.room_id}:{display}"] = extra
                                    if is_mystery:
                                        if extra and extra.get('nickname') and extra['nickname'] == display:
                                            is_mystery = False
                                    if is_mystery:
                                        uid = user_id_str(user) or (extra.get('unique_id','') if extra else '')
                                        gift_info = {
                                            'display': display, 'real_name': real_name,
                                            'sec_uid': user.sec_uid, 'gift_name': msg.gift.name if msg.gift else '?',
                                            'count': msg.comboCount,
                                            'badge_level': get_badge_level(user),
                                            'consume_level': user.consume_diamond_level,
                                            'unique_id': uid,
                                            'is_regular': False}
                                        if extra:
                                            gift_info['extra'] = extra
                                        # 私密房无身份 → 不推送不保存
                                        has_id = bool(user.sec_uid) or (extra and extra.get('sec_uid'))
                                        if has_id or not self.is_private:
                                            gift_info['room_id'] = self.room_id
                                            gift_info['room_nickname'] = self.nickname
                                            _save_mystery_record(self.room_id, user.sec_uid or '', display, real_name, extra, 'gift', room_nickname=self.nickname, is_private=self.is_private)
                                            _save_interaction(self.room_id, user.sec_uid or '', display, 'gift', content=msg.gift.name if msg.gift else '?', gift_count=msg.comboCount)
                                            self.send_event('mystery_gift', gift_info)
                                    elif _record_all_enabled:
                                        has_id = bool(user.sec_uid) or (extra and extra.get('sec_uid'))
                                        if has_id or not self.is_private:
                                            # 私密直播间：用缓存补全真实名
                                            if extra and extra.get('nickname') and extra['nickname'] != display:
                                                gift_real_name = extra['nickname']
                                            else:
                                                gift_real_name = real_name
                                            gift_info = {
                                                'display': display, 'real_name': gift_real_name,
                                                'sec_uid': user.sec_uid, 'gift_name': msg.gift.name if msg.gift else '?',
                                                'count': msg.comboCount,
                                                'badge_level': get_badge_level(user),
                                                'consume_level': user.consume_diamond_level,
                                                'unique_id': user_id_str(user),
                                                'is_regular': True, 'event_type': 'gift'}
                                            if extra:
                                                gift_info['extra'] = extra
                                            gift_info['room_id'] = self.room_id
                                            gift_info['room_nickname'] = self.nickname
                                            self._write_all_user(gift_info)
                                            _save_interaction(self.room_id, user.sec_uid or '', display, 'gift', content=msg.gift.name if msg.gift else '?', gift_count=msg.comboCount)
                                            self.send_event('mystery_gift', gift_info)
                                except Exception:
                                    pass

                            elif item.method == 'WebcastRoomStatsMessage':
                                pass  # 忽略在线/累计，不刷屏

                            elif item.method == 'WebcastRoomRankMessage':
                                pass  # 忽略排行榜，不刷屏

                            elif item.method == 'WebcastRoomUserSeqMessage':
                                pass  # 忽略榜一二三，不刷屏

                    except: pass

                def on_open(ws):
                    reconnect_attempts = 0  # 连接成功，重置重试计数
                    self.send_event('connected', {'room_id': self.room_id, 'nickname': self.nickname})
                    def ping():
                        while self.running:
                            try:
                                # 每30秒检查一次下播（如果超过3分钟没收到消息）
                                if time.time() - self.last_msg_time > 180:
                                    try:
                                        info = DouyinAPI.get_live_info(cu.dy_live_auth, str(self.room_id))
                                        if not info or not isinstance(info, dict) or info.get('room_status') != '2':
                                            self.send_event('room_offline', {'room_id': self.room_id, 'nickname': self.nickname, 'mystery_count': self.mystery_count})
                                            self.running = False
                                            break
                                    except:
                                        pass
                                f = Live_pb2.PushFrame()
                                f.payloadType = "hb"
                                ws.send(f.SerializeToString(), opcode=0x02)
                                time.sleep(10)
                            except: break
                    threading.Thread(target=ping, daemon=True).start()

                def on_close(ws, code, msg):
                    if self.running:
                        self.send_event('disconnected', {'reconnecting': True, 'code': code})
                    else:
                        self.send_event('disconnected', {'code': code, 'mystery_count': self.mystery_count})

                def on_error(ws, error):
                    self.send_event('error', {'error': str(error)})

                self.ws = WebSocketApp(url=wss_url,
                    header={'Pragma':'no-cache','Accept-Language':'zh-CN,zh;q=0.9',
                            'User-Agent':HeaderBuilder.ua,
                            'Upgrade':'websocket','Cache-Control':'no-cache','Connection':'Upgrade'},
                    cookie=auth.cookie_str,
                    on_message=on_message, on_open=on_open,
                    on_error=on_error, on_close=on_close)
                self.ws.run_forever(origin='https://live.douyin.com')

                if self.running:
                    # 检查直播间是否还在播，防止下播后无限重连
                    try:
                        info = DouyinAPI.get_live_info(cu.dy_live_auth, str(self.room_id))
                        if not info or not isinstance(info, dict) or info.get('room_status') != '2':
                            self.send_event('room_offline', {'room_id': self.room_id, 'nickname': self.nickname, 'mystery_count': self.mystery_count})
                            self.running = False
                            break
                    except Exception:
                        pass

                    reconnect_attempts += 1
                    time.sleep(5)
            except Exception as e:
                if self.running:
                    self.send_event('error', {'error': f'连接异常: {str(e)}'})
                    time.sleep(5)

# ========== Flask 路由 ==========

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/resolve', methods=['POST'])
def resolve():
    """解析抖音号/链接，返回直播间信息"""
    data = request.get_json()
    if not data or 'input' not in data:
        return jsonify({'success': False, 'error': '请输入抖音号或链接'})
    result = get_room_id_by_douyin_id(data['input'].strip())
    return jsonify(result)

@app.route('/api/start', methods=['POST'])
def start_listen():
    """开始监听直播间（最多3个同时）"""
    data = request.get_json()
    room_id = data.get('room_id', '')
    nickname = data.get('nickname', '')
    if not room_id:
        return jsonify({'success': False, 'error': '缺少room_id'})

    # 检查是否已在监听
    if room_id in listeners and listeners[room_id].running:
        return jsonify({'success': True, 'room_id': room_id, 'already': True})

    # 检查数量限制
    # 🔧 同时监听上限，修改下面 `3` 即可调整
    # 性能说明：
    #   - 每个直播间 = 一个 Python 线程 + 一个 WebSocket 连接
    #   - 内存消耗：约 20-30MB / 每直播间
    #   - CPU 占用：几乎为零（空闲状态），消息多时约 1-5%
    #   - 网络：每个房间一个 WebSocket 长连接，流量极小
    #   - 主要瓶颈在抖音 API 限流（查询神秘人身份），与房间数量无关
    #   - 推荐上限：普通手机 5-8 个，云服务器/电脑 10-20 个
    MAX_ROOMS = 3  # ← 改这个数字即可调整上限
    running_count = sum(1 for l in listeners.values() if l.running)
    if running_count >= MAX_ROOMS:
        return jsonify({'success': False, 'error': f'最多同时监听{MAX_ROOMS}个直播间，请先停止一个再试'})

    listener = RoomListener(room_id, nickname)
    listeners[room_id] = listener
    
    # 从数据库加载该房间之前抓到的神秘人，回放到事件流
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute('''
            SELECT * FROM mystery_records
            WHERE is_regular = 0
            ORDER BY first_seen ASC
            LIMIT 100
        ''')
        all_db = [dict(r) for r in cur.fetchall()]
        # 过滤：seen_room_ids 包含当前 room_id
        db_records = []
        for r in all_db:
            seen = (r.get('seen_room_ids') or '').split(',')
            if str(room_id) in seen:
                db_records.append(r)
        conn.close()
        
        seq = 0
        for r in db_records:
            seq += 1
            extra = {}
            if r.get('extra'):
                try:
                    extra = json.loads(r['extra']) if isinstance(r['extra'], str) else r['extra']
                except:
                    extra = {}
            # 不再需要跨房间合并——DB 中已自然合并
            replay_info = {
                'display': r['display'],
                'real_name': r['real_name'] or r['display'],
                'unique_id': extra.get('unique_id', ''),
                'sec_uid': r['sec_uid'],
                'gender': '未知',
                'consume_level': 0,
                'badge_level': 0,
                'mystery_man': False,
                'mystery_seq': seq,
                'is_regular': False,
                'extra': extra,
                'room_id': room_id,
                'room_nickname': nickname,
            }
            listener.recent_mysteries.append(replay_info)
            listener.send_event('mystery_enter', replay_info)
        listener.mystery_count = len(db_records)
        if seq > 0:
            print(f"[回放] 房间 {room_id} 已回放 {seq} 条历史神秘人记录", flush=True)
    except Exception as e:
        print(f"[回放] 加载失败: {e}", flush=True)
    
    listener.start()
    return jsonify({'success': True, 'room_id': room_id, 'active': running_count + 1, 'max': MAX_ROOMS})

@app.route('/api/stop', methods=['POST'])
def stop_listen():
    """停止指定监听"""
    data = request.get_json()
    room_id = data.get('room_id', '')
    ua = request.headers.get('User-Agent', 'unknown')
    print(f"[操作] 停止监听 room={room_id} | UA: {ua[:120]}", flush=True)
    if room_id in listeners:
        listeners[room_id].stop()
        del listeners[room_id]
        return jsonify({'success': True, 'room_id': room_id})
    return jsonify({'success': False, 'error': '未找到该监听'})

@app.route('/api/stop_all', methods=['POST'])
def stop_all():
    """停止所有监听"""
    ua = request.headers.get('User-Agent', 'unknown')
    print(f"[操作] 停止全部监听 | UA: {ua[:120]}", flush=True)
    for rid, listener in list(listeners.items()):
        listener.stop()
    listeners.clear()
    return jsonify({'success': True})

@app.route('/api/status')
def status():
    """查看所有监听器状态"""
    result = {'active': [], 'count': 0, 'max': 3}
    for rid, listener in listeners.items():
        if listener.running:
            result['active'].append({
                'room_id': rid,
                'nickname': listener.nickname,
                'mystery_count': listener.mystery_count,
                'unique_count': len(set(m.get('sec_uid') for m in listener.recent_mysteries if m.get('sec_uid'))),
            })
    result['count'] = len(result['active'])
    return jsonify(result)

@app.route('/api/toggle_record_all', methods=['POST'])
def toggle_record_all():
    """开关：记录全部用户（仅后端记录，前端仍只显示神秘人）"""
    global _record_all_enabled
    data = request.get_json()
    _record_all_enabled = data.get('enabled', False)
    return jsonify({'success': True, 'record_all': _record_all_enabled})

@app.route('/api/record_all_status')
def record_all_status():
    """获取当前录制状态"""
    return jsonify({'record_all': _record_all_enabled})

@app.route('/api/real_names')
def real_names():
    """返回所有已缓存的真实昵称映射（sec_uid → 信息）"""
    return jsonify({
        'success': True,
        'users': _user_info_cache,
        'private_names': {k: v for k, v in _private_name_cache.items()},
        'count': len(_user_info_cache)
    })

@app.route('/api/history_rooms')
def history_rooms():
    """返回有历史记录的直播间列表"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        cur = conn.execute('''
            SELECT last_room_id, seen_room_ids, last_seen, extra
            FROM mystery_records WHERE is_regular = 0
            ORDER BY last_seen DESC
        ''')
        # 从 seen_room_ids + last_room_id 重建房间列表
        room_map = {}  # room_id -> {last_seen, count}
        for r in cur.fetchall():
            last_room = r[0]
            seen = (r[1] or '').split(',')
            last_seen = r[2]
            # 所有出现过的房间
            all_rooms = set(seen)
            if last_room:
                all_rooms.add(last_room)
            for rid in all_rooms:
                if not rid:
                    continue
                if rid not in room_map:
                    room_map[rid] = {'room_id': rid, 'last_seen': last_seen, 'mystery_count': 0}
                if (last_seen or 0) > (room_map[rid]['last_seen'] or 0):
                    room_map[rid]['last_seen'] = last_seen
                room_map[rid]['mystery_count'] += 1
        conn.close()
        rooms = sorted(room_map.values(), key=lambda x: x['last_seen'] or 0, reverse=True)
        # 补上房间昵称
        for r in rooms:
            listener = listeners.get(r['room_id'])
            if listener and listener.nickname:
                r['nickname'] = listener.nickname
            else:
                r['short_id'] = r['room_id'][:8]
        # 从数据库恢复房间昵称
        conn2 = sqlite3.connect(_DB_PATH)
        for r in rooms:
            cur2 = conn2.execute(
                "SELECT extra FROM mystery_records WHERE seen_room_ids LIKE ? AND extra LIKE '%room_nickname%' LIMIT 1",
                ('%' + r['room_id'] + '%',))
            row2 = cur2.fetchone()
            if row2:
                try:
                    ex = json.loads(row2[0])
                    if ex.get('room_nickname'):
                        r['nickname'] = ex['room_nickname']
                except:
                    pass
        conn2.close()
        return jsonify({'success': True, 'rooms': rooms})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== 搜索历史 API ==========

@app.route('/api/search_history/save', methods=['POST'])
def search_history_save():
    """保存搜索历史（按 input_text 去重）"""
    try:
        data = request.get_json(force=True)
        input_text = (data.get('input') or '').strip()
        nickname = (data.get('nickname') or '').strip()
        room_id = (data.get('room_id') or '').strip()
        if not input_text:
            return jsonify({'success': False, 'error': 'input is required'})
        conn = sqlite3.connect(_DB_PATH)
        conn.execute(
            'INSERT OR REPLACE INTO room_search_history (input_text, nickname, room_id, created_at) VALUES (?, ?, ?, ?)',
            (input_text, nickname, room_id, int(time.time()))
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/search_history/list')
def search_history_list():
    """返回最近 20 条搜索历史"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        cur = conn.execute(
            'SELECT input_text, nickname, room_id, created_at FROM room_search_history ORDER BY created_at DESC LIMIT 20'
        )
        rows = cur.fetchall()
        conn.close()
        data = [{'input_text': r[0], 'nickname': r[1], 'room_id': r[2], 'created_at': r[3]} for r in rows]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/search_history/delete', methods=['POST'])
def search_history_delete():
    """删除一条搜索历史"""
    try:
        data = request.get_json(force=True)
        input_text = (data.get('input') or '').strip()
        if not input_text:
            return jsonify({'success': False, 'error': 'input is required'})
        conn = sqlite3.connect(_DB_PATH)
        conn.execute('DELETE FROM room_search_history WHERE input_text = ?', (input_text,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/history_all')
def history_all():
    """返回指定直播间的历史神秘人记录（跨会话持久化）"""
    room_id = request.args.get('room_id', '')
    if not room_id:
        return jsonify({'success': False, 'error': '缺少room_id'})
    from datetime import datetime, timezone, timedelta
    # 北京时间
    beijing_tz = timezone(timedelta(hours=8))
    beijing_now = datetime.now(beijing_tz)
    # 计算凌晨3点截止线：如果现在>=今天3点，用今天3点；否则用昨天3点
    today_3am = beijing_now.replace(hour=3, minute=0, second=0, microsecond=0)
    if beijing_now >= today_3am:
        cutoff = today_3am
    else:
        cutoff = today_3am - timedelta(days=1)
    cutoff_ts = int(cutoff.timestamp())
    # dou 马甲按当天午夜判断
    today_midnight = beijing_now.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_ts = int(today_midnight.timestamp())
    
    history = _load_room_history(room_id)
    # 标记马甲状态：同类替换（dou只留最新dou，神秘人只留最新神秘人），不同类型都保留
    for item in history:
        displays = item.get('displays', []) or []
        if not displays:
            continue
        
        # 按类型分组
        mystery = [d for d in displays if d.get('display','').startswith('神秘人')]
        dou = [d for d in displays if d.get('display','').startswith('dou')]
        other = [d for d in displays if not d.get('display','').startswith('神秘人') and not d.get('display','').startswith('dou')]
        
        new_displays = []
        
        # 神秘人：今天3点后出现过 → 有效✅，否则已失效
        if mystery:
            mystery.sort(key=lambda x: x.get('last_seen', 0))
            latest_m = mystery[-1]
            today_m = [d for d in mystery if d.get('last_seen', 0) >= cutoff_ts]
            if today_m:
                latest_m['is_current'] = True
            else:
                latest_m['is_current'] = False
            new_displays.append(latest_m)
        
        # dou：当天午夜后有2+不同 → 最新稳定✅，否则仅供参考
        if dou:
            dou.sort(key=lambda x: x.get('last_seen', 0))
            today_d = [d for d in dou if d.get('last_seen', 0) >= midnight_ts]
            latest_d = dou[-1]
            if len(today_d) >= 2:
                latest_d['is_current'] = True
            else:
                latest_d['is_current'] = False
            new_displays.append(latest_d)
        
        # 其他：不显示（用户只要神秘人和dou两种）

        if new_displays:
            new_displays.sort(key=lambda x: x.get('last_seen', 0))
            item['displays'] = new_displays
            item['is_current'] = any(d.get('is_current') for d in new_displays)
            # 如果 extra 里有真实昵称，用它覆盖
            extra_nickname = (item.get('extra') or {}).get('nickname')
            if extra_nickname and extra_nickname != item.get('real_name'):
                item['real_name'] = extra_nickname
            # 从 extra 提取房间昵称
            extra_rn = (item.get('extra') or {}).get('room_nickname')
            if extra_rn:
                item['room_nickname'] = extra_rn
                item['nickname'] = extra_rn
        else:
            item['displays'] = []
            item['is_current'] = False
    return jsonify({'success': True, 'records': history, 'count': len(history)})


@app.route('/api/history_all_all')
def history_all_all():
    """返回所有直播间的历史神秘人记录，不分房间"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        
        cur = conn.execute('''
            SELECT r.*
            FROM mystery_records r
            WHERE r.is_regular = 0
            ORDER BY r.last_seen DESC
            LIMIT 500
        ''')
        all_records = [dict(r) for r in cur.fetchall()]
        
        # 拉取 display_names
        cur2 = conn.execute('''
            SELECT sec_uid, display, last_seen, seen_count
            FROM display_names
            ORDER BY last_seen DESC
        ''')
        dn_rows = [dict(r) for r in cur2.fetchall()]
        conn.close()
        
        display_map = {}
        for d in dn_rows:
            su = d['sec_uid']
            if su not in display_map:
                display_map[su] = []
            display_map[su].append({
                'display': d['display'],
                'last_seen': d['last_seen'],
                'seen_count': d['seen_count']
            })
        
        for item in all_records:
            su = item.get('sec_uid', '') or ''
            if item.get('extra'):
                try:
                    item['extra'] = json.loads(item['extra'])
                except:
                    item['extra'] = {}
            item['displays'] = sorted(display_map.get(su, []), key=lambda x: x['last_seen'], reverse=True)
        
        # 标记马甲状态
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        beijing_now = datetime.now(beijing_tz)
        today_3am = beijing_now.replace(hour=3, minute=0, second=0, microsecond=0)
        cutoff_ts = int(today_3am.timestamp()) if beijing_now >= today_3am else int((today_3am - timedelta(days=1)).timestamp())
        today_midnight = beijing_now.replace(hour=0, minute=0, second=0, microsecond=0)
        midnight_ts = int(today_midnight.timestamp())
        
        for item in all_records:
            displays = item.get('displays', []) or []
            if not displays:
                item_display = item.get('display', '') or ''
                if item_display:
                    displays = [{'display': item_display, 'last_seen': item.get('last_seen', 0)}]
                    item['displays'] = displays
                else:
                    continue
            mystery = [d for d in displays if d.get('display','').startswith('神秘人')]
            dou = [d for d in displays if d.get('display','').startswith('dou')]
            new_displays = []
            if mystery:
                mystery.sort(key=lambda x: x.get('last_seen', 0))
                latest_m = mystery[-1]
                latest_m['is_current'] = (any(d.get('last_seen', 0) >= cutoff_ts for d in mystery) or
                                            (item.get('last_seen', 0) or 0) >= cutoff_ts)
                new_displays.append(latest_m)
            if dou:
                dou.sort(key=lambda x: x.get('last_seen', 0))
                latest_d = dou[-1]
                today_d = [d for d in dou if d.get('last_seen', 0) >= midnight_ts]
                latest_d['is_current'] = len(today_d) >= 2
                new_displays.append(latest_d)
            if new_displays:
                item['displays'] = new_displays
                item['is_current'] = any(d.get('is_current') for d in new_displays)
                extra_nickname = (item.get('extra') or {}).get('nickname')
                if extra_nickname and extra_nickname != item.get('real_name'):
                    item['real_name'] = extra_nickname
            else:
                item['displays'] = []
        
        return jsonify({'success': True, 'records': all_records, 'count': len(all_records)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/history/<room_id>')
def history(room_id):
    """获取当前监听房间的神秘人历史"""
    listener = listeners.get(room_id)
    if not listener:
        return jsonify({'success': False, 'error': '未找到监听器'})
    return jsonify({'success': True, 'mystery_count': listener.mystery_count,
                    'history': listener.recent_mysteries[-50:]})

@app.route('/api/all_records/<room_id>')
def all_records(room_id):
    """获取全部用户记录（从 SQLite 读取，已聚合）"""
    hours = request.args.get('hours', default=0, type=int)
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # 查全表，Python 侧按 seen_room_ids 过滤 + 时间过滤
        cur = conn.execute('''
            SELECT r.*, 
                   GROUP_CONCAT(d.display || ':' || d.last_seen, '|') as all_displays
            FROM mystery_records r
            LEFT JOIN display_names d ON d.sec_uid = r.sec_uid
            GROUP BY r.sec_uid, r.display
            ORDER BY r.last_seen DESC
            LIMIT 500
        ''')
        
        rows = []
        cutoff = int(time.time()) - hours * 3600 if hours > 0 else 0
        for r in cur.fetchall():
            row = dict(r)
            # 过滤：seen_room_ids 包含 room_id
            seen = (row.get('seen_room_ids') or '').split(',')
            if str(room_id) not in seen:
                continue
            # 时间过滤
            if cutoff and (row.get('last_seen') or 0) < cutoff:
                continue
            if row.get('all_displays'):
                names = []
                for entry in row['all_displays'].split('|'):
                    parts = entry.rsplit(':', 1)
                    if len(parts) == 2:
                        names.append({'display': parts[0], 'last_seen': int(parts[1])})
                row['displays'] = sorted(names, key=lambda x: x['last_seen'], reverse=True)
            else:
                row['displays'] = []
            if row.get('extra'):
                try:
                    row['extra'] = json.loads(row['extra'])
                except:
                    row['extra'] = {}
            # 兼容前端：room_id 从 last_room_id 映射
            row['room_id'] = row.get('last_room_id', '')
            # 从 extra 提取 room_nickname
            row['room_nickname'] = (row.get('extra') or {}).get('room_nickname', '')
            rows.append(row)
        conn.close()
        
        # 按 sec_uid 去重（DB 已自然合并，这里只是兜底）
        seen_keys = {}
        for row in rows:
            key = row.get('sec_uid', '') or row.get('display', '')
            if key not in seen_keys:
                seen_keys[key] = row
            elif (row.get('last_seen') or 0) > (seen_keys[key].get('last_seen') or 0):
                seen_keys[key] = row
        
        # 每种 display 类型只保留最新的，不同类型都保留
        deduped = []
        for row in seen_keys.values():
            names = row.get('displays', [])
            if names:
                mystery = [n for n in names if n.get('display','').startswith('神秘人')]
                dou = [n for n in names if n.get('display','').startswith('dou')]
                other = [n for n in names if not n.get('display','').startswith('神秘人') and not n.get('display','').startswith('dou')]
                filtered = []
                for group in [mystery, dou, other]:
                    if group:
                        group.sort(key=lambda x: x.get('last_seen', 0))
                        filtered.append(group[-1])
                filtered.sort(key=lambda x: x.get('last_seen', 0))
                row['display'] = filtered[-1]['display']
                row['displays'] = filtered
            deduped.append(row)
        deduped.sort(key=lambda x: x.get('last_seen', 0) or 0, reverse=True)
        return jsonify({'success': True, 'records': deduped})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'fallback': True})

@app.route('/api/interactions/<room_id>/<sec_uid>')
def get_interactions(room_id, sec_uid):
    """获取某个用户在某直播间的互动记录"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.execute('''
            SELECT type, content, gift_count, timestamp
            FROM interaction_log
            WHERE room_id = ? AND sec_uid = ?
            ORDER BY timestamp DESC
            LIMIT 100
        ''', (room_id, sec_uid))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({'success': True, 'interactions': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stream/<room_id>')
def stream(room_id):
    """SSE 实时事件流"""
    def generate():
        listener = listeners.get(room_id)
        if not listener:
            yield f"data: {json.dumps({'type': 'error', 'data': {'error': '未找到监听器'}})}\n\n"
            return
        # 发送初始状态 + 已有神秘人历史
        init_data = {'room_id': room_id, 'nickname': listener.nickname,
                     'mystery_count': listener.mystery_count,
                     'is_anonymous': listener.is_private,
                     'history': listener.recent_mysteries[-50:]}
        yield f"data: {json.dumps({'type': 'init', 'data': init_data})}\n\n"
        while listener.running or not listener.events.empty():
            try:
                event = listener.events.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                # 心跳保活
                yield ": heartbeat\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive',
                             'Access-Control-Allow-Origin': '*'})




@app.route('/api/feed/<room_id>')
def feed_events(room_id):
    """返回某个直播间的互动时间线（公屏用）"""
    limit = request.args.get('limit', default=200, type=int)

    events = []

    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row

        # 1. 从 interaction_log 取 chat + gift 事件
        cur = conn.execute('''
            SELECT sec_uid, display, type, content, gift_count, timestamp
            FROM interaction_log
            WHERE room_id = ?
            ORDER BY timestamp ASC
        ''', (room_id,))

        for r in cur.fetchall():
            events.append({
                'type': r['type'],
                'display': r['display'] or '',
                'real_name': r['display'] or '',
                'content': r['content'] or '',
                'count': r['gift_count'] or 1,
                'timestamp': r['timestamp'],
                'sec_uid': r['sec_uid'] or '',
            })

        # 2. 从 mystery_records 生成 enter 事件
        cur2 = conn.execute('''
            SELECT sec_uid, display, real_name, first_seen, enter_count, seen_room_ids
            FROM mystery_records
            WHERE enter_count > 0
            ORDER BY first_seen ASC
        ''')

        for r in cur2.fetchall():
            seen = (r['seen_room_ids'] or '').split(',')
            if str(room_id) in seen:
                real_name = r['real_name'] or r['display'] or ''
                events.append({
                    'type': 'enter',
                    'display': r['display'] or '',
                    'real_name': real_name,
                    'content': '',
                    'count': r['enter_count'],
                    'timestamp': r['first_seen'],
                    'sec_uid': r['sec_uid'] or '',
                })

        conn.close()

        # 3. 合并、按 timestamp 排序、限制 limit 条
        events.sort(key=lambda x: x['timestamp'])
        events = events[:limit]

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

    return jsonify({'success': True, 'events': events, 'count': len(events)})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False, use_reloader=True)
