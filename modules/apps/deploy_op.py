"""The controller app deploy as ONE operation on the device-change lifecycle (P6; the signed board
docs/boards/controller-app-deploy.html; C2677): preview (`preview`: `channel.plan` for a
network's controller with the chosen set), confirm by the plan's hash as a verified person
(`start`), apply holding the controller for the whole operation (`run`), verify (the post-check,
`post_check.deploy`), rollback on a miss (the plan's own target), and record (the receipt,
`modules/controller_deploy_receipts`).

**What it reads (`Sources`).** The registered app versions (the registry, P4), the network's
controller host with its unit and listen address (NetBox's ``openflow`` Service), the host's
three shaped reads (`systemctl show`, `ls -la`, `systemctl cat`), the expected switches and
links (NetBox), and the controller's live read in the post-check's shape. They are one seam,
`Sources`; the production default is `modules/apps/sources.Wired` (C2765), each read from the
carrier Mercury has for it (that module's table), and the registry, which has none yet, refused
naming what is not built (``not_wired``). The screen draws a refusal as one, never an empty list
read as "nothing registered". `Unwired` answers every read ``not_wired``. A host read is a
person's: the preview's and the confirm's sources are made for the actor (`for_actor`).
`Sources.send` is the transport over the deploy account's plain session
(`modules/apps/transport.send`).

**The compile step (C2760).** Before the plan, each chosen app's start-time config is compiled
(`modules/apps/app_config.compile_set`: what its manifest declares under `compiled`, from the
expected switches' platform profiles, over the network's own config), so the plan stages it,
its sha256 rides in the request and the plan's hash, and the preview draws it with what each
switch's tables were placed from (``config_notes``). A config that cannot be compiled refuses
the preview, naming the app, the switch and why.

**The set.** Mercury's record of the controller's set (`deploy_receipts.record`, K2) is what
runs; a person chooses a version on an app's page, and the set previewed is the record with that
one change (`chosen_set`). The record's request is the plan's *previous* (the rollback target).
A plan whose drop-in after is the drop-in before changes nothing (`nothing_changes`): the
preview says so and offers the redeploy (K4), whose confirm names it.

**The confirm (`start`, `run`).** The job holds the controller (`management.HOST_DEPLOY`) for
the whole operation, so another deploy, a write or a Reload of it is refused by name while it
runs. Holding it, the plan is made again from the same set; a hash other than the confirmed one
sends nothing, declares no window and names what moved (`moved_words`, from the parts the
preview's form carried). Then `post_check.deploy`: the planned-restart window declared first
(`channel.window()`, the controller and its switches expected to drop), stage, the request, the
one command, the outcome, the post-check, and the rollback to the plan's target on a miss or an
apply that landed. The window is ended when the post-check (or the rollback's) passes, or when
nothing restarted; otherwise it runs to its end, and past it each switch not back is the SDN
reader's to raise. The receipt is written for every outcome, refusals included.
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
import threading
import time

log = logging.getLogger(__name__)

KIND = "controller app deploy"
#: The operation's steps, in order, as its manual page names them (docs/manual/how-it-works/
#: controller-app-deploy.md; tests/test_manual.py holds each to the page).
STEPS = ("plan", "confirm", "hold", "window", "stage", "command", "post-check", "rollback",
         "record")
ANNOUNCER = "controller-deploy"
#: Announced as the job moves (its running card redraws) and when it ends (the Apps tab, the
#: SDN reader's region and the restarts' windows read again).
PROGRESS_KEYS = ("controller_deploy",)
DONE_KEYS = ("controller_deploy", "sdn", "restarts")
_SET_ITEM = re.compile(r"^([a-z][a-z0-9_]{0,63})=([0-9A-Za-z.+-]{1,64})$")

_progress: dict = {}
_lock = threading.Lock()


class Refused(ValueError):
    """A preview or confirm refused, naming the comparison and both operands."""


# ── the sources (one seam) ────────────────────────────────────────────────────────────────────

class Sources:
    """What the operation reads, and the one write (`send`). Every read answers a dict with a
    ``state`` (``ok``, ``not_wired``, ``unreadable``, or for the stored read ``unread``: none
    is recorded yet) and its ``error`` in words."""

    def for_actor(self, actor: str) -> "Sources":
        """These sources for *actor*, the person a host read is held and recorded for."""
        return self

    def controllers(self, network: str) -> dict:
        """``{"state", "controllers": [{"name", "unit", "dev", "listen": {"host", "port"},
        "service": words, "connection", "problems": [words]}], "error"}``."""
        raise NotImplementedError

    def registered(self, network: str) -> dict:
        """``{"state", "apps": [{"name", "versions": [{"version": lifecycle.Version,
        "manifest": Manifest, "repo", "path", "rev", "commit", "reviewed_at"}]}], "repo":
        {"path", "commit", "fetched_at"}, "error"}``."""
        raise NotImplementedError

    def host_reads(self, network: str, controller: dict) -> dict:
        """``{"state", "show", "ls", "cat", "at", "error"}``: the three shaped reads."""
        raise NotImplementedError

    def expected(self, network: str, controller: dict) -> dict:
        """``{"state", "switches": [{"name", "dpid", "selected"}], "links": [...], "error"}``."""
        raise NotImplementedError

    def observe(self, network: str, controller: dict, apps: dict = None):
        """The controller read now in the post-check's shape (`post_check.evaluate`), or None;
        its ``health`` holds each of *apps* (``{name: its manifest's REST prefix}``,
        `health_prefixes`)."""
        raise NotImplementedError

    def controller_read(self, network: str, controller: dict) -> dict:
        """The stored read the Apps tab draws at rest: ``{"state", "at", "show", "cat",
        "health": {app: {"ok", "error"}}, "observed", "error"}``."""
        raise NotImplementedError

    def send(self, dev: dict, tplan: dict) -> dict:
        """`transport.send` over the deploy account's plain session to *dev*, which this thread
        holds."""
        from modules import connection
        from modules.apps import transport
        from modules.inventory.management import HOST_DEPLOY

        conn = connection.open_ssh(connection.stored_connection_params(dev),
                                   owner=f"{HOST_DEPLOY} {dev.get('hostname', '')}", plain=True)
        try:
            return transport.send(conn, tplan, ip=dev.get("ip") or "")
        finally:
            conn.disconnect()


#: What `Unwired` says behind each read; only ``registered`` is still unbuilt in production
#: (`modules/apps/sources.Wired` reads the rest, C2765).
NOT_WIRED = {
    "controllers": ("the network's controller host (NetBox's 'openflow' Service, its parent "
                    "device and the unit it runs) is not read for the deploy yet"),
    "registered": ("the app registry (P4) is not built: no app version is registered from the "
                   "network's code repository"),
    "host_reads": "the controller host's three reads are not wired to the deploy yet",
    "expected": ("the expected switches and links (NetBox's OpenFlow switches for this "
                 "controller and the cables between their OpenFlow ports) are not read yet"),
    "controller_read": ("the SDN reader does not read the controller's unit and its apps' "
                        "/health yet"),
}


class Unwired(Sources):
    """Sources with nothing wired: every read says what is not built, never "none"."""

    def _no(self, what, **extra):
        return dict({"state": "not_wired", "error": NOT_WIRED[what]}, **extra)

    def controllers(self, network):
        return self._no("controllers", controllers=[])

    def registered(self, network):
        return self._no("registered", apps=[], repo={})

    def host_reads(self, network, controller):
        return self._no("host_reads", show="", ls="", cat="", at=None)

    def expected(self, network, controller):
        return self._no("expected", switches=[], links=[])

    def observe(self, network, controller, apps=None):
        return None

    def controller_read(self, network, controller):
        return self._no("controller_read", at=None, show="", cat="", health={}, observed=None)


#: The sources in use: None until first asked, then `modules/apps/sources.Wired` (a test sets
#: its own).
SOURCES = None


def sources() -> Sources:
    global SOURCES
    if SOURCES is None:
        from modules.apps.sources import Wired
        SOURCES = Wired()
    return SOURCES


# ── the set ───────────────────────────────────────────────────────────────────────────────────

def parse_set(text: str) -> dict:
    """``{name: version}`` from the form's ``name=version,name=version``; refuses anything else,
    naming the item."""
    out = {}
    for item in [x.strip() for x in str(text or "").split(",") if x.strip()]:
        m = _SET_ITEM.match(item)
        if not m:
            raise Refused(f"the set's item {item[:80]!r} is not name=version")
        if m.group(1) in out:
            raise Refused(f"the set names {m.group(1)} twice")
        out[m.group(1)] = m.group(2)
    return out


def set_text(chosen: dict) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(chosen.items()))


def record_set(rec: dict) -> dict:
    """``{name: version}`` Mercury's record runs (`deploy_receipts.record`), {} with none."""
    req = (rec or {}).get("request") or {}
    return {a["name"]: a["version"] for a in req.get("apps") or []}


def chosen_set(rec: dict, app: str = "", version: str = "") -> dict:
    """The record's set with *app* at *version* (added when the record does not run it)."""
    out = record_set(rec)
    if app:
        out[app] = version
    return out


def changes(before: dict, after: dict) -> list:
    """``[{"name", "from", "to"}]`` for each app whose version moves, joins or leaves."""
    return [{"name": n, "from": before.get(n), "to": after.get(n)}
            for n in sorted(set(before) | set(after)) if before.get(n) != after.get(n)]


def change_words(ch: list) -> str:
    if not ch:
        return "no app changes"
    return ", ".join(f"{c['name']} {c['from']} → {c['to']}" if c["from"] and c["to"] else
                     f"{c['name']} {c['to']} added" if c["to"] else
                     f"{c['name']} {c['from']} left out" for c in ch)


# ── the preview ───────────────────────────────────────────────────────────────────────────────

def find_controller(network: str, name: str, src: Sources = None) -> dict:
    """``{"ok", "controller", "error"}``."""
    src = src or sources()
    got = src.controllers(network)
    if got.get("state") != "ok":
        return {"ok": False, "controller": None,
                "error": f"{network}'s controllers: {got.get('error') or got.get('state')}"}
    names = [c["name"] for c in got.get("controllers") or []]
    found = next((c for c in got["controllers"] if c["name"] == name), None)
    if found is None:
        return {"ok": False, "controller": None,
                "error": (f"no controller {name!r} in {network} (its controllers: "
                          f"{', '.join(names) or 'none'})")}
    return {"ok": True, "controller": found, "error": ""}


def _version_entry(registered: dict, name: str, version: str):
    app = next((a for a in registered.get("apps") or [] if a["name"] == name), None)
    if app is None:
        return None, (f"{name} is not a registered app (registered: "
                      f"{', '.join(a['name'] for a in registered.get('apps') or []) or 'none'})")
    entry = next((v for v in app["versions"] if v["version"].version == version), None)
    if entry is None:
        return None, (f"{name} has no registered version {version} (its versions: "
                      f"{', '.join(v['version'].version for v in app['versions']) or 'none'})")
    return entry, ""


def health_prefixes(manifests) -> dict:
    """``{name: rest prefix}`` for *manifests*: where each app's ``/health`` is read (its
    manifest's ``rest.prefix``, the one place it is declared, C2677)."""
    return {m.name: m.rest.prefix for m in manifests}


def sent_prefixes(request: dict, registered: dict) -> dict:
    """`health_prefixes` of the apps *request* runs, each version's manifest from *registered*
    (a put-back runs none of Mercury's); an app whose version is not registered is left out,
    and the post-check then says its /health was not read."""
    manifests = []
    for a in (request or {}).get("apps") or []:
        entry, _why = _version_entry(registered, a.get("name"), a.get("version"))
        if entry is not None:
            manifests.append(entry["manifest"])
    return health_prefixes(manifests)


def stage_set(registered: dict, chosen: dict, root: str) -> tuple:
    """``(items, refusals)``: each chosen version staged from its pinned revision's blobs into
    *root* (`channel.stage_published`), in `channel.plan`'s *enabled* shape."""
    from modules.apps import channel

    items, refusals = [], []
    for name, version in sorted(chosen.items()):
        entry, why = _version_entry(registered, name, version)
        if why:
            refusals.append(why)
            continue
        dest = f"{root}/{name}-{version}"
        try:
            got = channel.stage_published(entry["version"], entry["repo"], entry["path"],
                                          entry["rev"], dest)
        except channel.ChannelRefused as exc:
            refusals.append(f"{name} {version} could not be staged: {exc}")
            continue
        item = {"version": entry["version"], "manifest": entry["manifest"],
                "staged": got["staged"], "commit": entry.get("commit") or entry["rev"]}
        if entry.get("config") is not None:
            item["config"] = entry["config"]
        items.append(item)
    return items, refusals


def parts(plan: dict) -> dict:
    """The plan's hash in its parts (what a confirm carries, so a moved plan names what moved):
    ``{part: sha256}``."""
    def h(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()

    rb = plan.get("rollback") or {}
    return {"the request": plan.get("request_sha256", ""),
            "the drop-in before": h(plan.get("dropin_before", "")),
            "the drop-in after": h(plan.get("dropin_after", "")),
            "the unit": h(plan.get("unit", "")),
            "the expected switches, links and apps": h(plan.get("expected")),
            "the rollback target": h({"kind": rb.get("kind"),
                                      "request_sha256": rb.get("request_sha256"),
                                      "dropin_sha256": rb.get("dropin_sha256")})}


def moved_words(then: dict, now: dict) -> str:
    """Each part of the plan whose hash moved, both hashes short: "the drop-in before (3a7c…d912
    then, 5f02…e3aa now)"."""
    def short(x):
        return f"{x[:4]}…{x[-4:]}" if x and len(x) > 8 else (x or "none")

    moved = [f"{k} ({short(then.get(k))} then, {short(v)} now)" for k, v in now.items()
             if (then or {}).get(k) != v]
    return "; ".join(moved) or "no part the preview carried (its parts were not carried)"


def nothing_changes(plan: dict) -> bool:
    """A plan that changes no file and no line (K4): the drop-in after is the one before."""
    return bool(plan.get("ok")) and plan.get("dropin_before") == plan.get("dropin_after")


def build(network: str, controller_name: str, chosen: dict, *, root: str,
          src: Sources = None, observe: bool = True) -> dict:
    """The plan for *chosen* on the controller, staged into *root*: `channel.plan`'s answer with
    ``set``, ``record_set``, ``change``, ``record`` (K2's state), ``dev`` and ``refusals``
    gathered before the plan where a source could not answer."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import app_config, channel

    src = src or sources()
    base = {"ok": False, "network": network, "controller": controller_name,
            "set": dict(chosen), "refusals": []}
    found = find_controller(network, controller_name, src)
    if not found["ok"]:
        return dict(base, refusals=[found["error"]])
    ctl = found["controller"]
    rec = deploy_receipts.record(network, controller_name)
    base.update(record=rec, record_set=record_set(rec), change=changes(record_set(rec), chosen),
                dev=ctl.get("dev") or {}, listen=ctl.get("listen") or {})
    refusals = []
    if rec["state"] == "unreadable":
        refusals.append(f"{rec['words']}, so what a miss rolls back to is not known")
    if not chosen:
        refusals.append(f"the set is empty: {controller_name} would run no managed app")
    registered = src.registered(network)
    if registered.get("state") != "ok":
        refusals.append(f"the registered apps: {registered.get('error') or registered['state']}")
    host = src.host_reads(network, ctl)
    if host.get("state") != "ok":
        refusals.append(f"can't read {controller_name}: {host.get('error') or host['state']}")
    exp = src.expected(network, ctl)
    if exp.get("state") != "ok":
        refusals.append(f"what the post-check expects: {exp.get('error') or exp['state']}")
    if refusals:
        return dict(base, refusals=refusals)
    items, why = stage_set(registered, chosen, root)
    if why:
        return dict(base, refusals=why)
    # The compile step (C2760): each app's start-time config from its manifest's `compiled`
    # and the expected switches' platform profiles, in place on the items, so the plan stages
    # it and its sha256 rides in the request and the plan's hash.
    config_notes, why = app_config.compile_set(items, exp.get("switches") or [])
    if why:
        return dict(base, refusals=why, config_notes=config_notes)
    observed = src.observe(network, ctl, apps=health_prefixes(
        i["manifest"] for i in items)) if observe else None
    got = channel.plan(network=network, controller=controller_name, unit=ctl["unit"],
                       enabled=items, host=host, listen=ctl.get("listen") or {},
                       switches=exp.get("switches") or [], links=exp.get("links") or [],
                       previous=rec["request"] if rec["state"] == "ok" else None,
                       observed=observed)
    out = dict(base, **got)
    out["read_at"] = host.get("at")
    out["commits"] = {i["manifest"].name: i.get("commit", "") for i in items}
    out["switches"] = [{"name": s.get("name"), "dpid": s.get("dpid")}
                       for s in exp.get("switches") or []]
    out["manifests"] = {i["manifest"].name: i["manifest"] for i in items}
    out["config_notes"] = config_notes
    if got.get("ok"):
        out["parts"] = parts(got)
        out["nothing"] = nothing_changes(got)
        out["record_configs"] = deploy_receipts.configs_for(rec, rec.get("request"))
    return out


def preview(network: str, controller_name: str, chosen: dict, src: Sources = None) -> dict:
    """`build` into a throwaway folder, removed before it answers: a preview stages nothing on
    the controller and keeps nothing here. Writes nothing."""
    root = tempfile.mkdtemp(prefix="nmas-ctl-preview-")
    try:
        return build(network, controller_name, chosen, root=root, src=src)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def confirm_parts(plan: dict, redeploy: bool = False) -> dict:
    """The confirm button's words in parts (the template draws them around its own fixed
    words): ``{"redeploy", "what", "tail"}``, *what* the work ("of_versions 1.1.0", "2 apps"),
    *tail* a first deploy's missing rollback and what the post-check expects to recover (K3,
    K6)."""
    ch = plan.get("change") or []
    what = ("" if redeploy or not ch else
            f"{ch[0]['name']} {ch[0]['to']}" if len(ch) == 1 and ch[0]["to"] else
            f"{len(ch)} apps")
    tail = ""
    rb = plan.get("rollback") or {}
    if rb and rb.get("request") is None:
        tail += ", with no rollback"
    sick = [w.split(" ", 1)[1].rsplit("'s /health", 1)[0] for w in
            (plan.get("already") or {}).get("expecting") or [] if w.endswith("/health to recover")]
    if sick:
        tail += f", expecting {', '.join(sick)}'s /health to recover"
    return {"redeploy": not what, "what": what, "tail": tail}


def confirm_words(plan: dict, redeploy: bool = False) -> str:
    """What the confirm button says (one decision, one control): the work, the restart, and a
    first deploy's missing rollback or what the post-check expects to recover (K3, K6)."""
    p = confirm_parts(plan, redeploy)
    lead = "Redeploy the same set" if p["redeploy"] else f"Deploy {p['what']}"
    return f"{lead} and restart {plan.get('controller')}{p['tail']}"


# ── the confirm: the job ──────────────────────────────────────────────────────────────────────

class _Channel:
    """`post_check.deploy`'s channel over the held controller: ``stage(request)`` picks what is
    sent (the plan's own request with its staged files, or the plan's rollback target with the
    files its request names, staged again from their pins), ``apply()`` sends it and answers the
    script's outcome, ``{"ok": False, "command_sent": False}`` when the command never went, or
    ``{"ok": False, "unknown": True}`` when this run's outcome could not be read (K7)."""

    def __init__(self, plan, *, dev, src, registered, root, configs, progress):
        self.plan, self.dev, self.src, self.registered = plan, dev, src, registered
        self.root, self.configs, self.progress = root, configs, progress
        self.tplan = None

    def stage(self, req):
        if req == self.plan["request"]:
            self.tplan = self.plan
            self.progress("stage", "running")
            return
        rb = self.plan["rollback"]
        if req != rb.get("request"):
            raise Refused("the request asked for is neither the plan's nor its rollback target")
        self.progress("rollback", "running")
        if rb["kind"] == "dropin_before":
            self.tplan = {"ok": True, "request": req}
            return
        chosen = {a["name"]: a["version"] for a in req["apps"]}
        items, why = stage_set(self.registered, chosen, f"{self.root}/rollback")
        if why:
            raise Refused("the rollback target's apps could not be staged again: "
                          + "; ".join(why))
        by_name = {i["manifest"].name: i for i in items}
        for a in req["apps"]:
            got = by_name[a["name"]]["staged"]["sha256"]
            if got != a["sha256"]:
                raise Refused(f"{a['name']} {a['version']} stages as {got} now, and the request "
                              f"before recorded {a['sha256']}")
        self.tplan = {"ok": True, "request": req,
                      "files": {n: i["staged"]["files"] for n, i in by_name.items()},
                      "folders": {n: i["staged"]["folder"] for n, i in by_name.items()},
                      "configs": dict(self.configs)}

    def apply(self):
        self.progress("command", "running")
        r = self.src.send(self.dev, self.tplan) or {}
        self.progress("command", "done", sent=bool(r.get("command_sent")),
                      staged=len(r.get("staged") or []),
                      not_staged=len(r.get("not_staged") or []))
        summary = {k: r.get(k) for k in ("step", "error", "request_written", "command_sent")}
        summary["staged"] = len(r.get("staged") or [])
        summary["not_staged"] = len(r.get("not_staged") or [])
        if not r.get("command_sent"):
            return {"ok": False, "command_sent": False, "error": r.get("error") or "not sent",
                    "transport": summary}
        out, printed = r.get("outcome"), r.get("printed")
        if isinstance(out, dict) and printed == out:
            return dict(out, ok=bool(r.get("ok")), transport=summary,
                        **({"error": r.get("error")} if not r.get("ok") else {}))
        return {"ok": False, "unknown": True, "transport": summary,
                "error": r.get("error") or "this run's outcome was not read"}


def _step(job_id, name, state, **fields):
    with _lock:
        p = _progress.get(job_id)
        if p is None:
            return
        now = time.time()
        was = p["steps"].get(name) or {}
        p["steps"][name] = dict(was, state=state, at=now, since=was.get("since", now),
                                **fields)
    try:
        from modules import invalidation
        invalidation.announce(PROGRESS_KEYS, by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (the page asks again)
        log.info("controller deploy %s: progress not announced (%s)", job_id, exc)


def progress(job_id: str):
    """The running card's steps (artboard E), or None when this server has no record."""
    with _lock:
        p = _progress.get(job_id)
        return json.loads(json.dumps(p)) if p is not None else None


def _declare(network, record_into):
    from modules import restarts

    def declare(devices, start, end, by, why, unreachable):
        # The switches restart, so the window covers the far end of each of their links
        # (C2751); intent that cannot be read refuses it, and nothing is staged.
        from modules.neighbours import restart_far_ends
        far, err = restart_far_ends(network, devices)
        if err:
            return {"ok": False, "error": f"committed intent could not be read ({err}), so the "
                                          "far ends of the restarted switches' links cannot "
                                          "be told"}
        got = restarts.record_planned(devices, start, end, by, why, via=KIND,
                                      list_name=network, unreachable=unreachable, far_ends=far)
        if got.get("ok"):
            record_into["window"] = got.get("record") or {}
        return got
    return declare


def _end_window(network, window, by, why):
    from modules import restarts

    if not window:
        return {"ok": False, "error": "no window was recorded"}
    try:
        return restarts.end_planned(network, restarts.window_id(window), by=by, why=why, via=KIND)
    except Exception as exc:                          # noqa: BLE001 (the receipt says it)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


#: The outcomes after which the window is ended at once: nothing restarted, or everything back.
ENDS_WINDOW = {"deployed": "the deploy's post-check passed",
               "rolled back": "the rollback's post-check passed",
               "apply failed": "nothing restarted: the apply failed before the drop-in was written"}


def _summary(check):
    if not check:
        return None
    return {"ok": check.get("ok"), "words": check.get("words"), "polls": check.get("polls"),
            "elapsed_s": check.get("elapsed_s"), "after_restart": check.get("after_restart"),
            "came_back": check.get("came_back"), "bound": check.get("bound"),
            "origin": check.get("origin"), "last": check.get("last")}


def receipt_from(plan: dict, done: dict, *, actor: str, actor_verified: str, confirmed: str,
                 window: dict, ended: dict) -> dict:
    """The receipt (artboard H) from the plan and `post_check.deploy`'s answer."""
    from modules.apps import channel, post_check

    s = channel.script()
    rb = plan.get("rollback") or {}
    rec = plan.get("record") or {}
    before_receipt = rec.get("receipt") or {}
    return {
        "controller": plan.get("controller"), "actor": actor, "actor_verified": actor_verified,
        "confirmed_sha256": confirmed, "plan_sha256": plan.get("plan_sha256"),
        "outcome": done.get("outcome"), "error": done.get("error", ""),
        "landed": done.get("landed", ""),
        "set": plan.get("set"), "change": plan.get("change"),
        "change_words": change_words(plan.get("change") or []),
        "request": plan.get("request"), "request_sha256": plan.get("request_sha256"),
        "configs": plan.get("configs") or {},
        "before": {"kind": rb.get("kind"), "request": rb.get("request") if rb.get("kind") ==
                   "request" else None, "request_sha256": rb.get("request_sha256"),
                   "dropin_sha256": rb.get("dropin_sha256"), "words": rb.get("words"),
                   "receipt": before_receipt.get("id", "")},
        "before_configs": plan.get("record_configs") or {},
        "files": {n: [dict(f) for f in fs] for n, fs in (plan.get("files") or {}).items()},
        "folders_sha256": {a["name"]: a["sha256"] for a in
                           (plan.get("request") or {}).get("apps") or []},
        "commits": plan.get("commits") or {},
        "dropin": {"before_sha256": hashlib.sha256(
                       (plan.get("dropin_before") or "").encode()).hexdigest(),
                   "after_sha256": hashlib.sha256(
                       (plan.get("dropin_after") or "").encode()).hexdigest(),
                   "before": plan.get("dropin_before", ""), "after": plan.get("dropin_after", "")},
        "window": {"seconds": (plan.get("window") or {}).get("seconds"),
                   "from": (window or {}).get("from"), "until": (window or {}).get("until"),
                   "ended": bool((ended or {}).get("ok")),
                   "ended_error": "" if (ended or {}).get("ok") else (ended or {}).get("error", ""),
                   "words": channel.window()["words"]},
        "apply": {k: (done.get("apply") or {}).get(k) for k in
                  ("step", "error", "refused", "main_pid_before", "main_pid_after",
                   "up_after_s", "started", "finished")} if done.get("apply") else None,
        "steps": done.get("steps") or [],
        "post_check": _summary(done.get("post_check")),
        "rollback_target": done.get("rollback_target", ""),
        "rollback_post_check": _summary(done.get("rollback_post_check")),
        "bounds": {"post_check": post_check.bound(),
                   "unit_up_s": {"seconds": s.UP_BOUND_S, "measured": False,
                                 "source": "UP_BOUND_S in the apply script, a placeholder"}},
    }


def run(job_id: str, network: str, controller_name: str, chosen: dict, confirmed: str, *,
        then_parts: dict, actor: str, actor_verified: str, src: Sources = None,
        clock=time.monotonic, sleep=time.sleep, now=time.time) -> dict:
    """The confirm's work (module docstring): hold, plan again, compare, deploy, record."""
    from modules import controller_deploy_receipts as deploy_receipts
    from modules.apps import channel, post_check
    from modules.inventory.management import HOST_DEPLOY
    from modules.nsot import device_ops

    src = src or sources()
    with _lock:
        _progress.setdefault(job_id, {"network": network, "controller": controller_name,
                                      "set": dict(chosen), "plan_sha256": confirmed,
                                      "actor": actor, "started": time.time(), "steps": {}})
    root = tempfile.mkdtemp(prefix="nmas-ctl-deploy-")
    holder = {}

    def mark(name, state, **fields):
        _step(job_id, name, state, **fields)

    def refused(words, plan=None):
        mark("plan", "failed", words=words)
        base = plan or {"controller": controller_name, "set": chosen}
        return {"controller": controller_name, "actor": actor, "actor_verified": actor_verified,
                "confirmed_sha256": confirmed, "plan_sha256": base.get("plan_sha256", ""),
                "outcome": "refused", "error": words, "set": chosen,
                "change": base.get("change") or [],
                "change_words": change_words(base.get("change") or []), "steps": []}

    try:
        found = find_controller(network, controller_name, src)
        dev = (found.get("controller") or {}).get("dev") or {}
        account = channel.script().DEPLOY_USER
        if not found["ok"]:
            receipt = refused(found["error"])
        elif (dev.get("device_type") or "") != "linux" or (dev.get("username") or "") != account:
            receipt = refused(f"{controller_name}'s driver is {dev.get('device_type')!r} and its "
                              f"login {dev.get('username')!r}; the deploy needs 'linux' and the "
                              f"deploy account {account!r}. Nothing was sent")
        else:
            try:
                with device_ops.hold(network, controller_name, HOST_DEPLOY, actor,
                                     detail=confirmed, ip=dev.get("ip") or ""):
                    receipt = _held(job_id, network, controller_name, chosen, confirmed,
                                    then_parts=then_parts, actor=actor,
                                    actor_verified=actor_verified, src=src, root=root,
                                    dev=dev, ctl=found["controller"], holder=holder,
                                    mark=mark, refused=refused, clock=clock, sleep=sleep,
                                    now=now)
            except device_ops.DeviceBusy as exc:
                receipt = refused(f"{controller_name} is held by another operation ({exc}). "
                                  "Nothing was sent; this is not queued")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    mark("record", "running")
    wrote = deploy_receipts.write(network, receipt)
    mark("record", "done" if wrote["ok"] else "failed", words=wrote["error"])
    return {"ok": True, "receipt_id": wrote["id"], "outcome": receipt.get("outcome"),
            "written": wrote["ok"], "error": wrote["error"]}


def _held(job_id, network, controller_name, chosen, confirmed, *, then_parts, actor,
          actor_verified, src, root, dev, ctl, holder, mark, refused, clock, sleep, now):
    from modules.apps import post_check

    mark("plan", "running")
    # What is already missing is a live read outside the hash (`channel.plan_hash`), drawn at
    # the preview; the confirm's plan does not read the controller again for it.
    plan = build(network, controller_name, chosen, root=root, src=src, observe=False)
    if not plan.get("ok"):
        return refused("the plan made again at the confirm is refused: "
                       + "; ".join(plan.get("refusals") or []), plan)
    if plan["plan_sha256"] != confirmed:
        what = moved_words(then_parts or {}, plan["parts"])
        return refused(f"the plan made again at the confirm, holding {controller_name}, has "
                       f"hash {plan['plan_sha256']}, and you confirmed {confirmed}. What moved: "
                       f"{what}. Nothing was staged or sent", plan)
    mark("plan", "done", words=plan["plan_sha256"])
    registered = src.registered(network)
    adapter = _Channel(plan, dev=dev, src=src, registered=registered, root=root,
                       configs=plan.get("record_configs") or {},
                       progress=lambda n, st, **f: mark(n, st, **f))
    polls = {"n": 0}
    planned = health_prefixes((plan.get("manifests") or {}).values())

    def read():
        # Each app's /health under the prefix its manifest declares, for the set last sent:
        # the plan's, or after a rollback's staging its target's (`sent_prefixes`).
        sent = adapter.tplan
        apps = planned if sent is None or sent is plan else \
            sent_prefixes(sent.get("request") or {}, registered)
        polls["n"] += 1
        observed = src.observe(network, ctl, apps=apps) or {}
        got = post_check.evaluate(plan["expected"], observed)
        mark("post-check", "running", reads=polls["n"],
             missing_switches=len(got["missing_switches"]),
             missing_links=len(got["missing_links"]), unhealthy=len(got["unhealthy"]),
             unreadable=len(got["unreadable"]))
        return observed

    declare = _declare(network, holder)
    mark("window", "running")
    done = post_check.deploy(plan, channel=adapter, read=read, declare_window=declare,
                             by=actor, clock=clock, sleep=sleep, now=now)
    mark("window", "done" if holder.get("window") else "failed")
    ended = {}
    if done.get("outcome") in ENDS_WINDOW and holder.get("window"):
        ended = _end_window(network, holder["window"], actor, ENDS_WINDOW[done["outcome"]])
    mark("post-check", "done" if done.get("outcome") == "deployed" else "failed",
         words=done.get("error", ""))
    return receipt_from(plan, done, actor=actor, actor_verified=actor_verified,
                        confirmed=confirmed, window=holder.get("window"), ended=ended)


def start(network: str, controller_name: str, chosen: dict, confirmed: str, *,
          then_parts: dict, actor: str, actor_verified: str) -> str:
    """Start the confirm's job and return its id at once (the operation takes minutes: a
    restart and every switch's reconnect)."""
    from modules.nsot import capture_job

    # The running cards' steps are kept as long as their jobs are (capture_job.KEEP_S).
    with _lock:
        cutoff = time.time() - capture_job.KEEP_S
        for old in [k for k, v in _progress.items() if v.get("started", 0) < cutoff]:
            _progress.pop(old, None)

    def work(job_id):
        # The job's host reads (the plan made again, holding the controller) are the actor's.
        return run(job_id, network, controller_name, chosen, confirmed, then_parts=then_parts,
                   actor=actor, actor_verified=actor_verified,
                   src=sources().for_actor(actor))

    label = f"{controller_name}: {set_text(chosen)}"
    job = capture_job.start(network, label, actor, work, kind=KIND, announce_keys=DONE_KEYS,
                            announcer=ANNOUNCER)
    log.info("controller deploy %s on %s of %s started by %s", job, controller_name, network,
             actor)
    return job
