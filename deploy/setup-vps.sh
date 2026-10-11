#!/usr/bin/env bash
# One-step setup of a Legacy Player shared server on a fresh Ubuntu/Debian machine with a public address.
#   curl -fsSL https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/deploy/setup-vps.sh | sudo bash
# It installs Python and git, downloads the server, starts it (and keeps it running after a reboot), opens TCP 8765 in the
# machine's own firewall and prints the server code to give your players. Open TCP 8765 in your provider's cloud firewall too.
# Run it again any time to update; the code stays the same. Set LP_ADDRESS=name.or.ip first to use a name instead of the detected address.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo."; exit 1; }
PORT="${LP_PORT:-8765}"
apt-get update -y >/dev/null
apt-get install -y python3 git curl >/dev/null
id legacyplayer >/dev/null 2>&1 || useradd --system --home /var/lib/legacy-player --shell /usr/sbin/nologin legacyplayer
mkdir -p /var/lib/legacy-player/state /var/lib/legacy-player/replays
if [ -d /opt/legacy-player/.git ]; then git -C /opt/legacy-player pull --ff-only; else git clone --depth 1 https://github.com/Alpallyoop/legacy-player /opt/legacy-player; fi
chown -R legacyplayer: /var/lib/legacy-player
sed "s/--port 8765/--port ${PORT}/" /opt/legacy-player/deploy/legacy-player-server.service > /etc/systemd/system/legacy-player-server.service
systemctl daemon-reload
systemctl enable legacy-player-server >/dev/null
systemctl restart legacy-player-server
if command -v ufw >/dev/null 2>&1; then ufw allow "${PORT}/tcp" >/dev/null || true; fi
ADDRESS="${LP_ADDRESS:-$(curl -fsS -4 https://api.ipify.org || true)}"
[ -n "$ADDRESS" ] || { echo "Could not find this machine's public address. Run again with LP_ADDRESS=your.address"; exit 1; }
sleep 2
echo
echo "Server is running. Give this code to your players (Settings > Your server > Shared server code):"
cd /opt/legacy-player
sudo -u legacyplayer python3 -m server.cli code --state-dir /var/lib/legacy-player/state --address "$ADDRESS" --port "$PORT"
echo
echo "If friends cannot connect, open TCP ${PORT} in your provider's firewall / security group."
