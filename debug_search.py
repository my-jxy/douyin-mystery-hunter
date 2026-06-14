"""调试：直接调用搜索 API 看返回什么"""
import sys, os
sys.path.insert(0, '.')
from utils.common_util import load_env
from dy_apis.douyin_api import DouyinAPI
from builder.params import Params
from builder.header import HeaderBuilder, HeaderType
from utils.dy_util import generate_a_bogus
import urllib.parse, urllib3
urllib3.disable_warnings()

auth = load_env()

# 手动调用搜索 API
api = "/aweme/v1/web/live/search/"

params = Params()
params.add_param("device_platform", "webapp")
params.add_param("aid", "6383")
params.add_param("channel", "channel_pc_web")
params.add_param("search_channel", "aweme_live")
params.add_param("keyword", "游戏")
params.add_param("search_source", "switch_tab")
params.add_param("query_correct_type", "1")
params.add_param("is_filter_search", "0")
params.add_param("offset", "0")
params.add_param("count", "25")

query = urllib.parse.urlencode(params.get())
abogus = generate_a_bogus(query)
url = f"https://www.douyin.com{api}?{query}&a_bogus={abogus}"

headers = HeaderBuilder().build(HeaderType.GET)
headers.set_referer(f"https://www.douyin.com/search/游戏?type=live")

import requests
resp = requests.get(url, headers=headers.get(), cookies=auth.cookie, verify=False, timeout=15)
print(f"状态: {resp.status_code}")

data = resp.json()
print(f"status_code: {data.get('status_code')}")
if data.get('status_code') == 0:
    print(f"找到 {len(data.get('data',[]))} 个直播")
    for lv in data.get('data', [])[:3]:
        o = lv.get('owner', {})
        s = lv.get('stats', {})
        print(f"  主播: {o.get('nickname','?')} | 标题: {lv.get('title','?')}")
        print(f"  room_id: {lv.get('room_id_str','?')} | 在线: {s.get('user_count','?')}人")
else:
    import json
    print(f"返回: {json.dumps(data, ensure_ascii=False)[:500]}")
