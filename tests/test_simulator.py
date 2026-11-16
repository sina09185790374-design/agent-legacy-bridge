"""Tests for the demo device and the reader, over a real socket."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bridge.reader import Client, DemoSession, DeviceError, WriteRefused  # noqa: E402
from bridge.simulator import serve  # noqa: E402


class SimulatorTestCase(unittest.TestCase):
    def setUp(self):
        self.server = serve("127.0.0.1", 0, seed=7)
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def client(self):
        return Client("127.0.0.1", self.port)


class TestReader(SimulatorTestCase):
    def test_read_all_returns_seven_parameters(self):
        with self.client() as client:
            values = client.read_all()
        self.assertEqual(len(values), 7)
        self.assertEqual(values["TEMP_OUT"][1], "C")
        self.assertAlmostEqual(values["TEMP_OUT"][0], 23.4, places=1)

    def test_read_single_param(self):
        with self.client() as client:
            name, value, unit = client.read_param("06")
        self.assertEqual((name, value, unit), ("BATT", 12.5, "V"))

    def test_unknown_param_is_an_error(self):
        with self.client() as client:
            with self.assertRaises(KeyError):
                client.read_param("99")

    def test_unknown_request_is_refused_by_device(self):
        with self.client() as client:
            with self.assertRaises(DeviceError):
                client.send("?Z")

    def test_healthy_device_has_no_faults(self):
        with self.client() as client:
            self.assertEqual(client.faults(), [])

    def test_selftest_passes_when_healthy(self):
        with self.client() as client:
            result = client.selftest()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["faults"], [])

    def test_set_interval_needs_confirmation(self):
        with self.client() as client:
            with self.assertRaises(WriteRefused):
                client.set_interval(60)
            self.assertEqual(client.interval(), 30)  # nothing was sent
            client.set_interval(60, confirm=True)
            self.assertEqual(client.interval(), 60)

    def test_set_interval_rejects_out_of_range(self):
        with self.client() as client:
            with self.assertRaises(ValueError):
                client.set_interval(3, confirm=True)

    def test_live_stream_yields_frames(self):
        with self.client() as client:
            client.set_interval(5, confirm=True)
            seen = []
            count = client.live(11, lambda values: seen.append(values))
        self.assertGreaterEqual(count, 2)
        self.assertTrue(all("TEMP_OUT" in frame for frame in seen))

    def test_demo_session_is_deterministic(self):
        with DemoSession(seed=7) as first:
            first_values = first.read_all()
        with DemoSession(seed=7) as second:
            second_values = second.read_all()
        self.assertEqual(first_values, second_values)


class TestFaultInjection(SimulatorTestCase):
    def setUp(self):
        self.server = serve("127.0.0.1", 0, seed=7, faults=("F02",))
        self.port = self.server.server_address[1]

    def test_injected_fault_is_reported_and_decoded(self):
        with self.client() as client:
            faults = client.faults()
        self.assertEqual([code for code, _ in faults], ["F02"])
        self.assertIn("battery", faults[0][1].lower())

    def test_selftest_fails_with_fault(self):
        with self.client() as client:
            result = client.selftest()
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual([code for code, _ in result["faults"]], ["F02"])


if __name__ == "__main__":
    unittest.main()
