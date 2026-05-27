"""测试 RoomUserSeqMessage - 获取当前在线观众列表"""
import sys, os, time, gzip, threading
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
room_id = LIVE_ID
auth = cu.dy_live_auth
user_unique_id = auth.cookie.get('uid', '7638929563125138984')

log_file = os.path.expanduser(f"~/room_users_{LIVE_ID}.txt")
with open(log_file, "w") as f:
    f.write(f"[{time.strftime('%H:%M:%S')}] 开始扫描 {LIVE_ID}\n")

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

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

user_cache = {}
target_sec_uid = "MS4wLjABAAAAG3_E5jkCuqDHPHqOkYfX8EsYsm0ncEEk2wtQmRoJJddMXM6CpFfs1Ba_TSX-JrdN"  # 柠檬酸Suan

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
        }
        user_cache[sec_uid] = info
        return info
    except Exception as e:
        return {'nickname': f'[err:{str(e)[:30]}]'}

# 已处理的 message_id 去重
processed_ids = set()

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
            if item.method == 'WebcastRoomUserSeqMessage':
                msg = Live_pb2.RoomUserSeqMessage()
                msg.ParseFromString(item.payload)
                total = msg.totalUser or msg.total or 0
                log(f"📊 RoomUserSeq: 在线{msg.popStr} 总{total} 人气{msg.popularity}")
                
                # 解析 ranksList (排行榜)
                for contributor in msg.ranksList:
                    user = contributor.user
                    is_hidden = contributor.isHidden
                    rank = contributor.rank
                    score = contributor.score
                    display = user.desensitized_nickname or user.nickname
                    real = user.nickname
                    
                    line = f"  #{rank} 显示={display}"
                    if is_hidden:
                        # 神秘人！
                        info = lookup_user(user.sec_uid)
                        line += f" 🔥神秘人! 真实={info.get('nickname','?')} 抖音号={info.get('unique_id','?')} IP={info.get('ip_location','?')}"
                    elif display != real:
                        line += f" ⚡显示≠真实: 真实={real}"
                    else:
                        line += f" 昵称={real}"
                    line += f" sec_uid={user.sec_uid[:40]}..."
                    log(line)
                    
                    # 检查是否是目标
                    if user.sec_uid == target_sec_uid:
                        log(f"🎯🎯🎯 目标在排行榜中! 排名#{rank} 真实={real}")
                
                # 解析 seatsList (座次)
                for i, contributor in enumerate(msg.seatsList):
                    user = contributor.user
                    is_hidden = contributor.isHidden
                    display = user.desensitized_nickname or user.nickname
                    real = user.nickname
                    line = f"  座位#{i+1} 显示={display}"
                    if is_hidden:
                        info = lookup_user(user.sec_uid) 
                        line += f" 🔥神秘人! 真实={info.get('nickname','?')}"
                    elif display != real:
                        line += f" ⚡显示≠真实: 真实={real}"
                    else:
                        line += f" 昵称={real}"
                    log(line)
                    
                    if user.sec_uid == target_sec_uid:
                        log(f"🎯🎯🎯 目标在座位列表中!")
                
            elif item.method in ['WebcastMemberMessage', 'WebcastGiftMessage', 'WebcastChatMessage']:
                pass  # 忽略，我们只关心 RoomUserSeqMessage
                
    except Exception as e:
        pass

def on_open(ws):
    log(f"✅ 连接成功! 房间={LIVE_ID}")
    log(f"🔍 正在监听 RoomUserSeqMessage 获取在线观众...")
    def ping():
        while True:
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(5)
            except: break
    threading.Thread(target=ping, daemon=True).start()

def on_error(ws, error):
    log(f"❌ 错误: {error}")

def on_close(ws, code, msg):
    log(f"⚠️ 连接关闭 (code={code})")

ws = WebSocketApp(url=wss_url,
    header={'Pragma':'no-cache','Accept-Language':'zh-CN,zh;q=0.9','User-Agent':HeaderBuilder.ua,
            'Upgrade':'websocket','Cache-Control':'no-cache','Connection':'Upgrade'},
    cookie=auth.cookie_str,
    on_message=on_message, on_open=on_open,
    on_error=on_error, on_close=on_close)

log("启动中...")
try:
    ws.run_forever(origin='https://live.douyin.com')
except KeyboardInterrupt:
    log("停止")
except Exception as e:
    log(f"异常: {e}")
