"""直接连接抖音直播间 WebSocket（简化版，同 hunt_mystery.py）
用法: python3 connect_direct.py <直播间ID>

仅检测神秘人（经典/深度/dou匿名）+ 排行榜显示
"""
import sys, os, time, gzip, json, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder
from utils.dy_util import generate_signature
from urllib.parse import urlencode
from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2

# 参数
live_id = sys.argv[1] if len(sys.argv) > 1 else "7643362348794776355"
room_id = live_id
user_unique_id = cu.dy_live_auth.cookie.get('uid', '7638929563125138984')
auth = cu.dy_live_auth

print("=== 直接连接直播间 WebSocket ===")
print(f"Room ID: {room_id}")

# 生成签名
sig = generate_signature(room_id, user_unique_id)

# 构建 params
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

# ===== 工具函数 =====
GENDER_MAP = {0: '未设置', 1: '男', 2: '女'}
_level_cache = {}

def user_id_str(user):
    """安全获取用户抖音号"""
    return (getattr(user, 'unique_id', '') or 
            getattr(user, 'display_id', '') or 
            str(user.short_id or '?'))

def get_badge_level(user):
    """从badge_image_list提取抖音等级，失败则查缓存"""
    try:
        for badge in user.badge_image_list:
            c = badge.content if hasattr(badge, 'content') else None
            if c and hasattr(c, 'level') and c.level:
                sec_uid = getattr(user, 'sec_uid', None)
                if sec_uid:
                    _level_cache[sec_uid] = c.level
                return c.level
    except:
        pass
    sec_uid = getattr(user, 'sec_uid', None)
    if sec_uid and sec_uid in _level_cache:
        return _level_cache[sec_uid]
    return 0

def is_real_mystery_user(user):
    display = (user.desensitized_nickname or '').strip()
    real_name = (user.nickname or '').strip()
    mm = getattr(user, 'mystery_man', 0)
    is_masked = display.startswith('神秘人') and len(display) > 3
    is_dou = (display.startswith('dou') and len(display) > 5) or (real_name.startswith('dou') and len(real_name) > 5)
    is_deep = mm >= 2
    return is_masked or is_dou or is_deep, display, real_name, mm

# ===== 统计 =====
mystery_count = 0
recent_mysteries = []

def on_message(ws, message):
    global mystery_count
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
                
                is_m, display, real_name, mm = is_real_mystery_user(user)
                if is_m:
                    mystery_count += 1
                    info = {
                        'display': display, 'real_name': real_name,
                        'sec_uid': user.sec_uid,
                        'unique_id': user_id_str(user),
                    }
                    recent_mysteries.append(info)
                    print(f"\n{'='*50}")
                    print(f"🎯🎯🎯 抓到真实神秘人 #{mystery_count}！🎯🎯🎯")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  📱 抖音号: {user_id_str(user)}")
                    print(f"  👤 性别: {GENDER_MAP.get(user.gender, '未知')}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    print(f"{'='*50}")
                    
            elif item.method == 'WebcastChatMessage':
                msg = Live_pb2.ChatMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                is_m, display, real_name, mm = is_real_mystery_user(user)
                if is_m:
                    print(f"\n💬 [神秘人] 发弹幕:")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  内容: {msg.content}")
                    
            elif item.method == 'WebcastGiftMessage':
                msg = Live_pb2.GiftMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                is_m, display, real_name, mm = is_real_mystery_user(user)
                if is_m:
                    print(f"\n🎁 [神秘人] 送礼:")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  礼物: {msg.gift.name} x{msg.comboCount}")
                    
            elif item.method == 'WebcastRoomStatsMessage':
                msg = Live_pb2.RoomStatsMessage()
                msg.ParseFromString(item.payload)
                print(f"\r📊 在线: {msg.displayShort} | 累计: {msg.total} | 神秘人: {mystery_count}", end='')
                
            elif item.method == 'WebcastRoomRankMessage':
                msg = Live_pb2.RoomRankMessage()
                msg.ParseFromString(item.payload)
                rank_list = []
                for rank in msg.ranksList:
                    nick = rank.user.nickname
                    badge_lv = get_badge_level(rank.user)
                    consume_lv = rank.user.consume_diamond_level
                    is_m, display, real_name, mm = is_real_mystery_user(rank.user)
                    if is_m:
                        recent_mysteries.append({'display': display, 'real_name': real_name, 'sec_uid': rank.user.sec_uid})
                        print(f"\n🏆 榜上有神秘人！{display} → {real_name} 🆔 {rank.user.sec_uid}")
                    rank_pos = getattr(rank, 'rank', len(rank_list) + 1)
                    rank_list.append(f"  #{rank_pos} {nick} | 🏅{badge_lv} 💎{consume_lv}")
                if rank_list:
                    print(f"\n🏆 排行榜 TOP3:\n" + "\n".join(rank_list) + "\n")
                    
            elif item.method == 'WebcastRoomUserSeqMessage':
                msg = Live_pb2.RoomUserSeqMessage()
                msg.ParseFromString(item.payload)
                top = []
                for c in msg.ranksList[:3]:
                    name = c.user.nickname if not c.isHidden else '隐藏用户'
                    bl = get_badge_level(c.user)
                    cl = c.user.consume_diamond_level
                    if c.isHidden:
                        is_m, d, rn, _ = is_real_mystery_user(c.user)
                        if is_m:
                            recent_mysteries.append({'display': d, 'real_name': rn, 'sec_uid': c.user.sec_uid})
                            print(f"\n🔒 隐藏榜上有神秘人！{d} → {rn}")
                    top.append(f"  #{c.rank} {name} | 🏅{bl} 💎{cl}")
                if top:
                    print(f"\n📊 榜一榜二榜三:\n" + "\n".join(top) + "\n")
                    
    except Exception:
        pass

def on_open(ws):
    print(f"✅ 已连接到直播间: {live_id}")
    print("🔍 监听神秘人 + 排行榜...（Ctrl+C 停止）\n")
    def ping():
        while True:
            frame = Live_pb2.PushFrame()
            frame.payloadType = "hb"
            try:
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(5)
            except:
                break
    threading.Thread(target=ping, daemon=True).start()

def on_error(ws, error):
    print(f"\n❌ 错误: {error}")

def on_close(ws, code, msg):
    print(f"\n⚠️ 连接关闭 (code={code})")
    if mystery_count > 0:
        print(f"\n📊 共抓到 {mystery_count} 个神秘人")

ws = WebSocketApp(url=wss_url,
    header={'Pragma':'no-cache','Accept-Language':'zh-CN,zh;q=0.9','User-Agent':HeaderBuilder.ua,
            'Upgrade':'websocket','Cache-Control':'no-cache','Connection':'Upgrade'},
    cookie=auth.cookie_str,
    on_message=on_message, on_open=on_open,
    on_error=on_error, on_close=on_close)

try:
    ws.run_forever(origin='https://live.douyin.com')
except KeyboardInterrupt:
    print("\n👋 停止监听")
except Exception as e:
    print(f"\n❌ 连接失败: {e}")
