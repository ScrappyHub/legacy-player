# Cross-network multiplayer test plan

Goal: one player on the home network, one on a phone hotspot (a different network), on another computer.

## The one thing to know first
A phone hotspot is usually behind carrier-grade NAT: nothing outside can connect *in* to it. That is fine as long as the
hotspot computer only connects *out*. So:

- **Run the Legacy Player server on the home network.** Forward its port on the router to that computer (or use a VPN such
  as Tailscale on both computers and use the VPN address; then no forwarding is needed).
- **The hotspot computer is only ever the client.** Do not try to host from the hotspot.
- If the game itself needs a direct peer-to-peer link between the two players, the hotspot side may not allow it; then use
  the relay path (Network page shows "relay" vs "direct").

## Setup (what the player does)
1. Home computer: Servers page, leave "Let friends connect" ticked, press Start. The app asks the router (UPnP) to open
   the port by itself, learns the public address from the router, and the server code it shows already contains it.
   Windows may ask once to allow Legacy Player through the firewall: choose Allow.
2. Share the server code. The friend pastes it into Connect to a server.
3. Both: Settings > Privacy > Problem reports > "Ask me each time", so a failure produces a report you can read.

Windows Firewall: after Start the app offers to add a firewall rule for every network type (one Windows approval box).
"Test my router" (Servers page) opens the port and closes it again, so you can see whether the router cooperates.

If the router cannot be opened (UPnP off, or a provider-shared address), the app moves you to the shared server by itself
when one is set (see `docs/HOSTING_PUBLIC_SERVER.md`); otherwise it says so, and Tailscale on both computers still works.

## What to check, in order
1. Network page on each side: address kind (home / hotspot-style / CGNAT) and the connectivity test result.
2. Hotspot side can see the server and the room list.
3. Create a room on one side, join from the other; players count shows 2 on both.
4. Start a game; note relay vs direct, and the ping shown in the title bar.
5. Leave and rejoin once; stop the server and see that the client says so clearly.

## When something fails
Choose "See exactly what would be sent", then send (or copy) the report. Until the receiver is hosted
(`server/report_receiver.py` behind https, address in `launcher/version.py` `REPORT_URL`), use "Copy the newest report"
in Settings and paste it to the maintainers.
