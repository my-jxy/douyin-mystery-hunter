#!/bin/bash
# ============================================================
# WARP 分流规则管理
# 中国 IP 直连（eth0），国外 IP 走 WARP
# ============================================================
set -e

# ---- 1. 创建中国 IP 集合 ----
CHINA_FILE="/opt/script/china_ip_list.txt"
if [ ! -f "$CHINA_FILE" ]; then
    echo "下载中国 IP 段..."
    mkdir -p /opt/script
    # 从 APNIC 获取中国 IPv4 段
    curl -sSL https://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest -o /tmp/delegated-apnic-latest
    grep 'apnic|CN|ipv4|' /tmp/delegated-apnic-latest | \
        awk -F'|' '{print $4"/"$5}' | \
        awk -F'/' '{mask=32; while($2>1){mask--;$2/=2} printf "%s/%d\n", $1, mask}' | \
        sort -u > "$CHINA_FILE"
    rm -f /tmp/delegated-apnic-latest
    echo "共 $(wc -l < "$CHINA_FILE") 个中国 IP 段"
fi

sudo ipset create china hash:net 2>/dev/null || sudo ipset flush china
echo "加载中国 IP 段到 ipset china..."
while IFS= read -r net; do
    sudo ipset add china "$net" 2>/dev/null || true
done < "$CHINA_FILE"
echo "加载完成: $(sudo ipset list china 2>/dev/null | grep -c '^[0-9]') 条"

# ---- 2. 创建 Douyin WebSocket 豁免集合 ----
# 这些 IP 虽然是中国的，但直连超时，需要走 WARP
sudo ipset create douyin-ws hash:net 2>/dev/null || sudo ipset flush douyin-ws
for net in 111.62.113.0/24 163.181.66.0/24 98.96.242.0/24 98.96.213.0/24; do
    sudo ipset add douyin-ws "$net" 2>/dev/null || true
done

# ---- 3. 配置 iptables 标记 ----
# 先清除旧的 iptables 规则
sudo iptables -t mangle -F OUTPUT 2>/dev/null || true

# 规则1: Douyin WebSocket IP → RETURN（不标记，走 WARP）
sudo iptables -t mangle -A OUTPUT -m set --match-set douyin-ws dst -j RETURN

# 规则2: 中国 IP → 标记 0x100cf（绕过 WARP 走直连）
sudo iptables -t mangle -A OUTPUT -m set --match-set china dst -j MARK --set-mark 0x100cf

echo "iptables 规则配置完成"
