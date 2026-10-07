# Checking Legacy Player on a real Windows computer

Start with `python tools/windows_selfcheck.py`. It tests the Recycle Bin move, the computer-specs read, the program
icon, the tray icon and the cleanup script that removes the running exe, and prints PASS, FAIL or SKIP for each. Then
do the short hand checks below. Do the uninstall check on a **copy** of the exe.

| Part | How to check | Good looks like |
|---|---|---|
| Recycle Bin | Library, right-click a game, Uninstall | the game's files are in the Recycle Bin and can be restored |
| Read-only game file | same, on a file marked read-only | it is removed, no "Access is denied" |
| Specs read | Tools, My computer | CPU, memory and graphics card shown (a laptop shows both GPUs) |
| Tray icon | close the window with X | icon stays; right-click shows Open, Start/Stop server, Make a fresh code, Exit |
| Server running notice | start a server, close with X | a balloon says the server is still running |
| Copy buttons | Servers, Copy on the code; Together, Copy invite | paste somewhere and it matches (a message appears if copying is blocked) |
| Program uninstall | Doctor's office, Uninstall Legacy Player (on a copy) | the report lists what was removed, then the exe and log folder disappear a few seconds after it closes |
| Icon | look at the exe in Explorer, the taskbar and the tray | Martin everywhere (rose only on the Featured card) |
| Dolphin pads | Controllers: give player 1 a pad, launch a GameCube game | the pad works at once; the file you had is kept as `GCPadNew.ini.legacy-player-backup` in Dolphin's Config folder |
| Full-screen flags | Display: tick "Start full screen" for each emulator you use | it opens full screen. If not, the page already says which flags are best guesses |
| Open in front | Library, Play a game | the game's window is in front of Legacy Player (not behind it) |
| Full screen / windowed ask | Play a game from an emulator that has no saved choice | a box asks Full screen or Windowed (and which screen with two or more); "Remember" stops the question; Display and video > Where games open changes it |
| Choose the screen | with two monitors, pick the second one and play | the game opens on that screen; picking Windowed afterwards gives back the title bar |
| Overlay shortcut | with a game running press Ctrl+Shift+L | a small window appears top-right, over the game; press it again and it closes |
| Overlay controller combo | hold Back + Start for about a second on an Xbox-style pad | the same window opens; D-pad moves, A presses, B closes |
| Force quit | overlay or the red button next to "game running" | the game stops at once, even if the emulator asked "are you sure?" |
| Doctor's save-folder question | Doctor's office, Uninstall Legacy Player, with a custom save or backup folder set | the doctor lists the folders he made there and asks; Keep leaves them, Delete removes only those folders |

Anything that fails: the exact wording of the message and what you clicked is enough to fix it.
