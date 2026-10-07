# Netplay by console: what works, what does not, and how

| Console | How you play together | Address privacy | Status |
|---|---|---|---|
| NES, SNES, GB/GBC/GBA, Genesis, Atari | RetroArch netplay, launched by Legacy Player | Relay (default) or direct with consent | Verified: 4 players, 60 s, no desync (RetroArch 1.18) |
| PlayStation | RetroArch netplay, PCSX-ReARMed core (or SwanStation) | Relay or direct | Experimental: same BIOS everywhere; large save states |
| Nintendo 64 | RetroArch netplay, Mupen64Plus-Next core | Relay or direct | Experimental: least stable, expect desyncs |
| Nintendo DS | RetroArch netplay, melonDS core | Relay or direct | Experimental: one game in lockstep; no local-wireless |
| GameCube, Wii | Dolphin NetPlay, guided by Legacy Player | **Players see each other's addresses** (traversal server only introduces them); use a VPN | Guided; needs Privacy > Allow direct connections |
| PSP | PPSSPP ad hoc: host turns on *Enable built-in PRO ad hoc server*, everyone sets *Change PRO ad hoc server IP* to the host; each player needs a unique MAC in PPSSPP settings | Direct only; VPN recommended | Manual; Legacy Player opens the game and shows these steps |
| PlayStation 2 | None. PCSX2 has no netplay | — | Not possible today |
| Xbox | None (System Link on one home network only) | — | Not possible |
| Xbox 360 | None | — | Not possible |
| PlayStation 3 | None through Legacy Player; some games' own online works through RPCN inside RPCS3 | — | Not possible here |
| 3DS | None through Legacy Player; Azahar local-wireless rooms exist | — | Not possible here |

How the relay keeps addresses private: the host and every guest connect *out* to the lobby
server; the server pairs them and copies bytes. The bytes are the match's TLS-PSK tunnel, so
the server cannot read the game. Verified with real RetroArch: host + 2 guests, about 25 ms
extra ping on loopback.

When direct connections are allowed (Settings > Privacy), the host can untick *Relay* at
launch; both the host and each guest must confirm, because addresses are exchanged.

## Known limits

- **RetroArch still listens on its port on every network interface in relay mode.** RetroArch has no bind
  option. Guests only ever reach the match through the relay, so keep that port (55435 by default) closed at
  your router and firewall; opening it would let people connect around the relay and see your address.
- **Step guides** for PSP, 3DS and PS3 are shown in Play Together when those games are in the room (the
  emulators run these modes themselves; Legacy Player cannot start them).
- **Pad profiles** (identify and map) are applied to RetroArch only. Other emulators keep their own controller
  settings; set the pad inside the emulator once.
- **Waiting while you play:** you can play any game in any emulator while you hold a place in line; when a seat
  opens you get a notice, and *It's my turn: switch* closes your current game politely (the emulator saves like
  clicking X) and joins. A background pre-loaded spectator was tried with real RetroArch: it can connect without
  taking a seat (netplay_start_as_spectator), but RetroArch cannot be switched from watching to playing without a
  keypress inside its window, so a fresh launch at switch time is used instead.
