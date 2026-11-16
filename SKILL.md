# SKILL.md — legacy-device bridge

## When to use this skill

A coding agent needs to read (or, with approval, write) a "dumb" legacy
device: a serial weather station, an old engine computer, a PLC, any box
that speaks a small fixed protocol and has no API. Use the demo device to
learn the pattern, then point the same reader at the real hardware.

## The pattern (why it works)

1. **The protocol is data, not code.** `protocol.json` holds the commands,
   parameter ids, scaling formulas and fault codes. The agent reads the
   spec; the code only enforces it. A new device means a new spec file,
   not a rewrite.
2. **The demo is the device.** The simulator speaks the exact protocol on
   a TCP socket, seeded so a session is reproducible. The agent practices
   end-to-end — including the unhappy path, via injected faults — with
   zero hardware and zero risk.
3. **The transport is a seam.** The reader only knows TCP. Demo, real
   serial behind `socat`, or a captured log replay all look the same to it,
   so nothing changes between practice and production.
4. **Writes are a human decision.** A write command is refused unless a
   human approved it first. The gateway is the flag, not the prompt.
5. **Every session leaves a log.** JSONL, one frame per line, summarizable
   with `bridge log`. Evidence beats memory.

## Workflow

```bash
python -m bridge check-spec                                  # spec valid?
python -m bridge read --demo                                 # snapshot
python -m bridge faults --demo                               # healthy?
python -m bridge selftest --demo                             # PASS?
python -m bridge live --demo --seconds 12 --interval 5 --log session.jsonl
python -m bridge log session.jsonl                           # summary
```

Then, only with the human's go-ahead and the exact host/port of the
serial-to-TCP bridge:

```bash
python -m bridge read --host 127.0.0.1 --port 19090
python -m bridge set-interval 60 --host 127.0.0.1 --port 19090 --confirm
```

## Safety

- Never send a byte that is not in `protocol.json`.
- Never auto-approve a write: ask the human, then `--confirm`.
- Never report a value from a frame that failed its checksum.
- Never connect to real hardware while another program holds the port.
