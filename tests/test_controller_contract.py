import unittest

from adapters.controller import ControllerState


class ControllerContractTests(unittest.TestCase):
    def test_controller_state_validates_axis_range(self):
        self.assertEqual(127, ControllerState(stick_x=127).stick_x)
        with self.assertRaises(ValueError):
            ControllerState(stick_x=128)


if __name__ == "__main__":
    unittest.main()
