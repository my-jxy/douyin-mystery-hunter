import sys
sys.path.insert(0, '.')
from utils.common_util import load_env, init
from dy_apis.douyin_api import DouyinAPI

# 加载 cookie
print("加载 cookie...")
auth = load_env()
print(f"Cookie 解析完成, msToken: {auth.msToken}")
print(f"Cookie 条数: {len(auth.cookie)}")

# 测试 - 获取自己的 UID
try:
    uid = DouyinAPI.get_my_uid(auth)
    print(f"✅ 认证成功！你的 UID: {uid}")
except Exception as e:
    print(f"❌ 认证失败: {e}")
