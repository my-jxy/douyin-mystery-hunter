"""抖音神秘人猎人 🎯
用法: python3 hunt_mystery.py <直播间ID> [--target "神秘人XXXXX"]

检测真正的神秘人：desensitized_nickname 以"神秘人"开头
或 mystery_man >= 2（深度匿名模式），或 dou数字匿名模式。
"""
import sys, os, time, gzip, json, threading, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder
from utils.dy_util import generate_signature
from urllib.parse import urlencode
from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2

# ========== 参数解析 ==========
parser = argparse.ArgumentParser(description='抖音神秘人猎人 🎯')
parser.add_argument('live_id', help='直播间ID或链接末尾数字')
parser.add_argument('--target', '-t', help='指定要追查的神秘人显示名 (如 "神秘人011555")')
args = parser.parse_args()

LIVE_ID = args.live_id.split('/')[-1]
TARGET = args.target

room_id = LIVE_ID
user_unique_id = cu.dy_live_auth.cookie.get('uid', '7638929563125138984')
auth = cu.dy_live_auth

# ========== 工具函数 ==========
GENDER_MAP = {0: '未设置', 1: '男', 2: '女'}

def gender_str(g):
    return GENDER_MAP.get(g, '未知')

# 等级缓存：进入/弹幕时从badge_image_list提取，排行榜查不到时用缓存
_level_cache = {}

def user_id_str(user):
    """安全获取用户抖音号，处理 protobuf 字段不存在的坑"""
    return (getattr(user, 'unique_id', '') or 
            getattr(user, 'display_id', '') or 
            str(user.short_id or '?'))

def get_badge_level(user):
    """从badge_image_list提取抖音等级，失败则尝试缓存"""
    try:
        for badge in user.badge_image_list:
            c = badge.content if hasattr(badge, 'content') else None
            if c and hasattr(c, 'level') and c.level:
                # 缓存起来供排行榜消息使用
                sec_uid = getattr(user, 'sec_uid', None)
                if sec_uid:
                    _level_cache[sec_uid] = c.level
                return c.level
    except:
        pass
    # 查缓存
    sec_uid = getattr(user, 'sec_uid', None)
    if sec_uid and sec_uid in _level_cache:
        return _level_cache[sec_uid]
    return 0

# ========== 轻量级用户信息查询 ==========
# 使用 ttwid + 空msToken + 无a_bogus 绕过反爬
# 只在抓到真正神秘人时才调用
import requests as _req
import urllib3 as _urllib3
_urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)

_user_info_cache = {}
_TTWID = cu.dy_live_auth.cookie.get('ttwid', '')

def lookup_user(sec_uid):
    """轻量级API查询用户信息（缓存 + 省着用）"""
    if sec_uid in _user_info_cache:
        return _user_info_cache[sec_uid]
    if not sec_uid or len(sec_uid) < 10:
        return {}
    try:
        params = {
            'device_platform': 'webapp',
            'aid': '6383',
            'sec_user_id': sec_uid,
            'version_code': '170400',
            'msToken': '',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/116.0.0.0',
            'Referer': f'https://www.douyin.com/user/{sec_uid}',
        }
        cookies = {'ttwid': _TTWID} if _TTWID else {}
        resp = _req.get(
            'https://www.douyin.com/aweme/v1/web/user/profile/other/',
            params=params, headers=headers, cookies=cookies,
            verify=False, timeout=8)
        j = resp.json()
        if j.get('status_code') == 0 and 'user' in j:
            user = j['user']
            info = {
                'nickname': user.get('nickname', '?'),
                'unique_id': user.get('unique_id') or user.get('short_id', '?'),
                'gender': gender_str(user.get('gender')),
                'ip_location': user.get('ip_location', ''),
                'follower_count': user.get('follower_count', 0),
                'following_count': user.get('following_count', 0),
                'total_favorited': user.get('total_favorited', 0),
                'aweme_count': user.get('aweme_count', 0),
                'signature': (user.get('signature') or '')[:100],
            }
            _user_info_cache[sec_uid] = info
            return info
    except Exception:
        pass
    return {}

def is_real_mystery_user(user):
    """判断是否真正的神秘人模式用户"""
    display = (user.desensitized_nickname or '').strip()
    real_name = (user.nickname or '').strip()
    mystery_man = getattr(user, 'mystery_man', 0)
    
    # 条件①: 显示名以"神秘人"开头（深度匿名时真实名也是"神秘人XXXXX"）
    is_masked = (
        display.startswith('神秘人')
        and len(display) > 3
    )
    # 条件①B: 显示名以"dou"开头（低配版神秘人，如 dou6573159）
    # 同时检查 desensitized_nickname 和 nickname，有些 dou 用户只在其中一个字段
    is_dou_mystery = (
        (display.startswith('dou') and len(display) > 5) or
        (real_name.startswith('dou') and len(real_name) > 5)
    )
    # 条件②: 深度匿名模式
    is_deep = mystery_man >= 2
    # 条件③: 指定目标
    is_target = bool(TARGET and TARGET == display)
    
    return is_masked or is_dou_mystery or is_deep or is_target, display, real_name, mystery_man

# ========== 统计 ==========
found_target = False
recent_mysteries = []  # 存最近抓到的，方便查看

# ========== WebSocket 处理 ==========
def on_message(ws, message):
    global found_target
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
            # ===== 用户进入（只检测神秘人） =====
            if item.method == 'WebcastMemberMessage':
                msg = Live_pb2.MemberMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                
                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                
                if is_mystery:
                    info = {
                        'display': display,
                        'real_name': real_name,
                        'unique_id': user_id_str(user),
                        'sec_uid': user.sec_uid,
                        'gender': gender_str(user.gender),
                        'consume_level': user.consume_diamond_level,
                        'mystery_man': mm,
                    }
                    recent_mysteries.append(info)
                    print(f"\n{'='*55}")
                    print(f"🎯🎯🎯 抓到真实神秘人 #{len(recent_mysteries)}！🎯🎯🎯")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  📱 抖音号: {user_id_str(user)}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  👤 性别: {gender_str(user.gender)}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    if hasattr(user, 'total_recharge_diamond_count') and user.total_recharge_diamond_count:
                        print(f"  💰 累计充值: {user.total_recharge_diamond_count}钻石")
                    print(f"  🔒 匿名等级: {mm}")
                    print(f"  主页: https://www.douyin.com/user/{user.sec_uid}")
                    print(f"{'='*55}")

                    # 轻量API查询额外信息（IP属地、粉丝数等）
                    extra = lookup_user(user.sec_uid)
                    if extra:
                        print(f"  🌍 IP: {extra.get('ip_location', '?')}")
                        print(f"  📊 粉丝{extra.get('follower_count')} 关注{extra.get('following_count')} 获赞{extra.get('total_favorited')}")
                        print(f"  🎬 作品{extra.get('aweme_count')}")
                        if extra.get('signature'):
                            print(f"  📝 简介: {extra['signature']}")
                        print(f"{'='*55}")

                    if TARGET and display == TARGET:
                        found_target = True
                        print(f"\n★ 🎯🎯🎯 目标找到！🎯🎯🎯 ★")
                        print(f"  真实身份: {real_name}")
                        print(f"  主页: https://www.douyin.com/user/{user.sec_uid}")
                        print(f"{'='*55}\n")

            # ===== 弹幕（只检测神秘人） =====
            elif item.method == 'WebcastChatMessage':
                msg = Live_pb2.ChatMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                if is_mystery:
                    print(f"\n💬 [神秘人] 发弹幕:")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  📱 抖音号: {user_id_str(user)}")
                    print(f"  内容: {msg.content}")

            # ===== 礼物（只检测神秘人） =====
            elif item.method == 'WebcastGiftMessage':
                msg = Live_pb2.GiftMessage()
                msg.ParseFromString(item.payload)
                user = msg.user
                is_mystery, display, real_name, mm = is_real_mystery_user(user)
                if is_mystery:
                    print(f"\n🎁 [神秘人] 送礼:")
                    print(f"  显示名: {display}")
                    print(f"  🎯 真实名: {real_name}")
                    print(f"  🏅 抖音等级: {get_badge_level(user)}")
                    print(f"  💎 财富等级: {user.consume_diamond_level}")
                    print(f"  🆔 sec_uid: {user.sec_uid}")
                    print(f"  礼物: {msg.gift.name} x{msg.comboCount}")

            # ===== 房间热度 =====
            elif item.method == 'WebcastRoomStatsMessage':
                msg = Live_pb2.RoomStatsMessage()
                msg.ParseFromString(item.payload)
                print(f"\r📊 在线: {msg.displayShort} | 累计: {msg.total} | 神秘人: {len(recent_mysteries)}", end='')

            # ===== 排行榜 TOP3 =====
            elif item.method == 'WebcastRoomRankMessage':
                msg = Live_pb2.RoomRankMessage()
                msg.ParseFromString(item.payload)
                rank_list = []
                for rank in msg.ranksList:
                    nick = rank.user.nickname
                    badge_lv = get_badge_level(rank.user)
                    consume_lv = rank.user.consume_diamond_level
                    
                    is_mystery, display, real_name, mm = is_real_mystery_user(rank.user)
                    if is_mystery:
                        info = {
                            'display': display,
                            'real_name': real_name,
                            'unique_id': user_id_str(rank.user),
                            'sec_uid': rank.user.sec_uid,
                            'gender': gender_str(rank.user.gender),
                            'mystery_man': mm,
                        }
                        recent_mysteries.append(info)
                        print(f"\n🏆 榜上有神秘人！")
                        if hasattr(rank, 'rank'):
                            print(f"  排名: #{rank.rank}")
                        print(f"  显示名: {display}")
                        print(f"  🎯 真实名: {real_name}")
                        print(f"  🏅 抖音等级: {badge_lv}")
                        print(f"  💎 财富等级: {consume_lv}")
                        print(f"  🆔 sec_uid: {rank.user.sec_uid}")
                        print(f"  📱 抖音号: {user_id_str(rank.user)}")
                        print(f"{'='*55}")
                    
                    rank_pos = getattr(rank, 'rank', rank_list.__len__() + 1)
                    rank_str = f"  #{rank_pos} {nick} | 🏅{badge_lv} 💎{consume_lv}"
                    rank_list.append(rank_str)
                
                if rank_list:
                    print(f"\n🏆 排行榜 TOP3:\n" + "\n".join(rank_list) + "\n")

            # ===== RoomUserSeq 排行榜 =====
            elif item.method == 'WebcastRoomUserSeqMessage':
                msg = Live_pb2.RoomUserSeqMessage()
                msg.ParseFromString(item.payload)
                top_three = []
                for contributor in msg.ranksList[:3]:
                    contributor_name = contributor.user.nickname if not contributor.isHidden else '隐藏用户'
                    badge_lv = get_badge_level(contributor.user)
                    consume_lv = contributor.user.consume_diamond_level
                    
                    if contributor.isHidden:
                        is_m, display, real_name, mm = is_real_mystery_user(contributor.user)
                        if is_m:
                            info = {'display': display, 'real_name': real_name,
                                    'sec_uid': contributor.user.sec_uid,
                                    'unique_id': user_id_str(contributor.user)}
                            recent_mysteries.append(info)
                            print(f"\n🔒 榜上有隐藏用户（isHidden=True）！")
                            print(f"  显示名: {display}")
                            print(f"  🎯 真实名: {real_name}")
                            print(f"  🏅 抖音等级: {badge_lv}")
                            print(f"  💎 财富等级: {consume_lv}")
                            print(f"  🆔 sec_uid: {contributor.user.sec_uid}")
                            print(f"{'='*55}")
                    
                    top_three.append(f"  #{contributor.rank} {contributor_name} | 🏅{badge_lv} 💎{consume_lv}")
                
                if top_three:
                    print(f"\n📊 榜一榜二榜三:\n" + "\n".join(top_three) + "\n")

    except Exception:
        pass  # 静默处理解析错误

def on_open(ws):
    print(f"\n✅ 已连接到直播间: {LIVE_ID}")
    if TARGET:
        print(f"🔍 目标: {TARGET}")
    print(f"📡 正在监听神秘人...（Ctrl+C 停止）")

    def ping():
        while True:
            try:
                frame = Live_pb2.PushFrame()
                frame.payloadType = "hb"
                ws.send(frame.SerializeToString(), opcode=0x02)
                time.sleep(10)
            except:
                break
    threading.Thread(target=ping, daemon=True).start()

def on_error(ws, error):
    print(f"\n❌ 错误: {error}")

def on_close(ws, code, msg):
    print(f"\n⚠️ 连接关闭 (code={code})")
    print(f"📊 共抓到 {len(recent_mysteries)} 个真实神秘人")
    if TARGET and not found_target:
        print(f"❌ 目标 '{TARGET}' 未出现")
    if recent_mysteries:
        print(f"\n📋 汇总:")
        for i, m in enumerate(recent_mysteries, 1):
            print(f"  {i}. 显示「{m['display']}」→ 🎯 {m['real_name']} (@{m['unique_id']})")

# ========== 启动 ==========
print(f"🎯 抖音神秘人猎人")
print(f"📺 直播间: https://live.douyin.com/{LIVE_ID}")
print(f"⏳ 正在生成签名...")

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

try:
    ws.run_forever(origin='https://live.douyin.com')
except KeyboardInterrupt:
    print("\n\n👋 停止监听")
    if recent_mysteries:
        print(f"\n📋 汇总: 共抓到 {len(recent_mysteries)} 个真实神秘人")
        for i, m in enumerate(recent_mysteries, 1):
            print(f"  {i}. 显示「{m['display']}」→ 🎯 {m['real_name']} (@{m['unique_id']})")
