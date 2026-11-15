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
