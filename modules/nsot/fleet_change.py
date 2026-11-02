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


def _chained(text: str) -> list:
    """Each configuration line keyed by its section chain (`interface Gi2` › ` description x`),
    in order, so a nested line is never mistaken for the same text under another section."""
    out, stack = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line in ("!", "end"):
            continue
        depth = len(raw) - len(raw.lstrip())
        while stack and stack[-1][0] >= depth:
            stack.pop()
        out.append(tuple(s[1] for s in stack) + (line,))
        stack.append((depth, line))
    return out


def _rendered(list_name: str, host: str) -> tuple:
    """``(keyed lines, captured)``: the device's render as the deploy builds it, masked, its
    lines keyed (`_chained`), and the configuration it was captured with."""
    from routes.deploy import _artifact_for

    built, _error = _artifact_for(list_name, host)
    return (_chained(built[0].rendered_masked), built[1]) if built else ([], "")


def left_on_device(was: list, now: list, captured: str) -> list:
    """The lines a change leaves on a device (C2302): rendered before it (*was*), not after it
    (*now*), and held by the device (*captured*); merge-only never removes them. A line with a
    secret is masked in the render and kept by the device, so it never matches and is not named
    here (removing an account is phase 4's, measured)."""
    after, held = set(now), set(_chained(captured))
    return [" › ".join(k) for k in was if k not in after and k in held]


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
           "refused": [], "devices": [], "headline": "", "hash": "", "steps": []}
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
    # A form's path is dotted text ("users", "snmp.settings"); the core's is a list.
    steps = [dict(s, path=s["path"].split(".") if isinstance(s["path"], str) else list(s["path"]))
             for s in steps]
    out["steps"] = steps
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

    # A controller-managed switch is configured only through its SDN controller (PHASE8_PLAN
    # 17.1 S12): the layer's group is read here, never named by the request, so each such device
    # is refused in the plan, in the authority's own words, and the run never sends to one.
    from modules.sdn import authority
    by_name = {r["hostname"]: r for r in rows}
    for host in list(reached):
        auth = authority.of(by_name[host], list_name)
        if auth["kind"] == "controller":
            out["refused"].append({"device": host, "reasons": [auth["words"]]})
            reached.remove(host)

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
        was = {h: _rendered(list_name, h) for h in reached}
        with L.proposed(repo, rank, slug, after):
            new = {e["device"]: e for e in plan_devices(list_name, reached)}
            then = {h: _rendered(list_name, h)[0] for h in reached}
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
        # What the change leaves on the device (C2302): lines the device holds that its render
        # had before the change and no longer has. Merge-only never removes them, so the plan
        # names them, as a device's own Deploy… names what is left on the device.
        left = left_on_device(was[host][0], then[host], was[host][1])
        out["devices"].append({"device": host, "change": change, "left": left,
                               "pending": len(n.get("to_add") or []) - len(change),
                               "command_hash": n.get("command_hash", "")})
        groups.setdefault((tuple(change), tuple(left)), []).append(host)
    out["groups"] = [{"lines": list(lines), "left": list(left), "devices": hosts}
                     for (lines, left), hosts in sorted(groups.items(),
                                                        key=lambda g: (-len(g[1]), g[0]))]
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


#: What a fleet change's plan job announces when it ends (`invalidation.ANNOUNCERS`).
ANNOUNCE_KEYS = ("fleet_change",)
ANNOUNCER = "fleet-change"


def plan_start(list_name: str, layer_key: str, steps: list, actor: str) -> str:
    """Start `plan_layer` as a job (a plan reads every reached device's program, so it is a job,
    never a request's work: the scale rule) and return its id at once. Its payload is the plan,
    masked on the way out; the job announces `fleet_change` when it ends."""
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    def work(_job):
        return mask_payload(plan_layer(list_name, layer_key, steps))
    return capture_job.start(list_name, f"Plan {layer_key}'s change", actor, work,
                             kind="fleet change plan", announce_keys=ANNOUNCE_KEYS,
                             announcer=ANNOUNCER)


# ---------------------------------------------------------------------------
# (d) The approval and the run (PHASE8_PLAN 22.2 (3) and (4)).
# ---------------------------------------------------------------------------

#: What a run announces as each batch ends: the plan card's own key, and what a deploy moves.
RUN_KEYS = ("fleet_change", "deploy_job", "device_state", "baselines", "drift", "rolled_back",
            "goldens", "remote", "intent", "approvals")
RUN_ANNOUNCER = "fleet-change-run"
#: After the canary: wait for a person's Go on (the default), or carry on.
AFTER_CANARY = ("pause", "go")


def approve(list_name: str, layer_key: str, steps: list, confirmed_hash: str, *,
            summary: str, reason: str, actor: str) -> dict:
    """The approval (22.2 (3)): under the repository's lock, recompute the plan, refuse when its
    hash is not the one confirmed (naming both), then write the layer's file and make ONE
    commit (`repo.commit`, Source `fleet-change`). ``{"ok", "error", "commit", "plan"}``; the
    plan is the recomputed one, its devices' program hashes what the run must send. Sends
    nothing."""
    import os

    import yaml

    from modules.nsot import listref
    from modules.nsot import repo as R

    if not (summary or "").strip():
        return {"ok": False, "error": "a one-line summary is needed: it becomes the commit's "
                                      "subject"}
    if not (reason or "").strip():
        return {"ok": False, "error": "a reason is needed: it is recorded with the commit"}
    repo = listref.resolve(list_name).repo_dir
    with R.repo_lock(repo):
        plan = plan_layer(list_name, layer_key, steps)
        if not plan["ok"]:
            return {"ok": False, "error": f"the plan cannot be made now: {plan['error']}"}
        if plan["hash"] != confirmed_hash:
            return {"ok": False, "plan": plan, "error": (
                f"the plan moved since you read it (confirmed {confirmed_hash[:10]}, now "
                f"{plan['hash'][:10]}): a device, its intent, a layer or the repository changed. "
                "Nothing was committed or sent; plan again and read the new plan")}
        if not plan["devices"]:
            return {"ok": False, "plan": plan, "error": "no device's program changes: there is "
                                                         "nothing to run"}
        rel = plan["layer"]["file"]
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(yaml.safe_dump(plan["layer"]["after"], sort_keys=False))
        devices = ", ".join(d["device"] for d in plan["devices"])
        message = (f"{summary.strip()}\n\n{plan['layer']['label']}: {reason.strip()}\n\n"
                   f"Actor: {actor}\nSource: fleet-change\nPlan: {plan['hash']}\n"
                   f"Devices: {devices}\n")
        try:
            R.stage_exactly(repo, [rel])              # a writer stages exactly its file
            rc, sha, err = R.commit(repo, message, list_name=list_name, paths=[rel],
                                    source="fleet-change", actor=actor)
        except R.StagesMoreThanItWrote as exc:
            rc, sha, err = 1, "", str(exc)
        if rc != 0 or not sha:
            # The file put back as committed, byte for byte (a new layer's file removed), so
            # the working tree holds nothing nobody committed.
            got, text, _e = R.git_raw(repo, "show", f"HEAD:{rel}")
            if got == 0:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            elif os.path.exists(path):
                os.remove(path)
            return {"ok": False, "plan": plan,
                    "error": f"the layer could not be committed: {err or rc}. Nothing was sent"}
    return {"ok": True, "error": "", "commit": sha, "plan": plan}


def batches_of(devices: list, canary: str, size: int) -> list:
    """The run's order: the canary alone, then the rest in batches of *size*, in plan order."""
    rest = [d for d in devices if d != canary]
    size = max(1, int(size or 1))
    return [[canary]] + [rest[i:i + size] for i in range(0, len(rest), size)]


def run_batches(list_name: str, plan: dict, batches: list, *, actor: str, actor_kind: str,
                on_device=None) -> dict:
    """Run *batches* in order through THE apply (`routes.deploy.apply_batch`: each device's
    program recomputed and refused if it moved, held, sent, verified, rolled back on failure,
    recorded), the first failed device stopping the run (22.2 (4)). Before each batch, each
    device's program as committed must be the one the plan confirmed. ``{"results":
    [{"device", "outcome", ...}], "stopped": reason or "", "done": [batch index]}``; devices not
    reached are ``unattempted``."""
    from modules.nsot.deploy import DEPLOYED, UNATTEMPTED
    from routes.deploy import apply_batch, plan_devices

    planned = {d["device"]: d["command_hash"] for d in plan["devices"]}
    out = {"results": [], "stopped": "", "done": []}
    for n, batch in enumerate(batches):
        if out["stopped"]:
            out["results"] += [{"device": d, "outcome": UNATTEMPTED,
                                "reason": f"not attempted: {out['stopped']}"} for d in batch]
            continue
        entries = {e["device"]: e for e in plan_devices(list_name, batch)}
        moved = [d for d in batch if (entries.get(d) or {}).get("command_hash") != planned.get(d)]
        if moved:
            out["stopped"] = (f"{', '.join(moved)}'s program is not the one approved: plan "
                              "again")
            out["results"] += [{"device": d, "outcome": UNATTEMPTED,
                                "reason": f"not sent: {out['stopped']}"} for d in batch]
            continue
        report = apply_batch(list_name, {d: entries[d]["capture_hash"] for d in batch},
                             {d: entries[d]["command_hash"] for d in batch}, actor=actor,
                             actor_kind=actor_kind, on_device=on_device, stop_at_first=True)
        results = report.get("results") or []
        out["results"] += results
        out["done"].append(n)
        failed = [r["device"] for r in results
                  if r.get("outcome") != DEPLOYED or (r.get("verify") or {}).get("ok") is False]
        if failed:
            out["stopped"] = f"{', '.join(failed)} did not deploy and verify"
    return out


def approve_and_run_start(list_name: str, layer_key: str, steps: list, confirmed_hash: str, *,
                          summary: str, reason: str, canary: str, batch: int,
                          after_canary: str, actor: str, actor_kind: str) -> str:
    """The approval and the run's first part as ONE job (the approval recomputes the plan, which
    reads every reached device, so it is never a request's work): `approve`, then the canary
    alone (and every batch after it when *after_canary* is ``go``). A refused approval is the
    job's ``refused`` payload, naming why, nothing committed or sent."""
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    def work(_job):
        got = approve(list_name, layer_key, steps, confirmed_hash, summary=summary,
                      reason=reason, actor=actor)
        if not got["ok"]:
            return mask_payload({"state": "refused", "error": got["error"]})
        plan = got["plan"]
        hosts = [d["device"] for d in plan["devices"]]
        first = canary if canary in hosts else hosts[0]
        batches = batches_of(hosts, first, batch)
        return _run(list_name, plan, got["commit"], batches, after_canary=after_canary,
                    actor=actor, actor_kind=actor_kind, start_at=0)
    return capture_job.start(list_name, f"Approve and run {layer_key}'s change", actor, work,
                             kind="fleet change run", announce_keys=RUN_KEYS,
                             announcer=RUN_ANNOUNCER)


def _run(list_name: str, plan: dict, commit: str, batches: list, *, after_canary: str,
         actor: str, actor_kind: str, start_at: int) -> dict:
    """One job's part of the run, its masked payload: the canary alone when pausing after it,
    else every batch from *start_at*."""
    from modules.outbound import mask_payload

    todo = batches[start_at:start_at + 1] if (start_at == 0 and after_canary == "pause") \
        else batches[start_at:]
    got = run_batches(list_name, plan, todo, actor=actor, actor_kind=actor_kind)
    paused = (start_at == 0 and after_canary == "pause" and not got["stopped"]
              and len(batches) > 1)
    return mask_payload({"state": "paused" if paused else
                         ("stopped" if got["stopped"] else "done"),
                         "commit": commit, "plan": plan, "batches": batches,
                         "next": start_at + len(todo), "results": got["results"],
                         "stopped": got["stopped"], "actor": actor})


def run_start(list_name: str, plan: dict, commit: str, batches: list, *, after_canary: str,
              actor: str, actor_kind: str, start_at: int = 0) -> str:
    """Start the run as a job from batch *start_at*: the canary first (``start_at`` 0), then, if
    *after_canary* is ``go``, every batch; ``pause`` stops after the canary for a person's Go
    on, which starts the rest (``start_at`` 1). Its payload is masked; it announces
    `RUN_KEYS` when it ends."""
    from modules.nsot import capture_job

    def work(_job):
        return _run(list_name, plan, commit, batches, after_canary=after_canary, actor=actor,
                    actor_kind=actor_kind, start_at=start_at)
    return capture_job.start(list_name, f"Run {plan['layer']['label']}'s change", actor, work,
                             kind="fleet change run", announce_keys=RUN_KEYS,
                             announcer=RUN_ANNOUNCER)
