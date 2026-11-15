# The err-disabled port's reads (C3712, G7)

Read through Mercury on 2026-11-14 (masked by `redact_text`), on the lab's IOSvL2 switches, and
used by tests/test_errdisable.py. Each file holds the lines exactly as read; nothing is typed
from memory except where the table says so.

| File | Read | What it is |
|---|---|---|
| `s1_status_errdisabled.txt` | s1, `show interfaces status err-disabled` | the one err-disabled row, captured (the header line was not kept with it, so the parser takes rows with or without one) |
| `s1_status.txt` | s1, `show interfaces status` | the two host rows, captured: Gi1/0 err-disabled, Gi1/1 connected |
| `s1_loki_lines.txt` | s1's lines in Loki | the BPDU guard line, the err-disable line and the interface's down line, captured; kept as the message from its mnemonic on (Loki's own prefix of time and host is not part of the capture) |
| `s5_mac_table_gi03.txt` | s5, `show mac address-table interface GigabitEthernet0/3` | before any violation: its one row (Vlan 10, aabb.cc00.8007, DYNAMIC, Gi0/3) captured; **the header and the total line are IOS's standard layout around that row, not captured** |
| `s5_gi03_running.txt` | s5's running configuration, Gi0/3 | the two port-security lines in their order, captured |
| `psecure_lines_documented.txt` | **documented, not captured** | the port-security violation lines (`%PORT_SECURITY-2-PSECURE_VIOLATION`, `%PM-4-ERR_DISABLE` psecure-violation) in Cisco's documented form, with the drill's foreign MAC (aa:bb:cc:00:80:99). The trial's capture replaces this file |

Measured beside them (2026-11-14 19:5x UTC, scripts/nmas-config-read): s1, s2 and s5's goldens
hold no `errdisable recovery` line.

## The AI's err-disable reads (C3797)

Read on 2026-11-15 through Mercury's read engine (`modules.nsot.reads.run`, recorded runs on
History › Reads), masked, before the three forms joined the AI's read families
(`modules/ai/router_reads.py` `SHOW_FAMILIES`); used by tests/test_ai_engineer_reads.py. Each
file is the answer's bytes exactly (the engine's byte count beside it), with no edit.

| File | Device, read, run | What it is |
|---|---|---|
| `s2_status_errdisabled.txt` | s2, `show interfaces status err-disabled`, run `20261115T192418810135Z-9faf4ba6588244dca613218e870f9146` | the whole answer, 134 bytes: an empty first line, the header, and Gi1/0's row (bpduguard). s1's answer (run `20261115T192414088169Z-8ebe93e8575e41a28630932247a04928`) is the same bytes but its description, `h1` for `h3` |
| `s5_status_errdisabled.txt` | s5, `show interfaces status err-disabled`, run `20261115T192425538822Z-9f712a7c86594a9387005d5233e72963` | the whole answer, 0 bytes: no port err-disabled, and IOS prints nothing, not even the header |
| `s1_errdisable_recovery.txt` | s1, `show errdisable recovery`, run `20261115T192414088169Z-8ebe93e8575e41a28630932247a04928` | the whole answer, 1194 bytes: every cause's timer Disabled, the 300 s interval, no interface listed. s2's and s5's answers (their runs above) are the same bytes |
| `s1_port_security_gi10.txt` | s1, `show port-security interface GigabitEthernet1/0`, run `20261115T192414088169Z-8ebe93e8575e41a28630932247a04928` | the whole answer, 429 bytes: port security Disabled on a BPDU-guard port. s2's GigabitEthernet1/0 (its run above) is the same bytes |
| `s5_port_security_gi03.txt` | s5, `show port-security interface GigabitEthernet0/3`, run `20261115T192425538822Z-9f712a7c86594a9387005d5233e72963` | the whole answer, 427 bytes: Enabled, Secure-up, Shutdown mode, one MAC (aabb.cc00.8007 on VLAN 10), no violation |
