# Real device output, captured read-only

Captured 2026-09-27 from the live fleet by a read-only probe run on the NMAS
host. The probe used a `git archive` copy of the code at `eecc900`, never the
live checkout, with bytecode writes off, and the checkout and `data/` were
unchanged afterwards. Only `show` commands were sent, through the pipeline's
own reader (`run_device_command`) on a fresh connection per device. Every
output passed through `redact_text` before leaving the host, and none carried
a masked value.

One file per device and command: `<host>__<command slug>.txt`, byte for byte
as the device printed it.
- r3 is IOS-XE 17.6.1a (C8000v); r1 the same platform;
- s1 and s3 are vIOS-L2 15.2.

**These exist because a hand-written sample is how C62 to C66 survived.**
Anyone writing a `show ip bgp summary` from memory writes eight columns,
and the device prints ten. Anyone writing `show ip protocols` from memory
leaves out the `"application"` pseudo-protocol that both platforms print
first. A parser's test is built from files in this directory, never from a
sample typed into the test (D4's rule).

Measured with them, beyond the parsers:
- **Only the first `|` is an output modifier on both platforms.**
  `show version | include Cisco | count` and `… include Cisco|count` both
  print the matching lines, not a count. The text after a filter is its
  regular expression.
- **`% Invalid input detected at '^' marker.`** is what both platforms
  print for an unknown command (`show foobar`).
