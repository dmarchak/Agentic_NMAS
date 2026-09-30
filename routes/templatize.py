"""Templatize blueprint: the coverage report, SEED INTENT, and committed intent.

Phase 3a made it read-only (extractions to a gitignored staging area) and 3b
added a reviewed commit. Both halves had no screen, and the commit refused
anything without a verified person, so seeding a device's first intent had no
working path (C148). Seed intent replaces them as one previewed, confirmed
operation; the intent editor, revert, retry and bulk intent commit here too.
"""

import logging
import os

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("templatize", __name__, url_prefix="/templatize")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


def _platform_for(device: dict) -> str:
    """The device's config dialect.

    Previously this returned the platform map's ``netmiko_device_type``, which
    is the session driver rather than the config dialect — the same conflation
    corrected in modules/nsot/platform.py.
    """
    from modules.nsot.platform import platform_for_device
    return platform_for_device(device)


@bp.route("/report", methods=["GET", "POST"])
def report():
    """Round-trip coverage for every device with a golden config.

    Reads golden configs only — it opens no SSH session and writes nothing.
    """
    from modules.ai_assistant import _list_golden_configs, _load_golden_config_file
    from modules.device import get_current_device_list, load_saved_devices
    from modules.nsot.roundtrip import rank_unmodeled, validate_device

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)

    try:
        _name, csv_path = get_current_device_list()
        devices = {d.get("ip", ""): d for d in load_saved_devices(csv_path)}

        reports, errors = [], []
        for entry in _list_golden_configs():
            ip = entry.get("device_ip", "")
            config = _load_golden_config_file(ip)
            if not config:
                continue
            device = devices.get(ip, {})
            result = validate_device(config, _platform_for(device))
            if result.get("error"):
                errors.append({"hostname": entry.get("hostname", ip),
                               "error": result["error"]})
                continue
            reports.append(result)

        summary = _summarise(reports)
        return jsonify({
            "ok": True, "list": list_name,
            "devices": [_public(r) for r in reports],
            "summary": summary,
            "unmodeled_ranked": rank_unmodeled(reports),
            "errors": errors,
        })
    except Exception as exc:                  # noqa: BLE001
        log.exception("templatize: report failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Seed intent (C148): a device's first full intent, from its committed golden
# ---------------------------------------------------------------------------
#
# It replaces extract, staged, rendered and the reviewed commit: four routes
# with no screen, the last refusing anything without a verified person, so no
# onboarded device could be made deployable from the interface. One operation
# now, previewed and confirmed by hash (modules/nsot/seed.py).

@bp.route("/seed/preview", methods=["POST"])
def seed_preview():
    """What seeding each device would commit. Reads git only: no session, no
    write. No `devices` is every device in the list whose intent is absent or
    only the bootstrap."""
    from modules.nsot import seed
    from modules.nsot.restore import _devices_of
    from modules.outbound import mask_payload
    from modules.preview_confirm import seed_preview as _parts

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)        # a read may derive its list
    inventory = _devices_of(list_name)
    wanted = [d for d in (data.get("devices") or []) if d]
    unknown = sorted(set(wanted) - {d.get("hostname") for d in inventory})
    if unknown:
        return jsonify({"ok": False, "error": f"not in {list_name}: {', '.join(unknown)}"}), 404
    devices = [d for d in inventory if not wanted or d.get("hostname") in set(wanted)]
    entries = [seed.public(seed.entry_for(list_name, d)) for d in devices]
    if not wanted:
        entries = [e for e in entries if e["intent_state"] != seed.FULL]
        if not entries:
            return jsonify({"ok": True, "list": list_name, "preview": None,
                            "nothing": (f"Every device in {list_name} has full committed "
                                        f"intent ({len(devices)} device(s)): nothing to seed.")})
    for e in entries:
        e["list"] = list_name
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "preview": _parts(entries, request=request), "nothing": ""}))


@bp.route("/seed/apply", methods=["POST"])
def seed_apply():
    """Seed the confirmed devices: each golden parsed AGAIN, one whose seed
    moved refused, ONE commit of exactly the seeded files as the verified
    person. The list is CARRIED from the preview, never derived: this ends
    in a commit, and a write may not infer its list."""
    from modules.nsot import seed
    from modules.nsot.restore import _devices_of
    from modules.outbound import mask_payload
    from modules.preview_confirm import seed_result

    data = request.get_json(silent=True) or {}
    list_name = (data.get("list_name") or "").strip()
    if not list_name:
        return jsonify({"ok": False, "error": (
            "No list named: a seed commits intent into one list's repository, so the "
            "list comes from the preview that was confirmed, never from whichever "
            "list is active. Nothing was committed.")}), 400
    confirmations = {k: v for k, v in (data.get("confirmations") or {}).items() if k}
    if not confirmations:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing committed"}), 400
    done = seed.apply(list_name, _devices_of(list_name), confirmations, request_actor())
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "result": seed_result(done["outcomes"], done["save"])}))


# ---------------------------------------------------------------------------
# Committed intent
# ---------------------------------------------------------------------------

@bp.route("/committed", methods=["GET"])
def committed():
    """Devices that have committed intent. The deploy path reads only these."""
    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    return jsonify({"ok": True,
                    "committed": hostvars.list_committed(repo),
                    "staged": hostvars.list_staged(repo)})


@bp.route("/committed/<path:hostname>", methods=["GET"])
def read_committed(hostname):
    """The committed host_vars document, verbatim, for editing."""
    from modules.nsot import hostvars

    repo = _repo_for(_active_list())
    # What is COMMITTED, from git (C104): the editor opens what deploy reads.
    text, _state = hostvars.committed_at_head(repo, hostname)
    if text is None:
        return jsonify({"ok": False, "committed": False, "error": (
            f"'{hostname}' has no committed intent. Extract it, review the "
            "diff, and commit before it can be deployed.")}), 404
    return jsonify({"ok": True, "hostname": hostname, "committed": True,
                    "yaml": text})


@bp.route("/committed/<path:hostname>/preview", methods=["POST"])
def preview_committed_edit(hostname):
    """Validate edited intent and show what it would DO. Writes nothing.

    A text editor is honest — the bytes reviewed in the diff are the bytes
    committed, with no translation layer, and nothing the field set does not
    model can vanish on the way through. A **structured** editor round-trips
    the document through the parser, so an ``unmodeled:`` block would
    disappear without appearing in any diff: the exact failure that block was
    built to prevent.

    Honest is not the same as usable, and this is what makes it usable:

    * a YAML or schema error is refused with a **line and column**, the way
      the template editor refuses bad Jinja;
    * the **render diff** is shown before committing, so somebody who does
      not remember the schema can see the consequence rather than the
      document.

    Two diffs, and the first is the one that answers "what does my edit do":

    ``vs_intent``   render of the edited text vs render of what is committed
    ``vs_device``   render of the edited text vs the device's capture — what
                    a deploy would push
    """
    import yaml

    from modules.nsot import hostvars, roundtrip

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    text = data.get("yaml")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"ok": False, "error": "No host_vars document sent"}), 400

    # 1. Parse. A mark gives line and column; without one the error is still
    #    reported rather than swallowed, because "invalid somewhere" beats a
    #    silent refusal.
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return jsonify({
            "ok": False, "stage": "yaml",
            "line": (mark.line + 1) if mark else None,
            "column": (mark.column + 1) if mark else None,
            "error": getattr(exc, "problem", None) or str(exc)}), 400

    if not isinstance(parsed, dict):
        return jsonify({"ok": False, "stage": "schema", "line": 1, "column": 1,
                        "error": "host_vars must be a YAML mapping"}), 400

    # 2. Schema, such as it is: the document names its own device. A mismatch
    #    here is how one device's intent lands in another's file.
    named = parsed.get("hostname")
    if named and named != hostname:
        line = next((n for n, l in enumerate(text.splitlines(), 1)
                     if l.strip().startswith("hostname:")), 1)
        return jsonify({"ok": False, "stage": "schema", "line": line,
                        "column": 1,
                        "error": f"this document names {named!r}; a host_vars "
                                 f"file names its own device, and editing "
                                 f"{hostname}'s must say {hostname!r}"}), 400

    # 2b. UNKNOWN INTERFACE KEYS — the silent half.
    #
    # `StrictUndefined` catches a MISSING key and can never catch a MISSPELLED
    # one: `descripton` is simply never read, the line does not render, and
    # nothing says a word. That is the failure a human author actually has,
    # and it is the one the render cannot report — so it is reported here,
    # with the line, like a YAML error.
    unknown = hostvars.unknown_interface_keys(parsed)
    if unknown:
        first_key = unknown[0][1]
        line = next((n for n, l in enumerate(text.splitlines(), 1)
                     if l.strip().startswith(f"{first_key}:")), 1)
        names = ", ".join(sorted({f"{key!r} (interfaces[{i}])"
                                  for i, key in unknown}))
        return jsonify({
            "ok": False, "stage": "schema", "line": line, "column": 1,
            "error": (f"nothing reads {names}. An interface key that is not "
                      "one of the known thirty is silently ignored — the line "
                      "simply does not render — so it is refused here rather "
                      "than at the device. Omitting a key is fine and needs "
                      "no action; misspelling one does.")}), 400

    # 2c. THE SYSLOG BLOCK IS WHOLE OR ABSENT (NSOT_PLAN P.1). Refused here,
    #     with the line, rather than at the commit -- same reason as 2b.
    problems = hostvars.syslog_block_problems(parsed)
    if problems:
        line = next((n for n, l in enumerate(text.splitlines(), 1)
                     if l.strip().startswith("syslog:")), 1)
        return jsonify({"ok": False, "stage": "schema", "line": line,
                        "column": 1, "error": "; ".join(problems)}), 400

    # 3. The secret guards, BEFORE anything is rendered or written. Same two
    #    checks `write_committed_text()` applies, run here so the editor
    #    refuses rather than the commit.
    try:
        hostvars.assert_printable(text, hostname)
        hostvars.assert_no_secret_values(text, hostname)
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "stage": "secrets",
                        "error": str(exc)}), 400

    # The same capture the Template preview uses, from the same helpers --
    # one composition, so the editor's diff and the preview's diff cannot
    # disagree about what the device currently looks like.
    from routes.templates import (_captured_golden, _captured_running,
                                  _platform_for as _platform_of_host)
    from modules.nsot import templates_repo

    golden, _at = _captured_golden(hostname, list_name)
    running, _at2 = _captured_running(list_name, hostname)
    capture = golden or running
    if not capture:
        return jsonify({"ok": True, "valid": True, "rendered": "",
                        "message": ("Valid. No captured config for this "
                                    "device, so there is nothing to render "
                                    "against yet.")})

    platform = _platform_of_host(hostname)
    template = templates_repo.template_for_device(repo, hostname, platform)

    # `artifact_for()`, not `build_artifact()` directly. The latter defaults
    # `template_approved` to False and reports that as "template '<x>' is not
    # approved for this device" -- a claim about the approval store made
    # without consulting it. This route built artifacts directly and so
    # reported every device as not deployable, which read as an approval that
    # had revoked itself.
    from routes.templates import artifact_for

    # Both sides render what the device would INHERIT as well (P.9): an edit
    # that leaves the profile's lines alone must not read as removing them.
    from modules.nsot import profile as _profile

    def _eff(doc_):
        return _profile.effective_for(repo, list_name, hostname, doc_, platform)

    try:
        edited = artifact_for(hostname, capture, repo, platform, template,
                              host_vars=hostvars.hydrate_secrets(
                                  _eff(parsed), hostname, list_name))
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "stage": "render",
                        "error": f"{type(exc).__name__}: {exc}"}), 400

    # BOTH READ GIT, NOT THE WORKING TREE.
    #
    # `read_committed()` opens the file on disk, which is correct for "what
    # would deploy" and wrong for "what is committed". Editing the file
    # directly — how a person actually works — made `vs_intent` compare the
    # edit against itself: empty by construction, permanently. And
    # `document_changed`, added precisely to disambiguate an empty diff, read
    # the **same** working file, so the disambiguator was fooled by the cause
    # it was there to expose. Two signals that look independent, sharing one
    # source, so their agreement carried no information.
    committed_raw, intent_state = hostvars.committed_at_head(repo, hostname)
    committed = (hostvars.from_yaml(committed_raw)
                 if committed_raw is not None else None)
    document_changed = (committed_raw is not None and committed_raw != text)

    vs_intent = ""
    intent_note = None
    if intent_state == hostvars.NEVER_COMMITTED:
        # THE THIRD STATE, NAMED. "Never committed" and "committed and
        # identical" both render as an empty diff, and the operator cannot
        # tell them apart — the absent-versus-empty distinction that erased
        # the settings file, arriving in the editor. The same absence also
        # means opposite things depending on where the device is.
        intent_note = hostvars.intent_gap_note(repo, hostname)
    elif committed:
        current = artifact_for(hostname, capture, repo, platform, template,
                               host_vars=hostvars.hydrate_secrets(
                                   _eff(committed), hostname, list_name))
        vs_intent = roundtrip.canonical_diff(
            current.rendered_masked, edited.rendered_masked,
            fromfile=f"committed ({hostname})", tofile=f"edited ({hostname})")

    vs_device, masked = roundtrip.canonical_diff(
        capture, edited.rendered_masked, fromfile=f"device ({hostname})",
        tofile=f"edited ({hostname})", report_masked=True)

    return jsonify({
        "ok": True, "valid": True, "hostname": hostname,
        "deployable": edited.deployable,
        "blocking_reasons": list(edited.blocking_reasons),
        "vs_intent": vs_intent,
        "vs_intent_changed": bool(vs_intent),
        "intent_state": intent_state,
        "intent_note": intent_note,
        "document_changed": document_changed,
        "vs_device": vs_device,
        "masked_not_compared": masked,
        "rendered": edited.rendered_masked,
    })


@bp.route("/committed/<path:hostname>", methods=["POST"])
def edit_committed(hostname):
    """Edit committed intent and commit the edit.

    **This is how a change is expressed.** Not by configuring the device and
    re-extracting — that makes intent a function of current state and can only
    ever produce an empty diff. Edit what the network is supposed to be, commit
    it, and the render diff *is* the change.
    """
    from modules.nsot import hostvars, repo as repo_service

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    repo = _repo_for(list_name)
    text = data.get("yaml")
    summary = (data.get("summary") or "").strip()

    if not isinstance(text, str) or not text.strip():
        return jsonify({"ok": False, "error": "No host_vars document sent"}), 400
    if not summary:
        return jsonify({"ok": False, "error": (
            "A one-line summary is required — it becomes the commit subject, "
            "and 'host_vars: s4' on its own says nothing in a log.")}), 400
    if hostvars.committed_at_head(repo, hostname)[0] is None:
        return jsonify({"ok": False, "error": (
            f"'{hostname}' has no committed intent yet. Commit the extraction "
            "first, so the edit has a reviewed baseline to diff against.")}), 404

    try:
        hostvars.write_committed_text(repo, hostname, text)
    except hostvars.SecretLeak as exc:
        log.error("templatize: refused host_vars edit for %s: %s", hostname, exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    result = repo_service.save_host_vars(
        list_name, [hostname], actor=request_actor(),
        message=f"host_vars: {hostname} {summary}")
    return jsonify({"ok": result.get("ok", False), "hostname": hostname,
                    "commit": result.get("commit", ""),
                    "message": result.get("message", ""),
                    "error": result.get("error", "")})


# ---------------------------------------------------------------------------
# Revert and retry (7.3): the two ways out of a rollback, previewed and
# confirmed from the Device page (modules/nsot/intent_ops.py). They replace
# `/committed/<h>/revert` and `/rolled-back/<h>/retry`, two routes with no
# screen; the revert route also cleared the rollback block after ANY revert
# commit, whatever it undid (C214).
# ---------------------------------------------------------------------------

def _intent_op_args(data: dict, *, carried: bool, action: str):
    """``(list_name, device, error_response)``. A preview may derive its list;
    an apply CARRIES it, because it ends in a commit or a lifted block."""
    from modules.nsot.restore import _devices_of

    list_name = (data.get("list_name") or "").strip()
    if carried and not list_name:
        return "", "", (jsonify({"ok": False, "error": (
            f"No list named: {action} changes one list's record, so the list comes from the "
            "preview that was confirmed, never from whichever list is active. Nothing was "
            "changed.")}), 400)
    list_name = list_name or _active_list(data)
    device = (data.get("device") or "").strip()
    if not device:
        return list_name, "", (jsonify({"ok": False, "error": "No device named"}), 400)
    if device not in {d.get("hostname") for d in _devices_of(list_name)}:
        return list_name, device, (jsonify({"ok": False, "error": (
            f"{device} is not in {list_name}'s inventory: nothing to {action}")}), 404)
    return list_name, device, None


@bp.route("/revert/preview", methods=["POST"])
def revert_preview():
    """What undoing one intent commit would commit. Reads git only."""
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import revert_preview as _parts

    data = request.get_json(silent=True) or {}
    list_name, device, err = _intent_op_args(data, carried=False, action="revert")
    if err:
        return err
    entry = intent_ops.public(intent_ops.revert_entry(list_name, device,
                                                      (data.get("sha") or "").strip()))
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "commits": entry.get("commits") or [],
                                 "preview": _parts(entry, list_name=list_name,
                                                   request=request)}))


@bp.route("/revert/apply", methods=["POST"])
def revert_apply():
    """Revert the confirmed commit as the verified person: computed again,
    refused if it moved, one commit, the block measured after it."""
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import revert_result

    data = request.get_json(silent=True) or {}
    list_name, device, err = _intent_op_args(data, carried=True, action="revert")
    if err:
        return err
    sha, confirmed = (data.get("sha") or "").strip(), (data.get("hash") or "").strip()
    if not sha or not confirmed:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing committed"}), 400
    out = intent_ops.revert_apply(list_name, device, sha, confirmed, request_actor())
    return jsonify(mask_payload({"ok": True, "list": list_name, "result": revert_result(out)}))


@bp.route("/retry/preview", methods=["POST"])
def retry_preview():
    """The block a retry would lift, whether it blocks anything now, and how
    often this device was retried before. Reads the record only."""
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import retry_preview as _parts

    data = request.get_json(silent=True) or {}
    list_name, device, err = _intent_op_args(data, carried=False, action="retry")
    if err:
        return err
    entry = intent_ops.retry_entry(list_name, device)
    return jsonify(mask_payload({"ok": True, "list": list_name,
                                 "preview": _parts(entry, list_name=list_name,
                                                   request=request)}))


@bp.route("/retry/apply", methods=["POST"])
def retry_apply():
    """Authorise the retry as the verified person, with a reason in the shape
    of one. The ONLY way a standing block lifts while the failed change is
    still in intent."""
    from modules.nsot import intent_ops
    from modules.outbound import mask_payload
    from modules.preview_confirm import retry_result

    data = request.get_json(silent=True) or {}
    list_name, device, err = _intent_op_args(data, carried=True, action="retry")
    if err:
        return err
    confirmed = (data.get("hash") or "").strip()
    if not confirmed:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing authorised"}), 400
    out = intent_ops.retry_apply(list_name, device, confirmed,
                                 (data.get("reason") or "").strip(), request_actor())
    return jsonify(mask_payload({"ok": True, "list": list_name, "result": retry_result(out)}))


@bp.route("/rolled-back/retries", methods=["GET"])
def rolled_back_retries():
    """Every authorised retry, for audit."""
    from modules.nsot import hostvars
    return jsonify({"ok": True,
                    "retries": hostvars.retry_log(_repo_for(_active_list()))})


@bp.route("/rolled-back", methods=["GET"])
def rolled_back():
    """Rolled-back notes, split by whether they still apply (see
    `rolled_back_notes`, which Needs attention reads too: one classifier)."""
    got = rolled_back_notes(_active_list())
    return jsonify({"ok": True, "rolled_back": got["applies"], "stale": got["stale"],
                    "unreadable": got["unreadable"],
                    "blocking_count": len(got["applies"])})


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


def _public(result: dict) -> dict:
    """Report fields for the UI — host_vars and rendered config excluded."""
    return {k: v for k, v in result.items()
            if k not in ("host_vars", "rendered", "details")} | {
        "missing_sample": [m["line"] for m in result.get("details", {}).get("missing", [])[:20]],
        "extra_sample": [e["line"] for e in result.get("details", {}).get("extra", [])[:20]],
        "reordered": result.get("details", {}).get("reordered", []),
    }


def _summarise(reports: list) -> dict:
    if not reports:
        return {"devices": 0, "mean_modeled_coverage": 0.0,
                "mean_round_trip_fidelity": 0.0, "fully_reproduced": 0}
    count = len(reports)
    return {
        "devices": count,
        "mean_modeled_coverage": round(
            sum(r["modeled_coverage"] for r in reports) / count, 1),
        "mean_round_trip_fidelity": round(
            sum(r["round_trip_fidelity"] for r in reports) / count, 1),
        "fully_reproduced": sum(1 for r in reports if r["ok"]),
        "total_unmodeled": sum(r["unmodeled"] for r in reports),
    }


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
    from routes.templates import (_captured_golden, _captured_running,
                                  _platform_for as _platform_of_host,
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
        golden, _a = _captured_golden(host, list_name)
        running, _b = _captured_running(list_name, host)
        capture = golden or running
        if not capture:
            raise RuntimeError("no captured config to render against")
        platform = _platform_of_host(host)
        template = templates_repo.template_for_device(repo, host, platform)
        from modules.nsot import profile as _profile
        art = artifact_for(host, capture, repo, platform, template,
                           host_vars=hostvars.hydrate_secrets(
                               _profile.effective_for(repo, list_name, host, host_vars, platform),
                               host, list_name))
        return art.rendered_masked, art.deployable, art.blocking_reasons

    return render, eligible


@bp.route("/bulk/preview", methods=["POST"])
def bulk_preview():
    """Preview one change against N devices' intent. Writes nothing."""
    from modules.nsot import bulk_intent

    data = request.get_json(silent=True) or {}
    list_name, repo, devices, steps, error = _bulk_inputs(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    render, eligible = _bulk_render_and_eligible(list_name, repo)
    report = bulk_intent.plan(repo, devices, steps, render=render,
                              eligible=eligible,
                              summary=data.get("summary", ""))
    for entry in report.get("accepted", []):
        entry.pop("text", None)      # the preview shows effects, not files
    return jsonify({**report, "list_name": list_name}), (200 if report["ok"] else 400)


@bp.route("/bulk/apply", methods=["POST"])
def bulk_apply():
    """Recompute the preview; refuse unless it is what was confirmed; commit once."""
    from modules.nsot import bulk_intent

    data = request.get_json(silent=True) or {}
    list_name, repo, devices, steps, error = _bulk_inputs(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    render, eligible = _bulk_render_and_eligible(list_name, repo)
    result = bulk_intent.apply(list_name, repo, devices, steps,
                               str(data.get("confirmed_hash") or ""),
                               render=render, eligible=eligible,
                               summary=data.get("summary", ""),
                               actor=request_actor())
    return jsonify(result), (200 if result.get("ok") else 409)
