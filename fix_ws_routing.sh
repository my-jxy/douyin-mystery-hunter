#!/bin/bash
# Fix Douyin WebSocket routing: route through WARP, not direct eth0
# Douyin WebSocket servers are Chinese IPs but unreachable directly from Aliyun

# Create ipset if not exists
sudo ipset create douyin-ws hash:net 2>/dev/null || true

# Add Douyin WebSocket server IP ranges (webcast100-ws-web-hl.douyin.com)
sudo ipset add douyin-ws 111.62.113.0/24 2>/dev/null || true

# Add live.douyin.com IPs (163.181.66.0/24)
sudo ipset add douyin-ws 163.181.66.0/24 2>/dev/null || true

# Add webcast.amemv.com IPs
sudo ipset add douyin-ws 98.96.242.0/24 2>/dev/null || true
sudo ipset add douyin-ws 98.96.213.0/24 2>/dev/null || true

# Insert rule BEFORE china rule: skip marking for douyin-ws IPs (they go through WARP)
if ! sudo iptables -t mangle -C OUTPUT -m set --match-set douyin-ws dst -j RETURN 2>/dev/null; then
    sudo iptables -t mangle -I OUTPUT 1 -m set --match-set douyin-ws dst -j RETURN
fi
