> The ready-to-run kit (Docker, HTTPS proxy, systemd unit, deployment checker) is in `deploy/README.md`. This page explains the pieces.

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
Read what arrived: `python tools/read_reports.py reports`, or open the admin console.

### The admin console
Start the receiver with `--admin-token <another secret>` (or `LP_ADMIN_TOKEN`) and open
`https://<your address>/admin?token=<that secret>` in a browser. It lists everything that came in: crashes and failures
the app caught, and the reports players write themselves from Home > "See an issue or a problem?" (those carry a
category and the player's own words). Filter by kind, category and status, read each report in full, and mark it
new / looking / fixed / won't fix with a note. Triage lives in `<dir>/triage.json`; the reports are never changed. The
admin token is a different door from the report token: the app never needs it, and it never accepts a report.

## 5. The friends service (optional, separate)
```
python -m server.social --dir social --port 8791
```
A separate service for friend codes, who is online, one-click invites into a room and short messages. Legacy Player
works fully without it and no account is made: an app says hello once and gets a friend code (like `MK7-4Q2X`). Put it
behind https like the receiver; players paste its address under Settings > Friends and the Friends page appears. It
stores names, codes, friend lists, presence and messages (a week); never addresses or game traffic. Idle players are
forgotten after 60 days, and a player can leave at any time (everything about them is deleted).

### Who can reach whom
Only mutual friends can message or invite each other. Everyone else can only send a friend request, and only with the
player's friend code; a player can close requests altogether (Friends > "Let people with my code send me friend
requests"). Requests (20 an hour), code guesses (60 an hour), messages (20 a minute) and reports (20 a day) are limited
per player. Blocking hides a player from the blocker completely.

### Moderation console
```
python -m server.social --dir social --port 8791 --admin-token <a long random secret>
```
(or set `LP_SOCIAL_ADMIN_TOKEN`). Open `https://<your friends address>/admin?token=<secret>`. Without a token there is no
console (every `/admin` request answers 401).

- **Reports:** players report a player or a single message, with a category (harassment, hate, threats, spam, scam,
  sexual content, offensive name, cheating, other) and optional details. The console shows the reported message and
  the few before it **from the service's own copy**, so a report cannot put words in someone's mouth. The reported player
  is never told who reported them.
- **Time out** (1 hour, 24 hours, 7 days, 30 days): the player can still sign in and see friends but cannot message,
  invite or send requests; they see the reason and when it ends. **End time-out** lifts it.
- **Ban:** the player is shut out (they see the reason), removed from everyone's friends, requests and invites, and is never
  forgotten by the idle clean-up. **Unban** lets them back with an empty friends list.
- **Word filter:** off by default. When on, the service refuses messages and names containing filtered words (a built-in
  list of common profanity plus your own words, one per line). Each player also has their own filter in Settings >
  Friends (on by default) that hides those words as `****` in what they see; it works whether or not the service filters.
- **Log:** every moderator action, newest first, kept in `players.json` with the rest.

Limit worth knowing: there are no accounts and no addresses are kept, so a banned player can say hello again as a new
player with a new code. They start with no friends, and nobody can be messaged without accepting them first, so the
damage is small; report and block again if it happens.

## Notes
- A server code can carry an IPv4 address (short `LP-` code) or an IPv6 address / host name (longer `LP2-` code with a checksum). A host name means the address can change without a new code.
- Rotating the code (Make a fresh code) stops the old one working for new players only.
- Nothing here has been run on a real VPS yet; expect to fix small things on the first try.
