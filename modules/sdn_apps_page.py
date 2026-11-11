"""SDN › Apps: a network's controllers and their managed apps, an app's page, the deploy's plan,
its running card, its result and its receipt (P6; the signed board
docs/boards/controller-app-deploy.html, artboards A to H, J and L; C2677). Reads only: the
operation is `modules/apps/deploy_op.py`, the record `modules/controller_deploy_receipts.py`.

What each card draws comes from three places, each said where it is drawn: Mercury's record of
the controller's set (the receipts, K2), the registered app versions and the controller's stored
read (`deploy_op.Sources`; a source not wired yet is drawn as such, naming what is not built,
never as an empty list), and, for a plan, `channel.plan`'s answer.
"""

import logging
import re

log = logging.getLogger(__name__)

#: The table's groups, in the order a person acts on them (artboard A).
GROUPS = (("health", "/health failing"), ("drift", "Differs from Mercury's record"),
          ("newer", "A newer Published version"), ("as_recorded", "Running as recorded"),
          ("not_in_set", "Registered, not in the set"))
#: A receipt's outcome as a badge: its words and its colour. Green only for deployed.
OUTCOME_TONE = {"deployed": "ok", "rolled back": "warn", "rollback failed": "danger",
                "not rolled back": "danger", "apply failed": "danger", "unknown": "muted",
                "refused": "danger"}
OUTCOME_WORDS = {"deployed": "Deployed", "rolled back": "Rolled back",
                 "rollback failed": "Rollback failed", "not rolled back": "Not rolled back",
                 "apply failed": "Failed", "unknown": "Unknown", "refused": "Refused"}
_NUM = re.compile(r"\d+")


def vkey(version: str) -> tuple:
    """A version's sort key: its numbers in order, then the text (so 1.10.0 is after 1.9.0)."""
    return tuple(int(n) for n in _NUM.findall(str(version))), str(version)


def short(sha: str) -> str:
    sha = str(sha or "")
    return f"{sha[:4]}…{sha[-4:]}" if len(sha) > 8 else (sha or "none")


def _apps_words(req) -> str:
    return ", ".join(f"{a['name']} {a['version']}" for a in (req or {}).get("apps") or []) \
        or "no managed app"


def _versions(registered: dict, name: str) -> list:
    app = next((a for a in registered.get("apps") or [] if a["name"] == name), None)
    return sorted(app["versions"] if app else [], key=lambda v: vkey(v["version"].version))


def _newest(entries, state="published"):
    pub = [e for e in entries if e["version"].state == state]
    return pub[-1] if pub else None


def _drift_rows(rec: dict, read: dict, unit: str) -> dict:
    """Artboard J's table: each app and the User and the drop-in, Mercury's record against what
    the unit says, from what systemd holds. ``{"state": "ok"|"drift"|"unreadable"|"none",
    "rows", "words"}``."""
    from modules.apps import channel, post_check

    if (read or {}).get("state") != "ok":
        return {"state": "unread", "rows": [],
                "words": (read or {}).get("error") or "the controller has not been read"}
    if rec.get("state") != "ok":
        return {"state": "none", "rows": [], "words": rec.get("words", "")}
    s = channel.script()
    shown = channel.parse_show(read.get("show"))
    if not shown["readable"]:
        return {"state": "unreadable", "rows": [],
                "words": (f"{unit}'s command line cannot be read, so drift can't be told "
                          f"(`systemctl show` answered no ExecStart or User line)")}
    want = {a["name"]: a["version"] for a in rec["request"]["apps"]}
    have = post_check.running_apps(shown["argv"], s.APPS_ROOT)
    rows = []
    for name in sorted(set(want) | set(have)):
        rows.append({"what": name, "record": want.get(name, "not in the set"),
                     "unit": have.get(name, "not loaded"),
                     "differs": want.get(name) != have.get(name)})
    rows.append({"what": "User", "record": s.RYU_USER, "unit": shown["user"] or "(none)",
                 "differs": (shown["user"] or "") != s.RYU_USER})
    rendered = channel.render_dropin(rec["request"], shown["exec_path"] or shown["argv"][0])
    before = channel.dropin_before(read.get("cat"), unit)
    rows.append({"what": "The drop-in",
                 "record": f"the render of request {short(s.request_sha256(rec['request']))}",
                 "unit": "that render" if before == rendered else "not that render",
                 "differs": before != rendered})
    differs = [r for r in rows if r["differs"]]
    return {"state": "drift" if differs else "ok", "rows": rows,
            "words": ("what systemd holds for the unit; the running process's own command line "
                      "is not among the host's reads, so a unit changed and not yet restarted "
                      "reads as changed here")}


def _receipt_line(r: dict) -> dict:
    if not r:
        return {}
    return {"id": r.get("id"), "at": r.get("at"), "by": r.get("actor"),
            "tone": OUTCOME_TONE.get(r.get("outcome"), "muted"),
            "outcome_words": OUTCOME_WORDS.get(r.get("outcome"), r.get("outcome") or "?"),
            "change": r.get("change_words") or "", "slowest": _slowest(r)}


def _slowest(r: dict) -> str:
    pc = r.get("post_check") or {}
    after = pc.get("after_restart") or {}
    if not after:
        return ""
    dpid, secs = max(after.items(), key=lambda kv: kv[1])
    return f"{len(after)} switches back, the slowest {dpid} at {secs:g} s after the restart"


def controller_card(network: str, ctl: dict, registered: dict, src, *, open_app: str = "") -> dict:
    """Artboard A's controller card and its apps table (and J's drift), for one controller."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import deploy_op

    name = ctl["name"]
    rec = deploy_receipts.record(network, name)
    got = deploy_receipts.read(network, name, limit=50)
    rows = got["rows"]
    read = src.controller_read(network, ctl)
    drift = _drift_rows(rec, read, ctl.get("unit", ""))
    chip = {"ok": ("runs Mercury's record", "ok"), "drift": ("differs from Mercury's record",
                                                             "warn"),
            "unreadable": ("can't tell", "muted"), "unread": ("not read", "muted"),
            "none": ("no deploy through Mercury", "muted")}[drift["state"]]
    order = {a["name"]: i + 1 for i, a in enumerate(((rec.get("request") or {})
                                                     .get("apps")) or [])}
    running = deploy_op.record_set(rec)
    health = (read or {}).get("health") or {}
    names = sorted({a["name"] for a in registered.get("apps") or []} | set(running))
    drifted = {r["what"] for r in drift["rows"] if r["differs"]}
    groups = {k: [] for k, _ in GROUPS}
    for app in names:
        entries = _versions(registered, app)
        newest = _newest(entries)
        draft = _newest(entries, "draft")
        h = health.get(app)
        row = {"name": app, "running": running.get(app), "order": order.get(app),
               "newest": newest["version"].version if newest else "",
               "newest_by": newest["version"].reviewer if newest else "",
               "draft": draft["version"].version if draft and (
                   not newest or vkey(draft["version"].version) > vkey(
                       newest["version"].version)) else "",
               "openflow": ", ".join((newest or (entries[-1] if entries else {})).get(
                   "manifest").openflow_versions) if entries else "",
               "health": ({"ok": bool(h.get("ok")), "status": h.get("status", ""),
                           "error": h.get("error", "")} if isinstance(h, dict) else None)}
        if app in running and h is not None and not h.get("ok"):
            key, chip_words = "health", ("/health failing", "danger")
        elif app in drifted:
            key, chip_words = "drift", ("differs from the record", "warn")
        elif app in running and newest and vkey(newest["version"].version) > vkey(running[app]):
            key, chip_words = "newer", (f"{newest['version'].version} Published", "info")
        elif app in running:
            key, chip_words = "as_recorded", ("as recorded", "ok")
        else:
            key, chip_words = "not_in_set", ("not in the set", "muted")
        row["state"] = chip_words
        groups[key].append(row)
    summary = {"enabled": len(running),
               "health": len(groups["health"]), "newer": len(groups["newer"]),
               "drafts": sum(1 for g in groups.values() for r in g if r["draft"]),
               "drift": len(groups["drift"])}
    last = _receipt_line(rows[0]) if rows else {}
    listen = ctl.get("listen") or {}
    return {"name": name, "unit": ctl.get("unit", ""),
            "listen": {"host": listen.get("host"), "port": listen.get("port")},
            "service": ctl.get("service", ""),
            "dev": {"hostname": (ctl.get("dev") or {}).get("hostname", "")},
            "record": {"state": rec["state"], "words": rec["words"]},
            "record_words": _apps_words(rec.get("request")),
            "receipts_state": got["state"], "receipts_error": got.get("error", ""),
            "last": last, "read": {"at": (read or {}).get("at")}, "drift": drift, "chip": chip,
            "groups": [(k, label, groups[k]) for k, label in GROUPS if groups[k]],
            "summary": summary, "redeploy_set": deploy_op.set_text(running)}


def app_page(network: str, ctl: dict, registered: dict, app: str, chosen: str = "") -> dict:
    """Artboard B: an app's versions as registered and what the chosen one declares, with the
    one action, the preview of deploying the chosen Published version (the record's set with
    that one change)."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import deploy_op

    rec = deploy_receipts.record(network, ctl["name"])
    running = deploy_op.record_set(rec).get(app)
    entries = _versions(registered, app)
    receipts = deploy_receipts.read(network, ctl["name"], limit=200)["rows"]
    rows = []
    for e in reversed(entries):
        v = e["version"]
        until = next((r.get("at") for r in receipts if r.get("outcome") == "deployed"
                      and any(c["name"] == app and c["from"] == v.version
                              for c in r.get("change") or [])), "")
        rows.append({"version": v.version, "state": v.state, "reviewer": v.reviewer,
                     "reviewed_at": e.get("reviewed_at", ""),
                     "commit": (e.get("commit") or e.get("rev") or "")[:7],
                     "sha": v.content_sha256, "running": v.version == running,
                     "ran_until": until, "deployable": v.state == "published",
                     # C2854: the newest test run at this hash, and the publication's own words.
                     "test": e.get("test"), "self_review": bool(v.self_review)})
    pick = chosen or running or next((r["version"] for r in rows if r["deployable"]), "")
    entry = next((e for e in entries if e["version"].version == pick), None)
    m = entry["manifest"] if entry else None
    declares = None
    if m is not None:
        declares = {"controllers": ", ".join(f"{k} {v}" for k, v in m.controllers.items()),
                    "openflow": ", ".join(m.openflow_versions),
                    "requires": ", ".join(m.requires) or "nothing",
                    "rest": [{"path": f"{m.rest.prefix}{e.path}", "methods": " ".join(e.methods),
                              "health": e.path == "/health"} for e in m.rest.endpoints],
                    "owns": (f"cookie prefix {m.owns_flows.cookie_prefix}"
                             + (f"; classes {', '.join(m.owns_flows.classes)}"
                                if m.owns_flows.classes else "; no protected class"))
                    if m.owns_flows else "no flows of its own declared",
                    "egress": "; ".join(e.words() for e in m.egress) or "none",
                    "summary": m.summary}
    chosen_set = deploy_op.chosen_set(rec, app, pick) if pick else {}
    return {"name": app, "controller": ctl["name"], "running": running, "versions": rows,
            "pick": pick, "pick_deployable": bool(entry and entry["version"].state ==
                                                  "published"),
            "declares": declares, "set": deploy_op.set_text(chosen_set),
            "registered": bool(entries)}


def _dhcp_card(network: str):
    """The DHCP steering card at rest, or None where the network has no NSOT export to read
    (it is NetBox's view of a network; a network whose devices are not NetBox's has none)."""
    from modules.inventory import source_config
    from modules.sdn import dhcp_steer

    try:
        if (source_config.load(network) or {}).get("source") != source_config.SOURCE_NETBOX:
            return None
        return dhcp_steer.view(dhcp_steer.card(network))
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn apps: the DHCP steering card for %s failed (%s)", network,
                  type(exc).__name__)
        return {"network": network, "state_card": "rest", "server": None, "counts": None,
                "edge_switches": [], "hosts": 0, "steered_switches": 0, "protected": "",
                "error": f"the card could not be read ({type(exc).__name__})"}


def apps_view(network: str, args=None) -> dict:
    """The Apps tab's region: ``g`` for `v2/_sdn_apps.html`."""
    from modules.apps import deploy_op, draft_write
    from modules.nsot import export_op

    args = args or {}
    src = deploy_op.sources()
    listed = src.controllers(network)
    registered = src.registered(network)
    repo = registered.get("repo") or {}
    out = {"tab": "apps", "network": network, "state": listed.get("state"),
           "error": listed.get("error", ""), "registered_state": registered.get("state"),
           "registered_error": registered.get("error", ""),
           "registered_problems": list(registered.get("problems") or []),
           "repo": {"path": repo.get("path", ""), "commit": repo.get("commit", ""),
                    "fetched_at": repo.get("fetched_at", "")},
           # Board nsot-export, artboards A and B: the committed export, from its history.
           "export": dict(export_op.last(network), state_card="rest"),
           # Board authoring-from-words F: Add an app as a Draft… at rest (the setting only).
           "draft": draft_write.control(network),
           # Board lab9-sdn B (C2904): DHCP steering at rest, from the export and the store.
           "dhcp": _dhcp_card(network),
           "controllers": [], "app": None, "receipt": None}
    if listed.get("state") != "ok":
        return out
    want = (args.get("controller") or "").strip()
    for ctl in listed.get("controllers") or []:
        card = controller_card(network, ctl, registered, src, open_app=args.get("app") or "")
        out["controllers"].append(card)
        if args.get("app") and (not want or want == ctl["name"]):
            out["app"] = app_page(network, ctl, registered, args["app"], args.get("v") or "")
    if args.get("receipt"):
        from modules import controller_deploy_receipts as deploy_receipts
        r = deploy_receipts.get(network, args["receipt"])
        out["receipt"] = receipt_card(r) if r else {"missing": args["receipt"]}
    return out


# ── the plan (artboards C and D) ──────────────────────────────────────────────────────────────

def _dropin_lines(before: str, after: str) -> list:
    """The drop-in after, line by line, each marked added or kept, with the before's lines that
    left marked removed (the plan's before-and-after, artboard C)."""
    import difflib

    out = []
    for line in difflib.ndiff((before or "").splitlines(), (after or "").splitlines()):
        tag, text = line[:2], line[2:]
        if tag == "? ":
            continue
        out.append({"kind": {"+ ": "add", "- ": "del"}.get(tag, "same"), "text": text})
    return out


def config_cards(plan: dict, s) -> list:
    """Each app's start-time config as the plan stages it (C2760), in load order: ``[{"app",
    "version", "path", "sha", "text", "notes", "state"}]``, *text* the staged JSON laid out to
    read and masked by Mercury's redaction on the way out (the compile refuses a config holding
    a secret, so nothing should mask), *state* ``new`` (the controller's record holds none for
    the app), ``changed`` or ``same`` against the config the record last sent, *s* the apply
    script (its APPS_ROOT and CONFIG_SUFFIX: where the file goes)."""
    import json

    from modules import redact

    staged = plan.get("configs") or {}
    before = plan.get("record_configs") or {}
    notes = plan.get("config_notes") or {}
    out = []
    for a in (plan.get("request") or {}).get("apps") or []:
        text = staged.get(a["name"])
        if text is None:
            continue
        shown = json.dumps(json.loads(text), indent=2, sort_keys=True)
        was = before.get(a["name"])
        out.append({"app": a["name"], "version": a["version"],
                    "path": f"{s.APPS_ROOT}/{a['name']}/{a['version']}{s.CONFIG_SUFFIX}",
                    "sha": a.get("config_sha256", ""), "text": redact.redact_text(shown),
                    "notes": list(notes.get(a["name"]) or []),
                    "state": "new" if was is None else "same" if was == text else "changed"})
    return out


def _sdk_card(plan: dict, s) -> dict:
    """The app SDK the request names (C2852, option A), as the plan card draws it: its folder
    on the controller, its hash and its files; None for a request naming none."""
    sdk = plan.get("sdk") or {}
    sha = ((plan.get("request") or {}).get("sdk") or {}).get("sha256")
    if not sha:
        return None
    return {"sha": sha, "path": s.sdk_folder(s.APPS_ROOT, sha) + "/",
            "files": list(sdk.get("files") or [])}


def plan_card(plan: dict, redeploy: bool = False) -> dict:
    """The plan card, its refusals, or the plan that changes nothing (artboards C and D)."""
    from modules.apps import channel, deploy_op, post_check

    ctl = plan.get("controller")
    if not plan.get("ok"):
        return {"state": "refused", "controller": ctl, "network": plan.get("network"),
                "refusals": plan.get("refusals") or [], "set": deploy_op.set_text(
                    plan.get("set") or {})}
    s = channel.script()
    nothing = plan.get("nothing") and not redeploy
    req = plan["request"]
    files = plan.get("files") or {}
    change = plan.get("change") or []
    changed = {c["name"] for c in change}
    rows = []
    for i, a in enumerate(req["apps"], 1):
        c = next((x for x in change if x["name"] == a["name"]), None)
        rows.append({"n": i, "name": a["name"], "version": a["version"],
                     "from": c["from"] if c else None, "changed": a["name"] in changed,
                     "commit": (plan.get("commits") or {}).get(a["name"], "")[:7],
                     "sha": a["sha256"], "files": len(files.get(a["name"]) or []),
                     "config": bool(a.get("config_sha256"))})
    new_files = [{"app": a["name"], "version": a["version"], "files": files.get(a["name"])}
                 for a in req["apps"] if a["name"] in changed]
    configs = config_cards(plan, s)
    config_state = {c["app"]: c["state"] for c in configs}
    for r in rows:
        r["config_state"] = config_state.get(r["name"], "")
    conf = plan.get("conformance") or {}
    rb = plan.get("rollback") or {}
    names = {sw.get("dpid"): sw.get("name") for sw in plan.get("switches") or []}
    already = plan.get("already") or {}
    win = channel.window()
    bound = post_check.bound()
    rec = plan.get("record") or {}
    dev, folder = plan.get("dev") or {}, plan.get("folder") or {}
    listen = plan.get("listen") or {}
    kept, ryu = plan.get("kept") or {}, post_check.ryu_bound()
    return {
        "state": "nothing" if nothing else "preview", "network": plan.get("network"),
        "controller": ctl, "unit": plan.get("unit"),
        "title": (f"Deploy to {ctl}: " + (deploy_op.change_words(change) if change else
                                         "no app changes")),
        "sub": (f"{len(change)} app{'s' if len(change) != 1 else ''} change"
                f"{'s' if len(change) == 1 else ''}, {len(req['apps']) - len(change)} stay as "
                f"they run. The controller restarts, so all {len(names)} switch"
                f"{'es' if len(names) != 1 else ''} drop and reconnect."),
        "dev": {"ip": dev.get("ip", ""), "device_type": dev.get("device_type", "")},
        "listen": {"host": listen.get("host"), "port": listen.get("port")},
        "user_now": plan.get("user_now"),
        "folder": {"owner": folder.get("owner", ""), "group": folder.get("group", ""),
                   "mode": folder.get("mode", "")},
        "apps_root": s.APPS_ROOT, "account": s.DEPLOY_USER, "read_at": plan.get("read_at"),
        "rows": rows, "new_files": new_files, "configs": configs,
        "sdk": _sdk_card(plan, s),
        "file_count": sum(len(v or []) for v in files.values()), "folder_count": len(files),
        "conformance": {"offered": ", ".join(conf.get("offered") or []),
                        "hello": (conf.get("offered") or ["?"])[-1],
                        "checked": [{"switch": x.get("switch"), "common": x.get("common") or [],
                                     "rejects_above": x.get("rejects_above")}
                                    for x in conf.get("checked") or []],
                        "count": len(names)},
        "dropin_path": f"{s.DROPIN_ROOT}/{plan.get('unit')}.d/{s.DROPIN_NAME}",
        "dropin": _dropin_lines(plan.get("dropin_before"), plan.get("dropin_after")),
        "up_bound": s.UP_BOUND_S, "up_bound_words": s.UP_BOUND_SOURCE,
        "ryu_bound": {"seconds": ryu["seconds"], "words": ryu["words"]},
        "bound": {"seconds": bound["seconds"], "measured": bound["measured"],
                  "words": bound["words"]},
        # What of the unit's own command line the drop-in carries (`channel.kept`; C2675,
        # C2985): REST's bind in words, each app the unit loads that Mercury does not manage
        # ("kept: ..." or "replaced: ..."), its other flags, and where the OpenFlow listen moves.
        "kept": {"rest_words": kept.get("rest_words", ""),
                 "listen_words": kept.get("listen_words", ""),
                 "flag_words": kept.get("flag_words", ""),
                 "apps": [{"state": a.get("state"), "words": a.get("words", "")}
                          for a in kept.get("apps") or []],
                 "note": kept.get("note", "")},
        "expected_switches": [{"name": names.get(d) or "?", "dpid": d}
                              for d in plan["expected"]["switches"]],
        "expected_links": [post_check._link_words(x) for x in plan["expected"]["links"]],  # noqa: SLF001
        "expected_apps": plan["expected"]["apps"],
        "already": {"read": already.get("read"), "expecting": already.get("expecting") or [],
                    "words": already.get("words", "")},
        "window": {"words": win["words"]}, "window_seconds": win["seconds"],
        "rollback_words": rb.get("words", ""), "rollback_none": rb.get("request") is None,
        "record_state": rec.get("state"), "record_words": rec.get("words", ""),
        "hash": plan["plan_sha256"], "short": short(plan["plan_sha256"]),
        "parts": plan.get("parts") or {},
        "set": deploy_op.set_text(plan.get("set") or {}),
        "cw": deploy_op.confirm_parts(plan, redeploy=bool(redeploy) or not change),
        "command": f"sudo -n {channel.INSTALLED}",
    }


# ── running and the result (artboards E, F and G) ─────────────────────────────────────────────

#: The running card's steps, in the order they run (artboard E's stepper).
RUN_STEPS = (("plan", "Plan made again, holding the controller"),
             ("window", "Window declared"), ("stage", "Stage (SFTP as the deploy account)"),
             ("command", "The one command, and its outcome"), ("post-check", "Post-check"),
             ("rollback", "Rollback, on a miss"), ("record", "Record"))


def _step_note(key: str, st: dict) -> str:
    """What a running or finished step says beside it (artboard E): the post-check's counts
    as the last read found them, the staging's files, a failure's words."""
    if key == "post-check" and st.get("reads"):
        return (f"{st.get('reads')} read{'s' if st.get('reads') != 1 else ''}: "
                f"{st.get('missing_switches', 0)} switch(es), {st.get('missing_links', 0)} "
                f"link(s) and {st.get('unhealthy', 0)} /health not back yet"
                + (f", {st['unreadable']} unreadable" if st.get("unreadable") else ""))
    if key == "command" and st.get("state") == "done":
        return (f"{st.get('staged', 0)} file(s) staged, {st.get('not_staged', 0)} not; the "
                f"command {'sent' if st.get('sent') else 'not sent'}")
    return str(st.get("words") or "")[:300] if st.get("state") == "failed" else ""


def run_card(job_id: str) -> dict:
    """A confirm's card by its job: running (the steps as they go) or its result (the receipt),
    or unknown to this server (a restart loses the job; the receipt is the record)."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import deploy_op
    from modules.nsot import capture_job

    job = capture_job.get(job_id)
    p = deploy_op.progress(job_id) or {}
    if job is None:
        return {"state": "lost", "job": job_id}
    if job["state"] == "running":
        from modules import run_stepper as RS

        got = p.get("steps") or {}
        steps = []
        for key, words in RUN_STEPS:
            st = got.get(key) or {}
            state = {"running": "running", "done": "done", "failed": "failed"}.get(
                st.get("state"), "waiting")
            took = round(st["at"] - st["since"], 1) if st.get("since") and st.get("at") else None
            steps.append(RS.step(key, words, state, took_s=took, note=_step_note(key, st)))
        model = RS.card([RS.row(p.get("controller") or "?", "running", steps, device=False)],
                        label="Controller app deploy", key="controller-deploy")
        # The model as the one stepper draws it (its counts and total are for a card that
        # groups many rows; a deploy has one).
        model = {k: v for k, v in model.items() if k not in ("counts", "total")}
        model["rows"] = [{k: v for k, v in r.items() if k != "elapsed_s"}
                         for r in model.get("rows") or []]
        model["groups"] = []                     # one row: never grouped (`card`'s grouped)
        return {"state": "running", "job": job_id, "controller": p.get("controller"),
                "actor": p.get("actor"), "short": short(p.get("plan_sha256")),
                "hash": p.get("plan_sha256"), "run": model}
    payload = job.get("payload") or {}
    if job["state"] == "failed":
        return {"state": "failed", "job": job_id, "error": job.get("error", "")}
    r = deploy_receipts.get(p.get("network") or job.get("list"), payload.get("receipt_id"))
    if r is None:
        return {"state": "failed", "job": job_id,
                "error": payload.get("error") or "its receipt could not be read"}
    return dict(result_card(r), job=job_id, write_error=payload.get("error", ""))


def _switch_rows(check: dict) -> list:
    after = (check or {}).get("after_restart") or {}
    out = [{"dpid": d, "secs": s} for d, s in sorted(after.items(), key=lambda kv: kv[1])]
    if out:
        out[-1]["slowest"] = True
    return out


def result_card(r: dict) -> dict:
    """Artboards F and G from a receipt: the outcome first, in its colour (green only when
    every expected switch, link and app came back)."""
    outcome = r.get("outcome")
    pc, rbc = r.get("post_check") or {}, r.get("rollback_post_check") or {}
    before = r.get("before") or {}
    titles = {
        "deployed": f"Deployed: {r.get('controller')} runs {r.get('change_words') or 'the set'}",
        "rolled back": "Rolled back to the request before" if before.get("kind") == "request"
        else "Rolled back: the drop-in before was put back",
        "rollback failed": f"Rollback failed: {r.get('controller')} is not back as it was",
        "not rolled back": "Post-check missed: nothing was rolled back",
        "apply failed": "Not deployed: stopped before the drop-in was written",
        "unknown": f"{r.get('controller')}'s deploy: the outcome is not known",
        "refused": "Not deployed: refused before anything was sent"}
    apply = r.get("apply") or {}
    win = r.get("window") or {}
    return {"state": "result", "id": r.get("id"), "outcome": outcome,
            "tone": OUTCOME_TONE.get(outcome, "muted"),
            "outcome_words": OUTCOME_WORDS.get(outcome, outcome or "?"),
            "title": titles.get(outcome, outcome or "?"), "controller": r.get("controller"),
            "error": r.get("error", ""), "post_check": {"words": pc.get("words", "")},
            "rollback_post_check": {"words": rbc.get("words", "")},
            "switches": _switch_rows(pc),
            "apply": {"main_pid_before": apply.get("main_pid_before"),
                      "main_pid_after": apply.get("main_pid_after"),
                      "up_after_s": apply.get("up_after_s")},
            "window": {"from": win.get("from"), "until": win.get("until"),
                       "ended": win.get("ended")},
            "breakglass": (outcome == "not rolled back"),
            # K7: an unknown outcome offers the rollback as a preview, never run by itself:
            # the set before (the request the deploy would have rolled back to).
            "network": r.get("network", ""),
            "rollback_set": (",".join(f"{a['name']}={a['version']}" for a in
                                      (before.get("request") or {}).get("apps") or [])
                             if outcome == "unknown" and before.get("kind") == "request"
                             else ""),
            "row": outcome in ("unknown", "rollback failed", "not rolled back")}


def receipt_card(r: dict) -> dict:
    """Artboard H's receipt: the deploy's whole record, masked again on the way out."""
    from modules import controller_deploy_receipts as deploy_receipts

    r = deploy_receipts.masked(r)
    req = r.get("request") or {}
    before = r.get("before") or {}
    files = r.get("files") or {}
    dropin = r.get("dropin") or {}
    apply = r.get("apply") or {}
    win = r.get("window") or {}
    up = (r.get("bounds") or {}).get("unit_up_s") or {}
    listen = req.get("listen") or {}
    return {"id": r.get("id"), "at": r.get("at"), "controller": r.get("controller"),
            "tone": OUTCOME_TONE.get(r.get("outcome"), "muted"),
            "outcome_words": OUTCOME_WORDS.get(r.get("outcome"), r.get("outcome") or "?"),
            "actor": r.get("actor"), "actor_verified": r.get("actor_verified"),
            "plan": r.get("plan_sha256"),
            "request": short(r.get("request_sha256")), "request_apps": _apps_words(req),
            "listen": {"host": listen.get("host"), "port": listen.get("port")},
            "before": {"receipt": before.get("receipt", "")},
            "before_words": (f"request {short(before.get('request_sha256'))} "
                             f"({_apps_words(before.get('request'))})"
                             if before.get("kind") == "request" else
                             (before.get("words") or "none recorded")),
            "files": sum(len(v or []) for v in files.values()), "folders": len(files),
            "dropin": {"before_sha256": dropin.get("before_sha256", ""),
                       "after_sha256": dropin.get("after_sha256", "")},
            "window": {"from": win.get("from"), "until": win.get("until"),
                       "ended": win.get("ended"), "ended_error": win.get("ended_error", "")},
            "apply": ({k: apply.get(k) for k in ("started", "finished", "main_pid_before",
                                                 "main_pid_after", "up_after_s", "error",
                                                 "refused")} if apply else {}),
            "post_check": {"words": (r.get("post_check") or {}).get("words", "")},
            "rollback_post_check": {"words": (r.get("rollback_post_check") or {})
                                    .get("words", "")},
            "bounds": {"unit_up_s": {"seconds": up.get("seconds"),
                                     "measured": up.get("measured")}} if up else {},
            "steps": [{"step": s.get("step"), "ok": s.get("ok")} for s in r.get("steps") or []],
            "error": r.get("error", ""), "change": r.get("change_words", "")}
