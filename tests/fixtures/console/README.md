# Console fixtures (Lab 9, s5)

What s5's serial console (a vIOS-L2 switch, `vrnetlab/cisco_vios:L2-20180619`) really printed,
read on 2026-10-22 and copied here unchanged apart from two replacements made when they were
read: the switch's serial number (`<serial>`) and a contact address (`<redacted>`). They are the
console's replies in `tests/test_lab9_console_scripts.py`, which tests the two lab scripts that
talk to a console: `lab/lab9/console-reader.py` and `lab/lab9/s5-erase-session.py` (C1545).
They are also the real console text for out-of-band ZTP's session and survey tests
(`tests/test_console_session.py`, `tests/test_console_survey.py`).

- `s5-boot-to-release.txt`: s5's boot, from its boot loader's countdown to the hardware summary,
  from s5's container log (`docker logs`; the launcher logs the console while it holds it,
  before releasing it). CRLF line endings, as logged.
- `s5-pnp-stopped.txt`: the end of AutoInstall and the console becoming available, after the
  launcher released the console, from s5's one-way reader's log (`console-reader.py`), its
  chunks joined.
- `s5-session-enable-dir-nvram.txt`: the diagnostic session's transcript, as
  `s5-erase-session.py` wrote it: each `>>> send '...'` line is what the session sent, and the
  text after it, up to the next, is what the console answered (its echo, then the reply). The
  telnet negotiation bytes are the `?` run after the first send. nvram's startup file is
  0 bytes here, so the session stopped before any erase.

    sha256 4306ba009d8a00b67c090f86dc2704796d788b39d8e7b0464f65061abf97dd02  s5-boot-to-release.txt
    sha256 2e76f07e3e98edfffd6a560bb8ccd67133f649822c46d8290f224f0c996414cc  s5-pnp-stopped.txt
    sha256 c600487a80e452c73cb3b211ba78faa865dfb9231d01aa5e288f19e86bb1e2b0  s5-session-enable-dir-nvram.txt
