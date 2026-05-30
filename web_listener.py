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
    # 纯数字抖音号 → 用旧版v2 API查
    if douyin_id.isdigit():
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
            if rid: return {'success': True, 'room_id': rid.group(1), 'type': 'live'}
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
                            if item.method == 'WebcastMemberMessage':
                                msg = Live_pb2.MemberMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                if is_mystery:
                                    self.mystery_count += 1
                                    badge_lv = get_badge_level(user)
                                    info = {'display': display, 'real_name': real_name,
                                            'unique_id': user_id_str(user), 'sec_uid': user.sec_uid,
                                            'gender': gender_str(user.gender),
                                            'consume_level': user.consume_diamond_level,
                                            'badge_level': badge_lv, 'mystery_man': mm}
                                    self.recent_mysteries.append(info)
                                    extra = lookup_user(user.sec_uid)
                                    if extra:
                                        # 用API查询到的真实昵称覆盖
                                        if extra.get('nickname') and extra['nickname'] != real_name:
                                            info['real_name'] = extra['nickname']
                                        info['extra'] = extra
                                    info['room_id'] = self.room_id
                                    info['room_nickname'] = self.nickname
                                    self.send_event('mystery_enter', info)

                            elif item.method == 'WebcastChatMessage':
                                msg = Live_pb2.ChatMessage()
                                msg.ParseFromString(item.payload)
                                user = msg.user
                                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                if is_mystery:
                                    badge_lv = get_badge_level(user)
                                    chat_info = {
                                        'display': display, 'real_name': real_name,
                                        'content': msg.content, 'sec_uid': user.sec_uid,
                                        'badge_level': badge_lv,
                                        'consume_level': user.consume_diamond_level,
                                        'unique_id': user_id_str(user)}
                                    extra = lookup_user(user.sec_uid)
                                    if extra:
                                        if extra.get('nickname') and extra['nickname'] != real_name:
                                            chat_info['real_name'] = extra['nickname']
                                        chat_info['extra'] = extra
                                    chat_info['room_id'] = self.room_id
                                    chat_info['room_nickname'] = self.nickname
                                    self.send_event('mystery_chat', chat_info)

                            elif item.method == 'WebcastGiftMessage':
                                try:
                                    msg = Live_pb2.GiftMessage()
                                    msg.ParseFromString(item.payload)
                                    user = msg.user
                                    is_mystery, display, real_name, mm = is_real_mystery_user(user)
                                    if is_mystery:
                                        gift_info = {
                                            'display': display, 'real_name': real_name,
                                            'sec_uid': user.sec_uid, 'gift_name': msg.gift.name if msg.gift else '?',
                                            'count': msg.comboCount,
                                            'badge_level': get_badge_level(user),
                                            'consume_level': user.consume_diamond_level,
                                            'unique_id': user_id_str(user)}
                                        extra = lookup_user(user.sec_uid)
                                        if extra:
                                            if extra.get('nickname') and extra['nickname'] != real_name:
                                                gift_info['real_name'] = extra['nickname']
                                            gift_info['extra'] = extra
                                        gift_info['room_id'] = self.room_id
                                        gift_info['room_nickname'] = self.nickname
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

@app.route('/api/history/<room_id>')
def history(room_id):
    """获取当前监听房间的神秘人历史"""
    listener = listeners.get(room_id)
    if not listener:
        return jsonify({'success': False, 'error': '未找到监听器'})
    return jsonify({'success': True, 'mystery_count': listener.mystery_count,
                    'history': listener.recent_mysteries[-50:]})

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

# ========== HTML 前端 ==========
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
h1{font-size:22px;text-align:center;padding:12px 0 8px;background:linear-gradient(135deg,#fe2c55,#ff6b35);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:700}
.input-group{display:flex;gap:8px;margin:12px 0}
.input-group input{flex:1;padding:12px 14px;border:1px solid #333;border-radius:10px;background:#1a1a1a;color:#e0e0e0;font-size:15px;outline:none;transition:border .2s}
.input-group input:focus{border-color:#fe2c55}
.input-group input::placeholder{color:#666}
.input-group button{padding:12px 18px;border:none;border-radius:10px;background:linear-gradient(135deg,#fe2c55,#ff6b35);color:#fff;font-size:15px;font-weight:600;cursor:pointer;white-space:nowrap;transition:opacity .2s}
.input-group button:disabled{opacity:.5;cursor:not-allowed}
.status-bar{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#1a1a1a;border-radius:10px;margin:8px 0;font-size:13px;color:#999}
.status-bar .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status-bar .dot.green{background:#34c759}
.status-bar .dot.red{background:#ff3b30}
.status-bar .dot.gray{background:#555}
.events{max-height:70vh;overflow-y:auto;padding:4px 0}
.events::-webkit-scrollbar{width:4px}
.events::-webkit-scrollbar-thumb{background:#333;border-radius:2px}
.event{padding:8px 12px;margin:4px 0;border-radius:8px;font-size:13px;line-height:1.5;animation:fadeIn .3s ease}
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
.summary{background:#1a1a1a;border-radius:10px;padding:10px 14px;margin:8px 0;font-size:13px}
.summary .row{display:flex;justify-content:space-between;padding:3px 0}
.summary .val{font-weight:600;color:#fe2c55}
</style>
</head>
<body>
<div class="container">
  <h1>🎯 神秘人猎人</h1>
  <div class="input-group">
    <input id="input" type="text" placeholder="抖音号 / 链接 / 直播间ID" autocomplete="off" enterkeyhint="search">
    <button id="btn" onclick="connect()">🔍 监听</button>
  </div>
  <div class="hint">支持：抖音号 · 直播间链接 · 主页链接 · 直播间ID</div>
  <div class="status-bar" id="statusBar">
    <span><span class="dot gray" id="dot"></span><span id="statusText">未连接</span></span>
    <span><span id="statsText" style="margin-right:8px">神秘人: 0</span><span id="syncBtn" onclick="syncAllRooms()" style="color:#5ac8fa;font-size:12px;cursor:pointer;display:none">🔄 同步</span></span>
  </div>
  <div class="summary" id="summary" style="display:none">
    <div class="row"><span>🎬 主播</span><span id="anchorName">-</span></div>
    <div class="row"><span>🆔 房间</span><span id="roomIdDisplay">-</span></div>
  </div>
  <div id="rooms" style="display:none;margin:6px 0"></div>
  <div class="events" id="events">
    <div class="empty"><div class="icon">🎯</div>输入抖音号或链接<br>点击「监听」开始</div>
  </div>
</div>
<script>
let eventSources = {}       // room_id -> EventSource
const currentRooms = {}     // room_id -> {nickname}
const mysteries = {}        // sec_uid -> {display, real_name, ..., room_id, room_nickname}
let disconnectTimers = {}   // room_id -> timer
let autoSyncTimer = null

function escapeHtml(text) {
  const d = document.createElement('div')
  d.textContent = text
  return d.innerHTML
}

function setStatus(text, color) {
  document.getElementById('statusText').textContent = text
  document.getElementById('dot').className = 'dot ' + color
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
      btn.disabled = false; btn.textContent = '🔍 监听'
      return
    }
    if (data.room_id && data.live_status == 1) {
      if (currentRooms[data.room_id]) {
        showToast('⚠️ 已在监听该直播间')
        btn.disabled = false; btn.textContent = '🔍 监听'
        return
      }
      startListening(data.room_id, data.nickname || '')
    } else if (data.room_id && data.live_status == 0) {
      showToast('❌ 该主播未在直播')
      btn.disabled = false; btn.textContent = '🔍 监听'
    } else {
      showToast('❌ 无法获取直播间信息')
      btn.disabled = false; btn.textContent = '🔍 监听'
    }
  })
  .catch(err => {
    showToast('❌ 网络错误: ' + err.message)
    btn.disabled = false; btn.textContent = '🔍 监听'
  })
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
      document.getElementById('syncBtn').style.display = 'inline'
      document.getElementById('summary').style.display = 'none'
      // 自动每30秒全量同步所有房间
      if (!autoSyncTimer) {
        autoSyncTimer = setInterval(() => {
          syncAllRooms(true)
        }, 30000)
      }
      // 首次监听显示提示
      if (Object.keys(mysteries).length === 0) {
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
      document.getElementById('btn').disabled = false
      document.getElementById('btn').textContent = '🔍 监听'
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
          if (!mysteries[h.sec_uid]) {
            const realName = h.real_name || h.display
            const extraData = h.extra || null
            mysteries[h.sec_uid] = {
              display: h.display, real_name: realName,
              sec_uid: h.sec_uid,
              unique_id: h.unique_id || extraData?.unique_id || '',
              badge_level: h.badge_level || 0, consume_level: h.consume_level || 0,
              extra: extraData,
              room_id: h.room_id || roomId,
              room_nickname: h.room_nickname || currentRooms[roomId]?.nickname || roomId,
              chats: [], gifts: [],
              time: Date.now(), expanded: false
            }
          }
        })
        renderMysteries()
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

function handleEvent(event, roomId) {
  const d = event.data
  // 补充房间信息
  const roomNick = currentRooms[roomId]?.nickname || roomId
  switch(event.type) {
    case 'init':
    case 'connected':
      cancelDisconnect(roomId)
      setStatus('已连接', 'green')
      break
    case 'disconnected':
      if (d.reconnecting) {
        setStatus('重连中...', 'gray')
      } else {
        setStatus('已断开', 'red')
      }
      break
    case 'mystery_enter':
      mysteries[d.sec_uid] = {
        display: d.display, real_name: d.real_name,
        sec_uid: d.sec_uid,
        unique_id: d.unique_id || d.extra?.unique_id || '',
        badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
        extra: d.extra || null,
        room_id: d.room_id || roomId,
        room_nickname: d.room_nickname || roomNick,
        chats: mysteries[d.sec_uid]?.chats || [],
        gifts: mysteries[d.sec_uid]?.gifts || [],
        time: Date.now(), expanded: false
      }
      renderMysteries()
      break
    case 'mystery_chat':
      if (!mysteries[d.sec_uid]) {
        mysteries[d.sec_uid] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: d.unique_id || '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick
        }
      }
      mysteries[d.sec_uid].chats.push({content: d.content, time: Date.now()})
      renderMysteries()
      break
    case 'mystery_gift':
      if (!mysteries[d.sec_uid]) {
        mysteries[d.sec_uid] = {
          display: d.display, real_name: d.real_name,
          sec_uid: d.sec_uid, unique_id: '',
          badge_level: d.badge_level || 0, consume_level: d.consume_level || 0,
          extra: null, chats: [], gifts: [], time: Date.now(), expanded: false,
          room_id: d.room_id || roomId,
          room_nickname: d.room_nickname || roomNick
        }
      }
      mysteries[d.sec_uid].gifts.push({name: d.gift_name, count: d.count, time: Date.now()})
      renderMysteries()
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
  const total = Object.keys(mysteries).length
  document.getElementById('statsText').textContent = '神秘人: ' + total
  if (total === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">🎯</div>输入抖音号或链接<br>点击「监听」开始</div>'
    return
  }
  // 房间颜色列表
  const roomColors = ['#fe2c55', '#5ac8fa', '#34c759']
  const roomMap = {}; let ci = 0
  Object.keys(currentRooms).forEach(rid => { roomMap[rid] = ci++ % 3 })

  let html = ''
  const sorted = Object.keys(mysteries).sort((a, b) => mysteries[b].time - mysteries[a].time)
  sorted.forEach((secUid, idx) => {
    const m = mysteries[secUid]
    const uniqueId = m.unique_id || m.extra?.unique_id || m.sec_uid?.slice(0,12) || '?'
    const followerText = m.extra ? `粉丝${m.extra.follower_count} 作品${m.extra.aweme_count}` : ''
    const ipText = m.extra?.ip_location ? `🌍 ${m.extra.ip_location}` : ''
    const totalActions = m.chats.length + m.gifts.length
    const isLast = idx === sorted.length - 1
    const colorIdx = roomMap[m.room_id] !== undefined ? roomMap[m.room_id] : 0
    const roomColor = roomColors[colorIdx]

    html += `<div class="event mystery" style="margin-bottom:${isLast?0:6}px">`
    // 房间标签 + 展开按钮
    html += `<div style="display:flex;justify-content:space-between;align-items:start">`
    html += `<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">`
    html += `<span style="font-size:11px;color:${roomColor};font-weight:600">${escapeHtml(m.room_nickname || '?')}</span>`
    if (m.display && m.display !== m.real_name) {
      html += `<span style="color:#888;font-size:12px">${escapeHtml(m.display)}</span>`
    }
    html += `</div>`
    html += `<span style="color:#666;font-size:11px;cursor:pointer" onclick="toggleExpand('${secUid}')">${m.expanded ? '▲' : '▼'}</span>`
    html += `</div>`
    html += `<div><strong style="color:#fe2c55">${escapeHtml(m.real_name)}</strong>`
    if (m.badge_level) html += ` <span class="tag lv">🏅${m.badge_level}</span>`
    if (m.consume_level) html += ` <span class="tag dia">💎${m.consume_level}</span>`
    html += `</div>`
    html += `<div style="font-size:12px;color:#888;margin:2px 0">🆔 ${escapeHtml(uniqueId)}</div>`
    if (followerText) html += `<div style="font-size:12px;color:#888">📊 ${followerText}</div>`
    if (ipText) html += `<div style="font-size:12px;color:#888">${ipText}</div>`
    if (m.extra?.signature) html += `<div style="font-size:12px;color:#777;margin-top:2px">📝 ${escapeHtml(m.extra.signature)}</div>`
    html += `<div style="font-size:11px;color:#555;margin-top:2px"><a class="link" href="javascript:;" onclick="window.open('https://www.douyin.com/user/${secUid}','_blank')">🔗 主页</a></div>`

    if (totalActions > 0) {
      html += `<div id="actions-${secUid}" style="display:${m.expanded?'block':'none'};margin-top:6px;border-top:1px solid #222;padding-top:4px">`
      m.chats.forEach(c => {
        html += `<div style="font-size:12px;color:#ccc;padding:2px 0">💬 ${escapeHtml(c.content)}</div>`
      })
      m.gifts.forEach(g => {
        html += `<div style="font-size:12px;color:#ff9500;padding:2px 0">🎁 ${escapeHtml(g.name)} x${g.count}</div>`
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

function toggleExpand(secUid) {
  if (mysteries[secUid]) {
    mysteries[secUid].expanded = !mysteries[secUid].expanded
    renderMysteries()
  }
}

// 同步所有房间
function syncAllRooms(silent) {
  const btn = document.getElementById('syncBtn')
  if (!silent) btn.textContent = '⏳ 同步中'
  let count = 0
  Object.keys(currentRooms).forEach(roomId => {
    fetch('/api/history/' + roomId)
      .then(r => r.json())
      .then(data => {
        if (data.success && data.history) {
          data.history.forEach(h => {
            if (!mysteries[h.sec_uid]) {
              const realName = h.real_name || h.display
              const extraData = h.extra || null
              mysteries[h.sec_uid] = {
                display: h.display, real_name: realName,
                sec_uid: h.sec_uid,
                unique_id: h.unique_id || extraData?.unique_id || '',
                badge_level: h.badge_level || 0, consume_level: h.consume_level || 0,
                extra: extraData,
                room_id: h.room_id || roomId,
                room_nickname: h.room_nickname || currentRooms[roomId]?.nickname || roomId,
                chats: [], gifts: [],
                time: Date.now(), expanded: false
              }
            }
          })
        }
        count++
        if (count >= Object.keys(currentRooms).length) {
          renderMysteries()
          btn.textContent = '🔄 同步'
        }
      })
      .catch(() => {
        count++
        if (count >= Object.keys(currentRooms).length) {
          btn.textContent = '🔄 同步'
        }
      })
  })
  if (Object.keys(currentRooms).length === 0) btn.textContent = '🔄 同步'
}

// 回车提交
document.getElementById('input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') connect()
});

// 定时刷新活跃房间列表
setInterval(refreshRooms, 5000)

function refreshRooms() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById('rooms')
      if (data.count === 0) {
        el.style.display = 'none'
        return
      }
      el.style.display = 'block'
      let html = '<div style="background:#1a1a1a;border-radius:10px;padding:8px 12px;font-size:13px">'
      html += `<div style="display:flex;justify-content:space-between;margin-bottom:4px;color:#888">`
      html += `<span>🎯 监听中 (${data.count}/${data.max})</span>`
      html += `<span onclick="stopAll()" style="color:#ff3b30;cursor:pointer">全部停止</span>`
      html += `</div>`
      data.active.forEach(r => {
        html += `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-top:1px solid #222">`
        html += `<span>${r.nickname || r.room_id} <span style="color:#888;font-size:12px">神秘人:${r.unique_count}</span></span>`
        html += `<span onclick="stopRoom('${r.room_id}')" style="color:#ff3b30;font-size:12px;cursor:pointer">停止</span>`
        html += `</div>`
      })
      html += '</div>'
      el.innerHTML = html
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
      if (autoSyncTimer) { clearInterval(autoSyncTimer); autoSyncTimer = null }
      document.getElementById('syncBtn').style.display = 'none'
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
  if (autoSyncTimer) { clearInterval(autoSyncTimer); autoSyncTimer = null }
  document.getElementById('syncBtn').style.display = 'none'
  document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>已停止</div>'
  document.getElementById('summary').style.display = 'none'
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
        document.getElementById('syncBtn').style.display = 'inline'
        if (!autoSyncTimer) {
          autoSyncTimer = setInterval(() => syncAllRooms(true), 30000)
        }
        setStatus('已连接', 'green')
        document.getElementById('events').innerHTML = '<div class="empty"><div class="icon">🎯</div>等待神秘人出现...</div>'
      }
    })
    .catch(() => {})
})()
</script>
</body>
</html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎯 神秘人猎人 Web 版启动: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
