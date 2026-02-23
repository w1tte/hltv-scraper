#!/bin/bash
# Start local proxy tunnels that strip auth and forward to Webshare SOCKS5 proxies.
# Chrome can't handle credentials in --proxy-server, so we tunnel through localhost.

VENV=".venv/bin/python3"
PIDS=()

upstreams=(
    "socks5://fjhcddxl:q0wad2e3iwlx@31.59.20.176:6754"
    "socks5://fjhcddxl:q0wad2e3iwlx@23.95.150.145:6114"
    "socks5://fjhcddxl:q0wad2e3iwlx@198.23.239.134:6540"
    "socks5://fjhcddxl:q0wad2e3iwlx@45.38.107.97:6014"
    "socks5://fjhcddxl:q0wad2e3iwlx@107.172.163.27:6543"
    "socks5://fjhcddxl:q0wad2e3iwlx@198.105.121.200:6462"
    "socks5://fjhcddxl:q0wad2e3iwlx@64.137.96.74:6641"
    "socks5://fjhcddxl:q0wad2e3iwlx@216.10.27.159:6837"
    "socks5://fjhcddxl:q0wad2e3iwlx@142.111.67.146:5611"
    "socks5://fjhcddxl:q0wad2e3iwlx@23.26.53.37:6003"
)

# Kill any existing pproxy tunnels
pkill -f "pproxy" 2>/dev/null || true
sleep 1

# Write local proxy file
> proxies_local.txt

for i in "${!upstreams[@]}"; do
    port=$((11080 + i))
    upstream="${upstreams[$i]}"
    $VENV -m pproxy -l "socks5://127.0.0.1:$port" -r "$upstream" &
    PIDS+=($!)
    echo "socks5://127.0.0.1:$port" >> proxies_local.txt
    echo "  Tunnel $((i+1)): localhost:$port -> $upstream"
done

echo ""
echo "Started ${#PIDS[@]} proxy tunnels. PIDs: ${PIDS[*]}"
echo "Local proxy file: proxies_local.txt"
echo ""
echo "To stop: pkill -f pproxy"
