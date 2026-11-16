# agent-legacy-bridge

Teach an AI agent to talk to a dumb legacy device — safely, with zero hardware.

> **EN** — A stdlib-only Python toolkit for reading a legacy serial device
> through an agent: the protocol is a JSON spec, a deterministic demo device
> speaks it on a TCP socket, and an agent playbook (`AGENTS.md` / `SKILL.md`)
> walks through the session. Writes need a human's go-ahead, by construction.
>
> **FA** — ابزاری با پایتون خالص (بدون وابستگی) برای اینکه یک ایجنت یاد بگیرد
> با یک دستگاه قدیمی سریال حرف بزند: پروتکل یک فایل JSON است، یک دستگاه دمو
> همان پروتکل را روی سوکت TCP حرف می‌زند، و یک راهنمای ایجنت (`AGENTS.md` /
> `SKILL.md`) قدم‌به‌قدم جلسه را جلو می‌برد. نوشتن روی دستگاه بدون تأیید
> انسان ممکن نیست — از اساس همین‌طور ساخته شده.

## The pattern

Inspired by the pattern of [MZULALI/xj-scanner](https://github.com/MZULALI/xj-scanner)
(an AI agent reading a 1991–95 Jeep engine computer through a $3 Arduino):
the agent is the *interpreter* for a device that cannot speak for itself.
This repo generalizes that pattern to any legacy device — original code, a
different device, a different protocol. No code was copied.

1. **The protocol is data, not code.** `protocol.json` holds the commands,
   parameter ids, scaling formulas and fault codes. A new device means a new
   spec file, not a rewrite.
2. **The demo is the device.** The simulator speaks the exact protocol,
   seeded so a session is reproducible (`--seed 7` always walks the same
   weather). The agent practices end-to-end — including the unhappy path,
   via injected faults — with zero hardware and zero risk.
3. **The transport is a seam.** The reader only knows TCP. Demo, real serial
   behind `socat`/`ser2net`, or a replayed log all look the same to it.
4. **Writes are a human decision.** A write is refused unless a human
   approved it first. The gateway is the flag, not the prompt.
5. **Every session leaves a log.** JSONL, one frame per line, summarizable
   with `bridge log`.

## Quickstart

```bash
python -m bridge check-spec
python -m bridge read --demo
python -m bridge faults --demo
python -m bridge selftest --demo
python -m bridge live --demo --seconds 12 --interval 5 --log session.jsonl
python -m bridge log session.jsonl
```

Real hardware sits behind a serial-to-TCP bridge on your machine:

```bash
python -m bridge read --host 127.0.0.1 --port 19090
python -m bridge set-interval 60 --host 127.0.0.1 --port 19090 --confirm
```

See [`examples/demo-session.md`](examples/demo-session.md) for a full session
with real output, including the unhappy path (injected low-battery fault).

## Commands

| Command | What it does |
| --- | --- |
| `demo` | Run the demo device on a TCP port (Ctrl-C stops it) |
| `read [--param 01] [--json]` | One snapshot of all parameters, or one |
| `faults` | Active fault codes, decoded to plain language |
| `live --seconds N [--interval S] [--log f.jsonl]` | Stream live frames, optionally logging |
| `selftest` | Run the device self-test (exit 1 on FAIL) |
| `set-interval S --confirm` | **WRITE:** live-stream interval (refused without `--confirm`) |
| `log <file.jsonl>` | Summarize a session log (min/max/mean, faults seen) |
| `check-spec [--spec f.json]` | Validate a protocol spec |

## The demo device (WS-90)

A fictional 1990s serial weather station: 7 parameters (temperature,
humidity, wind speed/direction, rainfall, battery, pressure), 6 fault codes,
ASCII frames with an XOR-8 checksum (`#P01=0634*5A`). The values are
invented for the demo — the pattern is what transfers to real hardware.

## Safety rules

- **DEMO first, always.** Never connect to real hardware before the demo
  session passes.
- **The spec is the contract.** Never send a byte that is not in
  `protocol.json`.
- **Writes need a human.** Ask first, then `--confirm`.
- **Verify every frame.** A bad checksum means the line is lying.
- **Log everything.** A reading without a session log did not happen.

## Tests

```bash
python -m unittest discover -s tests -v   # 39 tests, stdlib unittest
```

Tests cover frame round-trips and checksum rejection, scaling math for all
7 parameters, spec validation, the demo device over a real socket, fault
injection, the write-refusal gate, and the full CLI end-to-end. Two real bugs
were caught by the suite before shipping: a missing default in `check-spec`,
and the first live frame being dropped by the streaming loop.

## Layout

```
protocol.json          the WS-90 spec — the contract
AGENTS.md              the agent's playbook: session order + safety rules
SKILL.md               the pattern, as an installable skill
bridge/
  protocol.py          frames, checksums, scaling, spec validation
  simulator.py         the deterministic demo device (TCP)
  reader.py            the client: demo or real, same code path
  cli.py               the command line
examples/demo-session.md   a real session, with real output
tests/                 39 tests, all passing
```

## License

MIT. No API keys, no network beyond localhost, no secrets — `.env.example`
holds only `BRIDGE_HOST`/`BRIDGE_PORT` placeholders.

---

## فارسی

**این ابزار چیست؟** دستگاه‌های قدیمی — ایستگاه هواشناسی سریال، کامپیوتر موتور
ماشین‌های قدیمی، PLC — API ندارند؛ یک پروتکل کوچک ثابت حرف می‌زنند. این
ریپو به ایجنت یاد می‌دهد با چنین دستگاهی حرف بزند: اول روی دستگاه دمو تمرین
می‌کند (بدون هیچ سخت‌افزاری)، بعد همان کد را روی دستگاه واقعی می‌گذارد.

**الگو از کجاست؟** از [xj-scanner](https://github.com/MZULALI/xj-scanner)
(ایجنتی که با یک آردوینوی ۳ دلاری کامپیوتر موتور جیپ ۱۹۹۴ را می‌خواند): ایجنت
مترجمِ دستگاهی است که خودش نمی‌تواند حرف بزند. کد اینجا کاملاً تازه است و
دستگاه و پروتکل دیگری را پیاده می‌کند — چیزی کپی نشده.

**چرا امن است؟** نوشتن روی دستگاه (مثلاً تغییر فاصلهٔ ارسال داده) بدون پرچم
`--confirm` رد می‌شود، و راهنما می‌گوید ایجنت باید اول از انسان بپرسد. هر
فریم چکسام دارد؛ فریم خراب گزارش نمی‌شود. هر جلسه لاگ JSONL می‌سازد.

**شروع سریع:**

```bash
python -m bridge read --demo
python -m bridge live --demo --seconds 12 --interval 5 --log session.jsonl
python -m bridge log session.jsonl
```
