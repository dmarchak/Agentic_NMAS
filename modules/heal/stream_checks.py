"""A lost stream's checks as a command plan names them (`command_plan.NAMED_CHECKS`), for the
lost stream's ladder's later rungs (`modules/fixit/ladder.py`: the built-in plans
`telemetry-subscription-recreate` and `telemetry-stack-restart`), each answering ``(result,
words)``, result ``pass``, ``fail`` or ``unreadable`` (an unreadable read neither passes nor
fails).

**No second verify** (the review of 2026-11-16): the stream's return is judged by the
re-subscribe's own checks, combined as its verify combines them (`resubscribe.verify`):
- `resubscribe._device_check`: the receiver State Connected on a connection id that differs
  from the one read before the send (a Connected receiver is not a stream, C2890);
- for the device's ONE subscription to its receiver by intent: `resubscribe._bytes_check`, a
  NEW session, absent before the send, whose bytes received grew TWICE by at least
  `resubscribe.MIN_GROWTH_BYTES` (one growth can be gRPC's own opening);
- for a subscription sharing its receiver with another (one connection carries both, so the
  bytes cannot tell one's own): `resubscribe._stream_check` (its own series in Prometheus by
  the lost-stream alert's query) and `resubscribe._collector_check` (a new session receiving).
Every subscription in the plan's scope must pass: the one a subscription parameter names, or,
for a plan with none, EVERY subscription the device's committed intent declares.

**The baseline is taken in the precondition** (`check_read_before`): each subscription's
receiver and the collector's sessions on its receiver's port, read holding the device before
anything is sent, kept on the run (`BEFORE_ATTR`), never in its record. The checks after
compare with it; a run whose baseline was not read cannot pass.

- `check_collector_not_receiving`: the stream still lost: no ESTABLISHED session from the device
  on a receiver's port received inside the stream's window (`diagnose_stream.receiving_now`);
  a session in another state (CLOSE_WAIT, TIME_WAIT) is not the stream and is not read. A
  session receiving again (the plan's close step alone brought it back) answers
  ``not_needed``: the step passes with nothing sent (`command_plan_run.NOT_NEEDED`).
- `check_netconf_yang_on`, `check_iosxe`, `check_dmi_others`: the stack restart's own
  preconditions, from the running configuration's answer and the inventory.

Reads only: the device through the run's sources (the read engine, on the run's session),
this host's own socket tables, Prometheus, committed intent (read once per run). Sends nothing
and closes nothing.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Where a run keeps what it read before the send (on its `command_plan_run.CheckRun`).
BEFORE_ATTR = "stream_before"
#: Where a run keeps the device's committed intent and its scope, read once.
INTENT_ATTR = "stream_intent"
#: Where `_bytes_check` keeps each new session's reads across polls.
FIRST_ATTR = "stream_bytes_reads"


def _intent(run) -> tuple:
    """``(hv, why)``: the device's committed host vars, read ONCE per run (the review: never
    every device's on every poll) through `neighbours.committed_intents_of`, the device's own
    document taken even when another device's does not parse (that error is another file's)."""
    got = getattr(run, INTENT_ATTR, None)
    if got is None:
        from modules.neighbours import committed_intents_of

        intents, err = committed_intents_of(run.network)
        hv = (intents or {}).get(run.device)
        got = (hv, "" if hv else (f"{run.device}'s committed intent could not be read "
                                  f"({err})" if err else
                                  f"{run.device} has no committed intent"))
        setattr(run, INTENT_ATTR, got)
    return got


def _units(run) -> tuple:
    """``(units, sources, why)``: each subscription in the plan's scope with its receiver
    (`diagnose_stream.receiver_of`) and whether it is the device's only one to that receiver
    (``alone``, as `resubscribe.plan` decides it), and the device's addresses."""
    from modules.heal import diagnose_stream as DS

    hv, why = _intent(run)
    if why:
        return [], [], why
    declared = [(str(s.get("subscription")), DS.receiver_of(s.get("settings") or []))
                for s in hv.get("telemetry") or []
                if isinstance(s, dict) and s.get("subscription") is not None]
    if not declared:
        return [], [], f"{run.device}'s committed intent declares no telemetry subscription"
    # A recreate plan's scope is every subscription on the named one's receiver
    # (`command_plan.receiver_group`, ``<name>_each``); a plan naming none, all of them.
    d = run.derived or {}
    want = [str(s) for s in d.get("subscription_each") or []] or (
        [str(d["subscription"])] if d.get("subscription") else [])
    scope = [x for x in declared if x[0] in want] if want else declared
    if not scope:
        return [], [], (f"{run.device}'s committed intent declares no subscription "
                        f"{', '.join(want)}")
    unread = [s for s, r in declared if r.get("why")]
    if any(r.get("why") for _s, r in scope):
        s, r = next((s, r) for s, r in scope if r.get("why"))
        return [], [], f"subscription {s}'s receiver is not known: {r['why']}"
    ends = {}
    for _s, r in declared:
        if not r.get("why"):
            ends[(r["address"], r["port"])] = ends.get((r["address"], r["port"]), 0) + 1
    units = [{"sub": s, "address": r["address"], "port": r["port"],
              "alone": not unread and ends[(r["address"], r["port"])] == 1}
             for s, r in scope]
    return units, DS._addresses(hv), ""            # noqa: SLF001 (the stream module's own)


def _receiver(run, sub: str) -> dict:
    """One subscription's receiver as `resubscribe.Sources.receiver` answers it, ``{"state",
    "rows", "why"}``, read through the run's sources (the read engine, on the run's session)
    by `resubscribe.receiver_command`. A device whose platform Mercury does not know is
    unread, saying so (`platform.unknown_words`), never read as IOS-XE (C452)."""
    from modules.heal import diagnose_parse as P
    from modules.heal import resubscribe as R
    from modules.nsot.platform import platform_for_device, unknown_words

    dialect = platform_for_device(run.dev or {})
    if not dialect:
        return {"state": "unread", "rows": None,
                "why": unknown_words(dict(run.dev or {}, hostname=run.device))}
    cmd = R.receiver_command(dialect, sub)
    answer = (run.sources.read(run.device, [cmd]) or {}).get(cmd)
    if answer is None:
        return {"state": "unread", "rows": None, "why": f"`{cmd}` could not be read"}
    got = P.parse("telemetry_receiver", answer)
    if got["state"] != P.PARSED:
        return {"state": "unread", "rows": None, "why": got["why"]}
    return {"state": "read", "rows": got["facts"]["receivers"], "why": ""}


def check_read_before(_answer, run) -> tuple:
    """The baseline, before anything is sent: each subscription's receiver and the collector's
    sessions on its receiver's port (`diagnose_stream.read_collector`, the reader the
    re-subscribe's checks compare). Passes when each was read; unreadable otherwise (the
    verify could not tell a new connection or session, so nothing is sent)."""
    from modules.heal import diagnose_stream as DS

    units, src, why = _units(run)
    if why:
        return "unreadable", why
    before = {}
    for u in units:
        rcv, col = _receiver(run, u["sub"]), DS.read_collector(u["address"], u["port"], src)
        if rcv["state"] != "read":
            return "unreadable", f"subscription {u['sub']}'s receiver: {rcv['why']}"
        if col.get("state") != "read":
            return "unreadable", (f"the collector at {u['address']} port {u['port']}: "
                                  f"{col.get('why')}")
        before[u["sub"]] = {"receiver": rcv, "collector": col}
    setattr(run, BEFORE_ATTR, before)
    said = []
    for s, b in before.items():
        rows = b["receiver"]["rows"] or []
        state = ", ".join(f"{r.get('state') or '?'} on connection {r.get('connection')}"
                          for r in rows) or "no receiver"
        said.append(f"{s}: {state}; {len(b['collector'].get('sessions') or [])} collector "
                    f"session(s) from {run.device}")
    return "pass", "read before: " + "; ".join(said)


def check_stream_back(_answer, run) -> tuple:
    """Every subscription in scope is back, by the re-subscribe's own checks (the module
    docstring): its receiver Connected on a new connection, and, alone on its receiver, a new
    session whose bytes grew twice; sharing it, its series and a new session receiving."""
    from modules.heal import diagnose_stream as DS
    from modules.heal import resubscribe as R

    before = getattr(run, BEFORE_ATTR, None)
    if not before:
        return "unreadable", "what the device and the collector held before was not read"
    units, src, why = _units(run)
    if why:
        return "unreadable", why
    firsts = getattr(run, FIRST_ATTR, None)
    if firsts is None:
        firsts = {}
        setattr(run, FIRST_ATTR, firsts)
    said, states = [], []
    for u in units:
        b = before.get(u["sub"]) or {}
        checks = [R._device_check(run.device, u["sub"], b.get("receiver") or {},  # noqa: SLF001
                                  _receiver(run, u["sub"]))]
        now = DS.read_collector(u["address"], u["port"], src)
        if u["alone"]:
            direct, read = R._bytes_check(run.device, u, b.get("collector") or {}, now,  # noqa: SLF001
                                          firsts.setdefault(u["sub"], {}))
            checks.append(direct if read else {"state": "cant_tell", "words": (
                f"the collector's bytes were not read ({R._bytes_unread(now)})")})  # noqa: SLF001
        else:
            checks.append(R._stream_check(run.device, u["sub"],  # noqa: SLF001
                                          DS.series_of(run.device, u["sub"])))
            checks.append(R._collector_check(run.device, u, b.get("collector") or {},  # noqa: SLF001
                                             now)[0])
        states += [c["state"] for c in checks]
        said.append(f"{u['sub']}: " + "; ".join(c["words"] for c in checks))
    if all(s == "pass" for s in states):
        return "pass", "every subscription is back: " + " | ".join(said)
    # A check that cannot tell neither passes nor fails; one still waiting is not back yet
    # (the poll reads again until its bound).
    return ("unreadable" if "cant_tell" in states else "fail"), " | ".join(said)


def check_collector_not_receiving(_answer, run) -> tuple:
    """A stream in scope is still lost: ``pass`` (the step runs) when any subscription in scope
    has no data; ``not_needed`` only when EVERY one is back (the close alone brought them back:
    the step passes with nothing sent, `command_plan_run.NOT_NEEDED`); ``unreadable`` when one
    cannot be told. Each subscription is judged as `check_stream_back` judges it (the third
    review): alone on its receiver, by an ESTABLISHED session from the device receiving inside
    the stream's window (`diagnose_stream.receiving_now`; another state is not the stream);
    sharing its receiver, by its OWN series (`resubscribe._stream_check`), since a session
    carrying another subscription's data says nothing of this one."""
    from modules.heal import diagnose_stream as DS
    from modules.heal import resubscribe as R

    units, src, why = _units(run)
    if why:
        return "unreadable", why
    lost, back = [], []
    for u in units:
        if not u["alone"]:
            c = R._stream_check(run.device, u["sub"],  # noqa: SLF001
                                DS.series_of(run.device, u["sub"]))
            if c["state"] == "cant_tell":
                return "unreadable", f"subscription {u['sub']}: {c['words']}"
            (back if c["state"] == "pass" else lost).append(f"{u['sub']} ({c['words']})")
            continue
        got = DS.read_collector(u["address"], u["port"], src)
        if got.get("state") != "read":
            return "unreadable", f"the collector for {u['sub']} was not read: {got.get('why')}"
        est = [s for s in got.get("sessions") or [] if s.get("state") == DS.ESTABLISHED]
        if any(DS.receiving_now(s) is None for s in est):
            return "unreadable", (f"whether the collector's session for {u['sub']} receives "
                                  "was not read")
        live = [s for s in est if DS.receiving_now(s)]
        if live:
            back.append(f"{u['sub']} (the session from {live[0]['remote']} port "
                        f"{live[0]['rport']} received {int(live[0]['lastrcv_ms']) // 1000} s ago)")
        else:
            lost.append(f"{u['sub']} (no established session receiving)")
    if lost:
        return "pass", "still lost: " + "; ".join(lost)
    return "not_needed", ("every stream in scope carries data again, so there is nothing to "
                          "reset: " + "; ".join(back))


_NETCONF = re.compile(r"^netconf-yang[ \t]*$", re.M)
_DMI_OTHERS = re.compile(r"^(restconf|gnmi-yang)\b[^\n]*$", re.M)


_NETCONF_MORE = re.compile(r"^netconf-yang[ \t]+\S.*$", re.M)


def check_netconf_yang_on(answer, _run) -> tuple:
    """``netconf-yang`` is in the running configuration, alone: else the restart would turn
    NETCONF on, which is no restart. A further ``netconf-yang ...`` line (``feature
    candidate-datastore``, an ssh port) may be taken away by ``no netconf-yang``, and the
    rollback would not put it back: it inverts the lines pushed and restores, from the snapshot,
    only what the program's own ``no`` lines remove (the transient restore,
    `removal.transient_removal_units`: here ``netconf-yang`` itself), never a line the device
    drops by itself as a consequence (the full compare after it would say NOT RESTORED). So it
    is refused."""
    if answer is None:
        return "unreadable", "the running configuration's netconf-yang lines were not read"
    more = sorted(set(m.group(0).strip() for m in _NETCONF_MORE.finditer(answer)))
    if more:
        return "fail", (f"the running configuration holds {', '.join(more)}: no netconf-yang may "
                        "take it away, and the rollback restores only netconf-yang itself, not "
                        "a line the device drops with it, so the restart is refused")
    if _NETCONF.search(answer):
        return "pass", "the running configuration holds netconf-yang, and no other netconf-yang line"
    return "fail", ("the running configuration holds no netconf-yang line: turning it off and on "
                    "would turn NETCONF on, which is no restart")


def check_dmi_others(answer, _run) -> tuple:
    """Neither ``restconf`` nor ``gnmi-yang`` is configured: either may keep the NETCONF-YANG
    processes up through ``no netconf-yang`` (UNKNOWN: not documented, not measured), so the
    restart is refused rather than run on a guess."""
    if answer is None:
        return "unreadable", "the running configuration's restconf and gnmi-yang lines were not read"
    found = sorted(set(m.group(0).strip() for m in _DMI_OTHERS.finditer(answer)))
    if found:
        return "fail", (f"the running configuration holds {', '.join(found)}, which may keep the "
                        "NETCONF-YANG processes running through the restart (unknown, not "
                        "measured): refused rather than run on a guess")
    return "pass", "no restconf or gnmi-yang line is configured"


def check_subscription_as_intent(answer, run) -> tuple:
    """Every subscription the plan recreates (the receiver group, ``subscription_each``) holds
    exactly intent's lines in the running configuration (as a set: the device prints its own
    order): else the re-creation would change it. Lines said are masked."""
    from modules.nsot.command_plan import subscription_lines
    from modules.redact import redact_text

    d = run.derived or {}
    subs = [str(s) for s in d.get("subscription_each") or []] or [str(d.get("subscription"))]
    if answer is None:
        return "unreadable", "the subscriptions' running configuration was not read"
    hv, why = _intent(run)
    if why:
        return "unreadable", why
    blocks, cur = {}, None
    for line in answer.splitlines():
        words = line.split()
        if line[:1] and not line[:1].isspace():
            cur = words[3] if words[:3] == ["telemetry", "ietf", "subscription"] and \
                len(words) == 4 else None
            if cur is not None:
                blocks.setdefault(cur, [])
        elif cur is not None and line.strip():
            blocks[cur].append(line.strip())
    for sub in subs:
        head = f"telemetry ietf subscription {sub}"
        if sub not in blocks:
            return "fail", f"the running configuration holds no {head}"
        want, got = subscription_lines(hv, sub) or [], blocks[sub]
        extra, missing = sorted(set(got) - set(want)), sorted(set(want) - set(got))
        if extra or missing:
            return "fail", redact_text(
                f"{head} differs from committed intent ("
                + "; ".join(x for x in (f"running only: {', '.join(extra)}" if extra else "",
                                        f"intent only: {', '.join(missing)}" if missing else "")
                            if x)
                + "): the re-creation would change it, so it is refused")
    return "pass", (f"subscription {', '.join(subs)} each hold exactly committed intent's "
                    "lines")


def check_iosxe(_answer, run) -> tuple:
    """The device is IOS-XE by Mercury's platform map (`platform.platform_for_device`)."""
    from modules.nsot.platform import platform_for_device

    dialect = platform_for_device(run.dev or {})
    if dialect == "cisco_iosxe":
        return "pass", f"{run.device} is IOS-XE"
    return "fail", (f"{run.device}'s platform is {dialect or 'unknown'}, and the telemetry stack "
                    "restart is IOS-XE's (netconf-yang)")
