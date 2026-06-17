#!/usr/bin/env python3
"""
补全神秘人记录中缺失的真实昵称。
扫描 mystery_records 表中 real_name 以 dou 开头或等于 display 的记录，
调用 lookup_user API 补全。手动触发，每次跑完输出补全了多少条。
"""

import json
import sqlite3
import sys
import os
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import utils.common_util as cu
cu.load_env()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mystery_history.db')
_TTWID = cu.dy_live_auth.cookie.get('ttwid', '')
_USER_INFO_CACHE = {}
_LAST_API_CALL = 0.0


def lookup_user(sec_uid):
    """与 web_listener.py 中 lookup_user 逻辑一致的重试版"""
    global _LAST_API_CALL
    if sec_uid in _USER_INFO_CACHE:
        return _USER_INFO_CACHE[sec_uid]
    if not sec_uid or len(sec_uid) < 10:
        return {}

    for attempt in range(3):
        try:
            elapsed = time.time() - _LAST_API_CALL
            if elapsed < 0.3:
                time.sleep(0.3 - elapsed)
            _LAST_API_CALL = time.time()

            params = {
                'device_platform': 'webapp', 'aid': '6383',
                'sec_user_id': sec_uid, 'version_code': '170400', 'msToken': '',
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                'Referer': f'https://www.douyin.com/user/{sec_uid}',
            }
            resp = requests.get(
                'https://www.douyin.com/aweme/v1/web/user/profile/other/',
                params=params, headers=headers,
                cookies={'ttwid': _TTWID}, verify=False, timeout=8,
            )
            j = resp.json()
            if j.get('status_code') == 0 and 'user' in j:
                u = j['user']
                info = {
                    'nickname': u.get('nickname', '?'),
                    'unique_id': u.get('unique_id') or u.get('short_id', '?'),
                    'ip_location': u.get('ip_location', ''),
                    'follower_count': u.get('follower_count', 0),
                    'following_count': u.get('following_count', 0),
                    'total_favorited': u.get('total_favorited', 0),
                    'aweme_count': u.get('aweme_count', 0),
                    'signature': (u.get('signature') or '')[:100],
                }
                _USER_INFO_CACHE[sec_uid] = info
                return info
            else:
                raise Exception(f"status_code={j.get('status_code')}")
        except Exception as e:
            print(f"  [WARN] lookup 第{attempt+1}次失败({sec_uid[:12]}...): {e}", flush=True)
            if attempt < 2:
                time.sleep(1 * (attempt + 1))

    return {}


def repair_names():
    if not _TTWID:
        print("[ERROR] 无法加载 TTWID，退出")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    # 找 real_name 可疑的记录（排重按 sec_uid）
    rows = conn.execute('''
        SELECT sec_uid, display, real_name, extra
        FROM mystery_records
        WHERE sec_uid != '' AND sec_uid IS NOT NULL
          AND (real_name LIKE 'dou%'
               OR extra IS NULL
               OR extra = '{}'
               OR extra NOT LIKE '%unique_id%')
        GROUP BY sec_uid
        ORDER BY last_seen DESC
    ''').fetchall()

    if not rows:
        print("✅ 没有需要补全的名字")
        conn.close()
        return

    print(f"📝 发现 {len(rows)} 个可疑用户，开始补全...\n")

    fixed = 0
    failed = 0
    skipped = 0
    for sec_uid, display, real_name, extra_json in rows:
        print(f"  [{sec_uid[:12]}...] display={display}, real_name={real_name}", flush=True)
        info = lookup_user(sec_uid)
        if not info:
            print(f"    ❌ API 查询失败", flush=True)
            failed += 1
            continue

        # 已有的 extra
        extra = {}
        if extra_json:
            try:
                extra = json.loads(extra_json) if isinstance(extra_json, str) else extra_json
            except:
                pass

        # 合并所有字段到 extra
        changed = False
        for k in ['nickname', 'unique_id', 'ip_location', 'follower_count',
                  'following_count', 'total_favorited', 'aweme_count', 'signature']:
            v = info.get(k)
            if v is not None and v != '' and v != extra.get(k):
                extra[k] = v
                changed = True

        nickname = info.get('nickname', '')
        new_real_name = real_name
        if nickname and nickname != real_name:
            new_real_name = nickname
            changed = True

        if not changed:
            print(f"    ⏭️  无需补全", flush=True)
            skipped += 1
            continue

        extra_json_new = json.dumps(extra, ensure_ascii=False)
        conn.execute(
            'UPDATE mystery_records SET real_name=?, extra=? WHERE sec_uid=?',
            (new_real_name, extra_json_new, sec_uid)
        )
        conn.commit()
        print(f"    ✅ 补全: {real_name} → {new_real_name}, extra 新增 {len(info)} 个字段", flush=True)
        fixed += 1

        # 限流礼貌
        time.sleep(0.5)

    conn.close()
    print(f"\n🎯 完成：补全 {fixed} 条，失败 {failed} 条")


if __name__ == '__main__':
    repair_names()
