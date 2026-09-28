"""Reload one device: SEND, READ, DECIDE, and success is the session DROPPING.

Bulk reload sent `reload`, then a newline to whatever the device asked, then
waited for output, and a reloading device produces none. So a reload that
worked sat at "Executing..." until the session timed out, and would then have
been drawn FAILED: the inverse of C152 in the same screen (the operator,
R1, 2026-09-28). For every other command success is output; for reload it
is the session going away after the device accepted.

B13's rule, applied: a line is sent only in answer to the prompt that asks
for it, never on a timer.
- `[confirm]`: confirm, then success is the session dropping within the
  window, and the result says the drop was seen, never that the device came
  back (nothing here checks that).
- `Save? [yes/no]`: REFUSED. Saving writes a running config nobody approved
  over the startup config, and answering no loses the change: a person's
  decision, not this tool's. The prompt is abandoned with Ctrl-C.
- Anything else: refused, the prompt named (masked), and abandoned.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

_CONFIRM = re.compile(r"\[confirm\]\s*$", re.I)
_SAVE = re.compile(r"save\?\s*\[yes/no\]", re.I)

#: How long after the confirmation the session must drop. PROVISIONAL: never
#: measured. A C8000v closes the session within seconds of confirming, by the
#: operator's reports, and every result carries the drop time actually seen,
#: so the first real reloads measure it (re-derive the bound from them).
DROP_WINDOW_SECONDS = 30.0


def _last_line(text: str) -> str:
    lines = [l for l in str(text or "").splitlines() if l.strip()]
    return lines[-1].strip() if lines else ""


def _abandon(conn) -> None:
    try:
        conn.write_channel("\x03")
    except Exception:                          # noqa: BLE001
        pass


def reload_device(conn, *, drop_window: float = DROP_WINDOW_SECONDS, poll: float = 0.5,
                  clock=time.monotonic, sleep=time.sleep) -> dict:
    """``{"ok", "outcome", "detail", "dropped_after"}`` for one held session.

    *outcome* is ``reloading`` (confirmed, and the session dropped),
    ``refused_unsaved``, ``unexpected_prompt`` or ``not_dropped``.
    """
    from modules.redact import redact_text

    asked = conn.send_command_timing("reload", strip_prompt=False, strip_command=False,
                                     read_timeout=20) or ""
    if _SAVE.search(asked):
        _abandon(conn)
        return {"ok": False, "outcome": "refused_unsaved", "dropped_after": None,
                "detail": ("REFUSED, not reloaded: the device has configuration changes "
                           "that are not saved to startup, and asked whether to save them. "
                           "Saving would write a running config nobody approved over the "
                           "startup config; answering no would lose the change. That is a "
                           "person's decision, so the prompt was abandoned with Ctrl-C. "
                           "Save the device's config, or discard the change, then reload.")}
    tail = _last_line(asked)
    if not _CONFIRM.search(tail):
        _abandon(conn)
        return {"ok": False, "outcome": "unexpected_prompt", "dropped_after": None,
                "detail": (f"REFUSED, not reloaded: the device answered `reload` with "
                           f"{redact_text(tail)!r}, a prompt this tool does not handle, so "
                           "nothing was confirmed and the prompt was abandoned with Ctrl-C.")}

    conn.write_channel("\n")
    start = clock()
    while clock() - start < drop_window:
        try:
            if not conn.is_alive():
                break
            conn.read_channel()
        except Exception:                      # noqa: BLE001  (the transport closing IS the answer)
            break
        sleep(poll)
    else:
        return {"ok": False, "outcome": "not_dropped", "dropped_after": None,
                "detail": (f"the device confirmed the reload, but the session was still up "
                           f"{drop_window:.0f} s later: whether it is reloading is unknown. "
                           "Check its console before doing anything else to it.")}
    after = clock() - start
    log.info("reload: confirmed, session dropped after %.1f s", after)
    return {"ok": True, "outcome": "reloading", "dropped_after": round(after, 1),
            "detail": (f"reload confirmed at the device's [confirm] prompt, and the session "
                       f"dropped {after:.0f} s later, as a reload does. Nothing here checks "
                       "that the device came back up.")}
