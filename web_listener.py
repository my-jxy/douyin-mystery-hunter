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

from flask import Flask, Response, request, jsonify

app = Flask(__name__)

# ========== 工具函数 ==========
GENDER_MAP = {0: '未设置', 1: '男', 2: '女'}
_TTWID = cu.dy_live_auth.cookie.get('ttwid', '')
_user_info_cache = {}
_level_cache = {}
_last_api_call = 0  # 限流时间戳
_record_all_enabled = False  # 全局录制开关：True=记录所有用户，False=仅记录神秘人
_private_name_cache = {}  # (room_id:display) -> real_nickname, 私密直播间送礼拿到真实名后缓存

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
    except: pass
    # 查询失败也缓存（空结果），避免重复请求
    _user_info_cache[sec_uid] = {}
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
        self.all_users_path = None
        self._mystery_seq = 0
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
        # 删除磁盘记录文件
        if self.all_users_path and os.path.exists(self.all_users_path):
            try:
                os.remove(self.all_users_path)
            except:
                pass

    def send_event(self, event_type, data):
        self.events.put({'type': event_type, 'data': data, 'time': time.time()})

    def _init_all_users_file(self):
        if self.all_users_path:
            return
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
        os.makedirs(data_dir, exist_ok=True)
        # 清除该房间的旧文件
        for f in os.listdir(data_dir):
            if f.endswith('.jsonl') and f.startswith(f'{self.room_id}_'):
                try: os.remove(os.path.join(data_dir, f))
                except: pass
        ts = time.strftime('%Y%m%d_%H%M%S')
        self.all_users_path = os.path.join(data_dir, f'{self.room_id}_{ts}.jsonl')

    def _write_all_user(self, info):
        try:
            self._init_all_users_file()
            info['time'] = time.time()
            with open(self.all_users_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(info, ensure_ascii=False) + '\n')
        except:
            pass

    def _run(self):
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
                                msg = Live_pb2.MemberMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                # 私密直播间：先查缓存（不管是不是神秘人，只要sec_uid为空就查）
                                extra = None
                                if not user.sec_uid:
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
                                    info = {'display': display, 'real_name': real_name,
                                            'unique_id': user_id_str(user), 'sec_uid': user.sec_uid,
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
                                    info['room_id'] = self.room_id
                                    info['room_nickname'] = self.nickname
                                    self.send_event('mystery_enter', info)
                                    # 全部页：私密直播间用户（sec_uid为空）也写入磁盘记录
                                    if _record_all_enabled and not info.get('sec_uid'):
                                        rec = info.copy()
                                        rec['event_type'] = 'enter'
                                        print(f"[JSONL] 写入: real_name={rec.get('real_name','?')} sec_uid={rec.get('sec_uid','')} has_extra={bool(rec.get('extra'))}", flush=True)
                                        self._write_all_user(rec)
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

                            elif item.method == 'WebcastChatMessage':
                                msg = Live_pb2.ChatMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                # 私密直播间：先查缓存
                                extra = None
                                if not user.sec_uid:
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
                                    chat_info = {
                                        'display': display, 'real_name': real_name,
                                        'content': msg.content, 'sec_uid': user.sec_uid,
                                        'badge_level': badge_lv,
                                        'consume_level': user.consume_diamond_level,
                                        'unique_id': user_id_str(user),
                                        'mystery_man': mm,
                                        'is_regular': False}
                                    if extra:
                                        if extra.get('nickname') and extra['nickname'] != real_name:
                                            chat_info['real_name'] = extra['nickname']
                                        chat_info['extra'] = extra
                                    chat_info['room_id'] = self.room_id
                                    chat_info['room_nickname'] = self.nickname
                                    self.send_event('mystery_chat', chat_info)
                                    # 全部页：私密直播间用户（sec_uid为空）也写入磁盘记录
                                    if _record_all_enabled and not chat_info.get('sec_uid'):
                                        rec = chat_info.copy()
                                        rec['event_type'] = 'chat'
                                        self._write_all_user(rec)
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

                            elif item.method == 'WebcastGiftMessage':
                                try:
                                    msg = Live_pb2.GiftMessage()
                                    msg.ParseFromString(item.payload)
                                    user = msg.user
                                    is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                    # 私密直播间：有sec_uid就查API缓存真实名
                                    extra = None
                                    if user.sec_uid:
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
                                        gift_info = {
                                            'display': display, 'real_name': real_name,
                                            'sec_uid': user.sec_uid, 'gift_name': msg.gift.name if msg.gift else '?',
                                            'count': msg.comboCount,
                                            'badge_level': get_badge_level(user),
                                            'consume_level': user.consume_diamond_level,
                                            'unique_id': user_id_str(user),
                                            'is_regular': False}
                                        if extra:
                                            gift_info['extra'] = extra
                                        gift_info['room_id'] = self.room_id
                                        gift_info['room_nickname'] = self.nickname
                                        self.send_event('mystery_gift', gift_info)
                                    elif _record_all_enabled:
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
    return INDEX_HTML

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
    listener.start()
    return jsonify({'success': True, 'room_id': room_id, 'active': running_count + 1, 'max': MAX_ROOMS})

@app.route('/api/stop', methods=['POST'])
def stop_listen():
    """停止指定监听"""
    data = request.get_json()
    room_id = data.get('room_id', '')
    if room_id in listeners:
        listeners[room_id].stop()
        del listeners[room_id]
        return jsonify({'success': True, 'room_id': room_id})
    return jsonify({'success': False, 'error': '未找到该监听'})

@app.route('/api/stop_all', methods=['POST'])
def stop_all():
    """停止所有监听"""
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
    """获取全部用户记录（从磁盘读取）"""
    listener = listeners.get(room_id)
    if not listener or not listener.all_users_path:
        return jsonify({'success': False, 'records': [], 'error': '无记录'})
    try:
        records = []
        with open(listener.all_users_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        if records:
            print(f"[API] all_records: {len(records)}条, 最新extra={bool(records[-1].get('extra'))}, real_name={records[-1].get('real_name','?')}", flush=True)
        return jsonify({'success': True, 'records': records[-500:]})
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

# ========== 启动清理 ==========
import atexit
_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
def _cleanup_data_dir():
    if os.path.isdir(_data_dir):
        for f in os.listdir(_data_dir):
            if f.endswith('.jsonl'):
                try: os.remove(os.path.join(_data_dir, f))
                except: pass
atexit.register(_cleanup_data_dir)

# ========== 启动 ==========
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>抖音神秘人猎人 🎯</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f0f0f;color:#e0e0e0;min-height:100vh;padding:16px}
.container{max-width:600px;margin:0 auto}
h1{font-size:26px;text-align:center;padding:12px 0 8px;background:linear-gradient(135deg,#fe2c55,#ff6b35,#fe2c55,#ff6b35,#fe2c55);background-size:300% 100%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-weight:700;animation:titleShimmer 4s ease-in-out infinite}
@keyframes titleShimmer{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.input-group{display:flex;gap:8px;margin:12px 0}
.input-group input{flex:1;padding:12px 14px;border:1px solid #333;border-radius:10px;background:rgba(26,26,26,0.75);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);color:#e0e0e0;font-size:15px;outline:none;transition:border .2s}
.input-group input:focus{border-color:#fe2c55}
.input-group input::placeholder{color:#666}
.input-group button{padding:12px 18px;border:none;border-radius:10px;background:linear-gradient(135deg,#fe2c55,#ff6b35);color:#fff;font-size:15px;font-weight:600;cursor:pointer;white-space:nowrap;transition:opacity .2s}
.input-group button:disabled{opacity:.5;cursor:not-allowed}
.input-group button.stop-btn{background:#333;color:#ff6b6b;font-weight:600}
/* 停止选择弹窗 */
.stop-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:999;display:flex;align-items:center;justify-content:center;animation:fadeIn .2s}
.stop-box{background:#1a1a1a;border:1px solid #333;border-radius:14px;padding:18px;width:280px;max-height:70vh;overflow-y:auto}
.stop-box h3{font-size:15px;color:#e0e0e0;margin-bottom:12px;text-align:center}
.stop-item{display:flex;align-items:center;padding:10px 12px;border-radius:8px;cursor:pointer;font-size:13px;color:#ccc;transition:background .15s;margin-bottom:4px}
.stop-item:hover{background:#222}
.stop-item .stop-dot{width:8px;height:8px;border-radius:50%;margin-right:10px;flex-shrink:0}
.stop-item .stop-icon{margin-left:auto;color:#888;font-size:14px}
.stop-all-item{display:flex;align-items:center;padding:10px 12px;margin-top:6px;border-top:1px solid #333;cursor:pointer;font-size:13px;color:#fe2c55;font-weight:600;border-radius:8px;transition:background .15s}
.stop-all-item:hover{background:rgba(254,44,85,.1)}
.stop-cancel{display:block;text-align:center;margin-top:10px;padding:8px;color:#888;font-size:12px;cursor:pointer;border-radius:8px}
.stop-cancel:hover{background:#222}
.status-bar{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:rgba(26,26,26,0.6);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-radius:10px;margin:8px 0;font-size:13px;color:#999}
.status-bar .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status-bar .dot.green{background:#34c759}
.status-bar .dot.red{background:#ff3b30}
.status-bar .dot.gray{background:#555}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.event.mystery{background:linear-gradient(135deg,rgba(254,44,85,.15),rgba(255,107,53,.08));border-left:3px solid #fe2c55}
.event.chat{background:rgba(52,199,89,.08);border-left:3px solid #34c759}
.event.gift{background:rgba(255,149,0,.08);border-left:3px solid #ff9500}
.event.rank{background:rgba(90,200,250,.08);border-left:3px solid #5ac8fa}
.event.stats{background:rgba(142,142,147,.08);border-left:3px solid #8e8e93;font-size:12px;color:#999;padding:4px 12px}
.event.sys{background:rgba(90,200,250,.06);border-left:3px solid #5ac8fa;font-size:12px;color:#5ac8fa;padding:4px 12px}
.event .label{font-weight:600;margin-right:6px}
.event .tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin-right:4px}
.event .tag.m{background:rgba(254,44,85,.3);color:#fe2c55}
.event .tag.lv{background:rgba(90,200,250,.2);color:#5ac8fa}
.event .tag.dia{background:rgba(255,149,0,.2);color:#ff9500}
.event .content{color:#ccc;margin-top:2px}
.event .extra{font-size:12px;color:#888;margin-top:2px}
.event .link{color:#5ac8fa;text-decoration:none;font-size:12px}
.empty{text-align:center;color:#555;padding:40px 0;font-size:14px}
.empty .icon{font-size:40px;margin-bottom:12px}
.hint{text-align:center;color:#444;font-size:12px;margin:6px 0}
.loading{display:inline-block;width:14px;height:14px;border:2px solid #666;border-top-color:#fe2c55;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
/* 模式按钮 */
.mode-btn{font-size:12px;cursor:pointer;padding:3px 9px;border-radius:6px;background:#222;color:#666;transition:all .2s;margin-left:4px;user-select:none}
.mode-btn.active{background:linear-gradient(135deg,rgba(254,44,85,.2),rgba(255,107,53,.1));color:#fe2c55;font-weight:600}
/* 普通用户 */
.event.regular{background:rgba(142,142,147,.06);border-left:3px solid #8e8e93}
.event.regular .tag.reg{background:rgba(142,142,147,.25);color:#8e8e93}
/* 名字截断 + 点击展开 */
.name-box{display:flex;align-items:center;gap:4px;margin:2px 0;min-width:0}
.name-text{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;flex:1;min-width:0;padding:1px 0}
.name-text.exp{white-space:normal;overflow:visible}
.name-text.mn{color:#fe2c55}
.name-text.rn{color:#999}
.name-text .dp{font-weight:400;color:#666;font-size:11px;margin-left:4px}
/* 状态栏统计固定宽度 */
.stats-text{display:inline-block;min-width:64px;text-align:right;color:#666;font-size:12px}
/* 卡片等高等宽 */
.events{max-height:70vh;overflow-y:auto;padding:4px 0;display:grid;grid-template-columns:1fr 1fr;gap:5px;align-content:start;align-items:stretch}
.events:empty,.events:has(.empty){display:block}
.events::-webkit-scrollbar{width:4px}
.events::-webkit-scrollbar-thumb{background:#333;border-radius:2px}
.event{padding:7px 9px;border-radius:8px;font-size:12px;line-height:1.4;overflow:hidden;height:108px;min-height:108px;background:rgba(26,26,26,0.7);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
.event.exp{height:auto;min-height:108px}
</style>
  <script src="/static/anime.min.js"></script>
</head>
<body>
<div class="container">
  <h1>🎯 神秘人猎人</h1>
  <div class="input-group">
    <input id="input" type="text" placeholder="抖音号 / 链接" autocomplete="off" enterkeyhint="search">
    <button id="btn" onclick="handleBtnClick()">🔍 监听</button>
  </div>
  <div class="hint">支持：抖音号 · 直播间链接 · 主页链接</div>
  <div class="status-bar" id="statusBar">
    <span><span class="dot gray" id="dot"></span><span id="statusText">未连接</span></span>
    <span><span id="statsText" class="stats-text" style="margin-right:4px"></span><span class="mode-btn active" id="modeMystery" onclick="switchMode('mystery')">🎯神秘人</span><span class="mode-btn" id="modeAll" onclick="switchMode('all')">📋全部</span></span>
  </div>
  <div class="events" id="events">
    <div class="empty"><div class="icon">🎯</div>输入抖音号或链接<br>点击「监听」开始</div>
  </div>
</div>
<script>
let eventSources = {}       // room_id -> EventSource
const currentRooms = {}     // room_id -> {nickname}
const mysteries = {}        // sec_uid -> {display, real_name, ..., room_id, room_nickname}
let disconnectTimers = {}   // room_id -> timer
let recordAllEnabled = false  // 是否记录全部用户
let currentView = 'mystery'   // 'mystery' 或 'all'
let lastRoomId = null         // 最近监听的房间，用于按钮切换停止

function escapeHtml(text) {
  const d = document.createElement('div')
  d.textContent = text
  return d.innerHTML
}

function setStatus(text, color) {
  document.getElementById('statusText').textContent = text
  document.getElementById('dot').className = 'dot ' + color
}

function resetBtnText() {
  const btn = document.getElementById('btn')
  const rooms = Object.keys(currentRooms)
  const input = document.getElementById('input').value.trim()
  if (rooms.length > 0 && !input) {
    btn.textContent = '停止'
    btn.className = 'stop-btn'
  } else {
    btn.textContent = '🔍 监听'
    btn.className = ''
  }
}

function connect() {
  const input = document.getElementById('input').value.trim()
  if (!input) return
  const btn = document.getElementById('btn')
  btn.disabled = true
  btn.textContent = '解析中...'
  setStatus('解析中...', 'gray')

  fetch('/api/resolve', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({input: input})
  })
  .then(r => r.json())
  .then(data => {
    if (!data.success) {
      showToast('❌ ' + data.error)
      btn.disabled = false
      resetBtnText()
      return
    }
    if (data.room_id && (data.live_status == 1 || data.live_status === undefined)) {
      if (currentRooms[data.room_id]) {
        showToast('⚠️ 已在监听该直播间')
        btn.disabled = false
        resetBtnText()
        return
      }
      startListening(data.room_id, data.nickname || '')
    } else if (data.room_id && data.live_status == 0) {
      showToast('❌ 该主播未在直播')
      btn.disabled = false
      resetBtnText()
    } else {
      showToast('❌ 无法获取直播间信息')
      btn.disabled = false
      resetBtnText()
    }
  })
  .catch(err => {
    showToast('❌ 网络错误: ' + err.message)
    btn.disabled = false
    resetBtnText()
  })
}

function handleBtnClick() {
  const btn = document.getElementById('btn')
  const rooms = Object.keys(currentRooms)
  // 有输入内容 → 监听模式
  const input = document.getElementById('input').value.trim()
  if (input) {
    connect()
    return
  }
  // 无输入内容 + 有房间 → 停止模式
  if (rooms.length === 1) {
    stopRoom(rooms[0])
    btn.textContent = '🔍 监听'
    btn.className = ''
    lastRoomId = null
  } else if (rooms.length > 1) {
    showStopDialog()
  }
}

function showStopDialog() {
  const rooms = Object.keys(currentRooms)
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  let html = '<div class="stop-overlay" id="stopOverlay" onclick="closeStopDialog(event)"><div class="stop-box" onclick="event.stopPropagation()">'
  html += '<h3>选择要停止的房间</h3>'
  rooms.forEach((rid, i) => {
    const nick = currentRooms[rid]?.nickname || rid.slice(0,10)
    html += `<div class="stop-item" onclick="stopRoomAndClose('${rid}')"><span class="stop-dot" style="background:${roomColors[i%3]}"></span>${escapeHtml(nick)}<span style="margin-left:auto;color:#fe2c55;font-weight:600">停止</span></div>`
  })
  html += '<div class="stop-all-item" onclick="stopAllAndClose()">全部停止</div>'
  html += '<div class="stop-cancel" onclick="closeStopDialog()">取消</div>'
  html += '</div></div>'
  document.body.insertAdjacentHTML('beforeend', html)
}

function closeStopDialog(e) {
  const el = document.getElementById('stopOverlay')
  if (el) el.remove()
}

function stopRoomAndClose(roomId) {
  closeStopDialog()
  stopRoom(roomId)
  const rooms = Object.keys(currentRooms)
  const btn = document.getElementById('btn')
  if (rooms.length === 0) {
    btn.textContent = '🔍 监听'
    btn.className = ''
    lastRoomId = null
  }
}

function stopAllAndClose() {
  closeStopDialog()
  stopAll()
  const btn = document.getElementById('btn')
  btn.textContent = '🔍 监听'
  btn.className = ''
  lastRoomId = null
}

function toggleRecordAll() {
  // 已废弃，由 switchMode 替代
}
function switchView(view) {
  // 已废弃，由 switchMode 替代
}

function switchMode(mode) {
  const allBtn = document.getElementById('modeAll')
  // 已在全部模式下再次点击 → 刷新
  if (mode === 'all' && currentView === 'all') {
    renderAllRecords()
    return
  }
  currentView = mode
  const isAll = mode === 'all'
  // 更新按钮状态和文字
  document.getElementById('modeMystery').className = 'mode-btn' + (mode === 'mystery' ? ' active' : '')
  allBtn.className = 'mode-btn' + (isAll ? ' active' : '')
  allBtn.textContent = isAll ? '刷新' : '📋全部'
  // 通知后端：全部用户模式才开启录制
  fetch('/api/toggle_record_all', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled: isAll})
  })
  if (isAll) {
    renderAllRecords()
  } else {
    renderMysteries()
  }
}

function showToast(msg) {
  const el = document.getElementById('events')
  // 只在没有任何神秘人时显示toast
  if (Object.keys(mysteries).length === 0) {
    el.innerHTML = `<div class="empty" style="color:#fe2c55">${msg}</div>`
  }
}

function startListening(roomId, nickname) {
  fetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room_id: roomId, nickname: nickname})
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      currentRooms[roomId] = {nickname: nickname || roomId}
      lastRoomId = roomId
      document.getElementById('btn').textContent = '停止'
      document.getElementById('btn').className = 'stop-btn'
      // 首次监听显示提示
      if (Object.keys(mysteries).length === 0) {
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
      setStatus('监听中', 'green')
      document.getElementById('btn').disabled = false
      document.getElementById('input').value = ''
      resetBtnText()
      connectSSE(roomId)
    } else {
      showToast('❌ ' + (data.error || '启动失败'))
      document.getElementById('btn').disabled = false
      document.getElementById('btn').textContent = '🔍 监听'
    }
  })
}

function connectSSE(roomId) {
  // 先拉取已有历史
  fetch('/api/history/' + roomId)
    .then(r => r.json())
    .then(data => {
      if (data.success && data.history && data.history.length > 0) {
        data.history.forEach(h => {
          if (!mysteries[mKey(h)]) {
            const realName = h.real_name || h.display
            const extraData = h.extra || null
            mysteries[mKey(h)] = {
              display: h.display, real_name: realName,
              sec_uid: h.sec_uid,
              unique_id: h.unique_id || extraData?.unique_id || '',
              badge_level: h.badge_level || 0, consume_level: h.consume_level || 0,
              extra: extraData,
              room_id: h.room_id || roomId,
              room_nickname: h.room_nickname || currentRooms[roomId]?.nickname || roomId,
              enter_count: 1,
              chats: [], gifts: [],
              time: Date.now(), expanded: false,
              is_regular: h.is_regular || false
            }
          }
        })
        if (currentView !== 'all') renderMysteries()
      }
    })

  const es = new EventSource('/stream/' + roomId)
  eventSources[roomId] = es
  disconnectTimers[roomId] = null

  es.onmessage = function(e) {
    if (!e.data) return
    // 收到消息取消该房间的断线延时
    cancelDisconnect(roomId)
    try {
      const event = JSON.parse(e.data)
      handleEvent(event, roomId)
    } catch(err) {}
  }
  es.onerror = function() {
    if (disconnectTimers[roomId]) return
    disconnectTimers[roomId] = setTimeout(() => {
      setStatus('已断开', 'red')
      disconnectTimers[roomId] = null
    }, 5000)
  }
}

function cancelDisconnect(roomId) {
  if (disconnectTimers[roomId]) {
    clearTimeout(disconnectTimers[roomId])
    disconnectTimers[roomId] = null
  }
}

function mKey(d) {
  const isPrivate = !d.sec_uid && (!d.unique_id || d.unique_id === '?')
  return d.room_id + ':' + (isPrivate
    ? d.display + ':' + (d.consume_level||0) + ':' + (d.badge_level||0)
    : d.sec_uid || d.display || '?')
}

function handleEvent(event, roomId) {
  const d = event.data
  // 补充房间信息
  const roomNick = currentRooms[roomId]?.nickname || roomId
  switch(event.type) {
    case 'init':
    case 'connected':
      cancelDisconnect(roomId)
      setStatus('监听中', 'green')
      break
    case 'disconnected':
      if (d.reconnecting) {
        setStatus('重连中...', 'gray')
      } else {
        setStatus('已断开', 'red')
      }
      break
    case 'mystery_enter':
      mysteries[mKey(d)] = {
        display: d.display, real_name: d.real_name,
        sec_uid: d.sec_uid,
        unique_id: d.unique_id || d.extra?.unique_id || '',
        badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
        extra: d.extra || null,
        room_id: d.room_id || roomId,
        room_nickname: d.room_nickname || roomNick,
        enter_count: (mysteries[mKey(d)]?.enter_count || 0) + 1,
        chats: mysteries[mKey(d)]?.chats || [],
        gifts: mysteries[mKey(d)]?.gifts || [],
        time: Date.now(), expanded: false,
        is_regular: d.is_regular || false
      }
      if (currentView !== 'all') renderSingleCard(mKey(d))
      break
    case 'mystery_chat':
      if (!mysteries[mKey(d)]) {
        mysteries[mKey(d)] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: d.unique_id || '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick,
          enter_count: 0, is_regular: d.is_regular || false
        }
      }
      mysteries[mKey(d)].chats.push({content: d.content, time: Date.now()})
      if (currentView !== 'all') renderSingleCard(mKey(d))
      break
    case 'mystery_gift':
      if (!mysteries[mKey(d)]) {
        mysteries[mKey(d)] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick,
          enter_count: 0, is_regular: d.is_regular || false
        }
      } else if (d.real_name && d.real_name !== d.display) {
        // 私密直播间：送礼拿到真实名，更新已有记录
        mysteries[mKey(d)].real_name = d.real_name
        if (d.extra) mysteries[mKey(d)].extra = d.extra
      }
      mysteries[mKey(d)].gifts.push({name: d.gift_name, count: d.count, time: Date.now()})
      if (currentView !== 'all') renderSingleCard(mKey(d))
      break
    case 'room_offline':
      setStatus('已断开', 'red')
      // 直播间已下播，自动停止监听
      showToast('📴 直播已结束，已自动停止')
      stopRoom(roomId)
      break
    case 'error':
      break
  }
}

function renderMysteries() {
  const container = document.getElementById('events')
  // 过滤：仅显示神秘人 / 显示全部
  const mysteryOnly = currentView === 'mystery'
  const keys = Object.keys(mysteries)
  const filtered = mysteryOnly ? keys.filter(k => !mysteries[k].is_regular) : keys
  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">🎯</div>暂无数据</div>'
    return
  }
  // 房间颜色列表
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  Object.keys(currentRooms).forEach(rid => { roomMap[rid] = ci++ % 3 })

  let html = ''
  const sorted = filtered.sort((a, b) => mysteries[b].time - mysteries[a].time)
  sorted.forEach((secUid, idx) => {
    const m = mysteries[secUid]
    const isRegular = m.is_regular || false
    const uniqueId = m.unique_id || m.extra?.unique_id || m.sec_uid?.slice(0,12) || '?'
    const followerText = m.extra ? `粉丝${m.extra.follower_count} 作品${m.extra.aweme_count}` : ''
    const ipText = m.extra?.ip_location ? `🌍 ${m.extra.ip_location}` : ''
    const totalActions = m.chats.length + m.gifts.length
    const colorIdx = roomMap[m.room_id] !== undefined ? roomMap[m.room_id] : 0
    const roomColor = roomColors[colorIdx]

    html += `<div class="event ${isRegular ? 'regular' : 'mystery'}${m.expanded?' exp':''}" data-su="${secUid}">`
    // 房间标签 + 展开按钮
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`
    html += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
    html += `<span style="font-size:10px;color:${roomColor};font-weight:600">${escapeHtml(m.room_nickname || '?')}</span>`
    if (isRegular) {
      html += ` <span class="tag reg" style="font-size:9px">普通</span>`
    } else {
      if (m.badge_level) html += ` <span class="tag lv" style="font-size:9px">🏅${m.badge_level}</span>`
      if (m.consume_level) html += ` <span class="tag dia" style="font-size:9px">💎${m.consume_level}</span>`
    }
    html += `</div>`
    html += `<span style="color:#666;font-size:11px;cursor:pointer;flex-shrink:0;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleExpand('${secUid}')">${m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`}</span>`
    html += `</div>`
    // 名字（可点击展开）
    html += `<div class="name-box"><span class="name-text ${isRegular?'rn':'mn'}" onclick="toggleName('${secUid}')">${escapeHtml(m.real_name)}`
    if (m.display && m.display !== m.real_name) {
      html += `<span class="dp">${escapeHtml(m.display)}</span>`
    }
    html += `</span></div>`
    html += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${escapeHtml(uniqueId)}</div>`
    if (followerText && !isRegular) html += `<div style="font-size:10px;color:#888">📊 ${followerText}</div>`
    if (ipText) html += `<div style="font-size:10px;color:#888">${ipText}</div>`
    if (m.extra?.signature && !isRegular) html += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(m.extra.signature)}</div>`
    // 统计
    html += `<div style="font-size:10px;color:#777;margin:1px 0">`
    if (m.enter_count) html += `🚪${m.enter_count}次 `
    if (m.chats.length) html += `💬${m.chats.length}条 `
    if (m.gifts.length) html += `🎁${m.gifts.length}个`
    html += `</div>`
    html += `<div style="font-size:10px;color:#555;margin-top:1px"><a class="link" href="javascript:;" onclick="window.open('https://www.douyin.com/user/${secUid}','_blank')">🔗 主页</a></div>`

    if (totalActions > 0) {
      html += `<div id="actions-${secUid}" style="display:${m.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
      m.chats.forEach(c => {
        html += `<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
        })
        m.gifts.forEach(g => {
          html += `<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
      })
      html += `</div>`
      html += `<div style="font-size:11px;color:#666;margin-top:2px;cursor:pointer" onclick="toggleExpand('${secUid}')">`
      html += m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`
      html += `</div>`
    }
    html += `</div>`
  })
  container.innerHTML = html
}

// 单张卡片增量更新（SSE 事件用，避免全量重绘+动画抖动）
function renderSingleCard(key) {
  const m = mysteries[key]
  if (!m || currentView === 'all') return

  const container = document.getElementById('events')
  // 移除空状态
  const empty = container.querySelector('.empty')
  if (empty) container.innerHTML = ''

  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  Object.keys(currentRooms).forEach(rid => { roomMap[rid] = ci++ % 3 })

  // 生成单张卡片 HTML（复用 renderMysteries 里的卡片逻辑）
  const isRegular = m.is_regular || false
  const uniqueId = m.unique_id || m.extra?.unique_id || m.sec_uid?.slice(0,12) || '?'
  const followerText = m.extra ? `粉丝${m.extra.follower_count} 作品${m.extra.aweme_count}` : ''
  const ipText = m.extra?.ip_location ? `🌍 ${m.extra.ip_location}` : ''
  const totalActions = m.chats.length + m.gifts.length
  const colorIdx = roomMap[m.room_id] !== undefined ? roomMap[m.room_id] : 0
  const roomColor = roomColors[colorIdx]

  let cardHtml = `<div class="event ${isRegular ? 'regular' : 'mystery'}${m.expanded?' exp':''}" data-su="${key}">`
  cardHtml += `<div style="display:flex;justify-content:space-between;align-items:start">`
  cardHtml += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
  cardHtml += `<span style="font-size:10px;color:${roomColor};font-weight:600">${escapeHtml(m.room_nickname || '?')}</span>`
  if (isRegular) {
    cardHtml += ` <span class="tag reg" style="font-size:9px">普通</span>`
  } else {
    if (m.badge_level) cardHtml += ` <span class="tag lv" style="font-size:9px">🏅${m.badge_level}</span>`
    if (m.consume_level) cardHtml += ` <span class="tag dia" style="font-size:9px">💎${m.consume_level}</span>`
  }
  cardHtml += `</div>`
  cardHtml += `<span style="color:#666;font-size:11px;cursor:pointer;flex-shrink:0;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleExpand('${key}')">${m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`}</span>`
  cardHtml += `</div>`
  cardHtml += `<div class="name-box"><span class="name-text ${isRegular?'rn':'mn'}" onclick="toggleName('${key}')">${escapeHtml(m.real_name)}`
  if (m.display && m.display !== m.real_name) {
    cardHtml += `<span class="dp">${escapeHtml(m.display)}</span>`
  }
  cardHtml += `</span></div>`
  cardHtml += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${escapeHtml(uniqueId)}</div>`
  if (followerText && !isRegular) cardHtml += `<div style="font-size:10px;color:#888">📊 ${followerText}</div>`
  if (ipText) cardHtml += `<div style="font-size:10px;color:#888">${ipText}</div>`
  if (m.extra?.signature && !isRegular) cardHtml += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(m.extra.signature)}</div>`
  cardHtml += `<div style="font-size:10px;color:#777;margin:1px 0">`
  if (m.enter_count) cardHtml += `🚪${m.enter_count}次 `
  if (m.chats.length) cardHtml += `💬${m.chats.length}条 `
  if (m.gifts.length) cardHtml += `🎁${m.gifts.length}个`
  cardHtml += `</div>`
  cardHtml += `<div style="font-size:10px;color:#555;margin-top:1px"><a class="link" href="javascript:;" onclick="window.open('https://www.douyin.com/user/${key}','_blank')">🔗 主页</a></div>`
  if (totalActions > 0) {
    cardHtml += `<div id="actions-${key}" style="display:${m.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
    m.chats.forEach(c => {
      cardHtml += `<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
    })
    m.gifts.forEach(g => {
      cardHtml += `<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
    })
    cardHtml += `</div>`
    cardHtml += `<div style="font-size:11px;color:#666;margin-top:2px;cursor:pointer" onclick="toggleExpand('${key}')">`
    cardHtml += m.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`
    cardHtml += `</div>`
  }
  cardHtml += `</div>`

  const existing = container.querySelector(`[data-su="${CSS.escape(key)}"]`)
  if (existing) {
    existing.outerHTML = cardHtml
  } else {
    container.insertAdjacentHTML('beforeend', cardHtml)
  }
}

// 全部用户模式：从磁盘读取并渲染（卡片形式）
let _allUsersCache = null  // 缓存数据，展开收起时不重复请求
function renderAllRecords(skipFetch) {
  const container = document.getElementById('events')
  const roomIds = Object.keys(currentRooms)
  if (roomIds.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">📋</div>暂无监听中的直播间</div>'
    return
  }
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  roomIds.forEach(rid => { roomMap[rid] = ci++ % 3 })

  // 有缓存且只是展开收起，直接用缓存渲染
  if (skipFetch && _allUsersCache) {
    renderAllCards(_allUsersCache, container, roomColors, roomMap)
    return
  }

  Promise.all(roomIds.map(rid =>
    fetch('/api/all_records/' + rid).then(r => r.json())
  )).then(results => {
    // 按用户聚合
    const userMap = {}
    results.forEach((res, ridx) => {
      if (!res.success || !res.records) return
      res.records.forEach(r => {
        // 判断是否私密直播（sec_uid空+unique_id='?'代表所有用户被脱敏）
        const isPrivate = !r.sec_uid && (!r.unique_id || r.unique_id === '?')
        const uid = isPrivate
          ? r.room_id + ':' + (r.display || r.real_name) + ':' + (r.consume_level||0) + ':' + (r.badge_level||0)
          : r.sec_uid || r.unique_id || r.real_name || '?'
        if (!userMap[uid]) {
          const colorIdx = roomMap[r.room_id] !== undefined ? roomMap[r.room_id] : ridx
          userMap[uid] = {
            display: r.display, real_name: r.real_name,
            unique_id: r.unique_id || '', sec_uid: r.sec_uid || '',
            badge_level: r.badge_level || 0, consume_level: r.consume_level || 0,
            mystery_man: r.mystery_man || 0,
            room_id: r.room_id, room_nickname: r.room_nickname,
            roomColor: roomColors[colorIdx],
            enter_count: 0, chats: [], gifts: [], time: r.time || 0,
            expanded: false, extra: null
          }
        }
        const u = userMap[uid]
        if (r.time > u.time) u.time = r.time
        if (!u.room_nickname && r.room_nickname) u.room_nickname = r.room_nickname
        if (!u.display && r.display) u.display = r.display
        if (!u.real_name && r.real_name) u.real_name = r.real_name
        if ((r.badge_level || 0) > u.badge_level) u.badge_level = r.badge_level
        if ((r.consume_level || 0) > u.consume_level) u.consume_level = r.consume_level
        if (!u.extra && r.extra) u.extra = r.extra
        if (r.event_type === 'enter') {
          u.enter_count++
        } else if (r.event_type === 'chat') {
          if (u.chats.length < 20) u.chats.push({content: r.content, time: r.time})
        } else if (r.event_type === 'gift') {
          if (u.gifts.length < 20) u.gifts.push({name: r.gift_name, count: r.count, time: r.time})
          // 私密直播间：礼物有extra则刷新真实名和用户数据
          if (r.extra && r.extra.nickname && r.extra.nickname !== u.real_name) {
            u.real_name = r.extra.nickname
            u.extra = r.extra
          }
        }
      })
    })

    // 按真实身份合并：同一room:display下，确认是同一人才合并
    const rawUsers = Object.values(userMap)
    const merged = []
    const mergeTracker = {} // "room:display" -> {identity: index}
    rawUsers.forEach(u => {
      const key = u.room_id + ':' + u.display
      const identity = (u.extra && u.extra.nickname) || u.real_name || '??'
      if (!mergeTracker[key]) mergeTracker[key] = {}
      // 完全相同的identity → 直接合并
      if (mergeTracker[key][identity] !== undefined) {
        const m = merged[mergeTracker[key][identity]]
        m.enter_count = (m.enter_count||0) + (u.enter_count||0)
        m.chats = [...(m.chats||[]), ...(u.chats||[])].slice(0, 20)
        m.gifts = [...(m.gifts||[]), ...(u.gifts||[])].slice(0, 20)
        if (u.time > m.time) m.time = u.time
        if ((u.badge_level||0) > (m.badge_level||0)) m.badge_level = u.badge_level
        if ((u.consume_level||0) > (m.consume_level||0)) m.consume_level = u.consume_level
        if (u.extra && u.extra.nickname) { m.real_name = u.extra.nickname } else if (!m.real_name && u.real_name) { m.real_name = u.real_name }
        if (!m.unique_id && u.unique_id) m.unique_id = u.unique_id
        if (!m.extra && u.extra) m.extra = u.extra
        if ((u.mystery_man||0) > (m.mystery_man||0)) m.mystery_man = u.mystery_man
        return
      }
      // 找已有的卡片：检查是否同一人
      let found = -1
      for (const id2 in mergeTracker[key]) {
        const m = merged[mergeTracker[key][id2]]
        if (u.extra && u.extra.nickname && u.extra.nickname === m.real_name) {
          found = mergeTracker[key][id2]
          break
        }
        if (m.extra && m.extra.nickname && m.extra.nickname === u.real_name) {
          found = mergeTracker[key][id2]
          break
        }
        if (!u.extra && !m.extra && u.real_name === m.real_name) {
          found = mergeTracker[key][id2]
          break
        }
        if (u.mystery_man >= 2 && m.mystery_man >= 2 && u.display === m.display) {
          found = mergeTracker[key][id2]
          break
        }
        // 私密直播间：同一display一个有extra一个没有→同一人（先来的没缓存，后来的送礼查到真实信息了）
        if (u.display === m.display && (u.extra ? 1 : 0) !== (m.extra ? 1 : 0)) {
          found = mergeTracker[key][id2]
          break
        }
      }
      if (found >= 0) {
        mergeTracker[key][identity] = found
        const m = merged[found]
        m.enter_count = (m.enter_count||0) + (u.enter_count||0)
        m.chats = [...(m.chats||[]), ...(u.chats||[])].slice(0, 20)
        m.gifts = [...(m.gifts||[]), ...(u.gifts||[])].slice(0, 20)
        if (u.time > m.time) m.time = u.time
        if ((u.badge_level||0) > (m.badge_level||0)) m.badge_level = u.badge_level
        if ((u.consume_level||0) > (m.consume_level||0)) m.consume_level = u.consume_level
        if (u.extra && u.extra.nickname) { m.real_name = u.extra.nickname } else if (!m.real_name && u.real_name) { m.real_name = u.real_name }
        if (!m.unique_id && u.unique_id) m.unique_id = u.unique_id
        if (!m.extra && u.extra) m.extra = u.extra
        if ((u.mystery_man||0) > (m.mystery_man||0)) m.mystery_man = u.mystery_man
      } else {
        mergeTracker[key][identity] = merged.length
        merged.push({
          display: u.display, real_name: u.real_name,
          sec_uid: u.sec_uid || '', unique_id: u.unique_id || '',
          badge_level: u.badge_level || 0, consume_level: u.consume_level || 0,
          mystery_man: u.mystery_man || 0,
          room_id: u.room_id, room_nickname: u.room_nickname,
          roomColor: u.roomColor,
          enter_count: u.enter_count || 0,
          chats: [...(u.chats||[])],
          gifts: [...(u.gifts||[])],
          time: u.time || 0, expanded: false, extra: u.extra || null
        })
      }
    })
    const users = merged.sort((a, b) => b.time - a.time)
    // 私密直播间：从mysteries实时数据里补全真实名和extra
    users.forEach(u => {
      if (u.extra === null) {
        // 在mysteries里按display匹配（送礼更新过real_name和extra）
        for (const mk in mysteries) {
          const m = mysteries[mk]
          if (m.room_id === u.room_id && m.extra && (m.display === u.display || m.display === u.real_name)) {
            u.real_name = m.real_name
            u.extra = m.extra
            break
          }
        }
      }
    })
    _allUsersCache = users
    renderAllCards(users, container, roomColors, roomMap)
  }).catch(() => {
    container.innerHTML = '<div class="empty" style="color:#fe2c55">加载失败</div>'
  })
}

// 渲染全部用户卡片（从缓存）
function renderAllCards(users, container, roomColors, roomMap) {
  if (users.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">📋</div>暂无记录<br><span style="font-size:11px;color:#666">点击刷新同步最新数据</span></div>'
    return
  }

  let html = ''
  users.forEach((u, idx) => {
    const totalActions = u.chats.length + u.gifts.length
    const uid = u.sec_uid || (u.unique_id && u.unique_id !== '?' ? u.unique_id : 'u' + idx)
    const uname = escapeHtml(u.real_name || u.display || u.unique_id || '?')
    const uniqueId = escapeHtml(u.unique_id || u.sec_uid?.slice(0,12) || u.extra?.sec_uid?.slice(0,12) || '?')

    const isMystery = u.mystery_man >= 2
    html += `<div class="event ${isMystery?'mystery':'regular'}${u.expanded?' exp':''}" data-su="${uid}" style="height:auto;min-height:80px">`
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`
    html += `<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap;min-width:0;flex:1">`
    html += `<span style="font-size:10px;color:${u.roomColor};font-weight:600">${escapeHtml(u.room_nickname || '?')}</span>`
    html += ` <span class="tag ${isMystery?'mystery':'reg'}" style="font-size:9px${isMystery ? ';color:#fe2c55':''}">${isMystery ? '神秘人' : '普通'}</span>`
    if (u.badge_level) html += ` <span class="tag lv" style="font-size:9px">🏅${u.badge_level}</span>`
    if (u.consume_level) html += ` <span class="tag dia" style="font-size:9px">💎${u.consume_level}</span>`
    html += `</div>`
    html += `<span style="color:#666;font-size:11px;cursor:pointer;flex-shrink:0;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleAllExpand('${uid}',${idx})">${u.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`}</span>`
    html += `</div>`
    html += `<div class="name-box"><span class="name-text ${isMystery?'mn':'rn'}">${escapeHtml(u.real_name || u.display || '?')}${u.display && u.display !== (u.real_name||u.display) ? `<span class="dp">${escapeHtml(u.display)}</span>` : ''}</span></div>`
    html += `<div style="font-size:10px;color:#888;margin:1px 0">🆔 ${uniqueId}</div>`
    // 私密直播间：有真实数据则显示粉丝数/IP/签名/主页
    if (u.extra && u.extra.nickname) {
      const ft = `粉丝${u.extra.follower_count} 作品${u.extra.aweme_count}`
      if (ft) html += `<div style="font-size:10px;color:#888">📊 ${ft}</div>`
      if (u.extra.ip_location) html += `<div style="font-size:10px;color:#888">🌍 ${escapeHtml(u.extra.ip_location)}</div>`
      if (u.extra.signature) html += `<div style="font-size:10px;color:#777;margin-top:1px">📝 ${escapeHtml(u.extra.signature)}</div>`
      if (u.extra.sec_uid) html += `<div style="font-size:10px;color:#555;margin-top:1px"><a class="link" href="javascript:;" onclick="window.open('https://www.douyin.com/user/${u.extra.sec_uid}','_blank')">🔗 主页</a></div>`
    }
    html += `<div style="font-size:10px;color:#777;margin:1px 0">`
    if (u.enter_count) html += `🚪${u.enter_count}次 `
    if (u.chats.length) html += `💬${u.chats.length}条 `
    if (u.gifts.length) html += `🎁${u.gifts.length}个`
    html += `</div>`
    if (totalActions > 0) {
      html += `<div id="all-actions-${uid}" style="display:${u.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
      u.chats.forEach(c => {
        html += `<div style="font-size:11px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
      })
      u.gifts.forEach(g => {
        html += `<div style="font-size:11px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
      })
      html += `</div>`
      html += `<div style="font-size:11px;color:#666;margin-top:2px;cursor:pointer;user-select:none" class="toggle-btn" data-collapsed="▼ ${totalActions}条互动" onclick="toggleAllExpand('${uid}',${idx})">`
      html += u.expanded ? '▲ 收起' : `▼ ${totalActions}条互动`
      html += `</div>`
    }
    html += `</div>`
  })
  container.innerHTML = html
}

// 全部用户卡片展开/收起
function toggleAllExpand(key, idx) {
  const users = _allUsersCache
  if (users && users[idx]) {
    users[idx].expanded = !users[idx].expanded
    const card = document.querySelector(`[data-su="${CSS.escape(key)}"]`)
    if (card) card.classList.toggle('exp')
    const actions = document.getElementById(`all-actions-${key}`)
    if (actions) actions.style.display = users[idx].expanded ? 'block' : 'none'
    card?.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.textContent = users[idx].expanded ? '▲ 收起' : btn.dataset.collapsed
    })
  }
}

function toggleExpand(secUid) {
  if (mysteries[secUid]) {
    mysteries[secUid].expanded = !mysteries[secUid].expanded
    const card = document.querySelector(`[data-su="${CSS.escape(secUid)}"]`)
    if (card) card.classList.toggle('exp')
    const actions = document.getElementById(`actions-${secUid}`)
    if (actions) actions.style.display = mysteries[secUid].expanded ? 'block' : 'none'
    card?.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.textContent = mysteries[secUid].expanded ? '▲ 收起' : btn.dataset.collapsed
    })
  }
}

// 点击名字展开/收起截断
function toggleName(secUid) {
  const card = document.querySelector(`[data-su="${secUid}"]`)
  if (card) {
    const nameEl = card.querySelector('.name-text')
    if (nameEl) nameEl.classList.toggle('exp')
  }
}

// 回车提交
document.getElementById('input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') connect()
});
// 输入时动态切换按钮文字
document.getElementById('input').addEventListener('keyup', resetBtnText)
document.getElementById('input').addEventListener('blur', resetBtnText)

// 定时刷新活跃房间列表
setInterval(refreshRooms, 5000)

function refreshRooms() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (data.count > 0) {
        document.getElementById('statsText').textContent = `${data.count}/${data.max}房`
      } else {
        document.getElementById('statsText').textContent = '0房'
      }
    })
}

function stopRoom(roomId) {
  // 关闭SSE
  if (eventSources[roomId]) {
    eventSources[roomId].close()
    delete eventSources[roomId]
  }
  if (disconnectTimers[roomId]) {
    clearTimeout(disconnectTimers[roomId])
    delete disconnectTimers[roomId]
  }
  // 移除该房间的神秘人
  Object.keys(mysteries).forEach(secUid => {
    if (mysteries[secUid].room_id === roomId) {
      delete mysteries[secUid]
    }
  })
  delete currentRooms[roomId]
  renderMysteries()
  fetch('/api/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room_id: roomId})
  }).then(() => {
    if (Object.keys(currentRooms).length === 0) {
      document.getElementById('btn').textContent = '🔍 监听'
      document.getElementById('btn').className = ''
      lastRoomId = null
      setStatus('未连接', 'gray')
    }
    refreshRooms()
  })
}

function stopAll() {
  // 关闭所有SSE
  Object.keys(eventSources).forEach(rid => {
    eventSources[rid].close()
  })
  eventSources = {}
  disconnectTimers = {}
  Object.keys(mysteries).forEach(k => delete mysteries[k])
  Object.keys(currentRooms).forEach(k => delete currentRooms[k])
  document.getElementById('btn').textContent = '🔍 监听'
  document.getElementById('btn').className = ''
  lastRoomId = null
  setStatus('未连接', 'gray')
  document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>已停止</div>'
  fetch('/api/stop_all', {method: 'POST'}).then(() => refreshRooms())
}

// 页面加载时：检测服务端是否已有监听中的房间，自动重连
;(function autoReconnectOnLoad() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      if (data.count > 0) {
        data.active.forEach(r => {
          currentRooms[r.room_id] = {nickname: r.nickname || r.room_id}
          connectSSE(r.room_id)
        })
        lastRoomId = data.active[0].room_id
        document.getElementById('btn').textContent = '停止'
        document.getElementById('btn').className = 'stop-btn'
        setStatus('监听中', 'green')
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
    })
    .catch(() => {})
})()

/* ═══ Anime.js 动画增强 ═══ */
const { animate, stagger, spring } = anime;

/* ---- 状态圆点呼吸 ---- */
(function dotPulse(){
  const dot = document.getElementById('dot');
  let anim = null;
  const obs = new MutationObserver(() => {
    if(anim) { anim.pause(); anim = null; }
    if(dot.classList.contains('green')){
      anim = animate(dot, {
        boxShadow: ['0 0 0 0 rgba(52,199,89,0)', '0 0 0 6px rgba(52,199,89,0.3)'],
        duration: 1500,
        loop: true,
        ease: 'inOutSine',
      });
    } else if(dot.classList.contains('red')){
      anim = animate(dot, {
        boxShadow: ['0 0 0 0 rgba(255,59,48,0)', '0 0 0 5px rgba(255,59,48,0.2)'],
        duration: 1200,
        loop: true,
        ease: 'inOutSine',
      });
    } else {
      dot.style.boxShadow = 'none';
    }
  });
  obs.observe(dot, { attributes: true, attributeFilter: ['class'] });
})();

/* ---- 按钮监听光晕 ---- */
(function btnGlow(){
  const btn = document.getElementById('btn');
  let glow = null;
  const obs = new MutationObserver(() => {
    if(glow) { glow.pause(); glow = null; }
    if(btn.classList.contains('stop-btn')){
      btn.style.transition = 'box-shadow .3s';
      glow = animate(btn, {
        boxShadow: ['0 0 0 0 rgba(255,107,53,0)', '0 0 12px 3px rgba(255,107,53,0.25)'],
        duration: 2000,
        loop: true,
        ease: 'inOutSine',
      });
    } else {
      btn.style.boxShadow = 'none';
    }
  });
  obs.observe(btn, { attributes: true, attributeFilter: ['class'] });
})();

/* ---- Hook renderMysteries 添加卡片动画 ---- */
const origRender = renderMysteries;
renderMysteries = function(){
  origRender();
  const cards = document.querySelectorAll('.events > .event');
  cards.forEach(c => { c.style.opacity = '0'; c.style.transform = 'translateY(8px)'; });
  animate(cards, {
    opacity: [0,1],
    translateY: [8,0],
    duration: 400,
    delay: stagger(60),
    ease: 'outCubic',
  });
};

/* ---- Hook renderAllCards 添加卡片动画 ---- */
const origRenderAll = renderAllCards;
renderAllCards = function(users, container, roomColors, roomMap){
  origRenderAll(users, container, roomColors, roomMap);
  const cards = document.querySelectorAll('.events > .event');
  cards.forEach(c => { c.style.opacity = '0'; c.style.transform = 'translateY(8px)'; });
  animate(cards, {
    opacity: [0,1],
    translateY: [8,0],
    duration: 400,
    delay: stagger(60),
    ease: 'outCubic',
  });
};

/* ---- 模式切换卡片动画 ---- */
const origSwitch = switchMode;
switchMode = function(mode){
  origSwitch(mode);
  // 切换后卡片已有新内容，动画在 render 函数里已触发
};
</script>
</body>
</html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
