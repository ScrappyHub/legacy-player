# Dolphin DSU Backend v1

Legacy Player uses Dolphin's existing DualShock UDP client as its first safe external
controller-injection surface. Dolphin currently identifies this source as `DSUClient`,
supports four pads, uses protocol version 1001, and defaults to UDP port 26760.

The implementation provides:

- DSU version responses
- virtual-pad discovery
- pad-data registration
- CRC-validated packets
- up to four virtual controller states
- broadcast updates when lockstep bundles are released

This backend deliberately separates input delivery from frame synchronization. DSU
does not provide an external API to pause Dolphin at a particular emulated frame. The
backend exposes that limitation explicitly and refuses non-contiguous network bundles.

Official implementation references:

- https://github.com/dolphin-emu/dolphin/tree/master/Source/Core/InputCommon/ControllerInterface/DualShockUDPClient
- https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerInterface/DualShockUDPClient/DualShockUDPProto.h
