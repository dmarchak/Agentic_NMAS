"""A device's configuration, read so it can be TRUSTED, and checked before
anything records it (the operator, 2026-10-01).

r2's capture for Save All held its running config, then ``r2#show
running-config``, then the whole config a second time, and the gate said
"device read: pass". Measured in the host's log: the prompt-based read raised
"Pattern not detected: 'r2\\#'" at its 60 s read timeout, and
``commands.run_device_command`` retried with ``send_command_timing`` ON THE
SAME SESSION. The first command's output was still arriving, so the retry read
it, then the prompt and the echoed second command, then the second output.
The intent comparison caught it by luck; a device with no committed intent
would have had the stitched text recorded as its golden.

Two halves, one module:

* ``read()`` sends ONE ``show running-config`` and waits for its prompt, with
  the deploy path's configured bound (``nsot_config_read_timeout``) and NO
  fallback: a read that does not finish is a failed read, never a second
  command on a channel still carrying the first one's output.
* ``problems()`` judges any text before it is recorded or compared: one
  configuration, ending in one ``end``; no prompt line and no echoed command;
  a ``hostname`` line naming the device; and, where a previous golden is
  known, a size that is not a multiple of it. ``save_golden`` runs the same
  judgement on every path that records, so a caller that forgets is refused
  anyway.

Calibrated on the host's whole golden history (2026-10-01, 73 distinct blobs
across every list): no genuine golden holds a prompt-shaped line or a second
``end``, and the largest step in size between two versions of one device was
1.05x, where a stitched read is about 2x.
"""

import logging
import re

log = logging.getLogger(__name__)

#: What a person reads when a capture is refused (the operator's words).
UNRELIABLE = "the device's output could not be read reliably"

#: A prompt at the start of a line: ``r2#``, ``r2>``, ``r2(config)#``.
PROMPT = re.compile(r"^[A-Za-z0-9._-]+(\([^)]*\))?[#>]")
#: A command echoed after a prompt.
ECHO = re.compile(r"^[A-Za-z0-9._-]+(\([^)]*\))?[#>]\s*(sh|show|more|term|terminal)\b", re.I)

#: A capture this many times its previous golden's size is not a change, it
#: is two configurations (the largest real step measured: 1.05x; a stitched
#: read: about 2x). Only judged against a previous golden of at least
#: SIZE_FLOOR lines, so a two-line fragment from before the shrink guard
#: (r1 and r2, 2026-09-21) does not make every later capture "too large".
SIZE_RATIO = 1.6
SIZE_FLOOR = 20


class UnreliableRead(Exception):
    """A device's output that cannot be trusted as one configuration."""

    def __init__(self, hostname: str, reasons: list):
        self.hostname, self.reasons = hostname, list(reasons)
        super().__init__(f"{hostname}: {UNRELIABLE}: " + "; ".join(reasons))


def _body(text: str) -> list:
    """The configuration's lines, without the golden file's own header."""
    return [l for l in (text or "").splitlines()
            if l.strip() and not l.startswith("! Golden config")]


def problems(text: str, hostname: str, previous: str = None, strict: bool = True) -> list:
    """Why *text* is not one configuration of *hostname*, or ``[]``.

    *previous*, when given, is the device's committed golden: a capture far
    larger than it is two configurations, not a change.

    *strict* (a device's output, read now) also requires what every real
    `show running-config` has: exactly one `end`, last, and a `hostname`
    line. ``save_golden`` judges with ``strict=False``: it refuses on
    EVIDENCE of a stitched or foreign text (a second `end`, a prompt, an
    echoed command, another device's hostname, a multiple of the size), and
    leaves presence to the reader that produced the text."""
    lines = (text or "").splitlines()
    out = []
    body = _body(text)
    if not body:
        return ["the device returned nothing"] if strict else []
    ends = sum(1 for l in lines if l == "end")
    if ends > 1:
        out.append(f"it holds {ends} `end` lines where one configuration has one "
                   "(a second configuration follows the first)")
    elif strict and ends == 0:
        out.append("it holds no `end` line: the configuration did not arrive whole")
    elif strict and body[-1] != "end":
        out.append(f"it does not end with `end`: its last line is {body[-1][:60]!r}")
    prompts = [l for l in lines if PROMPT.match(l)]
    if prompts:
        out.append(f"it holds {len(prompts)} device prompt line(s), the first "
                   f"{prompts[0][:60]!r}")
    echoed = [l for l in lines if ECHO.match(l)]
    if echoed:
        out.append(f"it holds {len(echoed)} echoed command(s)")
    names = [l.split()[1] for l in lines if l.startswith("hostname ") and len(l.split()) > 1]
    if len(names) > 1 or (strict and not names):
        out.append(f"it holds {len(names)} `hostname` lines where one configuration has one")
    elif strict and hostname and names[0].lower() != hostname.lower():
        # Read time only: a device renamed ON THE DEVICE before Refresh
        # Hostnames records its rename is this shape at save time, and the
        # read that produced the text has already been asked.
        out.append(f"its hostname is {names[0]!r}, not {hostname!r}")
    if previous:
        before = len(_body(previous))
        if before >= SIZE_FLOOR and len(body) > SIZE_RATIO * before:
            out.append(f"it is {len(body)} lines against {before} in the committed golden "
                       f"({len(body) / before:.1f}x; a real change has never passed "
                       f"1.05x here)")
    return out


def check(text: str, hostname: str, previous: str = None, strict: bool = True) -> str:
    """*text* if it is one configuration of *hostname*, else raise
    ``UnreliableRead`` naming every reason."""
    got = problems(text, hostname, previous, strict)
    if got:
        log.error("config_read: %s: %s: %s", hostname, UNRELIABLE, "; ".join(got))
        raise UnreliableRead(hostname, got)
    return text


def read_timeout() -> int:
    """The deploy path's bound for a config read (`nsot_config_read_timeout`,
    120 s by default: `write memory` leaves an emulated device slow for tens of
    seconds, measured), never the 60 s the stitched read ran out of."""
    try:
        from modules.settings_schema import get_setting
        return int(get_setting("nsot_config_read_timeout") or 120)
    except Exception:                                   # noqa: BLE001
        return 120


def read(conn, hostname: str, previous: str = None, timeout: int = None) -> str:
    """ONE ``show running-config`` on *conn*, waited for, checked, returned.

    No fallback: a read that does not see its prompt within the bound raises,
    and nothing is sent again on that session (a second command on a channel
    still carrying the first one's output is what stitched r2's capture)."""
    text = conn.send_command("show running-config", read_timeout=timeout or read_timeout(),
                             strip_prompt=True, strip_command=True)
    return check((text or "").lstrip("\x00"), hostname, previous)
