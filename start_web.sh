#!/data/data/com.termux/files/usr/bin/bash
# 自启脚本 - 神秘人猎人 + Hermes WebUI
# 启动 Flask + Serveo 隧道

# === 神秘人猎人 ===
cd ~/Douyin_Spider

pkill -f "python3 web_listener.py" 2>/dev/null
pkill -f "serveo.net.*mybb:" 2>/dev/null

nohup python3 web_listener.py > /dev/null 2>&1 &
sleep 3

nohup ssh -o StrictHostKeyChecking=no -R mybb:80:localhost:5000 serveo.net > /dev/null 2>&1 &

echo "✅ 神秘人猎人已启动：https://mybb.serveousercontent.com"

# === Hermes WebUI ===
export HERMES_AGENT_BRIDGE_ENDPOINT=tcp://127.0.0.1:18765

pkill -f "serveo.net.*mybbweb:" 2>/dev/null

hermes-web-ui start > /dev/null 2>&1 &
sleep 5

nohup ssh -o StrictHostKeyChecking=no -R mybbweb:80:localhost:8648 serveo.net > /dev/null 2>&1 &

echo "✅ Hermes WebUI 已启动：https://mybbweb.serveousercontent.com"
