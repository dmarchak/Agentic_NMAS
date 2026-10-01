# CDP and LLDP on each platform: real output, captured read-only

Captured 2026-09-30 by the operator on the NMAS host, with the tool's read-only
probe (`scripts/nmas-capture-output`, every command through the shared
allowlist), for C254: what an ABSENT `cdp run` or `lldp run` means on each
platform. Copied here byte for byte (none was masked: no secret position in any
of them). The verdicts drawn from them are in
`modules/nsot/platform_defaults.json`, each naming its file here.

## set1_2026-09-30T2353Z (`show cdp`, `show cdp interface`, `show lldp`)

Files written 23:53:39 (s1), 23:53:43 (r6), 23:53:46 (r1) UTC.

- **s1 (vIOS L2, its configuration carries no `cdp run`):** CDP globally
  enabled, and running on 6 of 6 interfaces. Measured: CDP is ON by default
  on vIOS, globally and per interface.
- **r1 (C8000V, IOS-XE, its configuration carries `cdp run`):** CDP globally
  enabled, `cdp enabled interfaces : 0`. Measured: on this platform `cdp run`
  alone enables no interface; each needs `cdp enable`. It is why r1 has
  `cdp run` and an empty CDP neighbour table.
- **r6 (C8000V, IOS-XE):** NOT a measurement of a default. The app log on the
  host shows r6's deploy of the monitoring profile diffing at 23:53:34 and
  finishing its push at 23:53:49, and the program's FIRST two lines were
  `cdp run` and `lldp run` (receipt `batch-2c6148`). This capture was taken
  during that push, after those lines were most likely sent; there is no
  per-command timestamp to prove the order, so it is recorded as taken during
  the push, never as "on by default".

## set2_2026-09-30T2355Z (`show lldp interface`, `show lldp neighbors`, `show running-config | include lldp|cdp`)

Files written 23:55:31 (r6) and 23:55:58 (s3), after r6's deploy (receipt at
23:55:00).

- **r6, after the push:** `lldp run` and `cdp run` in its running
  configuration; LLDP Tx and Rx enabled on Gi1 and Gi2; 0 neighbours (r6 is its
  own containerlab, with no data-plane link to any fleet device, and the Linux
  bridges between it and s3's management link drop LLDP, as they should).
  Measured: on IOS-XE `lldp run` enables LLDP on the interfaces (unlike
  `cdp run`).
- **s3:** LLDP on every interface; neighbours s4, r1 and r3.
