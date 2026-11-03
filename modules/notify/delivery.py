"""Sending to a team's destinations, the delivery log, and a last failure raised
(docs/HEAL_TO_INTENT.md section 10, "Delivery").

- **The log:** each attempt is a row (``notify_deliveries.jsonl``, owner-only, appended under
  its cross-process lock): its channel, recipient masked to its domain (a webhook to its
  host), event, incident, outcome and error, masked, and how long it took. Never a message's
  text, a code or a secret. History draws it, kind **notification**.
- **Retries:** an incident event is tried `ATTEMPTS` times, `RETRY_WAIT_S` apart; a refusal
  (the relay not set, a TLS rule, a secret not set) is not retried, because trying again
  cannot change it. A test send and a code are tried once: a person is waiting for the
  answer, which they read in place.
- **A last failure** is kept on the destination (`teams.note_outcome`), which Needs
  attention's `notify`/`failed` row reads; the next send to it that succeeds clears it.

Who receives an incident's events, and which events notify on a network, are the heal
policy's (`heal_notify_*`, H1): `deliver_event` is handed the event and the teams.
"""

import logging
import os
import secrets
import time

from modules import filestore
from modules.notify import addresses, message, relay, teams, webhook

log = logging.getLogger(__name__)

#: The record's store name (a line store kept once for the installation, on its file).
STORE = "notify_deliveries"
#: Attempts of an incident event to one destination (section 10: "Retries: three").
ATTEMPTS = 3
#: One attempt's bound, and the wait between attempts. UNMEASURED: no relay or receiver send
#: was measured in the build (no real mail; the tests use fakes). Python's own SMTP default is
#: none at all; 30 s is a placeholder that stops a hung relay holding a heal's job. Each row
#: keeps the attempt's `duration_s`, so the first walk's Test sends measure it, and this
#: becomes about 2.5 times that (CLAUDE.md's bound rule).
SEND_TIMEOUT_S = 30.0
RETRY_WAIT_S = SEND_TIMEOUT_S
#: What waits between attempts, a module attribute so a test does not sleep.
SLEEP = time.sleep
ANNOUNCER = "notify"
ANNOUNCE_KEYS = ("notifications",)


def _path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, "notify_deliveries.jsonl")


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def record(row: dict) -> bool:
    """Append one attempt's row. Never raises: a record that cannot be kept is logged loudly
    and said on the answer (``recorded``); the send it records has happened either way."""
    from modules import records_migrate
    try:
        records_migrate.store_append(STORE, _path(), row)
        return True
    except OSError as exc:
        log.error("notify: COULD NOT RECORD delivery %s attempt %s (%s)", row.get("id"),
                  row.get("attempt"), exc)
        return False


def read_log() -> dict:
    """Every attempt, newest first: ``{"state": "ok"|"absent"|"unreadable", "rows",
    "error"}``."""
    from modules import records_migrate
    got = records_migrate.store_rows(STORE, _path(), skip_unparsable=True)
    return dict(got, rows=list(reversed(got["rows"])))


def sent_before(incident: str) -> bool:
    """Whether a message about *incident* was sent already: its next one threads under it."""
    return any(r.get("incident") == incident and r.get("outcome") == "sent"
               for r in read_log()["rows"])


def recipient(dest: dict) -> str:
    """A destination as the log keeps it: an address masked to its domain, a webhook its
    host (a URL's path may be a receiver's token)."""
    if dest.get("channel") == "email":
        return addresses.email_domain(dest.get("address", ""))
    return addresses.url_host(dest.get("url", ""))


def _send_once(dest: dict, facts: dict, *, first: bool, token: str) -> None:
    if dest.get("channel") == "email":
        cfg = relay.config()
        relay.send(relay.build(facts, dest.get("address", ""), cfg, first=first, token=token),
                   cfg, timeout=SEND_TIMEOUT_S)
    elif dest.get("channel") == "webhook":
        webhook.send(dest, message.payload(facts), event=facts["event"],
                     timeout=SEND_TIMEOUT_S)
    else:
        raise ValueError(f"channel {dest.get('channel')!r} is not one of {teams.CHANNELS}")


def _error(exc: BaseException) -> str:
    """An error as the log and the row keep it: its type and first line, masked (a relay's
    answer can quote what it was sent)."""
    first = (str(exc).strip().splitlines() or [""])[0][:300]
    return message.mask(f"{type(exc).__name__}: {first}" if first else type(exc).__name__)


def send_to(team_id: str, team_name: str, dest_id: str, dest: dict, facts: dict, *,
            first: bool, attempts: int = ATTEMPTS, by: str = "") -> dict:
    """Send *facts* to one destination, *attempts* times at most, each attempt a row; the
    last outcome kept on the destination. ``{"id", "outcome", "error", "attempts"}``."""
    delivery = "d-" + secrets.token_hex(8)
    token = secrets.token_hex(4)
    base = {"id": delivery, "channel": dest.get("channel", ""), "team": team_id,
            "team_name": team_name, "destination": dest_id, "recipient": recipient(dest),
            "event": facts["event"], "incident": facts["incident"],
            "network": facts.get("network", ""), "device": facts.get("device", ""),
            "of": attempts, "by": by}
    outcome, error, n = "failed", "", 0
    for n in range(1, attempts + 1):
        started = time.monotonic()
        try:
            _send_once(dest, facts, first=first, token=token)
            outcome, error = "sent", ""
        except ValueError as exc:
            # A refusal: the settings, an address, a secret not set, a message carrying one.
            outcome, error = "refused", _error(exc)
        except OSError as exc:
            # smtplib's, ssl's and requests' errors are all OSError: the relay or the
            # receiver did not take it this time.
            outcome, error = "failed", _error(exc)
        final = outcome != "failed" or n == attempts
        row = dict(base, at=_iso(time.time()), attempt=n, outcome=outcome, error=error,
                   final=final, duration_s=round(time.monotonic() - started, 3))
        recorded = record(row)
        if final:
            teams.note_outcome(team_id, dest_id, {"outcome": outcome, "at": row["at"],
                                                  "delivery": delivery, "error": error,
                                                  "event": facts["event"]})
            break
        SLEEP(RETRY_WAIT_S)
    log.info("notify: %s %s to %s (%s): %s after %d attempt(s)%s", facts["event"],
             facts["incident"], recipient(dest), dest.get("channel"), outcome, n,
             "" if recorded else "; NOT RECORDED")
    return {"id": delivery, "outcome": outcome, "error": error, "attempts": n,
            "recorded": recorded}


def announce() -> None:
    """Tell open pages the delivery record moved. A process with no socket (a job's own, a
    CLI) has no page to tell: its next read finds it."""
    from modules import invalidation
    try:
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER)
    except RuntimeError as exc:
        log.debug("notify: not announced (%s)", exc)


def deliver_event(event: dict, team_ids) -> dict:
    """Send one incident event to every verified, enabled destination of the named teams,
    one message per destination. ``{"ok", "sent", "failed", "deliveries", "error"}``: *ok*
    when every destination took it (none configured is ok, and sends nothing)."""
    facts = message.check_event(event)
    if facts["event"] in ("test", "verification"):
        raise ValueError(f"a {facts['event']} is sent by its own call, never as an event")
    try:
        dests = teams.deliverable(team_ids)
    except filestore.StoreUnreadable as exc:
        log.error("notify: %s; nothing sent for %s", exc, facts["incident"])
        return {"ok": False, "sent": 0, "failed": 0, "deliveries": [], "error": str(exc)}
    first = not sent_before(facts["incident"]) if dests else True
    out = [dict(send_to(t, name, d, dest, facts, first=first), destination=d)
           for t, name, d, dest in dests]
    if out:
        announce()
    sent = sum(1 for o in out if o["outcome"] == "sent")
    return {"ok": sent == len(out), "sent": sent, "failed": len(out) - sent,
            "deliveries": out, "error": ""}


def _one(team_id: str, dest_id: str) -> tuple:
    got = teams.read()
    if got["state"] == "unreadable":
        raise teams.Refused(f"the teams store could not be read: {got['error']}")
    team = got["teams"].get(team_id)
    if team is None or dest_id not in (team.get("destinations") or {}):
        raise teams.Refused(f"no destination {dest_id!r} in team {team_id!r}")
    return team.get("name", ""), team["destinations"][dest_id]


def send_test(team_id: str, dest_id: str, *, by: str) -> dict:
    """Send a test message to one destination, verified or not and on or off, once: the
    person reads its outcome in place, and the log keeps it with who asked."""
    if not by:
        raise teams.Refused("a test send names the person who asked for it")
    name, dest = _one(team_id, dest_id)
    facts = message.check_event({
        "incident": f"test-{secrets.token_hex(4)}", "event": "test",
        "outcome": "A test send from Mercury: this channel delivers.",
        "todo": "Nothing is wrong. Incident notices come here once this destination is "
                "verified and on."})
    got = send_to(team_id, name, dest_id, dest, facts, first=True, attempts=1, by=by)
    announce()
    return dict(got, ok=got["outcome"] == "sent")


def send_code(team_id: str, dest_id: str, *, by: str) -> dict:
    """Send a new verification code to one destination, once; the code itself is in the
    message only, never in the log, the store or the answer."""
    if not by:
        raise teams.Refused("a verification code names the person who asked for it")
    name, dest = _one(team_id, dest_id)
    code = teams.issue_code(team_id, dest_id, by=by)
    minutes = teams.CODE_TTL_S // 60
    facts = message.check_event({
        "incident": f"verify-{secrets.token_hex(4)}", "event": "verification",
        "outcome": f"Mercury verification code: {code}",
        "todo": f"Type this code in Mercury, where this destination was added, within "
                f"{minutes} minutes. If nobody asked for it, ignore this message."})
    got = send_to(team_id, name, dest_id, dest, facts, first=True, attempts=1, by=by)
    announce()
    return dict(got, ok=got["outcome"] == "sent", expires_in_s=teams.CODE_TTL_S)


def confirm_code(team_id: str, dest_id: str, code: str, *, by: str) -> dict:
    """A typed code checked (`teams.confirm_code`); a verified destination announced."""
    got = teams.confirm_code(team_id, dest_id, code, by=by)
    if got["ok"]:
        announce()
    return got
