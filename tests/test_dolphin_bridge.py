import unittest

from adapters.dolphin.bridge import DolphinBridgeError, DolphinDsuBridge
from adapters.dolphin.dsu_protocol import DsuServerProtocol


class RecordingProtocol(DsuServerProtocol):
    def __init__(self):
        super().__init__()
        self.broadcasts = []

    def broadcast(self, pad_id):
        self.broadcasts.append(pad_id)


class DolphinBridgeTests(unittest.TestCase):
    def test_applies_complete_bundle_to_virtual_pads(self):
        bridge = DolphinDsuBridge({"host": 0, "peer": 1})
        protocol = RecordingProtocol()
        bridge.apply_bundle(
            {
                "frame": 0,
                "inputs": [
                    {"participant_id": "host", "buttons": 1, "stick_x": 2, "stick_y": 3},
                    {"participant_id": "peer", "buttons": 4, "stick_x": 5, "stick_y": 6},
                ],
            },
            protocol,
        )
        self.assertEqual(0, bridge.last_frame)
        self.assertEqual(1, bridge.pads[0].state.buttons)
        self.assertEqual(4, bridge.pads[1].state.buttons)
        self.assertEqual([0, 1], protocol.broadcasts)
        self.assertFalse(bridge.supports_frame_control)

    def test_rejects_missing_or_non_contiguous_frames(self):
        bridge = DolphinDsuBridge({"host": 0, "peer": 1})
        protocol = RecordingProtocol()
        with self.assertRaisesRegex(DolphinBridgeError, "non-contiguous"):
            bridge.apply_bundle({"frame": 1, "inputs": []}, protocol)
        with self.assertRaisesRegex(DolphinBridgeError, "missing participants"):
            bridge.apply_bundle(
                {"frame": 0, "inputs": [{"participant_id": "host", "buttons": 0}]},
                protocol,
            )


if __name__ == "__main__":
    unittest.main()
