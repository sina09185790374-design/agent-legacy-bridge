"""CLI: ``python -m bridge <command>``.

Commands
--------
demo          run the demo device on a TCP port (Ctrl-C stops it)
read          one snapshot of all parameters (or one with --param)
faults        active fault codes, decoded
live          stream live frames for N seconds, optionally logging JSONL
selftest      run the device self-test
set-interval  WRITE: change the live-stream interval (needs --confirm)
log           summarize a JSONL session log
check-spec    validate protocol.json

Every command except ``demo`` and ``log``/``check-spec`` takes ``--demo``
(practice on the built-in simulator, zero setup) or ``--host/--port``
(talk to a real device behind a serial-to-TCP bridge). ``--demo`` is the
default when no host is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import contextmanager

from .protocol import ChecksumError, FrameError, load_spec, validate_spec
from .reader import Client, DemoSession, DeviceError, WriteRefused, summarize_log
from .simulator import DEFAULT_PORT, serve, wait_ready


def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--demo", action="store_true",
                        help="use the built-in demo device (default)")
    parser.add_argument("--host", default=None, help="device TCP host")
    parser.add_argument("--port", type=int, default=None, help="device TCP port")
    parser.add_argument("--seed", type=int, default=7,
                        help="demo device seed (reproducible weather)")
    parser.add_argument("--fault", action="append", default=[],
                        help="inject a fault into the demo device, e.g. F02")


@contextmanager
def _connect(args):
    """Yield a Client: demo simulator, or the TCP host the user named."""
    if args.host is not None:
        port = args.port or DEFAULT_PORT
        with Client(args.host, port) as client:
            yield client
    else:
        with DemoSession(seed=args.seed, faults=args.fault) as client:
            yield client


def _print_values(values: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {name: {"value": value, "unit": unit}
             for name, (value, unit) in values.items()},
            indent=2,
        ))
        return
    width = max(len(name) for name in values)
    for name, (value, unit) in sorted(values.items()):
        print(f"{name:<{width}}  {value:>8} {unit}")


def cmd_demo(args) -> int:
    server = serve("127.0.0.1", args.port, seed=args.seed, faults=args.fault)
    port = server.server_address[1]
    print(f"WS-90 demo device on 127.0.0.1:{port} (seed {args.seed})")
    print("Talk to it with:  python -m bridge read --host 127.0.0.1 "
          f"--port {port}")
    print("Ctrl-C stops it.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


def cmd_read(args) -> int:
    with _connect(args) as client:
        if args.param:
            name, value, unit = client.read_param(args.param)
            if args.json:
                print(json.dumps({name: {"value": value, "unit": unit}}))
            else:
                print(f"{name}  {value} {unit}")
        else:
            _print_values(client.read_all(), args.json)
    return 0


def cmd_faults(args) -> int:
    with _connect(args) as client:
        faults = client.faults()
    if not faults:
        print("No active faults (F00).")
        return 0
    for code, text in faults:
        print(f"{code}  {text}")
    return 0


def cmd_live(args) -> int:
    log_handle = None
    if args.log:
        log_handle = open(args.log, "a", encoding="utf-8")
    frames = []

    def on_frame(values):
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "values": {n: v for n, (v, _) in values.items()}}
        frames.append(record)
        if log_handle is not None:
            log_handle.write(json.dumps(record) + "\n")
            log_handle.flush()
        if not args.json:
            line = "  ".join(f"{n}={v}{u}" for n, (v, u) in sorted(values.items()))
            print(line)

    with _connect(args) as client:
        if args.interval is not None and args.host is None:
            # demo device only: shorten the stream so a short session
            # still shows several frames. Real hardware keeps its interval
            # unless a human approves set-interval explicitly.
            client.set_interval(args.interval, confirm=True)
        count = client.live(args.seconds, on_frame)
    if log_handle is not None:
        log_handle.close()
    if args.json:
        print(json.dumps(frames, indent=2))
    print(f"received {count} live frame(s) in {args.seconds}s")
    return 0


def cmd_selftest(args) -> int:
    with _connect(args) as client:
        result = client.selftest()
    print(f"self-test: {result['result']}")
    for code, text in result["faults"]:
        print(f"  {code}  {text}")
    return 0 if result["result"] == "PASS" else 1


def cmd_set_interval(args) -> int:
    with _connect(args) as client:
        client.set_interval(args.seconds, confirm=args.confirm)
    print(f"live-stream interval set to {args.seconds}s")
    return 0


def cmd_log(args) -> int:
    summary = summarize_log(args.path)
    print(f"{args.path}: {summary['frames']} frame(s)")
    for name, stats in sorted(summary["parameters"].items()):
        print(f"  {name}: min {stats['min']}  max {stats['max']}  "
              f"mean {stats['mean']}  ({stats['samples']} samples)")
    if summary["faults_seen"]:
        print("  faults seen: " + ", ".join(summary["faults_seen"]))
    return 0


def cmd_check_spec(args) -> int:
    spec = load_spec(args.spec) if args.spec else load_spec()
    problems = validate_spec(spec)
    if problems:
        for problem in problems:
            print(f"INVALID: {problem}")
        return 1
    print(f"spec OK: {spec['device']} — "
          f"{len(spec['parameters'])} parameters, "
          f"{len(spec['faults'])} fault codes")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bridge",
        description="Teach an agent to talk to a dumb legacy device (WS-90).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="run the demo device on a TCP port")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--fault", action="append", default=[])
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("read", help="one snapshot of the device")
    _add_target(p)
    p.add_argument("--param", help="two-digit parameter id, e.g. 01")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("faults", help="active fault codes, decoded")
    _add_target(p)
    p.set_defaults(func=cmd_faults)

    p = sub.add_parser("live", help="stream live frames for N seconds")
    _add_target(p)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--interval", type=int, default=None,
                   help="demo only: set the stream interval first (5..3600)")
    p.add_argument("--log", help="append JSONL session log here")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_live)

    p = sub.add_parser("selftest", help="run the device self-test")
    _add_target(p)
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("set-interval", help="WRITE: live-stream interval")
    _add_target(p)
    p.add_argument("seconds", type=int)
    p.add_argument("--confirm", action="store_true",
                   help="required: a human approved this write")
    p.set_defaults(func=cmd_set_interval)

    p = sub.add_parser("log", help="summarize a JSONL session log")
    p.add_argument("path")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("check-spec", help="validate protocol.json")
    p.add_argument("--spec", default=None,
                   help="spec file (default: protocol.json)")
    p.set_defaults(func=cmd_check_spec)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WriteRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except (DeviceError, FrameError, ChecksumError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: cannot reach the device: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
