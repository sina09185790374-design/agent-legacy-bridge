"""End-to-end CLI tests: real subprocess runs against the demo device."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "bridge", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


class TestCli(unittest.TestCase):
    def test_read_demo(self):
        result = run("read", "--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TEMP_OUT", result.stdout)
        self.assertIn("23.4", result.stdout)

    def test_read_single_param_json(self):
        result = run("read", "--demo", "--param", "01", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["TEMP_OUT"]["value"], 23.4)

    def test_check_spec(self):
        result = run("check-spec")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("spec OK", result.stdout)

    def test_selftest_passes(self):
        result = run("selftest", "--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_faults_demo_healthy(self):
        result = run("faults", "--demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No active faults", result.stdout)

    def test_faults_demo_injected(self):
        result = run("faults", "--demo", "--fault", "F02")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("F02", result.stdout)
        self.assertIn("battery", result.stdout.lower())

    def test_set_interval_without_confirm_is_refused(self):
        result = run("set-interval", "30", "--demo")
        self.assertEqual(result.returncode, 2)
        self.assertIn("refused", result.stderr.lower())

    def test_set_interval_with_confirm(self):
        result = run("set-interval", "45", "--demo", "--confirm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("45s", result.stdout)

    def test_live_streams_and_counts_frames(self):
        result = run("live", "--demo", "--seconds", "11", "--interval", "5")
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(r"received (\d+) live frame", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertGreaterEqual(int(match.group(1)), 2)

    def test_log_summarizes_a_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "session.jsonl")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(
                    {"ts": "2026-11-13T10:00:00",
                     "values": {"TEMP_OUT": 23.4, "BATT": 12.5}}) + "\n")
                handle.write(json.dumps(
                    {"ts": "2026-11-13T10:00:05",
                     "values": {"TEMP_OUT": 23.6, "BATT": 12.4},
                     "faults": ["F02"]}) + "\n")
            result = run("log", log_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 frame(s)", result.stdout)
        self.assertIn("TEMP_OUT", result.stdout)
        self.assertIn("F02", result.stdout)

    def test_bad_command_exits_nonzero(self):
        result = run("read", "--demo", "--param", "99")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
