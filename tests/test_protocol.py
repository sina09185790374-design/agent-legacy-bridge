"""Tests for the WS-90 protocol: frames, checksums, scaling, spec."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bridge.protocol import (  # noqa: E402
    ChecksumError,
    FrameError,
    decode_values,
    encode_frame,
    fault_text,
    load_spec,
    param_by_id,
    parse_frame,
    scale_value,
    validate_spec,
    xor8_hex,
)

SPEC = load_spec()


class TestChecksum(unittest.TestCase):
    def test_known_vector(self):
        # 0x41 ^ 0x42 ^ 0x43 == 0x40, hand-computed.
        self.assertEqual(xor8_hex("ABC"), "40")
        self.assertEqual(xor8_hex(""), "00")

    def test_round_trip(self):
        for payload in ("P01=0634", "F=F02", "T=PASS", "I=030", "OK",
                        "A,01=0634,02=0452", "L,01=0634,02=0452"):
            frame = parse_frame(encode_frame(payload))
            self.assertIn(frame["kind"], "PFTA LIOKE".replace(" ", ""))

    def test_tampered_checksum_is_rejected(self):
        frame = encode_frame("P01=0634")
        tampered = frame[:-1] + ("0" if frame[-1] != "0" else "1")
        with self.assertRaises(ChecksumError):
            parse_frame(tampered)

    def test_garbage_is_not_a_frame(self):
        for bad in ("", "hello", "#P01=0634", "P01=0634*5A"):
            with self.assertRaises(FrameError, msg=bad):
                parse_frame(bad)


class TestFrames(unittest.TestCase):
    def test_param_frame(self):
        frame = parse_frame(encode_frame("P01=0634"))
        self.assertEqual(frame, {"kind": "P", "param": "01", "raw": 634})

    def test_all_and_live_frames(self):
        frame = parse_frame(encode_frame("A,01=0634,02=0452,07=2130"))
        self.assertEqual(frame["kind"], "A")
        self.assertEqual(frame["values"], {"01": 634, "02": 452, "07": 2130})
        live = parse_frame(encode_frame("L,03=0042,04=0270"))
        self.assertEqual(live["kind"], "L")
        self.assertEqual(live["values"], {"03": 42, "04": 270})

    def test_fault_frame(self):
        frame = parse_frame(encode_frame("F=F02,F05"))
        self.assertEqual(frame["faults"], ["F02", "F05"])

    def test_selftest_frames(self):
        self.assertEqual(parse_frame(encode_frame("T=PASS"))["result"], "PASS")
        failed = parse_frame(encode_frame("T=FAIL:F02"))
        self.assertEqual((failed["result"], failed["faults"]), ("FAIL", ["F02"]))

    def test_interval_and_ok_and_error(self):
        self.assertEqual(parse_frame(encode_frame("I=030"))["seconds"], 30)
        self.assertEqual(parse_frame(encode_frame("OK"))["kind"], "OK")
        self.assertEqual(parse_frame(encode_frame("E=BADREQ"))["error"], "BADREQ")


class TestScaling(unittest.TestCase):
    def test_known_raw_to_value_pairs(self):
        cases = [("01", 634, 23.4), ("01", 0, -40.0), ("02", 452, 45.2),
                 ("03", 42, 4.2), ("04", 270, 270), ("05", 123, 1.23),
                 ("06", 1250, 12.5), ("07", 2130, 1013.0)]
        for pid, raw, expected in cases:
            param = param_by_id(SPEC, pid)
            self.assertEqual(scale_value(param, raw), expected, pid)

    def test_out_of_range_raw_rejected(self):
        param = param_by_id(SPEC, "01")
        with self.assertRaises(ValueError):
            scale_value(param, 1024)
        with self.assertRaises(ValueError):
            scale_value(param, -1)

    def test_unknown_param_rejected(self):
        with self.assertRaises(KeyError):
            param_by_id(SPEC, "99")

    def test_decode_all(self):
        decoded = decode_values(SPEC, {"01": 634, "06": 1250})
        self.assertEqual(decoded["TEMP_OUT"], (23.4, "C"))
        self.assertEqual(decoded["BATT"], (12.5, "V"))


class TestFaultsAndSpec(unittest.TestCase):
    def test_fault_text(self):
        self.assertIn("battery", fault_text(SPEC, "F02").lower())
        self.assertEqual(fault_text(SPEC, "F00"), "No fault")
        self.assertIn("Unknown", fault_text(SPEC, "F99"))

    def test_shipped_spec_is_valid(self):
        self.assertEqual(validate_spec(SPEC), [])

    def test_broken_specs_are_caught(self):
        broken = copy.deepcopy(SPEC)
        broken["parameters"].append(dict(broken["parameters"][0]))
        self.assertIn("duplicate parameter ids", validate_spec(broken))
        broken = copy.deepcopy(SPEC)
        del broken["faults"]["F00"]
        self.assertTrue(any("F00" in p for p in validate_spec(broken)))
        broken = copy.deepcopy(SPEC)
        broken["parameters"][0]["scale"] = 0
        self.assertTrue(any("scale" in p for p in validate_spec(broken)))


if __name__ == "__main__":
    unittest.main()
