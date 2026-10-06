#!/usr/bin/env bash
# Restore hakumods.xyz on a new VDS using Cloudflare Tunnel token
# (Zero Trust → Networks → Tunnels → Configure → Install connector → copy token).
# Usage: TUNNEL_TOKEN='eyJ...' sudo bash scripts/install_named_tunnel_token.sh
set -euo pipefail
TOKEN="${TUNNEL_TOKEN:-${CLOUDFLARE_TUNNEL_TOKEN:-}}"
if [[ -z "${TOKEN}" ]]; then
  echo "Set TUNNEL_TOKEN from Cloudflare dashboard (tunnel connector token)."
  exit 1
fi
if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL -o /tmp/cloudflared.deb \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  dpkg -i /tmp/cloudflared.deb || apt-get install -f -y
fi
systemctl stop hakumo-quick-tunnel 2>/dev/null || true
systemctl disable hakumo-quick-tunnel 2>/dev/null || true
# reinstall service with token
cloudflared service uninstall 2>/dev/null || true
cloudflared service install "${TOKEN}"
systemctl enable --now cloudflared
ENV_FILE="${HAKUMO_ENV:-/opt/hakumo/.env}"
if [[ -f "${ENV_FILE}" ]]; then
  sed -i 's|^PANEL_URL=.*|PANEL_URL=https://hakumods.xyz|' "${ENV_FILE}"
  sed -i 's|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://hakumods.xyz|' "${ENV_FILE}"
  sed -i 's|^PANEL_PUBLIC_URL=.*|PANEL_PUBLIC_URL=https://hakumods.xyz|' "${ENV_FILE}"
  grep -q '^WEB_BEHIND_PROXY=' "${ENV_FILE}" \
    && sed -i 's|^WEB_BEHIND_PROXY=.*|WEB_BEHIND_PROXY=1|' "${ENV_FILE}" \
    || echo 'WEB_BEHIND_PROXY=1' >> "${ENV_FILE}"
  systemctl restart hakumo 2>/dev/null || true
fi
echo "OK — check https://hakumods.xyz"
