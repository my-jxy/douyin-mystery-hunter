"""抖音神秘人猎人 - 结果写入文件版"""
import sys, os, time, gzip, json, threading, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder
from dy_apis.douyin_api import DouyinAPI
from utils.dy_util import generate_signature
from urllib.parse import urlencode
from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2

LIVE_ID = sys.argv[1] if len(sys.argv) > 1 else "7643331953759996672"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "神秘人011555"

room_id = LIVE_ID
auth = cu.dy_live_auth
user_unique_id = auth.cookie.get('uid', '7638929563125138984')

log_file = os.path.expanduser(f"~/mystery_log_{LIVE_ID}.txt")
with open(log_file, "w") as f:
    f.write(f"[{time.strftime('%H:%M:%S')}] 开始监听 {LIVE_ID}, 目标={TARGET}\n")

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

user_cache = {}

def lookup_user(sec_uid):
    if sec_uid in user_cache:
        return user_cache[sec_uid]
    try:
        user_url = f"https://www.douyin.com/user/{sec_uid}"
        result = DouyinAPI.get_user_info(auth, user_url)
        user = result.get('user', {})
        info = {
            'nickname': user.get('nickname', '?'),
            'unique_id': user.get('unique_id') or user.get('short_id', '?'),
            'gender': (lambda g: ['未设置','男','女'][g] if isinstance(g, int) and 0 <= g <= 2 else str(g) if g else '未知')(user.get('gender')),
            'ip_location': user.get('ip_location', ''),
            'follower_count': user.get('follower_count', 0),
            'sec_uid': sec_uid,
        }
        user_cache[sec_uid] = info
        return info
    except Exception as e:
        return {'nickname': f'[查询失败: {e}]', 'sec_uid': sec_uid}

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
                display = user.desensitized_nickname or "神秘人"
                if user.mystery_man or user.is_anonymous:
                    info = lookup_user(user.sec_uid)
                    log(f"🔍 神秘人进入! 显示={display} | 真实={info.get('nickname','?')} | ID={info.get('sec_uid','?')} | 抖音号={info.get('unique_id','?')} | 性别={info.get('gender','?')} | IP={info.get('ip_location','?')}")
                    if TARGET and display == TARGET:
                        log(f"🎯🎯🎯 目标找到! 真实身份={info.get('nickname','?')} | 抖音号={info.get('unique_id','?')} | 性别={info.get('gender','?')} | IP={info.get('ip_location','?')} | 主页=https://www.douyin.com/user/{user.sec_uid}")
            elif item.method == 'WebcastGiftMessage':
                msg = Live_pb2.GiftMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                display = user.desensitized_nickname or "神秘人"
                if user.mystery_man or user.is_anonymous or (TARGET and display == TARGET):
                    info = lookup_user(user.sec_uid)
                    log(f"🎁 [送礼] {display} → {msg.gift.name} x{msg.comboCount} | 真实={info.get('nickname','?')} | ID={info.get('sec_uid','?')}")
            elif item.method == 'WebcastChatMessage':
                msg = Live_pb2.ChatMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                display = user.desensitized_nickname or "神秘人"
                if TARGET and display == TARGET:
                    info = lookup_user(user.sec_uid)
                    log(f"💬 [弹幕] {display}: {msg.content} | 真实={info.get('nickname','?')}")
    except Exception as e:
        pass

def on_open(ws):
    log(f"✅ 连接成功! 房间={LIVE_ID}, 目标={TARGET}")
    def ping():
        while True:
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(10)
            except: break
    threading.Thread(target=ping, daemon=True).start()

def on_error(ws, error):
    log(f"❌ 错误: {error}")

def on_close(ws, code, msg):
    log(f"⚠️ 连接关闭 (code={code})")

sig = generate_signature(room_id, user_unique_id)

params = Params()
(params.add_param('app_name','douyin_web').add_param('version_code','180800')
 .add_param('webcast_sdk_version','1.0.15').add_param('update_version_code','1.0.15')
 .add_param('compress','gzip').add_param('device_platform','web')
 .add_param('cookie_enabled','true').add_param('screen_width','1707')
 .add_param('screen_height','960').add_param('browser_language','zh-CN')
 .add_param('browser_platform','Win32').add_param('browser_name','Mozilla')
 .add_param('browser_version',HeaderBuilder.ua.split('Mozilla/')[-1])
 .add_param('browser_online','true').add_param('tz_name','Etc/GMT-8')
 .add_param('cursor','-1').add_param('host','https://live.douyin.com')
 .add_param('aid','6383').add_param('live_id','1').add_param('did_rule','3')
 .add_param('endpoint','live_pc').add_param('support_wrds','1')
 .add_param('user_unique_id',user_unique_id).add_param('im_path','/webcast/im/fetch/')
 .add_param('identity','audience').add_param('need_persist_msg_count','15')
 .add_param('insert_task_id','').add_param('live_reason','')
 .add_param('room_id',room_id).add_param('heartbeatDuration','0')
 .add_param('signature',sig))

wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"

ws = WebSocketApp(url=wss_url,
    header={'Pragma':'no-cache','Accept-Language':'zh-CN,zh;q=0.9','User-Agent':HeaderBuilder.ua,
            'Upgrade':'websocket','Cache-Control':'no-cache','Connection':'Upgrade'},
    cookie=auth.cookie_str,
    on_message=on_message, on_open=on_open,
    on_error=on_error, on_close=on_close)

log("启动中...")
try:
    ws.run_forever(origin='https://live.douyin.com')
except Exception as e:
    log(f"异常: {e}")
