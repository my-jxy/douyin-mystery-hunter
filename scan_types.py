"""记录 WebSocket 收到的所有消息类型"""
import sys, os, time, gzip, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder
from utils.dy_util import generate_signature
from urllib.parse import urlencode
from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2

LIVE_ID = sys.argv[1] if len(sys.argv) > 1 else "7643331953759996672"
room_id = LIVE_ID
auth = cu.dy_live_auth
user_unique_id = auth.cookie.get('uid', '7638929563125138984')

log_file = os.path.expanduser(f"~/ws_types_{LIVE_ID}.txt")
with open(log_file, "w") as f:
    f.write(f"[{time.strftime('%H:%M:%S')}] 开始记录 {LIVE_ID}\n")

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

seen_methods = {}
msg_count = 0

def on_message(ws, message):
    global msg_count
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
            method = item.method
            msg_count += 1
            
            if method not in seen_methods:
                seen_methods[method] = {'count': 0, 'size': 0}
            
            seen_methods[method]['count'] += 1
            seen_methods[method]['size'] += len(item.payload)
            
            # 30秒后打印一次统计
            if len(seen_methods) > 0 and len(seen_methods) % 5 == 0 and seen_methods[method]['count'] == 1:
                log(f"📡 发现新消息类型: {method} ({len(item.payload)} bytes)")
    
    except Exception as e:
        pass

last_report = time.time()

def on_open(ws):
    log(f"✅ 连接成功! 房间={LIVE_ID}")
    log(f"📋 我将记录所有消息类型")
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
    # 最终统计
    log(f"\n=== 最终统计 ({msg_count} 条消息) ===")
    for m, info in sorted(seen_methods.items(), key=lambda x: -x[1]['count']):
        log(f"  {m}: {info['count']}次, 总计{info['size']}bytes")

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
