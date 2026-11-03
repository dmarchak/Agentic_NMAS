"""The topology hold: a recent change holds healing (board H, part H2; docs/HEAL_TO_INTENT.md
section 6 guard 5, and N3). It reads Mercury's own records and committed intent, never a
device.

**The rule (N3, the operator, 2026-11-03).** A device is held from healing for
``heal_topology_hold_minutes`` (60 minutes on a network marked lab, `policy.LAB_DEFAULTS`; 240,
the risk register's 4 hours, as the production default) after any of:
- a Mercury receipt (a deploy, restore, re-apply or profile apply) on the device or on a device
  committed intent names as its neighbour (`neighbours.expected`: OSPF, OSPFv3 and BGP peers,
  IPv4 and IPv6);
- a credential rotation of the device or such a neighbour (its commit, which is its record);
- an onboarding (its Verify or Abandon record) or a retirement anywhere in the network;
- a change in the network's observed link set (the `topology-graph` reader's links, each
  layer's set of links, a link's state aside; recorded by the trigger on that reader,
  `triggers.from_topology`).
A heal must not fight a rollout or a re-cabling in progress.

**Fails closed.** A record that cannot be read holds the device, naming it (section 6: "A guard
that cannot be read refuses the heal and says so"). The minutes are the network's own policy
(`policy.current`, the lab default included); a policy that cannot be read holds too.

It is a guard: H2 builds the judgement, and the decision (H3) asks it in section 6's order.
"""

import calendar
import logging
import os
import time

log = logging.getLogger(__name__)

GUARD = 5
KEY = "heal_topology_hold_minutes"


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(iso) -> float:
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def minutes(network: str, now: float = None) -> dict:
    """``{"minutes", "source", "words"}`` from *network*'s policy (its own, or the lab default
    on a network marked lab); ``{"minutes": None, ...}`` when it cannot be read."""
    from modules.heal import policy

    got = policy.current(network, now)
    g = (got.get("guards") or {}).get(KEY)
    if got.get("state") != "ok" or not g:
        return {"minutes": None, "source": "", "words": got.get("error") or got.get("words")}
    return {"minutes": int(g["value"]), "source": g["source"], "words": g["words"]}


# ── The sources, each replaceable in a test ─────────────────────────────────────────────────

def _neighbours(network: str, device: str) -> list:
    from modules.neighbours import committed_intents, expected
    from modules.nsot import listref

    intents, err = committed_intents(listref.resolve(network).repo_dir)
    if err:
        raise RuntimeError(f"{network}'s committed intent cannot be read ({err})")
    if device not in intents:
        raise RuntimeError(f"{device} has no committed intent in {network}, so its "
                           "neighbours are not known")
    return sorted({e["peer"] for e in expected(intents, device) if e.get("managed")
                   and e.get("peer") and e["peer"] != device})


def _receipts(network: str, device: str) -> list:
    from modules.heal.attribution import RECEIPTS_READ
    from modules.nsot import receipts as R

    got = R.read(network, device, limit=RECEIPTS_READ)
    if got["state"] == "unreadable":
        raise RuntimeError(f"{network}'s receipts cannot be read ({got.get('error')})")
    return got["rows"]


def _rotations(network: str) -> dict:
    from modules.nsot.scheduled_rotation import committed_rotations

    return committed_rotations(network)


def _onboarding(network: str) -> list:
    from modules.config import list_data_path
    from modules.nsot.onboard import read_runs

    got = read_runs(os.path.join(list_data_path(network), "config_repo"))
    if got["state"] == "unreadable":
        raise RuntimeError(f"{network}'s onboarding record cannot be read "
                           f"({got.get('error')})")
    return got["rows"]


def _retirements(network: str) -> dict:
    from modules.nsot.retire import retirements

    return retirements(network)


def _link_set(network: str) -> dict:
    from modules.heal.triggers import link_set

    return link_set(network)


def topology(network: str, device: str, now: float = None, *, hold_minutes=None,
             neighbours=None, receipts=None, rotations=None, onboarding=None,
             retirements=None, link_set=None) -> dict:
    """Is *device* held from healing by a recent change? ``{"held", "until", "words",
    "minutes", "changes", "unreadable", "guard"}``. *changes* names each change inside the
    window with its time; *until* is when the newest of them stops holding. The keyword
    sources stand in for Mercury's records in a test."""
    now = time.time() if now is None else float(now)
    if hold_minutes is None:
        m = minutes(network, now)
        hold_minutes, source = m["minutes"], m["source"]
        if hold_minutes is None:
            return {"held": True, "until": None, "minutes": None, "changes": [],
                    "unreadable": [m["words"]], "guard": GUARD,
                    "words": (f"held: the topology hold's minutes cannot be read "
                              f"({m['words']}), and a guard that cannot be read holds")}
    else:
        source = "given"
    window = float(hold_minutes) * 60
    since = now - window
    changes, unreadable = [], []

    def within(at: float, what: str) -> None:
        if at and since <= at <= now:
            changes.append({"at": _iso(at), "epoch": at, "what": what})

    try:
        peers = (neighbours or _neighbours)(network, device)
    except Exception as exc:
        peers = []
        unreadable.append(f"{device}'s neighbours in intent ({exc})")
    for d in [device] + list(peers):
        try:
            for r in (receipts or _receipts)(network, d):
                within(_epoch(r.get("at")), f"Mercury's {r.get('action') or 'operation'} of "
                                            f"{d} (receipt {r.get('id') or '?'})")
        except Exception as exc:
            unreadable.append(f"{d}'s receipts ({exc})")
    try:
        rot = (rotations or _rotations)(network) or {}
        for d in [device] + list(peers):
            if d in rot:
                within(float(rot[d][0]), f"a credential rotation of {d}")
    except Exception as exc:
        unreadable.append(f"{network}'s rotation commits ({exc})")
    try:
        for r in (onboarding or _onboarding)(network):
            within(_epoch(r.get("at")), f"an onboarding ({r.get('kind') or '?'}) of "
                                        f"{r.get('device') or '?'} in {network}")
    except Exception as exc:
        unreadable.append(f"{network}'s onboarding record ({exc})")
    try:
        for r in ((retirements or _retirements)(network) or {}).values():
            within(float(r.get("epoch") or 0), f"the retirement of {r.get('name') or '?'} "
                                               f"in {network}")
    except Exception as exc:
        unreadable.append(f"{network}'s retirements ({exc})")
    try:
        ls = (link_set or _link_set)(network) or {}
        if ls.get("changed_epoch"):
            within(float(ls["changed_epoch"]), f"{network}'s observed link set changed")
    except Exception as exc:
        unreadable.append(f"{network}'s observed link set ({exc})")
    changes.sort(key=lambda c: c["epoch"], reverse=True)
    out = {"minutes": int(hold_minutes), "minutes_source": source, "changes": changes,
           "unreadable": unreadable, "guard": GUARD,
           "neighbours": list(peers)}
    if unreadable:
        return dict(out, held=True, until=None,
                    words=(f"held: {'; '.join(unreadable)} cannot be read, and a guard that "
                           "cannot be read holds"))
    if changes:
        until = changes[0]["epoch"] + window
        return dict(out, held=True, until=_iso(until),
                    words=(f"held until {_iso(until)}: {changes[0]['what']} at "
                           f"{changes[0]['at']} is within the {int(hold_minutes)}-minute "
                           f"topology hold ({source})"
                           + (f", and {len(changes) - 1} more change(s)" if len(changes) > 1
                              else "")))
    return dict(out, held=False, until=None,
                words=(f"not held: no Mercury change on {device} or its "
                       f"{len(peers)} intent neighbour(s), no onboarding, retirement or link-set "
                       f"change in {network} in the last {int(hold_minutes)} minutes "
                       f"({source})"))
