"""检查 cookie 内容和缺失的字段"""
import sys
sys.path.insert(0, '.')
from utils.common_util import load_env

auth = load_env()
print("=== Cookie 中的字段 ===")
for k, v in sorted(auth.cookie.items()):
    print(f"  {k} = {v[:40] if len(str(v)) > 40 else v}")

print("\n=== 检查缺失的重要字段 ===")
required = ['s_v_web_id', 'msToken', 'ttwid', 'sessionid', 'odin_tt']
for key in required:
    if key in auth.cookie:
        print(f"  ✅ {key}")
    else:
        print(f"  ❌ {key} (缺失)")
