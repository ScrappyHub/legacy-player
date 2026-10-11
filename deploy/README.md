# Host the shared server (and report receiver)

What you need: one small Linux machine with a public address (any VPS), Docker, and TCP 8765 open in its firewall /
cloud security group. For problem reports you also need a name pointing at it (for example `reports.example.com`) and
TCP 80 and 443 open.

## Quickest: one command on a fresh Ubuntu/Debian machine
```
curl -fsSL https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/deploy/setup-vps.sh | sudo bash
```
It installs what it needs, starts the server (and restarts it after a reboot), opens TCP 8765 in the machine's own firewall and prints the server code. Open TCP 8765 in your provider's cloud firewall too. The server listens on IPv4 and IPv6. The rest of this page is the Docker route.

## 1. Start it (Docker)
```
cd deploy
cp .env.example .env
docker compose up -d --build            # the shared server only
# or, with report receiving (fill REPORTS_DOMAIN and REPORT_TOKEN in .env first):
docker compose --profile reports up -d --build
```
No Docker? Use `legacy-player-server.service` (systemd) with `python3 -m server.cli start --share`.

## 2. Get its server code
```
docker compose exec lobby python -m server.cli code --state-dir /data/state --address YOUR-PUBLIC-NAME-OR-IP
```
The address can be an IPv4 number, an IPv6 number or a host name; names and IPv6 give a longer `LP2-` code. The
certificate and key are made on first start and kept in the `lp-data` volume, so the code stays the same across
restarts and rebuilds. Do not delete that volume unless you want to hand out a new code.

## 3. Check it from another computer
```
python tools/check_deployment.py --code LP2-... [--reports https://reports.example.com]
```
It connects the way the app does (pinned certificate, access key) and says plainly what worked.

## 4. Point the app at it
Put the code in `PUBLIC_SERVER_CODE` and the report address in `REPORT_URL` (both in `launcher/version.py`), bump the
version, and release. For a test, a player can paste the code under Settings > Your server > "Shared server code".

## Running it
- Update: `git pull && docker compose up -d --build`. Back up the `lp-data` volume if you care about the code staying put.
- Rotate the code (the old one stops working for new players): stop the server, delete `state/access_key.bin` in the volume, start it, and run the `code` command again.
- Read reports: set `ADMIN_TOKEN` in `.env`, open `https://<REPORTS_DOMAIN>/admin` and paste the admin token into the form;
  or `docker compose exec reports ls /data/reports`, or copy them out and run `python tools/read_reports.py <folder>`.
- A `lp-reports` volume created by an older version of these files may be owned by root, so the receiver (uid 10001)
  cannot write to it. Fix it once: `docker compose run --rm --user root reports chown -R 10001:10001 /data/reports`.
- The receiver keeps no log of who sent a report. Caddy's access log is switched off (`log { output discard }`).
- Never put the server behind a proxy that terminates TLS: players check the server's own certificate fingerprint.

## What has and has not been run
The Python side (`start --share`, `code`, the checker) is covered by tests. The Docker files, Caddy and systemd unit have
not been run on a real server yet: expect a small fix on the first try.
