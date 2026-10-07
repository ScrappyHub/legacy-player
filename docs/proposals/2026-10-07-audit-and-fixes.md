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
| 0 | The tray icon was the generic Windows application icon, not the app's rose. | The rose is now a real `launcher/ui/legacy-player.ico` (16 to 256 px), used by the tray, the window tab and, via `--icon`, the built `.exe`. |
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

- Calls that change shared state (`server_control` start/stop, rescans) still hold the global lock. Making them
  non-blocking needs real per-area locking, a larger change.
- A one-time secret in a window's command line can be seen by other programs running as the same user. That is
  the same trust boundary as the player's own files; it removes the drive-by case, not a hostile program that
  already runs as the player.
- Text contrast on gradient cards, and keyboard-only use of the new dialogs, still need a manual pass.

## Still to verify on Windows

Moving files to the Recycle Bin (`SHFileOperationW`), the PowerShell computer-specs read, the tray icon and its
menu, the cleanup script that removes the running exe, copying a code to the clipboard, and the new `--icon`
build. Test the uninstall on a copy of the exe first.
