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
On that machine, in the app: Servers > Make my server code. It looks like `LP-0108-1G8J-AD18-3N2A-AAMD-YWSA-NX49-19F4-9D`
(nine groups after `LP`). A server reached by a host name or an IPv6 address gets a longer code that starts with `LP2-`.

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
Start the receiver with `--admin-token <another secret>` (or `LP_ADMIN_TOKEN`), open `https://<your address>/admin` in a
browser and paste the admin token into the form there (it is not put in the address, so it does not end up in browser
history or proxy logs). It lists everything that came in: crashes and failures
the app caught, and the reports players write themselves from Home > "See an issue or a problem?" (those carry a
category and the player's own words). Filter by kind, category and status, read each report in full, and mark it
new / looking / fixed / won't fix with a note. Triage lives in `<dir>/triage.json`; the reports are never changed. The
admin token is a different door from the report token: the app never needs it, and it never accepts a report.

## 5. The friends service (optional, separate)
Friend codes, who is online, one-click invites into a room, messages, reporting and blocking. Legacy Player works fully
without it and no account is made: an app says hello once and gets a friend code (like `MK7-4Q2X`).

### The easy way: from Legacy Player (no commands)
Friends > **Run a friends service on this computer**. Legacy Player then, by itself:
- starts the service in the background (it keeps running with the window closed, and starts again with the app and
  after updates);
- serves it over HTTPS with the same self-signed certificate as your multiplayer server, and gives you a **friends link**
  (`https://<your address>:8791/#pin=<fingerprint>`) to send to friends. Their app checks the fingerprint, so nobody can
  pretend to be your service;
- asks your router to open the port (when the router allows it) and offers to add a Windows Firewall rule;
- makes a moderator key and uses it itself: you are the moderator, and Friends > **Moderation** has the reports,
  players, time-outs, bans, word filter and log. Friends > **Your service** has the link, **Copy moderator key** (for
  people who help you moderate; they paste it under Friends > *I help moderate this service*) and **Stop**.

Everything it knows stays on that computer, in Legacy Player's data folder (`social/`). The privacy check lists it as
"A friends service on this computer".

### On a server (VPS)
```
python -m server.social --dir social --port 8791
```
On first start it makes the moderator key and keeps it in `social/moderator.key` (it prints where). Put HTTPS in front
(reverse proxy or tunnel), or pass `--tls-cert`/`--tls-key` and share the link with its `#pin=` fingerprint. Players paste
the link under Friends > Join a friends service. To moderate, paste the key once in Legacy Player (Friends > I help
moderate this service), or open `https://<address>/admin` in a browser and paste it there. `--admin-token` /
`LP_SOCIAL_ADMIN_TOKEN` still choose your own key. The service stores names, codes, friend lists, presence and messages
(a week); never addresses or game traffic. Idle players are forgotten after 60 days, and a player can leave at any time
(everything about them is deleted).

### Who can reach whom
Only mutual friends can message or invite each other. Everyone else can only send a friend request, and only with the
player's friend code; a player can close requests altogether (Friends > "Let people with my code send me friend
requests"). Requests (20 an hour), code guesses (60 an hour), messages (20 a minute) and reports (20 a day) are limited
per player. Blocking hides a player from the blocker completely.

### Moderation
In Legacy Player (Friends > Moderation) for whoever runs the service or has its key, or in a browser at `/admin`.

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
