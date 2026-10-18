"""Templatize: the rollback record's notes and bulk intent's core, with no routes of their own
(its coverage report went at 7.8; Templates › Coverage is its home; today's committed-intent
editor went at 7.8 on 2026-10-17, P7-23: each device's Intent tab; today's seed, revert and
retry routes went the same day, P7-24: each device page's Actions).

Bulk intent's core (`bulk_plan_of`, `bulk_apply_of`) lives here for v2's Change a setting, and
`rolled_back_notes` for Needs attention. The monitoring profile's JSON routes (GET
/templatize/profile, POST /templatize/profile/propose/preview and /apply) left at 7.8 on
2026-10-17 (P7-27; restore point tag `pre-remove/v1-pages`) with today's index, whose Needs
attention panel's Propose… was their one caller: Monitoring › Profile (`/v2/monitoring/profile`)
proposes, previews and commits through the same `modules/nsot/profile_propose.py`.
"""

import logging
import os

log = logging.getLogger(__name__)


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


# Seed intent (C148): today's two routes (POST /seed/preview and /seed/apply) left at 7.8 on
# 2026-10-17 (P7-24; restore point tag `pre-remove/v1-actions`). Its home is each device page's
# Actions › Seed intent… (`routes/device_v2.py`), over the same `modules/nsot/seed.py`.


# Committed intent: today's intent editor's three routes (GET and POST /committed/<host>, POST
# /committed/<host>/preview) left at 7.8 on 2026-10-17 (P7-23; restore point tag
# `pre-remove/v1-editors`). Their home is each device's Intent tab (`routes/intent_v2.py`),
# over the same `modules/nsot/intent_edit.py`.


# Revert and retry: today's four routes (POST /revert/preview and /revert/apply, POST
# /retry/preview and /retry/apply) left at 7.8 on 2026-10-17 (P7-24; restore point tag
# `pre-remove/v1-actions`). Their home is each device page's Actions, Revert intent… and Retry
# rolled-back change… (`routes/device_v2.py`), over the same `modules/nsot/intent_ops.py`.


# The two JSON reads of the rollback record (GET /rolled-back and /rolled-back/retries) left
# at 7.8 on 2026-10-15: no page called them. Needs attention draws the blocked devices from
# `rolled_back_notes` below, and History draws each retry (`history_sources`).


#: The applicability words that mean a note no longer blocks anything.
STALE_APPLICABILITY = ("no committed intent", "no longer applies")


def note_applicability(list_name: str, hostname: str, *, has_intent: bool = None) -> str:
    """Whether *hostname*'s rolled-back note blocks a plan NOW, in words:
    ``blocking``, ``no longer applies``, ``no committed intent`` or
    ``unknown``. The one per-device classifier: the list below and the
    Device page's revert and retry (7.3) all ask it."""
    from modules.nsot import hostvars
    from routes.deploy import _artifact_for, _current_program

    repo = _repo_for(list_name)
    if has_intent is None:
        has_intent = hostname in set(hostvars.list_committed(repo))
    if not has_intent:
        # A note for a device with no committed intent is planned by
        # nothing; it is history, not a block.
        return "no committed intent"
    try:
        built, _error = _artifact_for(list_name, hostname)
        program = _current_program(built[0], built[1]) if built else None
    except Exception as exc:              # noqa: BLE001
        log.warning("templatize: could not compute %s's program to test "
                    "its rolled-back note (%s) — reporting it as standing",
                    hostname, exc)
        return "unknown"
    if program is None:
        return "unknown"
    if hostvars.rolled_back_note(repo, hostname, program):
        return "blocking"
    return "no longer applies"


def rolled_back_notes(list_name: str) -> dict:
    """``{applies, stale, unreadable}`` for *list_name*'s rolled-back notes.

    The listing used to report every stored record, because
    ``rolled_back_note()`` without a program returns the raw note — which is
    correct for reading one, and wrong for answering "what is blocked". An
    operator saw "s4 is rolled back" beside a plan that said s4 was deployable.

    A note applies while the program a fresh plan would send still contains the
    lines that failed. Evaluating that means computing each device's program,
    which is why this is done here rather than in the store: the store should
    not need a renderer to answer a question about its own contents. The work
    is per NOTED device, bounded by the rollbacks on record, never by the
    inventory.

    An UNREADABLE record (C158) blocks every plan, and is answered ONCE here,
    before any device is planned: asked per device, it would return the same
    blocking note for each and plan the whole fleet to say one thing.
    """
    from modules.nsot import hostvars

    repo = _repo_for(list_name)
    record = hostvars._load_rolled_back(repo)
    if "__unreadable__" in record:
        return {"applies": {}, "stale": {},
                "unreadable": hostvars._unreadable_note(repo, record["__unreadable__"])["reason"]}
    applies, stale = {}, {}
    committed = set(hostvars.list_committed(repo))
    for hostname in sorted(record):
        raw = record[hostname]
        applicability = note_applicability(list_name, hostname,
                                           has_intent=hostname in committed)
        (stale if applicability in STALE_APPLICABILITY else applies)[hostname] = {
            **raw, "applicability": applicability}
    return {"applies": applies, "stale": stale, "unreadable": ""}


# ---------------------------------------------------------------------------
# Bulk intent (NSOT_PLAN P.1b): one structured change, N devices, ONE commit
# ---------------------------------------------------------------------------

def _bulk_inputs(data: dict):
    """(list_name, repo, devices, steps, error). The list is CARRIED, never
    derived: this ends in a commit, and a write may not infer its list."""
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return None, None, None, None, (
            "list_name is required -- a bulk intent change ends in a commit, "
            "and the list it commits into is stated, never inferred")
    devices = [str(d).strip() for d in (data.get("devices") or []) if str(d).strip()]
    steps = []
    for raw in data.get("steps") or []:
        path = raw.get("path")
        if isinstance(path, str):
            path = [p for p in path.split(".") if p]
        if not isinstance(path, list) or not path or "before" not in raw \
                or "after" not in raw:
            return None, None, None, None, (
                "each step needs path (a list), before and after -- use "
                '{"__absent__": true} for a key that is not there')
        steps.append({"path": path, "before": raw["before"],
                      "after": raw["after"]})
    if not devices:
        return None, None, None, None, "no devices named"
    # From the registry, never `get_list_data_dir()`, which creates the
    # directory: a mistyped list name must be refused, not brought into being.
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists
    match = next((l for l in get_device_lists() if l["name"] == list_name), None)
    if match is None:
        return None, None, None, None, f"no device list named {list_name!r}"
    return (list_name, os.path.join(LISTS_DIR, match["filename"], "config_repo"),
            devices, steps, "")


def _bulk_render_and_eligible(list_name: str, repo: str):
    from modules.device import load_saved_devices
    from modules.nsot import hostvars, manifest, templates_repo
    from routes.templates import (_captured_golden, _platform_for as _platform_of_host,
                                  artifact_for)

    from modules.config import LISTS_DIR
    from modules.device import get_device_lists
    match = next((l for l in get_device_lists() if l["name"] == list_name), None)
    inventory = ({d.get("hostname") for d in load_saved_devices(
        os.path.join(LISTS_DIR, match["filename"], "devices.csv"))}
        if match else set())
    pending = {p.get("name") for p in manifest.pending_devices(repo)}

    def eligible(host):
        if host in pending:
            return "pending onboarding -- not reached yet"
        if host not in inventory:
            return "not in this list's inventory (stale, or a typo)"
        return ""

    def render(host, host_vars):
        # Its committed golden only (C683): never the backup store, which retires at 7.8.
        capture, _a = _captured_golden(host, list_name)
        if not capture:
            raise RuntimeError("no golden is recorded for it yet to render against (its "
                               "page's Capture records one)")
        platform = _platform_of_host(host, list_name)       # this list's row (C495)
        from modules.nsot.platform import UnknownPlatform, is_dialect
        if not is_dialect(platform):
            from routes.templates import unknown_platform_words
            raise UnknownPlatform(unknown_platform_words(host, list_name))
        template = templates_repo.template_for_device(repo, host, platform)
        from modules.nsot import profile as _profile
        art = artifact_for(host, capture, repo, platform, template,
                           host_vars=hostvars.hydrate_secrets(
                               _profile.effective_for(repo, list_name, host, host_vars, platform),
                               host, list_name))
        return art.rendered_masked, art.deployable, art.blocking_reasons

    return render, eligible


def bulk_plan_of(data: dict) -> tuple:
    """THE bulk intent preview, for v2's Devices › Change a setting:
    ``(report, status)``; the report keeps each accepted device's new text (``text``) for a
    caller that draws the intent's diff, and names its list."""
    from modules.nsot import bulk_intent

    list_name, repo, devices, steps, error = _bulk_inputs(data)
    if error:
        return {"ok": False, "error": error}, 400
    render, eligible = _bulk_render_and_eligible(list_name, repo)
    report = bulk_intent.plan(repo, devices, steps, render=render,
                              eligible=eligible,
                              summary=data.get("summary", ""))
    return {**report, "list_name": list_name, "repo": repo}, (200 if report["ok"] else 400)


def bulk_apply_of(data: dict, actor: str) -> tuple:
    """THE bulk intent apply, for v2's Devices › Change a setting: ``(result, status)``."""
    from modules.nsot import bulk_intent

    list_name, repo, devices, steps, error = _bulk_inputs(data)
    if error:
        return {"ok": False, "error": error}, 400
    render, eligible = _bulk_render_and_eligible(list_name, repo)
    result = bulk_intent.apply(list_name, repo, devices, steps,
                               str(data.get("confirmed_hash") or ""),
                               render=render, eligible=eligible,
                               summary=data.get("summary", ""), actor=actor)
    return result, (200 if result.get("ok") else 409)


# The JSON routes (POST /bulk/preview and /bulk/apply) left at 7.8 on 2026-10-15: no page
# called them. Their home is v2's Devices › Change a setting (`routes/bulk_intent_v2.py`),
# which calls the two functions above.
