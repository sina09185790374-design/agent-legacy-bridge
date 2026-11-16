# Demo session (real output)

Every command below was run against the built-in demo device (`--demo`,
seed 7 — the weather is reproducible). No hardware involved.

```console
$ python -m bridge check-spec
spec OK: WS-90 — 7 parameters, 6 fault codes

$ python -m bridge read --demo
BATT          12.5 V
HUM_OUT       45.2 %
PRESS       1013.0 hPa
RAIN_TOT      1.23 mm
TEMP_OUT      23.4 C
WIND_DIR     270.0 deg
WIND_SPD       4.2 km/h

$ python -m bridge faults --demo
No active faults (F00).

$ python -m bridge selftest --demo
self-test: PASS

$ python -m bridge live --demo --seconds 11 --interval 5 --log session.jsonl
BATT=12.5V  HUM_OUT=45.2%  PRESS=1013.0hPa  RAIN_TOT=1.23mm  TEMP_OUT=23.4C  WIND_DIR=270.0deg  WIND_SPD=4.2km/h
BATT=12.56V  HUM_OUT=44.9%  PRESS=1013.2hPa  RAIN_TOT=1.23mm  TEMP_OUT=23.4C  WIND_DIR=263.0deg  WIND_SPD=4.4km/h
BATT=12.49V  HUM_OUT=44.9%  PRESS=1011.9hPa  RAIN_TOT=1.23mm  TEMP_OUT=23.0C  WIND_DIR=271.0deg  WIND_SPD=4.0km/h
received 3 live frame(s) in 11.0s

$ python -m bridge log session.jsonl
session.jsonl: 3 frame(s)
  BATT: min 12.49  max 12.56  mean 12.52  (3 samples)
  HUM_OUT: min 44.9  max 45.2  mean 45.0  (3 samples)
  PRESS: min 1011.9  max 1013.2  mean 1012.7  (3 samples)
  RAIN_TOT: min 1.23  max 1.23  mean 1.23  (3 samples)
  TEMP_OUT: min 23.0  max 23.4  mean 23.27  (3 samples)
  WIND_DIR: min 263.0  max 271.0  mean 268.0  (3 samples)
  WIND_SPD: min 4.0  max 4.4  mean 4.2  (3 samples)

$ python -m bridge set-interval 30 --demo   # no --confirm
refused: set-interval changes device state: re-run with --confirm after a human approves it
exit=2
```

Try the unhappy path — inject a fault and watch the agent's playbook work:

```console
$ python -m bridge faults --demo --fault F02
F02  Low battery

$ python -m bridge selftest --demo --fault F02
self-test: FAIL
  F02  Low battery
```
