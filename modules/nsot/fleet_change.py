"""nsot/fleet_change.py — one change across many devices, through a shared intent layer (board FC
phase 2; PHASE8_PLAN 22.2; C2283). This module is (b), the plan: nothing is sent, nothing written.

**The change** is bulk intent's compare-and-set steps (`bulk_intent`'s ``(path, before,
after)``, its paths and its schema check) applied to ONE layer's document: the layer as
committed (or empty, a new layer) must hold each step's *before*, or the change is refused naming
the path and both values, never applied around. The result must be a layer (`intent_layers.
problems`) and name no secret value (`hostvars.assert_no_secret_values`).

**The plan** is the deploy's own: for every device the layer reaches (its group read from the
inventory now; an unreadable inventory refuses the plan by name), `routes.deploy.plan_devices`
runs twice, as committed and with the change in place (`intent_layers.proposed`, through the one
chain), so each device's program, gates and refusals are exactly what a deploy would compute. A
device's CHANGE is the lines its program gains; devices are grouped by identical change (bulk
intent's grouping, "4 devices, 1 group"). A device whose program does not move is unchanged and
says who holds the value instead (its own document, or a later layer), never a failure. A device
the deploy refuses is refused with the deploy's reasons. Lines a device's program already held
before the change ride along on its run, so each device says how many.

**One hash** binds the layer's before and after, the repository's commit, and every planned
device's program hash: the approval (c) is refused if any of them moved.
"""

import copy
import hashlib
import json
import logging

log = logging.getLogger(__name__)


def _canon(value) -> str:
    from modules.nsot import bulk_intent as B
    if B._is_absent(value):
        return "<absent>"
    return json.dumps(value, sort_keys=True, default=str)


def _shown(value) -> str:
    from modules.nsot import bulk_intent as B
    return "nothing" if B._is_absent(value) else json.dumps(value, sort_keys=True, default=str)


def apply_steps(doc: dict, steps: list) -> tuple:
    """``(after, refusals)``: *doc* with each step applied, or the steps whose *before* the
    document does not hold, each naming the path, what it holds and what the change expected.
    Nothing is applied when any is refused."""
    from modules.nsot import bulk_intent as B

    after, refused = copy.deepcopy(doc or {}), []
    for step in steps:
        path, now = list(step["path"]), B.get_path(after, step["path"])
        if _canon(now) != _canon(step.get("before", B.ABSENT)):
            refused.append(f"{' › '.join(map(str, path))} holds {_shown(now)}, the change "
                           f"expected {_shown(step.get('before', B.ABSENT))}")
            continue
        if not B.set_path(after, path, copy.deepcopy(step["after"])):
            refused.append(f"{' › '.join(map(str, path))} cannot be set in a layer")
    return (doc, refused) if refused else (after, [])


def plan_layer(list_name: str, layer_key: str, steps: list) -> dict:
    """The plan for *steps* on the layer *layer_key* (its file's stem: ``network``,
    ``tag-blind-lab``) of *list_name*: ``{"ok", "error", "layer": {"key", "rank", "slug",
    "label", "file", "before", "after"}, "base", "groups": [{"lines", "devices"}],
    "unchanged": [{"device", "by"}], "refused": [{"device", "reasons"}], "devices":
    [{"device", "change", "pending", "command_hash"}], "headline", "hash"}``. Reads only;
    contacts no device; writes nothing."""
    import yaml

    from modules.nsot import bulk_intent as B
    from modules.nsot import hostvars, intent_layers as L, listref
    from modules.nsot import repo as R
    from routes.deploy import plan_devices

    out = {"ok": False, "error": "", "layer": {}, "base": "", "groups": [], "unchanged": [],
           "refused": [], "devices": [], "headline": "", "hash": ""}
    m = L._FILE.match(f"{layer_key}.yml")
    if not m:
        out["error"] = (f"{layer_key!r} is not a layer's name (network, or site-, role- or "
                        "tag-<slug>)")
        return out
    rank = "network" if m.group(1) == "network" else m.group(2)
    slug = m.group(3) or ""
    label = L.layer_label(rank, slug)
    if not steps:
        out["error"] = "the change has no steps"
        return out
    bad = B.unknown_paths(steps)
    if bad:
        out["error"] = ("the change names path(s) the schema does not know: "
                        + ", ".join(".".join(map(str, p)) for p in bad)
                        + "; refused before any device was read")
        return out
    repo = listref.resolve(list_name).repo_dir
    try:
        committed = {(r, s): d for r, s, _l, d in L._committed_layers(repo, "HEAD")}
    except L.LayersRefused as exc:
        out["error"] = f"the network's layers cannot be read: {exc}"
        return out
    before = copy.deepcopy(committed.get((rank, slug), {}))
    after, refused = apply_steps(before, steps)
    if refused:
        out["error"] = f"{label} does not hold what the change expected: " + "; ".join(refused)
        return out
    problems = L.problems(after)
    if problems:
        out["error"] = f"{label} cannot hold the result: " + "; ".join(problems)
        return out
    # Bulk intent's authoring gates, on the layer as a device's document would meet them.
    text = yaml.safe_dump(after, sort_keys=False)
    gate = hostvars.syslog_block_problems(after) + hostvars.description_problems(after) \
        + [msg for _n, msg in hostvars.contradiction_problems(after)]
    try:
        hostvars.assert_printable(text, label)
    except Exception as exc:                          # noqa: BLE001 (its words name the line)
        gate.append(str(exc))
    if gate:
        out["error"] = f"{label} would not be valid intent: " + "; ".join(gate)
        return out
    out["layer"] = {"key": layer_key, "rank": rank, "slug": slug, "label": label,
                    "file": L.layer_file(rank, slug), "before": before, "after": after}
    rc, head, _err = R.git(repo, "rev-parse", "HEAD")
    out["base"] = head if rc == 0 else ""

    try:
        from modules.nsot.restore import _devices_of
        rows = [r for r in _devices_of(list_name) if r.get("hostname")]
    except Exception as exc:                          # noqa: BLE001 (said, never guessed)
        out["error"] = (f"the inventory could not be read ({type(exc).__name__}: {exc}), so the "
                        "layer's devices are not known: no group is taken from an earlier read")
        return out
    proposal = [(rank, slug, label, after)]
    reached = sorted(r["hostname"] for r in rows if L.applicable(proposal, r))
    if not reached:
        out["error"] = f"{label} reaches no device of {list_name}: the inventory gives none its group"
        return out

    # The secret guard is keyed by device: the layer's text against every value each device it
    # reaches holds (`assert_no_secret_values` narrows by device, so a label would check none).
    for host in reached:
        try:
            hostvars.assert_no_secret_values(text, host)
        except Exception as exc:                      # noqa: BLE001 (its words name the line)
            out["error"] = f"the change names a secret value, never a reference: {exc}"
            return out

    from modules import neighbours
    docs, _why = neighbours.committed_intents(repo)        # every device's own, in two reads
    try:
        now = {e["device"]: e for e in plan_devices(list_name, reached)}
        with L.proposed(repo, rank, slug, after):
            new = {e["device"]: e for e in plan_devices(list_name, reached)}
            layers = L.read_layers(repo)
    except Exception as exc:                          # noqa: BLE001 (refused, by its words)
        log.warning("fleet change: %s on %s did not plan: %s", label, list_name, exc)
        out["error"] = f"the change does not render: {type(exc).__name__}: {exc}"
        return out
    by_row = {r["hostname"]: r for r in rows}
    origins = {host: L.merge(L.applicable(layers, by_row[host]), docs.get(host) or {})["from"]
               for host in reached}

    paths = [".".join(map(str, s["path"])) for s in steps]
    groups = {}
    for host in reached:
        n, o = new.get(host) or {}, now.get(host) or {}
        reasons = list(n.get("blocking_reasons") or [])
        if not n.get("deployable", True) or reasons:
            out["refused"].append({"device": host, "reasons": reasons or ["not deployable"]})
            continue
        had = set(o.get("to_add") or [])
        change = [line for line in n.get("to_add") or [] if line not in had]
        if not change:
            held = sorted({origins[host][p] for p in origins[host]
                           if any(p == q or p.startswith(q + ".") or p.startswith(q + "[")
                                  for q in paths) and origins[host][p] != label})
            out["unchanged"].append({"device": host, "by": ", ".join(held) or
                                     "nothing to send: the device already holds it"})
            continue
        out["devices"].append({"device": host, "change": change,
                               "pending": len(n.get("to_add") or []) - len(change),
                               "command_hash": n.get("command_hash", "")})
        groups.setdefault(tuple(change), []).append(host)
    out["groups"] = [{"lines": list(lines), "devices": hosts}
                     for lines, hosts in sorted(groups.items(), key=lambda g: (-len(g[1]), g[0]))]
    n_dev, n_grp = len(out["devices"]), len(out["groups"])
    out["headline"] = (f"{n_dev} device{'s' if n_dev != 1 else ''}, {n_grp} group"
                       f"{'s' if n_grp != 1 else ''}")
    out["hash"] = hashlib.sha256(json.dumps({
        "layer": layer_key, "before": before, "after": after, "base": out["base"],
        "devices": sorted((d["device"], d["command_hash"]) for d in out["devices"]),
        "unchanged": sorted(u["device"] for u in out["unchanged"]),
        "refused": sorted(r["device"] for r in out["refused"])},
        sort_keys=True, default=str).encode()).hexdigest()
    out["ok"] = True
    return out
