"""The grace period: a deviation is healed only once it persists (board H, part H2;
docs/HEAL_TO_INTENT.md section 4 step 1, section 6 guard 8, and N1). PURE: it judges reads it
is given and reads nothing.

**The rule (N1).** Two reads of the device at least the grace period apart (``heal_grace_seconds``:
900 s by default, 120 s on a network marked lab, `policy.LAB_DEFAULTS`), both departed from its
golden with THE SAME departure (`drift_check.departure`, a fingerprint of the masked differing
lines), and no outside change between them. That is IBN_DESIGN section 3's grace period and
PHASE8_PLAN section 7's "2 readings and 15 minutes".

**An outside change restarts it.** A configuration-change line from outside Mercury (or one
whose author cannot be known, `attribution.UNKNOWN`) at time *c* makes every read before *c* a
read of a state that no longer stands: only reads after the newest such change count, so the
first of the two reads is the first read after it. A second read whose departure differs from
the first (a change no line reported, as when the device's logging host itself was removed)
restarts it the same way, from that read.

**What a read can say.** ``drifted`` (with its departure), ``clean`` (at its golden),
``skipped`` (it could not be checked: no golden saved, or one refused, said), or ``error`` (the
read could not be made, said). A clean or skipped read settles at once: there is no deviation to
wait out, and what follows (nothing to heal, or a can't-fix) is the decision's (H3). An error
neither passes nor fails (CLAUDE.md, "an unreadable read neither passes nor fails"): it is read
again after `RETRY_SECONDS`, and after `READ_ATTEMPTS` errors in a row it settles as
``unreadable``, every error named.
"""

#: Errors in a row before a device settles as unreadable: three reads a minute apart outlast a
#: session refused while another operation held it, and a device down is then said, not waited
#: on for ever.
READ_ATTEMPTS = 3
#: The wait before a read that failed is tried again.
RETRY_SECONDS = 60

#: What `judge` answers. ``need_read`` and ``waiting`` keep the incident watching; the others
#: settle it, ready for the decision (H3).
WAITING_STATES = ("need_read", "waiting")
SETTLED_STATES = ("persisted", "at_golden", "not_checkable", "unreadable")


def _s(seconds: float) -> str:
    return f"{int(round(seconds))} s"


def _iso(epoch) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch or 0)))


def _same(a: dict, b: dict) -> tuple:
    """``(same, how)``: do two drifted reads hold the same departure? By fingerprint where both
    carry one, else by the count of differing lines, said."""
    if a.get("departure") and b.get("departure"):
        return a["departure"] == b["departure"], (
            f"the same departure ({b['departure']})" if a["departure"] == b["departure"] else
            f"a different departure ({a['departure']} then {b['departure']})")
    same = a.get("changed_lines") == b.get("changed_lines")
    return same, (f"{'the same' if same else 'a different'} count of differing lines "
                  f"({a.get('changed_lines')} then {b.get('changed_lines')}; a read carried no "
                  "departure fingerprint)")


def judge(reads: list, changes: list, grace_seconds: float, now: float) -> dict:
    """The grace period's state for one device: ``{"state", "due_at", "words", "first",
    "second", "operands"}``.

    *reads*: the device's reads, oldest first, each ``{"epoch", "state", "departure",
    "changed_lines", "error"}``. *changes*: the receive times of the configuration-change lines
    from outside Mercury (or of unknown author) on the device. *state* is one of
    `WAITING_STATES` (``due_at``: when the next read is due) or `SETTLED_STATES`; *first* and
    *second* are the reads it judged by (indexes into *reads*), where it judged by two."""
    grace = float(grace_seconds)
    last_change = max((float(c) for c in changes or []), default=None)
    usable = [(i, r) for i, r in enumerate(reads or [])
              if last_change is None or float(r.get("epoch") or 0) > last_change]
    operands = {"grace_seconds": int(grace), "reads": len(reads or []),
                "last_outside_change": last_change}
    after = (f"after the outside change at {_iso(last_change)}" if last_change is not None
             else "")
    if not usable:
        why = (f"every read so far was before the outside change at {_iso(last_change)}, so a "
               "read after it is due now" if reads else "no read yet, so the first is due now")
        return {"state": "need_read", "due_at": now, "first": None, "second": None,
                "operands": operands, "words": why}
    i_new, newest = usable[-1]
    if newest.get("state") == "clean":
        return {"state": "at_golden", "due_at": None, "first": i_new, "second": None,
                "operands": operands,
                "words": "the read found the device at its golden: nothing departed"}
    if newest.get("state") == "skipped":
        return {"state": "not_checkable", "due_at": None, "first": i_new, "second": None,
                "operands": operands,
                "words": f"the device could not be checked: {newest.get('error') or '?'}"}
    if newest.get("state") != "drifted":
        errors = []
        for _i, r in reversed(usable):
            if r.get("state") not in ("error", "busy"):
                break
            if r.get("state") == "error":
                errors.append(r)
        if len(errors) >= READ_ATTEMPTS:
            return {"state": "unreadable", "due_at": None, "first": None, "second": None,
                    "operands": operands,
                    "words": (f"{len(errors)} reads in a row could not be made: "
                              + "; ".join(r.get("error") or "?" for r in reversed(errors)))}
        due = float(newest.get("epoch") or now) + RETRY_SECONDS
        return {"state": "need_read", "due_at": due, "first": None, "second": None,
                "operands": operands,
                "words": (f"the last read could not be made ({newest.get('error') or '?'}): an "
                          f"unreadable read neither passes nor fails, and it is read again "
                          f"{_s(RETRY_SECONDS)} after it")}
    # The first read of the run of drifted reads holding the newest one's departure, errors
    # between them skipped (they say nothing of the device's state).
    i_first, how = i_new, ""
    for i, r in reversed(usable[:-1]):
        if r.get("state") in ("error", "busy"):
            continue
        if r.get("state") != "drifted":
            break
        same, how_ = _same(r, newest)
        if not same:
            how = how_
            break
        i_first = i
    first = reads[i_first]
    apart = float(newest.get("epoch") or 0) - float(first.get("epoch") or 0)
    operands.update(first_at=first.get("epoch"), second_at=newest.get("epoch"),
                    apart_seconds=int(apart), departure=newest.get("departure", ""))
    if i_first != i_new and apart >= grace:
        words = _same(first, newest)[1]
        return {"state": "persisted", "due_at": None, "first": i_first, "second": i_new,
                "operands": operands,
                "words": (f"two reads {_s(apart)} apart (at least {_s(grace)}), {words}, and no "
                          f"outside change between them{' (' + after + ')' if after else ''}")}
    due = float(first.get("epoch") or now) + grace
    restarted = (f"; it restarted at the read at {_iso(newest.get('epoch'))}: {how}" if how
                 else "")
    return {"state": "waiting", "due_at": due, "first": i_first, "second": None,
            "operands": operands,
            "words": (f"departed at the read at {_iso(first.get('epoch'))}; a second "
                      f"read at least {_s(grace)} after it is due at {_iso(due)}{restarted}")}
