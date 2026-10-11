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
- **Downloads and update checks.** The app contacts GitHub (`api.github.com` and GitHub's file hosts, for Legacy Player
  and emulator updates), `buildbot.libretro.com` (RetroArch and its cores) and the emulator projects' own download sites
  only when you press a button that downloads something or checks for updates, and it asks first before downloading.
- **Box art.** When you ask for covers, the game's name is sent to `thumbnails.libretro.com` (the libretro thumbnails
  project) to fetch its box art. The app asks you to confirm first.
- **Game cards.** When you ask the app to look up a game's details, the game's title is sent to Wikipedia
  (`en.wikipedia.org`) and Wikidata (`www.wikidata.org`) to fetch its release date, makers and description. Nothing is
  looked up until you ask; you can also write the card yourself.
- **Problem reports (off by default).** Reports have three settings in the app: off (the default), ask each time (you can
  read the report before deciding), and automatic (only if you pick it). A report is a short note about a failed action: the
  app version, Windows version, the kind of error and a scrubbed trace. Before anything is sent the app removes your user and
  PC names, folder paths, IP addresses, host names, e-mail addresses, server codes, invite codes and keys. The report
  receiver (`server/report_receiver.py`) keeps no record of who sent a report: no address, no headers, no request log.
- **Friends service (optional).** See the next section.
- **Nothing else.** The maintainers receive no list of your games, no files and no identifiers.

## Friends service (optional)
Friends (friend codes, who is online, room invites and messages) work only if you connect to a friends service; Legacy
Player works fully without one. There are no accounts and no e-mail or password. Whoever runs the service you connect to
stores, on their computer: the display name you chose, your friend code, your friends and pending requests, invites, a
presence line (online or not, and, only if you choose to share it, the room you are in with its invite and server code),
and messages waiting to be read, which are kept for 7 days. A player who has not used the service for 60 days is
forgotten. If someone reports you or a message of yours, the report keeps that message with the few messages before it
(for context), so whoever runs the service can moderate (time-outs, bans, a word filter).

Legacy Player can run a friends service on your own computer (Friends > Run a friends service on this computer). Then
you are the one running it: everything above is stored on your computer, and you see and handle the reports. The friends
link you give your friends contains your computer's network address, so anyone you give it to learns that address.

## Who can see what
- Players in the same room see the display name you chose (with a short tag) and your controller inputs during a game.
- The person running a server can see who is connected to it and from which network address, as with any server.
  Their server is theirs; this project does not run one for you.

## Your control
Turn problem reports off in Settings, and uninstall at any time: the doctor (Uninstall Legacy Player) asks whether to
keep or delete the save folders it made, removes only what Legacy Player created and leaves nothing running. Delete
`%USERPROFILE%\.legacy-player` to remove your data.

## Changes and contact
Changes to this policy are made in this file and visible in the repository history. Questions: open an issue at
https://github.com/Alpallyoop/legacy-player/issues.
