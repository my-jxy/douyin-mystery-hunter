"""测试 Douyin 直播间 WebSocket 连接 + 神秘人数据捕获"""
import sys, os, hashlib, execjs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

basedir = os.path.dirname(os.path.abspath(__file__)) + '/utils'

# 加载 JS 签名 - 修正路径
sign_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'dy_live_sign.js')
with open(sign_path, 'r', encoding='utf-8') as f:
    sign_js_code = f.read()
sign_ctx = execjs.compile(sign_js_code)

def generate_signature(room_id, user_unique_id):
    raw_string = f"live_id=1,aid=6383,version_code=180800,webcast_sdk_version=1.0.15,room_id={room_id},sub_room_id=,sub_channel_id=,did_rule=3,user_unique_id={user_unique_id},device_platform=web,device_type=,ac=,identity=audience"
    x_ms_stub = hashlib.md5(raw_string.encode("utf-8")).hexdigest()
    result = sign_ctx.call("get_signature", x_ms_stub)
    return result.get("X-Bogus")

from utils.common_util import load_env
from builder.params import Params
from builder.header import HeaderBuilder
from dy_apis.douyin_api import DouyinAPI

auth = load_env()

# 1. 先找个直播间测试 - 用搜索
print("=== 搜索直播间 ===")
lives = DouyinAPI.search_some_live(auth, "唱歌", 3)
if lives:
    live = lives[0]
    owner = live.get('owner', {})
    print(f"找到直播: {owner.get('nickname', '?')} - {live.get('title', '?')}")
    print(f"room_id: {live.get('room_id_str', '?')}")
    print(f"在线: {live.get('stats', {}).get('user_count', '?')}人")
else:
    print("没搜到直播")
