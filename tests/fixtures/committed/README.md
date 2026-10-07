# Committed documents, as the host holds them

Real files from the host's Default list, committed at HEAD on 2026-10-07, read through
`scripts/nmas-config-read` (every line masked by `redact_text`). Used by
`tests/test_committed_before_p1.py` (C568).

| File | Read from | What it is |
|---|---|---|
| `r2.yml` | `host_vars/r2.yml` | r2's committed intent (IOS-XE), committed before P1: no `source_interfaces` |
| `s1.yml` | `host_vars/s1.yml` | s1's committed intent (vIOS-L2), the same |
| `profile.yml` | `profiles/monitoring.yml` | the network's monitoring profile, with P1's `management` section |
| `r2.cfg` | `golden/r2.cfg` | r2's committed golden, masked |
| `s1.cfg` | `golden/s1.cfg` | s1's committed golden, masked |

**The edits, for publication, the same in every file that holds them:** each `10.0.0.x`
address is `192.0.2.x`; the SNMP contact is `noc`; r2's license serial is `9XXXXXXXXXX` (as
in `tests/fixtures/configs/fleet/`). Nothing else is changed; Cisco's call-home address is
exempted as VENDOR in `tests/publication_exemptions.py`. A golden's secret positions hold the masking's placeholders
(`<redacted:snmp_community>`, `9 <redacted:user_password>`); the test's secret lookup answers
each reference with the same placeholder, so a secret line renders equal to its golden.

**Why real files and not a fresh parse:** the suite's lab parses r2's golden with today's
parser, which emits every schema key. The host's intents were committed by an older one, and
the first render of such an intent after the schema gained a key refused every device (C568).
