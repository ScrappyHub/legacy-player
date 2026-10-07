# Private link for Dolphin online play (encrypted)

Dolphin NetPlay connects players straight to each other and Dolphin does not encrypt it. The **Private link** option runs the
same connection over a [Tailscale](https://tailscale.com/download) network (WireGuard), so it is encrypted, needs no router
setup, and each player sees the other's private `100.x` address instead of a home address.

Legacy Player does not install, start or configure Tailscale. It only reads whether `tailscale` is installed and what this
computer's `100.x` address is, then uses that address in the normal "Direct connection" flow.

## Setup (both players, once)
1. Install Tailscale and sign in.
2. The host shares their computer with the guest (Tailscale admin console > Machines > Share) or invites them to the same tailnet.
3. In the room, the host picks **Private link (encrypted, needs Tailscale)**, then Open Dolphin (host).
4. The guest presses Open Dolphin; the steps show the host's private address.

## Limits
- Both players need Tailscale. It is a third-party service with its own account and terms.
- Only Dolphin's game traffic is protected this way; the lobby and relay are already encrypted separately.
- Not verified on real Windows with two computers yet.

## Automatic mode (0.7.13)
Turn on **Settings > Privacy > Use an encrypted private link for Dolphin when everyone has Tailscale** (every player does this
themselves; it is off by default). With it on and Tailscale running, your app tells the room your `100.x` Tailscale address
(never your home address; anyone in the room can see it). When the host picks **Automatic**:
1. Every other player must have reported a Tailscale address.
2. The host pings each one over Tailscale to prove they can really be reached.
3. If both hold, the private link is used. If not, the normal traversal connection is used and the steps say why.
Legacy Player never downloads or installs Tailscale; Setup shows a link to the official download page.
