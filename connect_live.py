"""连接抖音直播间 WebSocket，捕获神秘人数据"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import utils.common_util as cu
cu.load_env()

from dy_apis.douyin_api import DouyinAPI
import json

# 房间 ID
room_id = "7643362348794776355"

# 1. 先获取直播间基本信息
print("=== 获取直播间信息 ===")
info = DouyinAPI.get_live_info(cu.dy_live_auth, room_id)
print(f"主播: {info.get('anchor_id')}")
print(f"状态: {'直播中' if info.get('room_status') == '2' else '未开播(' + str(info.get('room_status')) + ')'}")
print(f"标题: {info.get('room_title')}")

if info.get('room_status') == '2':
    # 2. 连接 WebSocket
    print("\n=== 连接 WebSocket 监听 ===")
    from dy_live.server import DouyinLive
    live = DouyinLive(room_id, cu.dy_live_auth)
    live.start_ws()
else:
    print("\n直播间未开播，无法连接 WebSocket")
