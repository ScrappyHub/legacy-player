# Audit of Legacy Player and the fixes made (7 October 2026)

Status: implemented on branch `launcher-phases-1-4`. Nothing in this note changes what Legacy Player is or
how it relates to the rest of the Atlas Systems ecosystem; it covers the launcher application only.

## Scope and honesty

The audit read the launcher code (`launcher/`), the local web server, the new tray, uninstall and keyboard code,
and ran the test suite and a headless browser against the real app. It did **not** run on a real Windows
machine with real emulators, so everything that talks to Windows directly is listed under "Still to verify on
Windows". The research code for Dolphin frame control and RAM analysis was not reviewed.

## What was already solid

- The UI server listens on the loopback address only, checks the Host header, requires a per-launch token and
  JSON on every call, and sends CSP and nosniff headers.
- Downloads come only from official hosts with size caps and refused redirects; the multiplayer server uses
  certificate pinning.
- Nothing is copied from the player's game folders, there is no telemetry, and cover lookups send only game names
  after the player agrees. Other players never see a player's address.
- Uninstalling a game can only touch the game file and its matching companion files inside configured library
  folders; saves are kept unless the player ticks the box.

## Findings and fixes

| # | Finding | Fix |
|---|---------|-----|
| 0 | The tray icon was the generic Windows application icon. | Martin is now the app icon: a real `launcher/ui/legacy-player.ico` (16 to 256 px) used by the tray, the window tab and, via `--icon`, the built `.exe`. The rose stays on the Home page Featured card only. |
| 1 | No single-instance guard: starting the exe again while it sat in the tray started a second copy on another port with a second tray icon. | A running copy writes `instance.json` (port and a wake secret) in the data folder. A second launch sends it a wake request and exits; the first copy opens its window. A stale file is ignored. |
| 2 | Uninstalling Legacy Player did not stop a running server, so its state folder was deleted underneath it. | The wizard stops the server first, then cleans up. The discharge report says it did. |
| 3 | The UI sources existed only in a working session; the repo held only the generated `index.html`. | `index.html` is declared the source of truth. The pieces and build script are archived in `tools/ui_archive/` with a README. |
| 4 | One global lock around every API call: a slow call (PowerShell computer specs, a server probe) froze all others. | `ping`, `bye`, `status`, `specs`, `server_status` and `network_last` run outside the lock; specs has its own lock. Calls that change shared state still run one at a time. |
| 5 | Any program on the computer could fetch the page, and so the API token, from the loopback port. | Each window opens a one-time secret address; the server swaps it for an HttpOnly, same-site cookie and redirects to a clean address. The bare address answers 403. A reused secret answers 403. |
| 6a | A `%` in a path would be expanded by the Windows cleanup script. | Percent signs are escaped. |
| 6b | A quote or backslash in a path would break the macOS Trash command. | Both are escaped. |
| 6c | An unsigned exe triggers SmartScreen and antivirus warnings. | `build_exe.bat` signs the exe when `LP_SIGN_PFX` (and `LP_SIGN_PASS`) are set. Signing needs a code-signing certificate, which is the owner's to obtain; see below. |
| 6d | Reduced motion and contrast were unchecked. | Reduced motion was already honoured by a global rule. Text contrast was measured for both themes against the page background; the only miss (the light theme's green, 3.6:1) was darkened to 5.5:1. Text on gradient cards was not measured. |
| 6e | No automated UI tests. | `tests/test_ui_smoke.py` starts the real app, opens every page in headless Chromium and fails on any script error, a page that draws twice, a missing game menu, or a page served without its secret. It skips itself if Playwright is not installed. |

Also fixed while there: a stylesheet variable typo (`--muted`) that left one label uncoloured.

## Signing the exe (decision for the owner)

Windows shows SmartScreen warnings for unsigned programs until a signing certificate has built a reputation.
Options: an OV or EV code-signing certificate from a certificate authority, or Azure Trusted Signing. Set
`LP_SIGN_PFX` to the certificate file and `LP_SIGN_PASS` to its password before running `build_exe.bat`.
This note does not choose a vendor.

## Still open

- A one-time secret in a window's command line can be seen by other programs running as the same user. That is
  the same trust boundary as the player's own files; it removes the drive-by case, not a hostile program that
  already runs as the player.
- Text contrast on gradient cards still needs a manual pass.

## Still to verify on Windows

Moving files to the Recycle Bin (`SHFileOperationW`), the PowerShell computer-specs read, the tray icon and its
menu, the cleanup script that removes the running exe, copying a code to the clipboard, and the new `--icon`
build. Test the uninstall on a copy of the exe first.

## Follow-up: fresh server codes (same day)

A server code now carries a short access key (the code grows from 18 to 26 characters; older codes still decode and
older servers without a key keep working). A server with a key asks for it from brand-new people only: creating a
room, joining one with an invite code, and browsing open rooms. Everything a player does once inside a room uses
that room's own credential, so **making a fresh code never disconnects anyone already connected**; it only stops the
old code from letting new people in. The Servers page and the tray both have "Make a fresh code". The key lives in
the server's state folder (`access_key.bin`, owner-only); the app reads its own server's current key from there.
Friends who saved the old code reconnect with the new one.

## Follow-up: second audit (same day)

Found and fixed: (1) starting or stopping the server held the one big lock while it waited for the server, so
every other click queued behind it; it now holds only its own lock and takes the big one just to save settings.
(2) Dialogs had no common keyboard behaviour: Esc now means Cancel on the top dialog, Tab stays inside it, and
focus returns to what opened it. (3) About twenty backend actions had no test (doctor, specs, update check, cover
lookup consent, save folders, scans, network state, host-only room actions); `tests/test_app_actions.py` covers
them, and the browser test checks Esc and Tab.

Still open: Dolphin pad profiles, emulator fullscreen flags per emulator, contrast measurement, and everything
under "Still to verify on Windows".

## Follow-up: the open items (same day)

- **Rescans** now walk the disk without the big lock (one walk at a time); only swapping the result in takes it.
- **Dolphin pads:** `launcher/dolphinpads.py` writes the assigned pad (or the player-1 keyboard layout) into Dolphin's
  `GCPadNew.ini` before a GameCube game starts, keeps the player's own file as `GCPadNew.ini.legacy-player-backup`,
  and puts it back on request or when the new setting "Set up Dolphin's GameCube controller for me" is turned off.
  Players with nothing assigned are left to Dolphin; Wii remotes are never touched. The control names are
  Dolphin's, but not yet confirmed on a real Windows Dolphin.
- **Full-screen flags:** added for bsnes, Mupen64Plus, melonDS and xemu. Each emulator is marked `documented`,
  `unconfirmed` or `none`, and the Display page says when a flag is a best guess.
- **Contrast:** `tools/contrast_check.py` measures real pixels behind text, in both themes. It found white text on
  the bright button/card gradients and some muted greys below 4.5:1; those are fixed (darker button gradient, a scrim
  under card gradients, lighter muted text, lighter links) and `tests/test_contrast.py` keeps them fixed.
- **Copy buttons** fall back to a hidden text box when the browser refuses clipboard access, and say so if both fail.
- **Windows:** `tools/windows_selfcheck.py` runs the Recycle Bin move, specs read, icon, tray icon and cleanup script
  and prints PASS/FAIL; `docs/WINDOWS_CHECKLIST.md` lists the hand checks. These still need one run on a real PC.

## Follow-up: Dolphin memory probe in the app

Tools > "Dolphin memory probe" runs the hot-action validator step by step (`launcher/memprobe.py` wraps
`tools/memory_probe/hot_action_validator.py`): take a baseline, do one thing in the game, capture. It shows which
known cluster of Dolphin's RAM changed and saves the full record under `<data folder>/probe_exports`. It is read-only
and local, asks for confirmation first, and says plainly when it is not on Windows or Dolphin is not running. Only
`coin_total_change_once` is grounded in the current cluster file; the other two clusters are placeholders, and the
page shows "no strong match" until they are filled in from real captures. `build_exe.bat` now bundles `tools` and
`game_packs` and installs `psutil`. Needs a real run on Windows with Dolphin open.
