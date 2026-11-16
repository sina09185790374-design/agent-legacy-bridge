# AGENTS.md — working with a WS-90 (or any dumb legacy device)

You are the agent. The device is old, literal, and has no patience for
guesses. This file is the whole job: read it before you send a single byte.

## The rules (non-negotiable)

1. **DEMO first, always.** Run every command against the built-in demo
   device (`--demo`) before you touch real hardware. A demo session that
   fails means your understanding is wrong, not the device.
2. **The spec is the contract.** `protocol.json` lists every command,
   parameter, scale and fault code. If a byte is not in the spec, do not
   send it. Never guess a command from a similar device.
3. **Writes need a human.** Anything starting with `!` changes device
   state. Ask the human first, in plain words, what will change — then pass
   `--confirm`. The CLI refuses writes without it, and so should you.
4. **Verify every frame.** A bad checksum means the line is lying, not the
   device. Say so, re-read, and never report a value from a frame that
   failed its checksum.
5. **Log everything.** A reading without a session log did not happen. Use
   `live --log session.jsonl` and `log` to summarize.

## The session (in order)

```bash
python -m bridge check-spec            # the spec itself must be valid
python -m bridge read --demo           # one snapshot, demo device
python -m bridge faults --demo         # any active faults?
python -m bridge selftest --demo       # PASS means the device is sane
python -m bridge live --demo --seconds 12 --interval 5 --log session.jsonl
python -m bridge log session.jsonl     # min / max / mean per parameter
```

Only after all six pass do you even discuss real hardware.

## Real hardware

The reader speaks TCP. A real serial device sits behind a serial-to-TCP
bridge on the user's machine (`socat`, `ser2net`, or the vendor's tool):

```bash
python -m bridge read --host 127.0.0.1 --port 19090
```

Before the first real read, confirm with the human, out loud: the exact
serial port, the baud rate from the device manual, and that nothing else is
already talking to the device. Two masters on one serial line corrupt each
other's frames.

## When something goes wrong

- `error: cannot reach the device` — the bridge is not running, or the
  host/port is wrong. Check the bridge, not the device.
- `checksum mismatch` — the line is noisy. Check cables and baud rate;
  never "fix" it by skipping the check.
- `device refused the request: BADREQ` — you sent a command the device
  does not know. Re-read `protocol.json`; do not retry variations.
- Self-test FAIL with a fault code — decode it with `faults`, report the
  plain-language text, and stop. Do not clear faults on real hardware
  without being asked.
