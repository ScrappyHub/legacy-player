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
