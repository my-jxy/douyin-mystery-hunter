"""手动解析 ResidentGuestMessage 的 protobuf 结构"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import utils.common_util as cu
cu.load_env()

from builder.params import Params
from builder.header import HeaderBuilder, HeaderType
from dy_apis.douyin_api import DouyinAPI
import static.Live_pb2 as Live_pb2
from google.protobuf.internal import decoder

auth = cu.dy_live_auth
room_id = "7643331953759996672"
user_id = "7638929563125138984"
url = f"https://live.douyin.com/{room_id}"

res_bytes = DouyinAPI.get_webcast_detail(auth, user_id, room_id, url)
response = Live_pb2.LiveResponse()
response.ParseFromString(res_bytes)

for item in response.messagesList:
    if item.method in ['WebcastResidentGuestMessage', 'WebcastRoomUserSeqMessage']:
        payload = item.payload
        print(f"\n=== {item.method} ({len(payload)} bytes) ===")
        print(f"Hex: {payload.hex()}")
        
        n = len(payload)
        pos = 0
        while pos < n:
            key, pos = decoder._DecodeVarint32(payload, pos)
            field_num = key >> 3
            wire_type = key & 0x7
            
            if wire_type == 0:  # Varint
                val, pos = decoder._DecodeVarint(payload, pos)
                print(f"  field {field_num} (varint) = {val}")
            elif wire_type == 2:  # Length-delimited
                length, pos = decoder._DecodeVarint32(payload, pos)
                data = payload[pos:pos+length]
                pos += length
                print(f"  field {field_num} (len={length}) = ", end="")
                try:
                    text = data.decode('utf-8', errors='replace')
                    print(f"'{text[:200]}'")
                except:
                    print(f"{data.hex()}")
            elif wire_type == 1:  # 64-bit
                val, pos = decoder._DecodeVarint(payload, pos)
                print(f"  field {field_num} (64bit) = {val}")
            elif wire_type == 5:  # 32-bit
                import struct
                val = struct.unpack('<I', payload[pos:pos+4])[0]
                pos += 4
                print(f"  field {field_num} (32bit) = {val}")
            else:
                print(f"  field {field_num} (wire_type={wire_type}) bytes left={n-pos}")
                break
        
        if pos >= n:
            print(f"  [解析完成]")

print("\n\n=== 查看 WebcastRoomUserSeqMessage ===")
for item in response.messagesList:
    if item.method == 'WebcastRoomUserSeqMessage':
        payload = item.payload  
        n = len(payload)
        pos = 0
        while pos < n:
            key, pos = decoder._DecodeVarint32(payload, pos)
            field_num = key >> 3
            wire_type = key & 0x7
            
            if wire_type == 0:
                val, pos = decoder._DecodeVarint(payload, pos)
                print(f"  field {field_num} (varint) = {val}")
            elif wire_type == 2:
                length, pos = decoder._DecodeVarint32(payload, pos)
                data = payload[pos:pos+length]
                pos += length
                print(f"  field {field_num} (len={length}) = ", end="")
                try:
                    text = data.decode('utf-8', errors='replace')
                    print(f"'{text[:200]}'")
                except:
                    print(f"{data.hex()}")
            elif wire_type == 1:
                val, pos = decoder._DecodeVarint(payload, pos)
                print(f"  field {field_num} (64bit) = {val}")
            elif wire_type == 5:
                import struct
                val = struct.unpack('<I', payload[pos:pos+4])[0]
                pos += 4
                print(f"  field {field_num} (32bit) = {val}")
            else:
                print(f"  field {field_num} (wire_type={wire_type})")
                break
