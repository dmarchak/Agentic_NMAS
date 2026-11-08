"""Self-healing's dampening proposal (board H's amendment, item 2, part H22; docs/HEAL_TO_INTENT.md
19.4, and 19.6's rows 8 and 8b; C2745): an action, never a heal. It proposes a change to intent,
so it is a person's (section 2: a heal never pushes intent the device never held).

**One home** (CLAUDE.md, "One owner per piece of state; one home per action"): when it is
raised, what it proposes, its one hash, its verify read and its act live here. The intent edit
is `intent_patch`'s ``set_dampening`` (the intent editor's path); the deploy is THE plan and
THE apply (`routes.deploy.plan_devices`, `apply_batch`); Approve… and Decline… are
`propose.approve` and `propose.decline`, as for any proposal.

**When it is raised** (`raise_after`, never raising): only in AUTO, after a real bounce
(`TRIGGERS`):
- ``still_flapping``: the port bounced once, and its stability window read a transition to down
  after the bounce's own up (`bounce._stable`);
- ``second_need``: guard 13d found the port bounced within ``heal_repeat_halts_hours`` (24), so
  a second need is this proposal, never a second bounce (`bounce.consider`).
In dry run no bounce was sent, so no proposal follows one: the bounce's record says so. One
proposal waits per port: while one waits (not taken, not lapsed), a later need names it and
records nothing new.

**What it proposes** (`plan`): intent gains ``dampening: true`` on that interface (the bare
``dampening`` line, the platform's defaults, N19), through `intent_patch.patched_text` on the
committed document; and the deploy program that intent renders, by THE plan with the patched
document in place (`hostvars.proposed`), reading the stored capture and contacting no device.
It is refused, naming why, when: the intent cannot be read or patched (hand-formatted, the
interface absent, a dampening line with parameters already there); it already holds dampening;
the device's deploy already holds lines pending (dampening is proposed only on a device at its
intent, so the program is exactly the one line); or the program is anything but ``dampening``
under that interface.

**Its one hash** (`one_hash`, the decision's ``program_hash``): the network, the device, the
interface, the committed blob patched, the patched document's hash and the deploy program's
hash. `propose.proposal_hash` binds it with the decision, so one approval confirms both the
intent commit and its deploy, and the act refuses if either moved.

**The rollback** (`rollback_program`, `rollback_refusal`): undoing the line is a removal, Mode
B's ``interface.dampening`` shape, built by THE removal builder (`removal.removal_program`:
``interface <if>`` / `` no dampening`` / ``exit``), which is what the pipeline's own rollback
sends for the added line. The operator's probe measured the shape ``exact`` on an IOS-XE router
and an IOS switch (2026-11-08, C2416), recorded in `removal_measured.json`. On a platform whose
record holds no ``exact`` row the proposal is still drawn, its hash shown, and its Approve
refused by name, saying so.

**The act** (`apply_approved`, `STEPS`), as the approving person (``Actor-Verified: access``
from `identity.carried`), its stops the proposal's (`propose._stops`):
1. ``take``, once; 2. ``stops``; 3. ``rollback``: the removal measured, or nothing is done;
4. ``plan`` again: refused unless the one hash is the approved one, naming both;
5. ``intent``: the patch committed as the person (`intent_patch.commit`, Source
   ``heal-dampening``, the proposal's hash and decision as trailers);
6. ``apply`` through THE apply as the person (``actor_kind="person"``), holding the device: the
   deploy's nine stages, its program recomputed from committed intent and refused unless its
   hash is the proposal's;
7. ``verify``, after the pipeline verified the line read back, the device still held and its
   save held: ``show interfaces dampening`` on the deploy's own session (`parse`) lists the
   interface; a read listing it not rolls the device back by the pipeline's own rollback
   (`roll_back_end`, the measured negation); an unreadable read neither passes nor fails
   (``unverified``, kept);
8. ``record``: `decisions.applied`, the incident closed, the step log's ``act`` row (History)
   and the announcement. A deploy refused or rolled back puts the intent back as the person (one
   forward commit), so intent never holds what the device was not given.

**The verify read's parser is shaped, not captured** (`VERIFY_CAPTURED`, False; H22's register
row for it): it is written against Cisco's documented ``show interfaces dampening`` table
(tests/fixtures/heal_dampening/), and no device's answer is in the suite. It reads ``tracked``
only where it recognises the table under the interface's own name; text it does not recognise
is unreadable, never a pass.

**It clears** (`attention._heal_dampening_rows`, its ``CLEARS`` entry): approved and verified,
or declined with a reason (the decision taken); or the port stable for `STABLE_HOURS` since the
last need of it (resolved by time, and said: its Approve is then refused as lapsed). An approved
act that ended otherwise is its own row until a later need of the port, or 7 days.
"""

import hashlib
import json
import logging
import re
import time

log = logging.getLogger(__name__)

KIND = "dampening_proposal"
#: The intent commit's ``Source:`` slug.
SOURCE = "heal-dampening"
#: Mode B's shape its rollback needs (`removal.SHAPES`), and the line it removes.
SHAPE = "interface.dampening"
LINE = " dampening"
VERIFY_READ = "show interfaces dampening"
#: Whether the verify read's parser has a real capture (H22's register row for it): it is
#: shaped from Cisco's documented output, so a verified result says it rests on that parser.
VERIFY_CAPTURED = False
#: A port stable this long since its last need resolves the proposal by time (19.4).
STABLE_HOURS = 24
#: What a proposal follows (the module's docstring).
TRIGGERS = {"still_flapping": "bounced once and still flapping",
            "second_need": "a second bounce needed within the repeat window"}
#: The approved act's steps, in order, for the step log and the manual's How it works page.
STEPS = (("take", "Take the approved proposal, once"),
         ("stops", "Check the kill switch, the mode, a halt, planned work and the kind proposed"),
         ("rollback", "Check the rollback's removal (interface.dampening) is measured on the "
                      "device's platform"),
         ("plan", "Patch intent again and plan its deploy; compare the proposal's one hash"),
         ("intent", "Commit the intent edit as the person who approved it"),
         ("apply", "Deploy it as the person, holding the device: the deploy's nine stages"),
         ("verify", "Read show interfaces dampening on the deploy's session: the interface "
                    "tracked, or rolled back"),
         ("record", "Record the outcome and close the incident"))
OUTCOMES = ("dampened", "unverified", "rolled_back", "failed", "refused")
OUTCOME_WORDS = {"dampened": "dampening deployed and verified",
                 "unverified": "dampening deployed; its verify read could not be judged",
                 "rolled_back": "rolled back: dampening is not on the device or in intent",
                 "failed": "NOT RESTORED after the dampening deploy",
                 "refused": "nothing was sent"}
#: What the act's job announces when it ends: a deploy's, and the intent it committed.
DONE_KEYS = ("drift", "goldens", "remote", "baselines", "device_state", "rolled_back",
             "intent")
ANNOUNCER = "heal-dampening"
READS_BY = "heal"
ACTOR = "Mercury (self-healing)"
#: An approved act that did not end dampened stays a row this long (as a bounce's, H20).
ENDED_DAYS = 7


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _same(a: str, b: str) -> bool:
    from modules.nsot import ifnames

    return bool(a) and bool(b) and ifnames.same_interface(a, b)


def patch_of(device: str, interface: str) -> dict:
    """The intent patch the proposal is: `intent_patch`'s ``set_dampening``."""
    return {"hostname": device, "operations": [{"op": "set_dampening", "interface": interface}]}


def rollback_program(interface: str, dialect: str) -> dict:
    """The proposal's undo on *dialect*: Mode B's removal of ``dampening`` under *interface*
    (``interface.dampening``), built by THE removal builder (`removal.removal_program`) over
    the line as the deploy leaves it: ``{"commands", "refused"}``, *refused* the gate's words
    while the shape is not measured there. It is the program the pipeline's own rollback sends
    for the added line (`deploy.rollback_commands`' negation, tests/test_heal_dampening.py);
    a rollback of THAT removal re-adds the line by `removal.restore_program`."""
    from modules.nsot import removal

    after = f"interface {interface}\n{LINE}\n"
    got = removal.removal_program(after, [{"chain": [f"interface {interface}"], "line": LINE}],
                                  mgmt_ip="", dialect=dialect)
    why = "; ".join(r.get("reason") or "" for r in got.get("refused") or [])
    return {"commands": [] if why else list(got.get("commands") or []), "refused": why}


def rollback_refusal(dialect: str, interface: str) -> str:
    """Why the proposal's undo (`rollback_program`) may not run on *dialect* yet, or "":
    Mode B's one gate, its shape's measurement."""
    from modules.nsot import removal

    why = removal.shape_refusal((f"interface {interface}",), LINE, "leaf", dialect)
    if not why:
        why = rollback_program(interface, dialect)["refused"]
    return (f"its rollback, the removal of `dampening` from {interface} ({SHAPE}), is not "
            f"available: {why}" if why else "")


def one_hash(network: str, device: str, interface: str, base: str, text: str,
             command_hash: str) -> str:
    """The proposal's one hash: the intent commit (the blob patched and the patched text) and
    its deploy (the program's hash), on one device's one interface."""
    body = {"network": network, "device": device, "interface": interface, "base": base or "",
            "intent": hashlib.sha256((text or "").encode()).hexdigest(),
            "program": command_hash or ""}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


# ── The verify read's parser (shaped, not captured: VERIFY_CAPTURED) ────────────────────────

_INVALID = re.compile(r"^% Invalid input detected", re.MULTILINE)
_HEADER = re.compile(r"^\s*Flaps\s+Penalty\s+Supp\s+ReuseTm\s+HalfL\s+ReuseV\s+SuppV\s+MaxSTm\s+"
                     r"MaxP\s+Restart\s*$")
_ROW = re.compile(r"^\s*(?P<flaps>\d+)\s+(?P<penalty>\d+)\s+(?P<supp>TRUE|FALSE)\s+"
                  r"(?P<reuse_tm>\d+)\s+(?P<half_life>\d+)\s+(?P<reuse>\d+)\s+(?P<suppress>\d+)"
                  r"\s+(?P<max_suppress>\d+)\s+(?P<max_penalty>\d+)\s+(?P<restart>\d+)\s*$")
_NAME = re.compile(r"^\s*(?P<name>[A-Za-z][A-Za-z-]*\d[\w/.:]*)\s*$")


def parse(text: str, interface: str) -> dict:
    """``show interfaces dampening`` as ``{"state", "tracked", "interfaces", "why"}``:
    *state* ``parsed`` (the table read: *tracked* whether *interface* is in it, by its own
    name), ``unsupported`` (IOS's invalid-input marker) or ``unreadable`` (text this parser does
    not recognise: never read as "not tracked"). An empty answer is parsed, tracking nothing."""
    text = text or ""
    if _INVALID.search(text):
        return {"state": "unsupported", "tracked": None, "interfaces": {},
                "why": "the device has no such read (it printed IOS's invalid input marker)"}
    lines = text.splitlines()
    found, name, bad = {}, "", []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = _NAME.match(line)
        if m and i + 2 < len(lines) and _HEADER.match(lines[i + 1]):
            name = m.group("name")
            row = _ROW.match(lines[i + 2])
            if not row:
                bad.append(lines[i + 2].strip())
                i += 3
                continue
            got = row.groupdict()
            found[name] = {k: (v == "TRUE" if k == "supp" else int(v)) for k, v in got.items()}
            i += 3
            continue
        bad.append(line.strip())
        i += 1
    if bad:
        return {"state": "unreadable", "tracked": None, "interfaces": found,
                "why": f"a line this parser does not recognise ({bad[0][:60]!r})"}
    tracked = any(_same(n, interface) for n in found)
    return {"state": "parsed", "tracked": tracked, "interfaces": found,
            "why": (f"{interface} is tracked ({len(found)} interface(s) in the table)" if tracked
                    else f"{interface} is not in the table ({len(found)} interface(s) in it)")}


# ── The sources (each replaceable in a test) ────────────────────────────────────────────────

class Sources:
    """Where the proposal and its act read and what they call: the policy, the stores, the
    committed intent and its patch, THE plan (with a patched document in place) and THE apply,
    the intent commit, and the verify read on the deploy's own session."""

    def __init__(self, network: str, *, clock=time.time, sleep=time.sleep):
        self.network, self.clock, self.sleep = network, clock, sleep

    def mode(self, now):
        from modules.heal import policy

        return policy.current(self.network, now)

    def planned(self, device, now):
        from modules.heal import guards

        return guards.g3_planned(self.network, device, now)

    def decisions(self):
        from modules.heal import decisions

        return decisions.decisions(self.network)

    def device(self, host):
        from modules import device_page
        from modules.nsot import listref

        _ref, dev = device_page.find_device(host, listref.resolve(self.network))
        return dev or {}

    def platform(self, host, dev):
        from modules.heal.decide import Sources as DecideSources

        return DecideSources(self.network).platform(host, dev)

    def doc(self, host) -> dict:
        from modules.nsot import intent_edit

        return intent_edit.open_doc(self.network, host)

    def patched(self, host, text, patch) -> dict:
        from modules.nsot import intent_patch

        return intent_patch.patched_text(host, text, patch, self.network)

    def plan(self, host, *, proposed: str = None, **kw) -> dict:
        """THE plan of *host*, as committed, or with *proposed* in place of its document."""
        import contextlib

        from modules.nsot import hostvars, listref
        from routes.deploy import plan_devices

        held = (hostvars.proposed(listref.resolve(self.network).repo_dir, {host: proposed})
                if proposed is not None else contextlib.nullcontext())
        with held:
            return plan_devices(self.network, [host], **kw)[0]

    def commit(self, host, patch, summary, base, actor, trailers) -> dict:
        from modules.nsot import intent_patch

        return intent_patch.commit(self.network, host, patch, summary, base, actor,
                                   source=SOURCE, extra_trailers=trailers)

    def put_back(self, host, text, summary, base, actor, trailers) -> dict:
        from modules.nsot import intent_edit

        return intent_edit.commit(self.network, host, text, summary, base, actor,
                                  source=SOURCE, extra_trailers=trailers)

    def apply(self, host, **kw) -> dict:
        from routes.deploy import apply_batch

        return apply_batch(self.network, **kw)

    def verify_read(self, dev, ctx) -> str:
        """``show interfaces dampening`` on the session the pipeline holds (``ctx``'s pool),
        masked by the one redactor."""
        from modules.commands import run_device_command
        from modules.connection import get_persistent_connection
        from modules.redact import known_secret_values, redact_text

        conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)
        return redact_text(run_device_command(conn, VERIFY_READ) or "", known_secret_values())


# ── The proposal ────────────────────────────────────────────────────────────────────────────

def _entry_refusal(entry: dict) -> str:
    if entry.get("refused") or entry.get("error"):
        return str(entry.get("refused") or entry.get("error"))
    if not entry.get("deployable", True) or entry.get("blocking_reasons"):
        return "; ".join(entry.get("blocking_reasons") or ["not deployable"])
    return ""


def plan(network: str, device: str, interface: str, *, src) -> dict:
    """What the proposal is now (the module's docstring): ``{"ok", "refused", "base", "text",
    "changes", "program", "command_hash", "hash"}``. Reads only Mercury's records; sends and
    writes nothing."""
    from modules.nsot.deploy import program_lines

    out = {"ok": False, "refused": "", "base": "", "text": "", "changes": [], "program": [],
           "command_hash": "", "hash": ""}

    def no(words):
        return dict(out, refused=words)

    opened = src.doc(device)
    if not opened.get("ok"):
        return no(f"{device}'s committed intent cannot be read: {opened.get('error')}")
    out["base"] = opened.get("base") or ""
    got = src.patched(device, opened.get("yaml") or "", patch_of(device, interface))
    if not got.get("ok"):
        return no(f"intent cannot take dampening on {interface}: {got.get('error')}")
    if not got.get("changed"):
        return no(f"{device}'s intent already holds dampening on {interface}, so there is "
                  "nothing to propose")
    out.update(text=got["text"], changes=[c.get("summary") for c in got.get("changes") or []])
    now = src.plan(device)
    why = _entry_refusal(now)
    if why:
        return no(f"{device}'s deploy cannot be planned as committed: {why}")
    if now.get("commands"):
        return no(f"{device}'s deploy already holds {len(now['commands'])} line(s) not sent: "
                  "dampening is proposed only on a device at its intent, so its program is the "
                  "one line; deploy or resolve those first")
    new = src.plan(device, proposed=got["text"])
    why = _entry_refusal(new)
    if why:
        return no(f"the deploy refuses intent with dampening on {interface}: {why}")
    prog = list(new.get("commands") or [])
    def ours(header: str) -> bool:
        return header.strip().startswith("interface ") and _same(
            header.strip().removeprefix("interface ").strip(), interface)

    # Every pair is the interface's own header, or `dampening` under it, and nothing else.
    pairs = sorted(program_lines(prog))
    leaves = [(c, l) for c, l in pairs if len(c) == 1 and ours(c[0])
              and l.strip() == LINE.strip()]
    wrong = [f"{' > '.join(c)} > {l}".lstrip(" >") for c, l in pairs
             if (c, l) not in leaves and not (not c and ours(l))]
    if not leaves or wrong:
        return no(f"the program for dampening on {interface} is not the one line under it ("
                  + ("; ".join(wrong[:3]) if wrong else "no line") + ")")
    out.update(ok=True, program=prog, command_hash=new.get("command_hash") or "",
               hash=one_hash(network, device, interface, out["base"], got["text"],
                             new.get("command_hash") or ""))
    return out


def last_need(rows: list, device: str, interface: str) -> float:
    """The newest epoch of a decision that needed *interface* on *device*: a bounce of it (or an
    OSPF reset through it), or this proposal."""
    from modules.heal.actions import BOUNCES

    seen = [float(d.get("epoch") or 0) for d in rows or []
            if (d.get("action") or {}).get("kind") in BOUNCES + (KIND,)
            and (d.get("action") or {}).get("device") == device
            and _same((d.get("action") or {}).get("interface") or "", interface)]
    return max(seen) if seen else 0.0


def lapsed(decision: dict, rows: list, now: float) -> str:
    """Words when *decision*'s port has been stable `STABLE_HOURS` since its last need (the
    proposal resolved by time), or ""."""
    a = decision.get("action") or {}
    last = max(last_need(rows, a.get("device") or "", a.get("interface") or ""),
               float(decision.get("epoch") or 0))
    if last and now - last >= STABLE_HOURS * 3600:
        return (f"{a.get('device')} {a.get('interface')} has needed no bounce for "
                f"{STABLE_HOURS} h (its last need {_iso(last)}), so the proposal lapsed: "
                "resolved by time; a later flap proposes it again")
    return ""


def waiting(rows: list, device: str, interface: str, now: float):
    """The proposal for *interface* on *device* waiting for a person (not taken, not lapsed),
    or None."""
    for d in reversed(rows or []):
        a = d.get("action") or {}
        if (a.get("kind") == KIND and d.get("outcome") == "propose" and not d.get("taken")
                and a.get("device") == device and _same(a.get("interface") or "", interface)
                and not lapsed(d, rows, now)):
            return d
    return None


def raise_after(network: str, after: dict, *, trigger: str, now: float = None,
                sources=None) -> dict:
    """The dampening proposal after *after* (a bounce decision of a port), judged and recorded:
    ``{"state", "decision", "words"}``, *state* ``recorded``, ``waiting`` (one waits already),
    ``none`` (not in AUTO: nothing recorded) or ``failed``. Never raises."""
    from modules.heal import decisions

    now = time.time() if now is None else float(now)
    a = (after or {}).get("action") or {}
    device, interface = a.get("device") or after.get("device") or "", a.get("interface") or ""
    if trigger not in TRIGGERS:
        return {"state": "failed", "decision": None,
                "words": f"{trigger!r} is not what a dampening proposal follows"}
    if (after or {}).get("mode") and after["mode"] != "auto":
        # The bounce's own decision was made outside AUTO: nothing was sent to follow.
        return {"state": "none", "decision": None, "words": (
            f"no dampening proposal: the bounce decision {after.get('id') or ''} was made in "
            f"{after['mode']} mode, so no bounce was sent for it to follow")}
    try:
        src = sources or Sources(network)
        mode = src.mode(now)
        if mode.get("mode") != "auto":
            return {"state": "none", "decision": None, "words": (
                f"no dampening proposal: {network} is in {mode.get('mode') or 'no'} mode, so no "
                "bounce was sent for it to follow")}
        rows = src.decisions()
        w = waiting(rows, device, interface, now)
        if w:
            return {"state": "waiting", "decision": w, "words": (
                f"dampening on {device} {interface} waits for a person already (decision "
                f"{w['id']})")}
        made = _decide(network, after, device, interface, trigger, mode, src, now)
        d = decisions.record(network, made, now)
    except Exception as exc:                          # said, never raised
        log.exception("heal: %s's dampening proposal for %s %s failed", network, device,
                      interface)
        return {"state": "failed", "decision": None,
                "words": f"the dampening proposal was not made ({type(exc).__name__}: {exc})"}
    _log_decision(network, d, now)
    _announce()
    return {"state": "recorded", "decision": d, "words": d.get("words") or ""}


def _decide(network, after, device, interface, trigger, mode, src, now) -> dict:
    """The proposal's record, not yet written."""
    from modules.heal.actions import KIND_WORDS

    a = after.get("action") or {}
    unit = {"kind": KIND, "tier": 2, "id": f"{KIND}:{interface}",
            "words": f"dampening on {device} {interface}, the platform's defaults (intent)"}
    base = {"incident": after.get("incident") or "", "device": device,
            "mode": mode.get("mode"),
            "policy": {"fingerprint": mode.get("fingerprint"),
                       "by": (mode.get("confirmed") or {}).get("by"),
                       "reason": (mode.get("confirmed") or {}).get("reason")},
            "guard": None, "units": [unit], "kind": KIND, "tier": 2, "program": [],
            "program_hash": "", "until": None,
            "triggers": [f"{device} {interface} {TRIGGERS[trigger]} (decision "
                         f"{after.get('id') or '?'})"],
            "action": {"kind": KIND, "device": device, "interface": interface, "peer": "",
                       "far_device": a.get("far_device") or "",
                       "far_interface": a.get("far_interface") or "",
                       "after": after.get("id") or "", "trigger": trigger},
            "steps": [{"step": "choose", "result": "ok",
                       "words": f"{KIND_WORDS[KIND]}: {TRIGGERS[trigger]}"}],
            "phase": "decide"}
    if KIND not in (mode.get("kinds_propose") or []):
        return dict(base, outcome="cant_fix", words=(
            f"dampening on {device} {interface} is a Tier 2 change the policy does not propose "
            f"(proposed now: {', '.join(mode.get('kinds_propose') or []) or 'none'}): nothing "
            "is sent, and a person decides it"))
    p = plan(network, device, interface, src=src)
    if not p["ok"]:
        return dict(base, outcome="cant_fix", words=(
            f"dampening on {device} {interface} was not proposed: {p['refused']}"))
    from modules.redact import redact_text

    dev = src.device(device) or {}
    dialect = src.platform(device, dev) or ""
    base["steps"].append({"step": "plan", "result": "ok", "words": (
        f"intent patched ({'; '.join(p['changes'])}); the deploy's program "
        f"{len(p['program'])} line(s), hash {p['command_hash']}")})
    return dict(base, outcome="propose", program=[redact_text(x) for x in p["program"]],
                program_hash=p["hash"],
                dampening={"base": p["base"], "command_hash": p["command_hash"],
                           "dialect": dialect, "patch": patch_of(device, interface),
                           "intent": p["changes"]},
                words=(f"proposed for a person: {unit['words']}, after it {TRIGGERS[trigger]}; "
                       f"one hash {p['hash']} for the intent commit and its deploy"))


def _log_decision(network: str, d: dict, now: float) -> None:
    from modules.heal import steplog

    try:
        steplog.record_decision(network, d, now)
    except Exception as exc:
        log.error("heal: %s's dampening decision %s is not in the step log: %s", network,
                  d.get("id"), exc)


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS["heal-act"], by="heal-act")
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("heal: a dampening decision recorded, not announced: %s", exc)


# ── What the card adds (propose.view) ───────────────────────────────────────────────────────

def refusals(decision: dict, rows: list, now: float) -> list:
    """Why the proposal may not be approved now, beyond `propose._stops`: its rollback not
    measured on the device's platform, or its port stable long enough that it lapsed."""
    out = []
    a, dz = decision.get("action") or {}, decision.get("dampening") or {}
    why = rollback_refusal(dz.get("dialect") or "", a.get("interface") or "")
    if why:
        out.append(f"not confirmable until measured: {why}")
    gone = lapsed(decision, rows, now)
    if gone:
        out.append(gone)
    return out


def units_words(decision: dict) -> list:
    """The card's Fix lines: what it changes, how it is verified and how it is undone."""
    a, dz = decision.get("action") or {}, decision.get("dampening") or {}
    iface, dialect = a.get("interface") or "", dz.get("dialect") or "its platform"
    why = rollback_refusal(dz.get("dialect") or "", iface)
    undo = rollback_program(iface, dz.get("dialect") or "")["commands"]
    return [u.get("words") for u in decision.get("units") or [] if u.get("words")] + [
        (f"intent: {decision.get('device')}'s host_vars gains `dampening: true` on {iface}, "
         f"committed as you (Source {SOURCE})"),
        (f"verified by `{VERIFY_READ}` listing {iface}"
         + ("" if VERIFY_CAPTURED else " (its parser shaped from Cisco's documented output, "
            "not yet a capture)")),
        (f"undone by removing `dampening` ({SHAPE}): "
         + (f"not measured on {dialect}" if why else
            f"measured on {dialect}, the rollback {' / '.join(x.strip() for x in undo)}"))]


# ── The approved act ────────────────────────────────────────────────────────────────────────

def apply_approved(network: str, decision: dict, approval: dict, *, now: float = None,
                   sources=None) -> dict:
    """Apply one taken, approved dampening proposal as the person, verify it and record it
    (`STEPS`): ``{"decision", "device", "outcome", "words", "steps", "sent", "report",
    "records"}``."""
    from modules.heal import decisions, incidents, propose, steplog
    from modules.nsot import receipts
    from modules.nsot.deploy import DEPLOYED
    from modules.redact import redact_text

    now = time.time() if now is None else float(now)
    src = sources or Sources(network)
    device = decision["device"]
    a, dz = decision.get("action") or {}, decision.get("dampening") or {}
    interface = a.get("interface") or ""
    by, reason = approval["by"], approval.get("reason") or ""
    via = f"dampening proposal approved by {by}"
    steps = [{"step": "take", "result": "ok",
              "words": f"taken on {by}'s approval of proposal {approval.get('hash')}"}]
    held = {"commit": "", "put_back": "", "verify": None}
    trailers = [f"Heal-Proposal: {approval.get('hash')}", f"Heal-Decision: {decision['id']}"]

    def step(name, result, words):
        steps.append({"step": name, "result": result, "words": redact_text(words),
                      "at": _iso(time.time())})

    def put_back(why):
        """The intent edit undone as the person (one forward commit), so intent never holds
        what the device was not given; said either way."""
        if not held["commit"]:
            return ""
        opened = src.doc(device)
        if not opened.get("ok"):
            held["put_back"] = f"NOT put back: {opened.get('error')}"
            return held["put_back"]
        got = src.put_back(device, held["was"], f"put back dampening on {interface}: {why}",
                           opened.get("base") or "", by, trailers)
        held["put_back"] = (f"put back as {by} ({(got.get('commit') or '')[:10]})"
                            if got.get("ok") else f"NOT put back: {got.get('error')}")
        step("intent", "ok" if got.get("ok") else "failed", f"intent {held['put_back']}")
        return held["put_back"]

    def finish(outcome, words, *, sent=False, report=None):
        step("record", outcome, f"{OUTCOME_WORDS[outcome]}: {words}")
        try:
            decisions.applied(network, decision["id"], outcome, by=by, words=words, now=now)
            if outcome == "failed":
                decisions.halt(network, guard=14, name="a heal sent and not verified",
                               words=(f"the approved dampening of {device} {interface} "
                                      f"({decision['id']}) failed after sending and was not "
                                      f"rolled back: {words}"),
                               operands={"decision": decision["id"], "device": device},
                               now=now)
        except Exception as exc:
            log.error("heal: %s's dampening outcome on %s was not recorded: %s", network,
                      device, exc)
        try:
            if decision.get("incident"):
                incidents.close(network, decision["incident"],
                                f"{outcome}: {words} (decision {decision['id']})", now)
        except Exception as exc:
            log.error("heal: %s's incident %s was not closed: %s", network,
                      decision.get("incident"), exc)
        result = {"decision": decision["id"], "device": device, "outcome": outcome,
                  "words": redact_text(words), "steps": steps, "sent": sent, "report": report,
                  "records": {
                      "intent": held["commit"] or "not committed",
                      "put_back": held["put_back"] or "not needed",
                      "verify": held["verify"] or "not read",
                      "receipt": (f"the deploy receipt of {device}" if report
                                  else "none: nothing reached the deploy's apply"),
                      "approval": (f"approved by {by} ({approval.get('verified')}) at "
                                   f"{approval.get('at')}, confirming proposal "
                                   f"{approval.get('hash')}, with the reason \"{reason}\"")}}
        try:
            steplog.record_act(network, decision, result, by=by, now=now)
            result["records"]["step_log"] = "written"
        except Exception as exc:
            log.error("heal: %s's dampening act on %s is not in the step log: %s", network,
                      device, exc)
            result["records"]["step_log"] = f"not written: {type(exc).__name__}: {exc}"
        log.info("heal: %s: dampening on %s %s, approved by %s: %s: %s", network, device,
                 interface, by, outcome, words)
        return result

    def refuse(name, words):
        step(name, "refused", words)
        back = put_back(words)
        return finish("refused", f"{words}. Nothing was sent"
                      + (f"; the intent edit {back}" if back else ""))

    why = propose._stops(network, decision, now, src)
    if why:
        return refuse("stops", why)
    step("stops", "ok", "self-healing on, no halt, no planned work, the kind still proposed")
    why = rollback_refusal(dz.get("dialect") or "", interface)
    if why:
        return refuse("rollback", f"not applied: {why}")
    undo = rollback_program(interface, dz.get("dialect") or "")["commands"]
    step("rollback", "ok", (f"the removal of `dampening` ({SHAPE}) is measured on "
                            f"{dz.get('dialect')}: {' / '.join(x.strip() for x in undo)}"))
    p = plan(network, device, interface, src=src)
    if not p["ok"]:
        return refuse("plan", f"the proposal cannot be planned now: {p['refused']}")
    if p["hash"] != decision.get("program_hash"):
        return refuse("plan", (f"the proposal moved since it was approved (approved "
                               f"{decision.get('program_hash')}, now {p['hash']}): {device}'s "
                               "intent or its deploy changed; a later need proposes it again"))
    step("plan", "ok", (f"intent patched and its deploy planned again: {len(p['program'])} "
                        f"line(s), the proposal's one hash {p['hash']}"))
    try:
        steplog.record_started(network, decision, steps + [{
            "step": "apply", "result": "running",
            "words": f"as {by}, who approved it, holding {device}"}],
            [redact_text(x) for x in p["program"]], p["hash"], by=by, now=now)
    except Exception as exc:
        return refuse("intent", (f"the program could not be written to the step log before it "
                                 f"is sent ({type(exc).__name__}: {exc}), and self-healing "
                                 "sends nothing it has not recorded"))
    opened = src.doc(device)
    held["was"] = opened.get("yaml") or ""
    c = src.commit(device, dz.get("patch") or patch_of(device, interface),
                   f"dampening on {interface} (self-healing's proposal, approved: {reason})",
                   p["base"], by, trailers)
    if not c.get("ok") or not c.get("commit"):
        return refuse("intent", f"the intent edit was not committed: "
                                f"{c.get('error') or c.get('message') or 'no commit'}")
    held["commit"] = c["commit"]
    step("intent", "ok", f"committed as {by}: {c['commit'][:10]} (Source {SOURCE})")
    entry = src.plan(device)
    if _entry_refusal(entry) or entry.get("command_hash") != p["command_hash"]:
        return refuse("apply", (f"the deploy planned from the committed intent is not the one "
                                f"approved (approved {p['command_hash']}, now "
                                f"{entry.get('command_hash') or _entry_refusal(entry)})"))
    dev = src.device(device) or {}

    def after_verify(host, result, ctx):
        text = src.verify_read(dev, ctx)
        got = parse(text, interface)
        shaped = "" if VERIFY_CAPTURED else " (a shaped parser, not yet a capture)"
        held["verify"] = f"{VERIFY_READ}: {got['state']}: {got['why']}{shaped}"
        record = {"dampening": {"read": VERIFY_READ, "state": got["state"],
                                "tracked": got["tracked"], "words": got["why"]}}
        if got["state"] == "parsed" and got["tracked"] is False:
            step("verify", "failed", held["verify"])
            return {"rollback": (f"`{VERIFY_READ}` does not list {interface} after the "
                                 "deploy, so what landed was undone"), "record": record}
        step("verify", "ok" if got["tracked"] else "unknown", held["verify"])
        return {"rollback": "", "record": record}

    step("apply", "running", f"as {by}, who approved it, holding {device}")
    report = src.apply(device, confirmations={device: entry.get("capture_hash")},
                       command_hashes={device: entry.get("command_hash")}, actor=by,
                       actor_kind="person", stop_at_first=True, after_verify=after_verify,
                       hold_detail=via)
    r = next((x for x in report.get("results") or [] if x.get("device") == device), {})
    outcome = r.get("outcome") or "refused"
    if outcome != DEPLOYED:
        sent = receipts.was_sent(r)
        step("apply", outcome, r.get("reason") or "")
        if not sent:
            back = put_back(r.get("reason") or outcome)
            return finish("refused", f"{r.get('reason') or outcome}. Nothing was sent; the "
                                     f"intent edit {back}", report=report)
        if r.get("rolled_back"):
            state = (r.get("rollback_outcome") or {}).get("state") or "ran"
            back = put_back(r.get("reason") or "rolled back")
            return finish("rolled_back", (f"{r.get('reason') or 'verify failed'}; the rollback: "
                                          f"{state}; the intent edit {back}"), sent=True,
                          report=report)
        return finish("failed", (f"{r.get('reason') or outcome}; nothing was rolled back, and "
                                 "intent keeps dampening"), sent=True, report=report)
    saved = r.get("saved_startup") or {}
    if saved.get("held") or (saved and not saved.get("ok")):
        return finish("unverified", (f"deployed; NOT saved to startup "
                                     f"({saved.get('why') or saved.get('error') or 'held'})"),
                      sent=True, report=report)
    if "verify" not in [s["step"] for s in steps] or (r.get("heal") or {}).get(
            "dampening", {}).get("tracked") is not True:
        return finish("unverified", (f"deployed and saved; {held['verify'] or 'the verify read '
                                     'was not made'}: neither passed nor failed, so it is "
                                     "kept"), sent=True, report=report)
    return finish("dampened", (f"dampening on {device} {interface} committed "
                               f"{held['commit'][:10]} and deployed as {by}; {held['verify']}"),
                  sent=True, report=report)
