#!/usr/bin/env bash
# Read-only inventory of the jump host before anything is deployed there.
# Connects with the deploy key, runs only inspection commands, changes nothing.
set -euo pipefail

ssh_target="root@jump"
ssh_key="$HOME/.ssh/vpn_deploy_ed25519"

ssh -i "$ssh_key" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 \
    "$ssh_target" 'bash -s' <<'REMOTE'
echo "=== identity ==="
whoami; hostname; uname -a
echo "=== distro ==="
cat /etc/os-release 2>/dev/null | grep -E "^(NAME|VERSION)=" || true
echo "=== cpu / ram ==="
nproc
free -h | head -2
echo "=== disk ==="
df -h / /var/lib/docker 2>/dev/null | sort -u
echo "=== docker ==="
docker --version 2>/dev/null || echo "no docker"
docker compose version 2>/dev/null || echo "no compose plugin"
echo "=== running containers ==="
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null || true
echo "=== published ports in use ==="
ss -tlnp 2>/dev/null | awk 'NR==1 || /LISTEN/' | head -20
echo "=== outbound to soulseek server reachable? ==="
(timeout 5 bash -c 'cat < /dev/null > /dev/tcp/server.slsknet.org/2416' && echo "server.slsknet.org:2416 reachable") || echo "server.slsknet.org:2416 NOT reachable"
REMOTE
