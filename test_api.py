"""用 Python 读取 douyin API 数据，绕过 JS 签名"""
import sys
sys.path.insert(0, '.')
import requests
import json
from urllib.parse import urlencode
from builder.params import Params

# 直接用 Python requests + cookie 试试
from utils.common_util import load_env

auth = load_env()

# 试试用最简单的 API - 搜索直播
def search_live_fast(query="测试直播"):
    params = Params()
    params.add_param("device_platform", "webapp")
    params.add_param("aid", "6383")
    params.add_param("channel", "channel_pc_web")
    params.add_param("search_channel", "aweme_live")
    params.add_param("keyword", query)
    params.add_param("search_source", "switch_tab")
    params.add_param("query_correct_type", "1")
    params.add_param("is_filter_search", "0")
    params.add_param("offset", "0")
    params.add_param("count", "20")
    
    base_url = "https://www.douyin.com/aweme/v1/web/live/search/"
    url = f"{base_url}?{urlencode(params.get())}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.douyin.com/search/{query}?type=live",
        "Cookie": auth.cookie_str,
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        if "data" in data:
            print(f"找到 {len(data['data'])} 个直播")
            for live in data['data'][:3]:
                print(f"  主播: {live.get('owner', {}).get('nickname', '?')} | 标题: {live.get('title', '?')}")
                print(f"  观众: {live.get('room_id_str', '?')}")
                print(f"  在线: {live.get('stats', {}).get('user_count', '?')}")
        else:
            print(f"返回: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
    except Exception as e:
        print(f"错误: {e}")

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
search_live_fast("游戏直播")
