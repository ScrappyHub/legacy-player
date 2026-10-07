# Privacy policy

Legacy Player runs on your own computer. This page says exactly what it does with information. It applies to the app,
the optional server you can run, and the optional shared server and report receiver.

## What the app collects
**Nothing is sent to the maintainers by default.** There is no account, no analytics, no advertising and no tracking.
Your library, settings, saves and controller profiles stay in `%USERPROFILE%\.legacy-player` on your computer.

## When data leaves your computer
- **Playing with friends.** If you press Start with "Let friends connect", your computer runs a server and shows you a
  server code. Friends who have the code connect to *your* computer, over an encrypted connection whose certificate is
  checked against the code. The server keeps room state (names you chose, rooms, invite code hashes) on your computer.
  If your own connection cannot be reached from outside, the app can use a shared server instead, if one is configured
  (none is built in today). Game traffic through it is encrypted between players.
- **Router.** To let friends in, the app may ask your router (UPnP) to open one port, and Windows Firewall to allow it
  after you approve a Windows prompt. Uninstalling removes what the app added.
- **Downloads and update checks.** The app contacts GitHub and the emulator projects' download sites only when you press a
  button that downloads something or checks for updates, and it asks first before downloading.
- **Problem reports (off by default).** Reports have three settings in the app: off (the default), ask each time (you can
  read the report before deciding), and automatic (only if you pick it). A report is a short note about a failed action: the
  app version, Windows version, the kind of error and a scrubbed trace. Before anything is sent the app removes your user and
  PC names, folder paths, IP addresses, host names, e-mail addresses, server codes, invite codes and keys. The report
  receiver (`server/report_receiver.py`) keeps no record of who sent a report: no address, no headers, no request log.
- **Nothing else.** The maintainers receive no list of your games, no files and no identifiers.

## Who can see what
- Players in the same room see the display name you chose (with a short tag) and your controller inputs during a game.
- The person running a server can see who is connected to it and from which network address, as with any server.
  Their server is theirs; this project does not run one for you.

## Your control
Turn problem reports off in Settings, uninstall at any time (it asks nothing and leaves nothing running), and delete
`%USERPROFILE%\.legacy-player` to remove your data.

## Changes and contact
Changes to this policy are made in this file and visible in the repository history. Questions: open an issue at
https://github.com/ScrappyHub/legacy-player/issues.
