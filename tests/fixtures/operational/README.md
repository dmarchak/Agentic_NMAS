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

**Taking more:** `scripts/nmas-capture-output` is this probe as a tool
(its docstring states what it guarantees). Captures of the second sweep
(OSPF detail, CDP, LLDP, `show ip ospf`, connected routes, `show ip
interface`) were added the same day by a probe that also ran each module's
own parser on the host.

## The Tier 2 probe's captures (2026-10-08)

`scripts/nmas-tier2-probe`, run by the operator on r2 (IOS-XE) and s1 (vIOS-L2) at 17:42 and
17:43 UTC, SENT Tier 2 commands (docs/NSOT_TIER2_PRIVILEGED.md section 5): `clear counters
Loopback0`, `clear arp-cache interface <a data interface>`, `clear logging`, `undebug all`, each
`[confirm]` answered with Enter. Every read passed through `redact_text` on the host. Copied from
its records byte for byte:

- `<host>__show_debugging.txt`: `show debugging` with no debug on. s1 prints nothing; r2 prints
  IOS-XE's conditional-debug and packet-tracing headers, which are not debugs;
- `<host>__show_interfaces_Loopback0.txt` and `…__after_clear_counters.txt`: the counters, and
  `Last clearing of "show interface" counters` going from `never` to `00:00:05` (r2), `00:00:02`
  (s1);
- `<host>__show_logging__after_clear_logging.txt`: the buffer EMPTY after the clear (nothing
  after `Log Buffer (… bytes):`), while `messages logged` keeps counting: it is not reset;
- `../tier2/r2__clear_counters_Loopback0.txt`, `r2__clear_logging.txt`, `r2__undebug_all.txt`: what each
  command printed before any answer (in `tests/fixtures/tier2/`: a send's output echoes the command
  and ends at the prompt, so it is not a read, which every file here is). Both platforms asked the same two prompts,
  `Clear "show interface" counters on this interface [confirm]` and
  `Clear logging buffer [confirm]`; `clear arp-cache interface` and `undebug all` asked nothing.

Measured beside them: the ARP entries were all back at the first read after the clear (2 of 2,
3 of 3: "back after 0 s" at the probe's one-second resolution).
