# Session transcripts

What the channel held for each command, read on the NMAS host on 2026-10-01
through the tool's own `open_ssh()` (read-only, allowlisted `show` commands
only), all nine devices at once as the hourly startup check reads them. One
file per device and command: everything read from the moment the command was
written until the device's prompt returned after its echo.

- `r1/`: a C8000v (IOS-XE 17.6), `cisco_ios` in Netmiko.
- `s1/`: a vIOS-L2 switch, `cisco_ios` in Netmiko.

The `show startup-config` files begin with the prompts the login left in the
channel (`\nr1#\nr1#\nr1#\nr1#`) BEFORE the command's echo, exactly as read.
They are why a read that ends on the prompt alone is wrong: it is answered by
one of those.

Four edits, and nothing else (the same as the fleet fixtures'):

- Secrets are masked by `redact_text()` (`<redacted:...>`), as every stored
  capture here is.
- The emulator's `10.0.0.x` addresses (vrnetlab's management network and the
  NMAS host's ACL entry) are rewritten to `192.0.2.x`, the documentation range,
  because the repository is public (CLAUDE.md, Conventions).
- The chassis serial (`license udi ... sn`) reads `9XXXXXXXXXX`.
- `snmp-server contact` reads `noc`.
- Cisco's own call-home address stays, excused by name in
  `tests/publication_exemptions.py`.

The timings measured in the same run (echo and prompt per command, every
device at once and then one at a time) are in register C281.
`tests/test_session_reads_wait_for_the_device.py` replays these through real
Netmiko.
