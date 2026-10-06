# Stress test results (2026-10-06, Linux container, Python 3.13, RetroArch 1.18)

Scripts are not in the repo; `tests/test_stress.py` keeps a small CI-sized version of the
lobby load test. Everything below ran against the real server and real RetroArch.

## Lobby server (TCP, newline JSON)

* 100 rooms created in parallel, each: host + 1 player + 6 on the waiting list (one given
  priority), 3 poll rounds per waiter, kick, priority waiter admitted, roster check,
  validate, ready, encrypted endpoint published and read back.
  **4,100 requests in 0.6 s (about 6,500 req/s), p50 13 ms, p99 34 ms, 0 errors.**
* Session cap enforced (129th room refused).
* Junk input (non-JSON, 5 KB of `{`, unknown operation, empty line, 300 KB line): server
  stayed up.
* Stop with 128 live rooms, restart: all 128 resumed from the snapshot.

## Launcher UI server (loopback HTTP)

* 20 clients hammering library/pads/engines/settings/ping: **2,500 calls in 3.5 s
  (about 720 req/s), p50 24 ms, max 177 ms, 0 dropped connections** after raising the
  listen backlog to 64 (before that fix, bursts of 20+ simultaneous requests occasionally
  got a connection reset).
* Wrong token 403, unknown action 404, 100 KB body 413, path traversal 404, foreign
  Host header 403.
* Bursts of 50/100/200 simultaneous connections: all answered.

## Encrypted match tunnel (TLS 1.2 PSK)

* 67 MB round trip: **260-315 MB/s** on loopback.
* 50 parallel connections x 120 ping-pongs (netplay-sized packets): all correct in 1.5 s.
* 100 wrong-key connection attempts: refused, good connections unaffected.

## Real RetroArch netplay through the tunnel

* 1 host + 3 guests (4 players) on the Nestopia core, managed save folders via
  `--appendconfig`, 60-second soak: **all four stayed connected, 0 desync lines, 0 netplay
  errors**, pings 25-64 ms (tunnel + Xvfb overhead). Save directory honoured.

## Library

* 5,600 files across 8 consoles: scanned in 0.48 s; search 2 ms; cold start from cache 13 ms.

## Not stress-tested

The Windows .exe itself, real controllers, PCSX2/Dolphin/other standalone engines, and
anything over a real network (only loopback was available here).
