"""The reader: talk to a WS-90 over TCP, demo or real.

One class, two transports, same code path:

- ``--demo`` spins up the in-process simulator on an ephemeral port, runs
  the command, and shuts it down. Zero setup, zero hardware — this is where
  every agent session starts.
- ``--host/--port`` talks to anything that speaks WS-90 on TCP: the demo
  server in another terminal, or a real serial device behind ``socat`` /
  ``ser2net``. The reader never knows the difference, by design.

Writes are refused unless the caller passes ``confirm=True`` — and the
playbook (``SKILL.md``) says the agent asks a human first. A refused write
sends nothing to the device.
"""

from __future__ import annotations

import json
import socket
import time

from .protocol import (
    ChecksumError,
    FrameError,
    decode_values,
    fault_text,
    load_spec,
    param_by_id,
    parse_frame,
)
from .simulator import DEFAULT_PORT, serve


class DeviceError(RuntimeError):
    """The device answered, but with an error or something unusable."""


class WriteRefused(RuntimeError):
    """A write was attempted without human confirmation."""


class Client:
    """A WS-90 connection: one socket, one request at a time."""

    def __init__(self, host: str, port: int, timeout: float = 5.0,
                 spec: dict | None = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.spec = spec or load_spec()
        self.sock: socket.socket | None = None

    def __enter__(self) -> "Client":
        self.sock = socket.create_connection(
            (self.host, self.port), timeout=self.timeout
        )
        self.sock.settimeout(self.timeout)
        self._buffer = b""
        return self

    def __exit__(self, *exc) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def _read_line(self) -> str:
        while b"\n" not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise DeviceError("device closed the connection")
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\n", 1)
        return line.decode("ascii").strip()

    def send(self, request: str) -> dict:
        """Send one request line, return the parsed response frame."""
        self.sock.sendall((request + "\r\n").encode("ascii"))
        frame = parse_frame(self._read_line())
        if frame["kind"] == "E":
            raise DeviceError(f"device refused the request: {frame['error']}")
        return frame

    def read_param(self, param_id: str) -> tuple:
        """Read one parameter; returns ``(name, value, unit)``."""
        param = param_by_id(self.spec, param_id)
        frame = self.send(f"?P{param_id}")
        if frame["kind"] != "P" or frame["param"] != param_id:
            raise DeviceError(f"unexpected reply to ?P{param_id}: {frame}")
        from .protocol import scale_value

        return param["name"], scale_value(param, frame["raw"]), param["unit"]

    def read_all(self) -> dict:
        """Read every parameter; returns ``{name: (value, unit)}``."""
        frame = self.send("?A")
        if frame["kind"] != "A":
            raise DeviceError(f"unexpected reply to ?A: {frame}")
        return decode_values(self.spec, frame["values"])

    def faults(self) -> list:
        """Return ``[(code, text)]`` for the active faults (empty = healthy)."""
        frame = self.send("?F")
        if frame["kind"] != "F":
            raise DeviceError(f"unexpected reply to ?F: {frame}")
        codes = [c for c in frame["faults"] if c != "F00"]
        return [(c, fault_text(self.spec, c)) for c in codes]

    def selftest(self) -> dict:
        """Run the device self-test; returns ``{"result": ..., "faults": [...]}``."""
        frame = self.send("?T")
        if frame["kind"] != "T":
            raise DeviceError(f"unexpected reply to ?T: {frame}")
        return {
            "result": frame["result"],
            "faults": [(c, fault_text(self.spec, c)) for c in frame["faults"]],
        }

    def interval(self) -> int:
        """Read the live-stream interval in seconds."""
        frame = self.send("?I")
        if frame["kind"] != "I":
            raise DeviceError(f"unexpected reply to ?I: {frame}")
        return frame["seconds"]

    def set_interval(self, seconds: int, confirm: bool = False) -> None:
        """WRITE: change the live-stream interval.

        Refused — and nothing is sent — unless ``confirm`` is True.
        The caller (and the playbook) must have a human's go-ahead first.
        """
        if not confirm:
            raise WriteRefused(
                "set-interval changes device state: re-run with --confirm "
                "after a human approves it"
            )
        if not 5 <= seconds <= 3600:
            raise ValueError("interval must be 5..3600 seconds")
        frame = self.send(f"!I{seconds:03d}")
        if frame["kind"] != "OK":
            raise DeviceError(f"unexpected reply to !I{seconds:03d}: {frame}")

    def live(self, seconds: float, on_frame) -> int:
        """Stream live frames for *seconds*; calls ``on_frame(decoded)`` per frame.

        Returns the number of frames received. The device streams at its
        configured interval, so a short session may yield one frame.
        """
        first = self.send(">L")
        count = 0
        if first["kind"] == "L":
            on_frame(decode_values(self.spec, first["values"]))
            count = 1
        deadline = time.time() + seconds
        try:
            while time.time() < deadline:
                remaining = deadline - time.time()
                self.sock.settimeout(max(0.1, remaining))
                try:
                    frame = parse_frame(self._read_line())
                except socket.timeout:
                    break
                if frame["kind"] == "L":
                    on_frame(decode_values(self.spec, frame["values"]))
                    count += 1
        finally:
            try:
                self.sock.settimeout(self.timeout)
                self.send(">S")
            except (OSError, FrameError, ChecksumError, DeviceError):
                pass
        return count


class DemoSession:
    """A throwaway demo device: start it, use it, shut it down.

    Usage::

        with DemoSession(seed=7) as client:
            print(client.read_all())
    """

    def __init__(self, seed: int = 7, faults=()):
        self.seed = seed
        self.faults = faults
        self.server = None
        self.client = None

    def __enter__(self) -> Client:
        self.server = serve("127.0.0.1", 0, seed=self.seed, faults=self.faults)
        port = self.server.server_address[1]
        self.client = Client("127.0.0.1", port)
        return self.client.__enter__()

    def __exit__(self, *exc) -> None:
        if self.client is not None:
            self.client.__exit__(*exc)
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


def summarize_log(path: str, spec: dict | None = None) -> dict:
    """Summarize a JSONL session log: min/max/mean per parameter + faults."""
    spec = spec or load_spec()
    frames = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                frames.append(json.loads(line))
    summary = {"frames": len(frames), "parameters": {}, "faults_seen": []}
    if not frames:
        return summary
    seen_faults = set()
    for name in {p["name"] for p in spec["parameters"]}:
        values = [f["values"][name] for f in frames if name in f.get("values", {})]
        if values:
            summary["parameters"][name] = {
                "min": min(values),
                "max": max(values),
                "mean": round(sum(values) / len(values), 2),
                "samples": len(values),
            }
    for frame in frames:
        for fault in frame.get("faults", []):
            seen_faults.add(fault)
    summary["faults_seen"] = sorted(seen_faults)
    return summary
