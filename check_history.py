"""检查初始 WebSocket 数据中的历史消息"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import utils.common_util as cu
cu.load_env()

from dy_apis.douyin_api import DouyinAPI
import static.Live_pb2 as Live_pb2
import gzip

auth = cu.dy_live_auth
room_id = "7643331953759996672"
user_id = "7638929563125138984"
url = f"https://live.douyin.com/{room_id}"

# 获取初始 protobuf 数据
res_bytes = DouyinAPI.get_webcast_detail(auth, user_id, room_id, url)
response = Live_pb2.LiveResponse()
response.ParseFromString(res_bytes)

print(f"共 {len(response.messagesList)} 条初始消息\n")

target_sec_uid = "MS4wLjABAAAAG3_E5jkCuqDHPHqOkYfX8EsYsm0ncEEk2wtQmRoJJddMXM6CpFfs1Ba_TSX-JrdN"

for item in response.messagesList:
    if item.method == 'WebcastChatMessage':
        msg = Live_pb2.ChatMessage()
        msg.ParseFromString(item.payload)
        user = msg.user
        display = user.desensitized_nickname or user.nickname
        real = user.nickname
        print(f"💬 [{display}] {msg.content}")
        if user.sec_uid == target_sec_uid:
            print(f"  ⚡ === 目标出现！真实: {real} ===")
        elif display != real:
            print(f"  ⚡ 显示≠真实: 真实={real}")

    elif item.method == 'WebcastMemberMessage':
        msg = Live_pb2.MemberMessage()
        msg.ParseFromString(item.payload)
        user = msg.user
        display = user.desensitized_nickname or user.nickname
        print(f"👤 进入: {display}")
        if user.sec_uid == target_sec_uid:
            print(f"  ⚡ === 目标出现！真实: {user.nickname} ===")

    elif item.method == 'WebcastGiftMessage':
        msg = Live_pb2.GiftMessage()
        msg.ParseFromString(item.payload)
        user = msg.user
        display = user.desensitized_nickname or user.nickname
        print(f"🎁 [{display}] 送出 {msg.gift.name} x{msg.comboCount}")
        if user.sec_uid == target_sec_uid:
            print(f"  ⚡ === 目标出现！真实: {user.nickname} ===")
            
    elif item.method == 'WebcastRoomStatsMessage':
        msg = Live_pb2.RoomStatsMessage()
        msg.ParseFromString(item.payload)
        print(f"📊 在线: {msg.displayShort} | 累计: {msg.total}")

print("\n=== 搜索目标 sec_uid 在所有消息中 ===")
for item in response.messagesList:
    if target_sec_uid.encode() in item.payload:
        print(f"🔍 目标出现在 {item.method} 中!")
