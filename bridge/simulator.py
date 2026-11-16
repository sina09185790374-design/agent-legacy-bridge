"""The DEMO device: a deterministic WS-90 weather station on a TCP socket.

This is the safe half of the pattern. Before an agent ever touches real
hardware it practices here: the simulator speaks the exact protocol from
``protocol.json``, with a seeded random walk so a session is reproducible
(``--seed 7`` always walks the same weather), and faults can be injected
(``--fault F02``) to rehearse the unhappy path.

Real hardware is reached the same way — over TCP, through a serial-to-TCP
bridge such as ``socat`` or ``ser2net`` — so the reader code never changes
between demo and device. The simulator is stdlib-only, like everything here.
"""

from __future__ import annotations

import random
import select
import socket
import socketserver
import threading
import time

from .protocol import encode_frame, load_spec, param_by_id

DEFAULT_PORT = 19090


class WeatherStation:
    """One WS-90's state: a slow random walk around plausible weather."""

    def __init__(self, spec: dict, seed: int = 7, faults=()):
        self.spec = spec
        self.rng = random.Random(seed)
        self.faults = set(faults)
        self.interval = 30
        self.streaming = False
        # raw values: a mild afternoon — 23.4 C, 45% humidity, light wind.
        self.raw = {
            "01": 634,   # 23.4 C
            "02": 452,   # 45.2 %
            "03": 42,    # 4.2 km/h
            "04": 270,   # west
            "05": 123,   # 1.23 mm
            "06": 1250,  # 12.50 V
            "07": 2130,  # 1013.0 hPa
        }

    def _step(self) -> None:
        """Advance the weather by one small random step, inside spec ranges."""
        for param in self.spec["parameters"]:
            pid = param["id"]
            if pid == "05":  # rainfall only ever grows, slowly
                self.raw[pid] = min(param["raw_max"], self.raw[pid] + self.rng.randint(0, 1))
                continue
            if pid == "04":  # wind direction wanders
                self.raw[pid] = (self.raw[pid] + self.rng.randint(-8, 8)) % 360
                continue
            span = max(1, (param["raw_max"] - param["raw_min"]) // 200)
            self.raw[pid] = max(
                param["raw_min"],
                min(param["raw_max"], self.raw[pid] + self.rng.randint(-span, span)),
            )
        if "F02" in self.faults:  # low battery drains while the fault is set
            self.raw["06"] = max(900, self.raw["06"] - 1)

    def _live_frame(self) -> str:
        body = ",".join(f"{pid}={self.raw[pid]:04d}" for pid in sorted(self.raw))
        return encode_frame(f"L,{body}")

    def handle(self, line: str) -> list:
        """Answer one request line with zero or more response frames."""
        request = line.strip()
        if request.startswith("?P"):
            pid = request[2:4]
            param_by_id(self.spec, pid)  # raises KeyError on unknown ids
            return [encode_frame(f"P{pid}={self.raw[pid]:04d}")]
        if request == "?A":
            body = ",".join(f"{pid}={self.raw[pid]:04d}" for pid in sorted(self.raw))
            return [encode_frame(f"A,{body}")]
        if request == "?F":
            faults = sorted(self.faults) or ["F00"]
            return [encode_frame("F=" + ",".join(faults))]
        if request == "?I":
            return [encode_frame(f"I={self.interval:03d}")]
        if request == "?T":
            self._step()
            if self.faults:
                return [encode_frame("T=FAIL:" + ",".join(sorted(self.faults)))]
            return [encode_frame("T=PASS")]
        if request.startswith("!I"):
            seconds = int(request[2:])
            if not 5 <= seconds <= 3600:
                raise ValueError("interval must be 5..3600 seconds")
            self.interval = seconds
            return [encode_frame("OK")]
        if request == ">L":
            self.streaming = True
            return [self._live_frame()]
        if request == ">S":
            self.streaming = False
            return [encode_frame("OK")]
        raise ValueError(f"unknown request: {request!r}")

    def tick(self) -> str | None:
        """Emit one live frame if streaming, else None."""
        if not self.streaming:
            return None
        self._step()
        return self._live_frame()


class _Handler(socketserver.BaseRequestHandler):
    """One connection: answer requests, and tick live frames while streaming.

    The socket is watched with ``select``: while the station streams, the
    wait times out every ``interval`` seconds and a live frame is emitted;
    otherwise the handler blocks until the next request arrives.
    """

    def handle(self) -> None:
        conn = self.request
        buf = b""
        while True:
            timeout = self.server.station.interval if self.server.station.streaming else None
            readable, _, _ = select.select([conn], [], [], timeout)
            if not readable:
                frame = self.server.station.tick()
                if frame:
                    conn.sendall((frame + "\r\n").encode("ascii"))
                continue
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    frames = self.server.station.handle(line.decode("ascii"))
                except (ValueError, KeyError):
                    frames = [encode_frame("E=BADREQ")]
                for frame in frames:
                    conn.sendall((frame + "\r\n").encode("ascii"))


class DemoServer(socketserver.ThreadingTCPServer):
    """Threading TCP server bound to one shared WeatherStation."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, station: WeatherStation):
        self.station = station
        super().__init__((host, port), _Handler)


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT,
          seed: int = 7, faults=()) -> DemoServer:
    """Start the demo device in a background thread; returns the server."""
    station = WeatherStation(load_spec(), seed=seed, faults=faults)
    server = DemoServer(host, port, station)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def wait_ready(host: str, port: int, timeout: float = 5.0) -> None:
    """Block until something answers on (host, port), or raise TimeoutError."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"nothing listening on {host}:{port}")
