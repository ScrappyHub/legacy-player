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
