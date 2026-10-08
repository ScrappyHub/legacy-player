# Library and Launcher v1

Status: implemented under Proposal 0002 (pending approval). Standard library only.

## Run it

```
python -m launcher --games "P:\Vimm"                    # use YOUR games folder; opens http://127.0.0.1:8780
python -m launcher                                       # or start empty and add the folder in the app
python -m server.cli start --detach                      # multiplayer server (optional)
```

User data (favorites, settings, history, controller overrides, save backups) lives in
`~/.legacy-player` (`--data-dir` to change). Game folders are only ever read.

## What it does

| Area | Behavior |
|---|---|
| Scanner | Walks the chosen folders and classifies files by extension, using the folder name for shared types (.iso, .bin, .zip, .7z). Skips `Emulators`, `ZZZ-*`, `saves`, `BIOS`. A `.bin` beside a `.cue` is collapsed to the `.cue`. Never opens, hashes, copies or modifies a file (tested). |
| Library | Console shelf with counts, search, favorites, sort (A-Z, recent, size), detail drawer. |
| Identity | `compat_id` = console + normalized title + region, identical on every player's machine; used to check that everyone in a room has the same game. |
| Emulators | Finds known emulators under the games folder (3 levels deep) and on PATH, or uses a path you set. Launch uses an argument list, never a shell, and only for a game already in the library. Default command lines are common documented ones and are unverified until proven on your machine. |
| Controllers | Standard-gamepad layout mapped per console (18 layouts). Editable, resettable, with live pad test in the browser. Applying a mapping inside each emulator is adapter work (Dolphin first). |
| Saves | Finds save files by game name in the emulator save folder (cartridge consoles default to the game's own folder), timestamped backups, restore backs up current saves first. |
| Settings | Schema-driven with plain-language help for every option. |
| Play Together | Host or join rooms by invite code, approve/decline requests, remove players with a reason, check everyone matches, ready up, live activity feed and toasts for joins, leaves, kicks, disconnects and server restarts. |

## Honest limits

- Match launch uses RetroArch's own netplay (see below), so it covers NES, SNES, Game Boy,
  Game Boy Color, GBA, Genesis and Atari only. GameCube (Dolphin, Mario Party 4) still goes
  through the lockstep adapter work; other consoles have no match launcher yet.
- Archives (.7z, most .zip) are listed but must be extracted by you before launching.
- Memory-card consoles share one card file, so per-game save backup needs a save folder set.
- Multiplayer feasibility labels per console are guidance, not a compatibility promise.

## Security model of the UI

Loopback only; every API call needs a per-run token embedded in the page; `Host` header and
`Content-Type: application/json` are enforced (blocks DNS rebinding and cross-site forms);
the UI builds the DOM with text nodes so file names cannot inject markup; errors never leak
tracebacks.

## Starting a match (Phase 3a: RetroArch native netplay)

`adapters/retroarch/netplay.py` is a *launch* adapter: it starts RetroArch in host or
client mode and leaves frame sync to RetroArch and the libretro core. It does not implement
the lockstep `ControllerAdapter`. Legacy Player supplies the room, invite code, compatibility
check and the host's address.

Flow: host presses "Check everyone matches", then "Launch match (host)". The launcher starts
RetroArch with `-L <core> <game> --host --port <port> --nick <name>`, then publishes the
address through the server (`set_endpoint`). Guests are notified, press "Join match", and the
launcher starts `... --connect <address> --port <port>`. Addresses are only visible to
authenticated room members.

Requirements and honest limits:
- RetroArch plus a libretro core for the console in `<retroarch folder>/cores` (the UI says
  exactly what is missing). Everyone needs the same core and the same game file version.
- The RetroArch flags were verified against a real RetroArch 1.18 (host + 3 guests, 60 s, no desync).
- RetroArch netplay traffic is wrapped in a TLS-PSK tunnel and, by default, relayed through the lobby server so players never learn each other's address. Dolphin NetPlay is neither encrypted nor relayed: use a VPN (Tailscale, ZeroTier).

## Dolphin (GameCube and Wii) guided NetPlay

Dolphin has no command-line option to start or join NetPlay, so `adapters/dolphin/netplay_guide.py`
does not drive it. "Open Dolphin" starts Dolphin with the game loaded (`-e`, normal window) and
shows ordered steps with the room details filled in:
- **Traversal (default):** the host starts NetPlay in Dolphin, then pastes Dolphin's host code into
  the room (`set_endpoint` kind `code`). Guests are notified and see the code in their steps.
- **Direct:** the host publishes address and port (default 2626); guests see them in their steps.

Everyone needs the same Dolphin version, the same game file (region and revision) and the same
settings. This guided path is separate from the repository's lockstep Dolphin/DSU work for
Mario Party 4, which is not changed.

## Setup page

`Setup` checks RetroArch, one core per supported console, and Dolphin.
- **Windows:** can download the official stable RetroArch package (`RetroArch.7z`, unpacked with
  7-Zip or the `tar` that ships with Windows) and the missing cores into `~/.legacy-player/emulators/retroarch`.
- **Linux:** downloads missing cores; RetroArch itself comes from your package manager or Flatpak
  (the page shows the command). **macOS:** guidance only.
- **Dolphin:** checked and linked to its official download page, not auto-installed.
- Downloads: official libretro build server only, https, redirects to other hosts refused, size caps,
  path-escape checks. The server publishes no checksums, so integrity rests on TLS to that host.
- The installer was tested against a local fake server. It could not reach the real server from the
  development sandbox, so the first real download happens on your machine.

## Controllers (any pad)

The **Controllers** tab lists every pad the browser can see (Xbox, PlayStation, Switch Pro, 8BitDo, generic USB pads). Press a button on a pad to make it appear.

* **Identify** shows name, vendor:product, button and axis counts, and rumbles the pad if it can.
* **Map buttons** walks through 17 standard controls ("press the button for ..."). Buttons and axis directions are both accepted, so odd pads and hat switches work. Skip, Back and Cancel are available. The profile is saved per pad.
* **Player 1-4** assigns a pad to a player slot.
* Two layers: your pad profile (raw input to standard control) and the console layout (standard control to console button).

What is applied outside this app: for **RetroArch**, pads in the browser's standard layout (XInput style) get their bindings written to a per-console config passed with `--appendconfig`. Other pads, and all other emulators, keep their own controller settings; set those once inside the emulator. Windows controller input for RetroArch bindings has not been verified on a real Windows machine; the config flag itself was verified against RetroArch 1.18.

## Save folders

The **Saves** tab sets one root folder (default: inside the Legacy Player data folder). RetroArch consoles get `<root>/<console>/saves` and `<root>/<console>/states`, passed with `--appendconfig` (`savefile_directory`, `savestate_directory`, no per-core subfolders). Verified against RetroArch 1.18: the folders are honored. Other emulators keep their own folders; the page shows where each usually keeps saves and lets you point backups at any folder. Backups remain timestamped copies and restoring backs up current files first.

## Encrypted matches

RetroArch matches run through a TLS 1.2 pre-shared-key tunnel (Python 3.13+, built into the downloadable app). The host shares a random key through the room; guests connect to a local tunnel port. A real RetroArch host and guest were connected through it (player 2 joined, ping about 30 ms). Limits: the lobby itself is only encrypted when the server uses TLS; RetroArch still listens on its private port, so keep it closed at the firewall; Dolphin NetPlay has no tunnel (use a VPN such as Tailscale). The Settings toggle "Encrypt match traffic" turns this off for trusted home networks; it never downgrades silently.

## Downloadable app (.exe)

`build_exe.bat` (Windows, Python 3.13+) builds `dist\LegacyPlayer.exe`: one file, no Python needed to run it. It opens its own app-style window with Edge or Chrome, quits when the window closes, runs the multiplayer server for you (Play Together > Start server) and keeps data in `%USERPROFILE%\.legacy-player`. A GitHub Actions workflow is provided at `tools/build-exe.workflow.yml`; copy it to `.github/workflows/build-exe.yml` to build and attach the exe on version tags. The PyInstaller packaging and the packaged server start/stop were verified on Linux; the owner has built `dist\\LegacyPlayer.exe` on Windows and opened it (Azahar launched from it). A full Windows smoke of every tab is still to do.

## Full rooms: waiting line and priority

The host picks a player limit (2 to 4) when hosting and can change it later. When the room is full, or others are already waiting, new people are not turned away: they join a **waiting line**.

* Everyone waiting sees their place ("You are number 2 in line"), and the host sees the list in the room.
* The line is first come, first served. **Priority** goes first: the host can give or remove priority per person, or create a **priority invite code**; anyone who joins with it queues ahead of normal people.
* When a spot frees (someone leaves or is removed, or the limit is raised) the next person is let in automatically, or sent to the host for approval if the room asks to approve everyone. The host can also remove someone from the line.
* Waiters must keep the page open. A place is dropped after about a minute without a check-in so a closed laptop cannot hold a spot. The line survives a server restart.
* Server operations: `set_priority`, `list_waiting`, `set_capacity`, `cancel_wait`; `create` accepts `max_players`, `invite` accepts `priority`.

## Engines, BIOS and Console mode (Phase 4, first slice)

See `docs/proposals/0003_OWNED_EMULATOR_SHELL.md`. In short: the **Engines** tab finds emulators already on the computer (Program Files, user folders, your emulator folders) when you press *Scan this computer*, fetches missing ones from each project's official GitHub releases when you press *Get* (only with Settings > Privacy > *Allow internet downloads* on, default off), and shows which BIOS files you need and where your own dumps are. BIOS files are never downloaded. **Console mode** is a big-tile, controller-driven view of the library. Load numbers are in `docs/STRESS_TEST_RESULTS.md`.

## Open rooms, waiting while you play, and your shared server (Phase 4, second slice)

* **Open rooms**: tick *Open room* when hosting (optionally name it). Anyone on the server sees it under *Open rooms on this server* with the game, region, players/limit and line length, never who is inside. *Join* walks in; *Wait in line* queues you in the background so you can keep playing or hosting; you get a notice when your seat is ready and press *Switch to it*. Hosts can toggle open/private live.
* **Seats free themselves**: a player who stops talking to the server is flagged after 45 s and removed after about 2 minutes so the line moves. Leaving a RetroArch/Dolphin match no longer ends it for everyone (lockstep matches still stop, as they must).
* **Your server, shared safely**: *Let friends connect* starts the server with TLS using a certificate the app makes itself (no OpenSSL needed). Friends paste your address and the fingerprint shown on the card; the app refuses a server whose certificate does not match. Plaintext internet hosting is not offered. Limits (players per room, rooms, line length) are in Settings > Your server.
* **Who sees what**: other players see `Name#tag` (random tag per install) and nothing else; the server sees your IP like any website does; matches go through the server relay by default, so other players never see your address. A host can only choose a direct connection (which exchanges addresses) after turning on Settings > Privacy > Allow direct connections, and every guest must confirm too. One caveat in relay mode: RetroArch itself still listens on its port on every network interface (it has no bind option), so do not forward that port at your router.

### Server operations (wire protocol, newline JSON)

create, join (invite code, join code, or open room by session id), validate, ready, input, poll, checkpoint, complete, status, join_status, decide_join, invite (priority flag), revoke_invites, kick, leave, heartbeat, set_priority, list_waiting, cancel_wait, browse, set_open, set_capacity, set_endpoint (kind direct/code/relay, optional psk), get_endpoint, punch (first line of a connection that introduces the host and one guest for a direct TCP hole-punched link; both must send consent; no game data touches the server), relay (first line of a connection that becomes a byte pipe), events; admin (loopback + token): admin_status, admin_shutdown.

## Your turn: switching from what you were playing

While you wait in line you can play anything from the library. When your seat is ready the app
says so; *It's my turn: switch* asks whether to close the game you are in (the emulator gets a
normal close request, the same as clicking its X, so it writes saves as usual), leaves any
room you were in, takes the seat, and joins the match at once if the host has launched.



## Direct connections (hole punching)

With Allow direct connections on, RetroArch matches first try a computer-to-computer link: both players connect to the lobby server from a local port (`punch` operation), the server tells each the address it saw for the other, then both connect to each other from that same port at once (`launcher/punch.py`). The result is a plain TCP socket that carries the usual TLS-PSK tunnel. The relay stays parked as a fallback; one failed direct attempt switches the guest to the relay for the rest of the match. The room shows which path is in use. Not covered: symmetric NATs and carrier-grade NAT usually refuse hole punching (the relay is used), and Dolphin/PSP keep their own traversal.
