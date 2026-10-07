# Hosting the shared server (and the report receiver)

Legacy Player falls back to a shared server when a player's own connection cannot be reached from outside (phone
hotspot, provider-shared address, router with UPnP off). Both players then connect *out* to it, so nothing needs opening
at home. Game traffic goes through `server/relay` and stays encrypted between the players (TLS-PSK); the shared server
cannot read it. It only needs a machine with a public address and one open TCP port (a small VPS is enough).

## 1. Run the server
```
python -m server.cli start --host 0.0.0.0 --port 8765 --tls-cert cert.pem --tls-key key.pem
```
(or run Legacy Player on that machine and press Start with "Let friends connect"). Open TCP 8765 in the machine's
firewall / cloud security group.

## 2. Make its server code
On that machine, in the app: Servers > Make my server code. It looks like `LP-XXXX-XXXX-XXXX-XXXX-XXXX-XX`.

## 3. Tell the app about it
Put the code in `PUBLIC_SERVER_CODE` in `launcher/version.py` and rebuild. For a test, any player can instead paste it
into Settings > Your server > "Shared server code". Players can turn the fallback off in the same place.

## 4. Problem reports (optional)
```
python -m server.report_receiver --dir reports --port 8790 --token <secret>
```
Put it behind https (a reverse proxy such as Caddy), then set `REPORT_URL` in `launcher/version.py`.
Read what arrived: `python tools/read_reports.py reports`.

## Notes
- A server code carries an IPv4 address, so give the VPS a fixed address.
- Rotating the code (Make a fresh code) stops the old one working for new players only.
- Nothing here has been run on a real VPS yet; expect to fix small things on the first try.
