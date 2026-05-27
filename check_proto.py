"""检查 MemberMessage 和 User 的 protobuf 字段"""
import sys
sys.path.insert(0, '.')
import static.Live_pb2 as Live_pb2

# 看看 MemberMessage 有哪些字段
msg = Live_pb2.MemberMessage()
print('=== MemberMessage fields ===')
for fd in msg.DESCRIPTOR.fields:
    print(f'  {fd.name} (type={fd.type})')

print()

# 再看看 User 的字段
user = Live_pb2.User()
print('=== User fields ===')
for fd in user.DESCRIPTOR.fields:
    print(f'  {fd.name} (type={fd.type})')

print()

# 看看 RoomStatsMessage 的字段
room_stats = Live_pb2.RoomStatsMessage()
print('=== RoomStatsMessage fields ===')
for fd in room_stats.DESCRIPTOR.fields:
    print(f'  {fd.name} (type={fd.type})')
