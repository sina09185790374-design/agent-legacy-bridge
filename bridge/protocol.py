"""WS-90 protocol: frames, checksums, scaling, spec validation.

The protocol is plain ASCII lines (CRLF terminated), the way 1990s serial
devices speak. A frame looks like::

    #P01=0634*5A

``#`` starts the frame, ``*`` introduces a two-digit uppercase hex XOR-8
checksum over every character between ``#`` and ``*``.

Nothing here guesses: every parameter, scale and fault code comes from
``protocol.json``. The agent reads the spec; the code only enforces it.
"""

from __future__ import annotations

import json
import os

SPEC_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protocol.json")


class FrameError(ValueError):
    """The line is not a well-formed WS-90 frame."""


class ChecksumError(FrameError):
    """The frame parses but its checksum does not match its bytes."""


def xor8_hex(payload: str) -> str:
    """XOR-8 checksum of *payload*, as two uppercase hex digits."""
    value = 0
    for byte in payload.encode("ascii"):
        value ^= byte
    return f"{value:02X}"


def encode_frame(payload: str) -> str:
    """Wrap *payload* in a checksummed frame, without the CRLF."""
    return f"#{payload}*{xor8_hex(payload)}"


def parse_frame(line: str) -> dict:
    """Parse one response frame into a dict.

    Returns ``{"kind": "P", "param": "01", "raw": 634}`` for ``#P01=0634*..``,
    ``{"kind": "A", "values": {"01": 634, ...}}`` for ``#L,...`` / ``#A,...``
    frames, ``{"kind": "F", "faults": ["F02"]}`` for fault frames,
    ``{"kind": "T", "result": "PASS", "faults": []}`` for self-tests,
    ``{"kind": "I", "seconds": 30}`` for interval reads and
    ``{"kind": "OK"}`` for write acknowledgements.
    """
    text = line.strip()
    if not text.startswith("#") or "*" not in text:
        raise FrameError(f"not a WS-90 frame: {line!r}")
    payload, _, checksum = text[1:].partition("*")
    if len(checksum) != 2 or checksum != xor8_hex(payload):
        raise ChecksumError(f"checksum mismatch in frame: {line!r}")
    if payload.startswith("P") and "=" in payload:
        param, _, raw = payload[1:].partition("=")
        return {"kind": "P", "param": param, "raw": int(raw)}
    if payload.startswith(("A", "L")) and "," in payload:
        body = payload[2:] if payload[1] == "," else payload[1:]
        values = {}
        for part in body.split(","):
            param, _, raw = part.partition("=")
            values[param] = int(raw)
        return {"kind": payload[0], "values": values}
    if payload.startswith("F="):
        faults = payload[2:].split(",") if payload[2:] else ["F00"]
        return {"kind": "F", "faults": faults}
    if payload.startswith("T="):
        body = payload[2:]
        result, _, rest = body.partition(":")
        faults = rest.split(",") if rest else []
        return {"kind": "T", "result": result, "faults": faults}
    if payload.startswith("I="):
        return {"kind": "I", "seconds": int(payload[2:])}
    if payload == "OK":
        return {"kind": "OK"}
    if payload.startswith("E="):
        return {"kind": "E", "error": payload[2:]}
    raise FrameError(f"unknown frame payload: {payload!r}")


def load_spec(path: str = SPEC_PATH) -> dict:
    """Load the protocol spec JSON."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def param_by_id(spec: dict, param_id: str) -> dict:
    """Return the parameter spec for a two-digit id, or raise KeyError."""
    for param in spec["parameters"]:
        if param["id"] == param_id:
            return param
    raise KeyError(f"unknown parameter id: {param_id!r}")


def scale_value(param: dict, raw: int) -> float:
    """Apply a parameter's scale and offset, rounded to its decimals."""
    if not param["raw_min"] <= raw <= param["raw_max"]:
        raise ValueError(
            f"raw {raw} out of range "
            f"[{param['raw_min']}..{param['raw_max']}] for {param['name']}"
        )
    return round(raw * param["scale"] + param["offset"], param["decimals"])


def decode_values(spec: dict, raw_values: dict) -> dict:
    """Decode a ``{id: raw}`` mapping into ``{name: (value, unit)}``."""
    decoded = {}
    for param_id, raw in raw_values.items():
        param = param_by_id(spec, param_id)
        decoded[param["name"]] = (scale_value(param, raw), param["unit"])
    return decoded


def fault_text(spec: dict, code: str) -> str:
    """Human-readable text for a fault code."""
    return spec["faults"].get(code, f"Unknown fault code {code}")


def validate_spec(spec: dict) -> list:
    """Return a list of problems with a spec; empty means the spec is valid."""
    problems = []
    ids = [p["id"] for p in spec.get("parameters", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate parameter ids")
    for param in spec.get("parameters", []):
        for key in ("id", "name", "unit", "scale", "offset", "raw_min", "raw_max"):
            if key not in param:
                problems.append(f"parameter {param.get('id', '?')} misses {key!r}")
        if param.get("raw_min", 0) > param.get("raw_max", 0):
            problems.append(f"parameter {param.get('id')} has raw_min > raw_max")
        if param.get("scale", 0) <= 0:
            problems.append(f"parameter {param.get('id')} has a non-positive scale")
    if not spec.get("faults", {}).get("F00"):
        problems.append("fault table misses F00 (no fault)")
    return problems
