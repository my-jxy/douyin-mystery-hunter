#!/usr/bin/env python3
"""
抖音直播间神秘人识别工具
不需要 Cookie，只要直播间链接或 room_id
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gzip
import threading
import time
import re
from urllib.parse import urlencode, urlparse, parse_qs

from websocket import WebSocketApp
import static.Live_pb2 as Live_pb2
from dy_apis.douyin_api import DouyinAPI
from builder.header import HeaderBuilder
from builder.params import Params
import utils.common_util as common_util
from utils.dy_util import generate_signature


class MysteryHunter:
    def __init__(self, live_id, verbose=False):
        self.live_id = live_id
        self.verbose = verbose
        self.mystery_count = 0
        self.total_users = 0
        self.ws = None
        
    def get_room_id(self):
        """从 live_id 获取 room_id"""
        try:
            info = DouyinAPI.get_live_info(None, self.live_id)
            if isinstance(info, dict) and 'room_id' in info:
                return info['room_id'], info.get('user_id', ''), ''
            return None, None, None
        except:
            return None, None, None
    
    def on_message(self, ws, message):
        try:
            frame = Live_pb2.PushFrame()
            frame.ParseFromString(message)
            origin_bytes = gzip.decompress(frame.payload)
            response = Live_pb2.LiveResponse()
            response.ParseFromString(origin_bytes)
            
            for item in response.messagesList:
                # 有人进入直播间
                if item.method == 'WebcastMemberMessage':
                    msg = Live_pb2.MemberMessage()
                    msg.ParseFromString(item.payload)
                    user = msg.user
                    self.total_users += 1
                    
                    # 检测神秘人
                    if user.mystery_man or user.is_anonymous:
                        self.mystery_count += 1
                        print("\n" + "=" * 50)
                        print(f"🔍 抓到神秘人 #{self.mystery_count}！")
                        print(f"  显示昵称: {user.desensitized_nickname or '神秘人'}")
                        print(f"  🎯 真实昵称: {user.nickname}")
                        print(f"  🆔 真实ID: {user.sec_uid}")
                        print(f"  消费等级: {user.consume_diamond_level}")
                        print(f"  用户等级: {user.level}")
                        print(f"  地区: {user.city}")
                        print("=" * 50)
                    elif self.verbose:
                        print(f"👤 进入: {user.nickname}")
                        
                # 有人发弹幕（神秘人发弹幕也能识别）
                elif item.method == 'WebcastChatMessage':
                    msg = Live_pb2.ChatMessage()
                    msg.ParseFromString(item.payload)
                    user = msg.user
                    if user.mystery_man or user.is_anonymous:
                        print(f"\n💬 [神秘人] 发送弹幕:")
                        print(f"  显示昵称: {user.desensitized_nickname}")
                        print(f"  🎯 真实昵称: {user.nickname}")
                        print(f"  内容: {msg.content}")
                
                # 房间热度更新
                elif item.method == 'WebcastRoomStatsMessage':
                    msg = Live_pb2.RoomStatsMessage()
                    msg.ParseFromString(item.payload)
                    print(f"\r📊 在线: {msg.displayShort} | 累计: {msg.total} | 神秘人: {self.mystery_count}", end='')
                
                # 礼物（神秘人送礼也能识别）
                elif item.method == 'WebcastGiftMessage':
                    msg = Live_pb2.GiftMessage()
                    msg.ParseFromString(item.payload)
                    user = msg.user
                    if user.mystery_man or user.is_anonymous:
                        print(f"\n🎁 [神秘人] 送礼:")
                        print(f"  显示昵称: {user.desensitized_nickname}")
                        print(f"  🎯 真实昵称: {user.nickname}")
                        print(f"  礼物: {msg.gift.name} x {msg.comboCount}")
                        
        except Exception as e:
            if self.verbose:
                print(f"  [解析错误] {e}")
    
    def on_open(self, ws):
        print(f"✅ 已连接到直播间: {self.live_id}")
        print("🔍 正在监听神秘人...（按 Ctrl+C 停止）\n")
    
    def on_error(self, ws, error):
        if self.verbose:
            print(f"❌ 错误: {error}")
    
    def on_close(self, ws, code, msg):
        print(f"\n⚠️ 连接关闭 (code={code})")
        if self.mystery_count > 0:
            print(f"\n📊 统计: 共识别 {self.mystery_count} 个神秘人 / 总进入 {self.total_users} 人")
    
    def connect(self):
        """连接直播间 WebSocket"""
        # 先获取房间信息
        info = DouyinAPI.get_live_info(None, self.live_id)
        if not isinstance(info, dict) or 'room_id' not in info:
            print(f"❌ 无法获取直播间信息: {self.live_id}")
            return
        
        room_id = info['room_id']
        user_id = info.get('user_id', '')
        
        params = Params()
        params.add_param('app_name', 'douyin_web')
        params.add_param('version_code', '180800')
        params.add_param('webcast_sdk_version', '1.0.15')
        params.add_param('update_version_code', '1.0.15')
        params.add_param('compress', 'gzip')
        params.add_param('device_platform', 'web')
        params.add_param('cookie_enabled', 'true')
        params.add_param('screen_width', '1707')
        params.add_param('screen_height', '960')
        params.add_param('browser_language', 'zh-CN')
        params.add_param('browser_platform', 'Win32')
        params.add_param('browser_name', 'Mozilla')
        params.add_param('browser_version', HeaderBuilder.ua.split('Mozilla/')[-1])
        params.add_param('browser_online', 'true')
        params.add_param('tz_name', 'Etc/GMT-8')
        params.add_param('cursor', '-1')
        params.add_param('host', 'https://live.douyin.com')
        params.add_param('aid', '6383')
        params.add_param('live_id', '1')
        params.add_param('did_rule', '3')
        params.add_param('endpoint', 'live_pc')
        params.add_param('support_wrds', '1')
        params.add_param('user_unique_id', user_id)
        params.add_param('im_path', '/webcast/im/fetch/')
        params.add_param('identity', 'audience')
        params.add_param('need_persist_msg_count', '15')
        params.add_param('insert_task_id', '')
        params.add_param('live_reason', '')
        params.add_param('room_id', room_id)
        params.add_param('heartbeatDuration', '0')
        params.add_param('signature', generate_signature(room_id, user_id))
        
        wss_url = f"wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?{urlencode(params.get())}"
        
        self.ws = WebSocketApp(
            url=wss_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        self.ws.run_forever(origin='https://live.douyin.com')


def extract_live_id(input_str):
    """从各种输入格式提取 live_id"""
    # 如果是 URL
    if input_str.startswith(('http://', 'https://')):
        parsed = urlparse(input_str)
        path = parsed.path.strip('/')
        if path:
            return path.split('/')[-1]
    
    # 纯数字
    if input_str.isdigit():
        return input_str
    
    return input_str


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='抖音神秘人识别器')
    parser.add_argument('live_id', help='直播间ID或链接')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示所有用户进入')
    args = parser.parse_args()
    
    live_id = extract_live_id(args.live_id)
    hunter = MysteryHunter(live_id, verbose=args.verbose)
    
    try:
        hunter.connect()
    except KeyboardInterrupt:
        print("\n👋 停止监听")
