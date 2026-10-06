# Proposal 0004: The fully owned player — engines, installer, open servers, privacy

Status: proposed, first slice implemented. Supersedes the Vimm decision in 0003 (the
owner chose to offer Vimm's Lair as an optional mirror).

## What the owner asked for, and what is realistic

| Ask | Verdict | What ships |
|---|---|---|
| Rewrite every emulator as our own | Not realistic (PCSX2, Dolphin, RPCS3 are each 10-20 years of work) | Legacy Player owns the **shell**; engines are the upstream projects, credited on the Credits page, unchanged, under their licenses. The in-process path is a libretro frontend (0003). |
| One-click install of all engines, no dependency hunting | Realistic | Engines tab > *Get all missing engines* fetches every engine with an official GitHub release into Legacy Player's own folder. RetroArch + cores via Setup. Python is not needed (the .exe bundles it). |
| Users choose their own programs or ours, in the initial installer | Realistic | First-run wizard: games folder, scan for own emulators or fetch ours, privacy switch, display name. Emulators tab can point any console at any program. |
| Server player limits so nobody queues needlessly | Realistic | Server-wide: players per room (2-8), rooms, waiting line length (0 turns lines off). Per room: host picks 2-8 and can change it live. |
| Open a game, go to a server, see what is being played, wait in line while playing something else | Realistic | Open rooms (host opt-in, with a name) listed on the server; *Join* walks in, *Wait in line* queues in the background; you are told when your seat is ready and switch when you are done. Hosts cannot be bumped; disconnected players free their seat after 3 missed heartbeats so lines move. |
| Put waiting players into a course to race while they wait | Deferred | That is a lobby mini-game: custom content, not emulation. "Play anything else while you wait" is in. |
| Never expose identity, IP, OS, location | Mostly realistic; one honest limit | Nothing about the computer or OS is ever sent. Room listings carry only game, region, counts and a label. Players see each other as `Name#tag` (random tag). The lobby is TLS with a pinned fingerprint when shared. Match traffic is TLS-PSK. **Limit:** direct netplay must give guests the host's address; hiding it needs a relay through the server (planned below) or a VPN. |
| Vimm's Lair "shop" | Partly | Vimm's Emulation Lair is linked as an optional mirror on the Credits page (download in the browser, add the folder). Not automated: Vimm asks for a browser and is not the projects' own channel. **Game (ROM) downloads will not be built.** |

## Implemented in this slice

- `server/selfsigned.py`: stdlib-only RSA-2048/SHA-256 self-signed certificate (about 1 s),
  made once per install in the background; `launcher/lobby_client.py` pins its fingerprint.
  The in-app shared server is **always TLS**; plaintext internet hosting is no longer
  possible from the app.
- Server: `browse`, `set_open`, `cancel_wait`, `--max-players/--max-rooms/--max-waiting`,
  open rooms, room labels, seat recovery for disconnected players, non-fatal leave for
  emulator-native matches (lockstep matches still fail cleanly as before).
- App: `api_mp_browse/open/switch/cancel_wait`, background waits, `Name#tag` player ids,
  Azahar launchable, a failed endpoint publish stops the stray emulator, graceful shutdown,
  API calls serialised, `api_credits`, `api_engines_install_all`, first-run wizard, Credits
  tab, server card with fingerprint and limits.
- Tests: `tests/test_server_tls_and_control.py`; additions to `test_waitlist.py`,
  `test_launcher.py`, `test_engines.py`.

## Done since the first slice

- **Relay mode shipped and is the default.** `server/relay`, `adapters/retroarch/tunnel.RelayHost`, `lobby_client.open_relay`. Verified with real RetroArch: host + 2 guests through the relay. Direct connections and Dolphin need *Allow direct connections* plus a confirmation on both sides.
- **libretro frontend groundwork**: `frontend/core.py` loads a core in-process with ctypes (Nestopia: boots, runs at thousands of fps headless, save states, RGB frames); `frontend/window.py` is a Tk viewer. Audio and pads need an SDL layer next.
- **Waiting-room warm-up track** in the app; experimental RetroArch netplay for PS1/N64/DS; `docs/NETPLAY_BY_CONSOLE.md` says what each console can do.

## Planned next

1. ~~Relay mode~~ (done) **Relay mode**: host connects *out* to the lobby server, guests connect to the server,
   bytes are piped end-to-end inside the existing TLS-PSK tunnel so the server cannot read
   them and nobody learns anyone's address. One extra hop of latency; optional per room.
2. libretro in-process frontend (0003) so the shell becomes the one window.
3. Netplay guides for PCSX2/DuckStation/PPSSPP; lobby mini-game content later if wanted.

## Canonical impact

0001's non-goals ("emulator execution", "public matchmaking") are contradicted by shipped
code; this proposal asks that the registry classify the service as "self-hosted legacy
multiplayer launcher and shell" with those as owned responsibilities.
`docs/WIRE_PROTOCOL_v1.md` must list the full operation set (now 37; see the appendix the
launcher docs carry).
