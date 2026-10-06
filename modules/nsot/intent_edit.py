"""Editing a device's committed intent: ONE code path for every editor (board H, 7.3).

Today's page (`routes/templatize.py`, `/templatize/committed/<host>`) and the v2 device page's
Intent tab (`routes/intent_v2.py`) both call these, so the checks, the two diffs, the save
bound to the version opened and the refusal when intent moved are one implementation. Each
function returns a plain dict with an HTTP ``status``; a route draws it as JSON or as a card.

- :func:`open_doc`: the committed document and the blob it was read from (the ``base`` the
  save sends back, CONCURRENCY_AUDIT R2).
- :func:`validate`: parse, the document names its device, no unknown interface key, the syslog
  block whole, no run's notes as a description, printable, no secret value. Line and column.
- :func:`preview`: what the edit changes in the render, what a deploy would send, whether it
  is deployable, and the document's unmodelled lines with whether each is acknowledged.
- :func:`commit`: under the repository lock, refused when intent moved since ``base`` (both
  changes, and the edit placed on theirs when the two touch different lines), else one
  commit as the person, with the reason.
- :func:`acknowledge`: the document with its ``unmodeled_ack`` block set to the lines a person
  chose (C481): content-bound, committed, reviewable in git, never a click that dismisses.
"""

import difflib
import logging
import os

log = logging.getLogger(__name__)

#: An edit's steps, in order: the manual's How it works page names each (tests/test_manual.py).
STEPS = ("open", "check", "acknowledge", "commit", "moved")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def open_doc(list_name: str, hostname: str) -> dict:
    """The committed host_vars document, verbatim, and its blob (``base``)."""
    from modules.nsot import hostvars

    repo = _repo_for(list_name)
    # What is COMMITTED, from git (C104), read FROM the blob it names as its base, so a
    # commit landing between two reads of HEAD cannot pair one version's text with
    # another's base (R2).
    base = hostvars.committed_blob(repo, hostname)
    text = hostvars.blob_text(repo, base) if base else None
    if text is None:
        return {"status": 404, "ok": False, "committed": False, "error": (
            f"'{hostname}' has no committed intent. Extract it, review the "
            "diff, and commit before it can be deployed.")}
    return {"status": 200, "ok": True, "hostname": hostname, "committed": True,
            "yaml": text, "base": base}


def _line_of(text: str, starts: str, contains: str = "") -> int:
    return next((n for n, l in enumerate(text.splitlines(), 1)
                 if l.strip().startswith(starts) and contains in l), 1)


def validate(hostname: str, text: str) -> dict:
    """``{"ok": True, "parsed"}`` or a refusal ``{"ok": False, "status": 400, "stage",
    "line", "column", "error"}``: the editor's checks, run by the preview AND the save (R2:
    a check only the preview ran was skipped by a save never previewed)."""
    import yaml

    from modules.nsot import hostvars

    def refuse(stage, error, line=None, column=None):
        out = {"ok": False, "status": 400, "stage": stage, "error": error}
        if line is not None or stage in ("yaml", "schema"):
            out.update(line=line, column=column)
        return out

    # 1. Parse. A mark gives line and column; without one the error is still reported.
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return refuse("yaml", getattr(exc, "problem", None) or str(exc),
                      (mark.line + 1) if mark else None, (mark.column + 1) if mark else None)
    if not isinstance(parsed, dict):
        return refuse("schema", "host_vars must be a YAML mapping", 1, 1)

    # 2. The document names its own device: a mismatch is how one device's intent lands in
    #    another's file.
    named = parsed.get("hostname")
    if named and named != hostname:
        return refuse("schema", f"this document names {named!r}; a host_vars file names its "
                                f"own device, and editing {hostname}'s must say {hostname!r}",
                      _line_of(text, "hostname:"), 1)

    # 2b. Unknown interface keys: `StrictUndefined` catches a missing key and never a
    #     misspelled one, which simply does not render.
    unknown = hostvars.unknown_interface_keys(parsed)
    if unknown:
        names = ", ".join(sorted({f"{key!r} (interfaces[{i}])" for i, key in unknown}))
        return refuse("schema", (
            f"nothing reads {names}. An interface key that is not one of the known thirty is "
            "silently ignored — the line simply does not render — so it is refused here "
            "rather than at the device. Omitting a key is fine and needs no action; "
            "misspelling one does."), _line_of(text, f"{unknown[0][1]}:"), 1)

    # 2c. The syslog block is whole or absent (NSOT_PLAN P.1).
    problems = hostvars.syslog_block_problems(parsed)
    if problems:
        return refuse("schema", "; ".join(problems), _line_of(text, "syslog:"), 1)

    # 2d. No run's notes as a description (C428).
    problems = hostvars.description_problems(parsed)
    if problems:
        bad = problems[0].split(" is ", 1)[1].split(":", 1)[0].strip("'\"")
        return refuse("schema", "; ".join(problems), _line_of(text, "description:", bad), 1)

    # 3. The secret guards, before anything is rendered or written.
    try:
        hostvars.assert_printable(text, hostname)
        hostvars.assert_no_secret_values(text, hostname)
    except Exception as exc:                  # noqa: BLE001
        return refuse("secrets", str(exc))
    return {"ok": True, "parsed": parsed}


def unmodelled(parsed: dict) -> list:
    """``[{"line", "acknowledged"}]``: every line the parser did not model in *parsed*, and
    whether its ``unmodeled_ack`` names it (the deploy gate's own reading)."""
    from modules.nsot.render_artifact import acknowledged_lines, unmodeled_lines

    acked = set(acknowledged_lines(parsed))
    return [{"line": l, "acknowledged": l in acked} for l in unmodeled_lines(parsed)]


def preview(list_name: str, hostname: str, text: str) -> dict:
    """Validate an edit and say what it would DO. Writes nothing.

    ``vs_intent``: the render of the edit against the render of what is committed (what the
    edit changes); ``vs_device``: the render of the edit against the device's capture (what
    a deploy would send). Both render what the device inherits from the network's monitoring
    profile (P.9), and both read git, never a working file."""
    from modules.nsot import hostvars, roundtrip

    if not isinstance(text, str) or not text.strip():
        return {"status": 400, "ok": False, "error": "No host_vars document sent"}
    repo = _repo_for(list_name)
    checked = validate(hostname, text)
    if not checked["ok"]:
        return checked
    parsed = checked["parsed"]
    lines = unmodelled(parsed)

    from routes.templates import (_captured_golden, _captured_running,
                                  _platform_for as _platform_of_host)
    from modules.nsot import templates_repo

    golden, _at = _captured_golden(hostname, list_name)
    running, _at2 = _captured_running(list_name, hostname)
    capture = golden or running
    if not capture:
        return {"status": 200, "ok": True, "valid": True, "rendered": "", "unmodelled": lines,
                "message": ("Valid. No captured config for this device, so there is nothing "
                            "to render against yet.")}

    # The platform from THIS list's inventory (C495): the active list's held no row for a
    # device of another network, and the refusal said its row named no platform.
    platform = _platform_of_host(hostname, list_name)
    from modules.nsot.platform import is_dialect
    if not is_dialect(platform):
        from routes.templates import unknown_platform_words
        return {"status": 409, "ok": False, "stage": "render",
                "error": unknown_platform_words(hostname, list_name)}
    template = templates_repo.template_for_device(repo, hostname, platform)

    # `artifact_for()`, never `build_artifact()` directly, which reports every device as not
    # deployable without consulting the approval store.
    from routes.templates import artifact_for
    from modules.nsot import profile as _profile

    def _eff(doc_):
        return _profile.effective_for(repo, list_name, hostname, doc_, platform)

    try:
        edited = artifact_for(hostname, capture, repo, platform, template,
                              host_vars=hostvars.hydrate_secrets(_eff(parsed), hostname,
                                                                 list_name))
    except Exception as exc:                  # noqa: BLE001
        return {"status": 400, "ok": False, "stage": "render",
                "error": f"{type(exc).__name__}: {exc}"}

    committed_raw, intent_state = hostvars.committed_at_head(repo, hostname)
    committed = hostvars.from_yaml(committed_raw) if committed_raw is not None else None
    document_changed = committed_raw is not None and committed_raw != text

    vs_intent, intent_note, current_render = "", None, None
    if intent_state == hostvars.NEVER_COMMITTED:
        intent_note = hostvars.intent_gap_note(repo, hostname)
    elif committed:
        current = artifact_for(hostname, capture, repo, platform, template,
                               host_vars=hostvars.hydrate_secrets(_eff(committed), hostname,
                                                                  list_name))
        current_render = current.rendered_masked
        vs_intent = roundtrip.canonical_diff(
            current.rendered_masked, edited.rendered_masked,
            fromfile=f"committed ({hostname})", tofile=f"edited ({hostname})")
    vs_device, masked = roundtrip.canonical_diff(
        capture, edited.rendered_masked, fromfile=f"device ({hostname})",
        tofile=f"edited ({hostname})", report_masked=True)
    return {"status": 200, "ok": True, "valid": True, "hostname": hostname,
            "deployable": edited.deployable,
            "blocking_reasons": list(edited.blocking_reasons),
            "vs_intent": vs_intent, "vs_intent_changed": bool(vs_intent),
            "intent_state": intent_state, "intent_note": intent_note,
            "document_changed": document_changed,
            "vs_device": vs_device, "masked_not_compared": masked,
            # The v2 editor's right column (C500): the same two diffs as rows, compared.
            "diffs": diffs(repo, hostname, current_render, edited.rendered_masked, capture),
            "captured_from": "golden" if golden else "running",
            "rendered": edited.rendered_masked, "template": template,
            "unmodelled": lines}


#: Commands that hold ONE value in their section, so a new line replaces the old on the
#: device (C500's rule: an edit's deleted line that one of these replaces is changed by a
#: deploy, not left behind). Longest prefix first; anything not here is not known to be one
#: setting, and the editor then shows both diffs, which is the safe reading.
ONE_SETTING = ("ip ospf priority", "ip ospf cost", "switchport access vlan", "switchport mode",
               "ip address", "description", "hostname", "bandwidth", "ip mtu", "mtu",
               "delay", "speed", "duplex", "load-interval", "router-id", "ip domain name")

#: How many of a device's goldens the "not from this edit" labels read (C500), newest first.
GOLDENS_READ = 20


def _setting(line: str) -> str:
    """The one-setting command *line* sets, or "" when it is not known to be one."""
    if " secondary" in f" {line} ":
        return ""
    for prefix in sorted(ONE_SETTING, key=len, reverse=True):
        if line == prefix or line.startswith(prefix + " "):
            return prefix
    return ""


def _rows_of(pairs, kind: str = "add") -> list:
    """Rows for (section, line) pairs, each section's line drawn once above its lines."""
    rows, last = [], None
    for section, line in pairs:
        if not line:
            rows.append({"kind": kind, "text": section})
            last = section
            continue
        if section != last and section != "(global)":
            rows.append({"kind": "head", "text": section})
        last = section
        rows.append({"kind": kind, "text": line})
    return rows


_GOLDEN_LINES = {}


def _golden_pairs(repo: str, hostname: str, sha: str):
    """The (section, line) pairs of *hostname*'s golden at *sha*, or None when unreadable;
    kept per commit (a commit's golden never changes)."""
    from modules.nsot import repo as repo_service
    from modules.nsot.roundtrip import canonical_lines

    key = (repo, hostname, sha)
    if key not in _GOLDEN_LINES:
        text = repo_service.golden_at(repo, hostname, sha)
        if text is None:
            return None
        pairs, section = set(), "(global)"
        for line in canonical_lines(text):
            if line.startswith("    "):
                pairs.add((section, line[4:]))
            else:
                section = line
                pairs.add((section, ""))
        if len(_GOLDEN_LINES) > 512:
            _GOLDEN_LINES.clear()
        _GOLDEN_LINES[key] = pairs
    return _GOLDEN_LINES[key]


def where_from(repo: str, hostname: str, pairs) -> dict:
    """Where each deploy line NOT from this edit came from, read from *hostname*'s golden
    history (C500): ``{"labels": {pair: {"words", "sha", "at"}}, "golden": newest or None,
    "read": n}``. A line an earlier golden held and a later one lacks was changed on the
    device; a line no golden read held was committed and not yet deployed; when the history
    cannot say, "already pending" alone."""
    from modules.nsot import repo as repo_service

    history = repo_service.golden_history(repo, hostname, limit=GOLDENS_READ)
    labels = {}
    for pair in pairs:
        labels[pair] = {"words": "already pending", "sha": "", "at": ""}
        if not history:
            continue
        held = None
        unreadable = False
        for entry in history:
            got = _golden_pairs(repo, hostname, entry["sha"])
            if got is None:
                unreadable = True
                break
            if pair in got:
                held = entry
                break
        if unreadable:
            continue
        if held is not None:
            labels[pair] = {"words": f"on {hostname} until its golden of", "sha": held["sha"],
                            "at": held["timestamp"], "then": "gone since: changed on the device"}
        elif held is None:
            within = (f" in its last {len(history)} goldens"
                      if len(history) >= GOLDENS_READ else "")
            labels[pair] = {"words": f"never on {hostname}{within}: not yet deployed",
                            "sha": "", "at": ""}
    return {"labels": labels, "golden": history[0] if history else None,
            "read": len(history)}


def diffs(repo: str, hostname: str, committed_render, edited_render: str,
          capture: str) -> dict:
    """The right column's two diffs, by the rule approved on board H (C500): EQUAL when the
    deploy's lines are exactly the edit's added lines and every line the edit deletes is a
    one-setting line an added one replaces; then one diff. Otherwise both, the deploy's lines
    split into those from this edit and those not (each labelled from the golden history),
    and the lines this edit deletes that a merge-only deploy will not remove named."""
    from modules.nsot.roundtrip import change_rows

    edit = (change_rows(committed_render, edited_render) if committed_render is not None
            else {"rows": [], "removed": [], "added": [], "masked": 0})
    deploy = change_rows(capture, edited_render)
    edit_added = set(edit["added"])
    replaced_keys = {(sec, _setting(line)) for sec, line in edit["added"] if _setting(line)}
    not_removed = [(sec, line) for sec, line in edit["removed"]
                   if not (line and (sec, _setting(line)) in replaced_keys)]
    from_edit = [p for p in deploy["added"] if p in edit_added]
    not_from = [p for p in deploy["added"] if p not in edit_added]
    same = (bool(edit["rows"]) and set(deploy["added"]) == edit_added and not not_removed)
    origin = where_from(repo, hostname, not_from) if not_from else {"labels": {}, "read": 0}
    if same or not not_from:
        from modules.nsot import repo as repo_service
        history = repo_service.golden_history(repo, hostname, limit=1)
        origin["golden"] = history[0] if history else None
    sent = len([p for p in deploy["added"] if p[1]])
    return {
        "same": same,
        "edit_rows": edit["rows"],
        "edit_changes": bool(edit["rows"]),
        "replaces": bool(edit["removed"]) and not not_removed,
        "not_removed": _rows_of(not_removed, "keep"),
        "from_edit_rows": _rows_of(from_edit),
        "from_edit": len([p for p in from_edit if p[1]]),
        "not_from": [{"section": sec, "line": line or sec,
                      **origin["labels"].get((sec, line), {"words": "already pending"})}
                     for sec, line in not_from],
        "sent": sent,
        "golden": origin.get("golden"),
        "masked": deploy["masked"],
    }


def merge3(base: str, theirs: str, yours: str):
    """*yours* placed on *theirs* when the two changed different lines of *base*, else None.

    Line-based: each side's changes against *base*; any two that touch or overlap (an insert
    at the same place included) refuse the merge, so a person decides, never this."""
    b, t, y = (s.splitlines(True) for s in (base, theirs, yours))

    def changes(other):
        return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2
                in difflib.SequenceMatcher(None, b, other, autojunk=False).get_opcodes()
                if tag != "equal"]

    ct, cy = changes(t), changes(y)
    for a1, a2, _ in ct:
        for b1, b2, _ in cy:
            if max(a1, b1) <= min(a2, b2):     # overlapping, touching, or one insert point
                return None
    out = list(b)
    for i1, i2, new in sorted(ct + cy, key=lambda c: c[0], reverse=True):
        out[i1:i2] = new
    return "".join(out)


def moved(repo: str, hostname: str, base: str, current: str, text: str) -> dict:
    """The refusal when HEAD moved after the editor opened: both blobs, who moved it, their
    change and this edit's, each against what was opened, and the edit placed on theirs when
    the two touch different lines (``merged``). 409, nothing written."""
    from modules.nsot import hostvars

    opened = hostvars.blob_text(repo, base)
    now = hostvars.blob_text(repo, current) or ""
    last = hostvars.last_intent_commit(repo, hostname)
    by = (f"{last.get('by') or 'someone'} in {last.get('commit')} "
          f"(\"{last.get('subject')}\", {last.get('at')})") if last else "a commit"
    mine = text if text.endswith("\n") else text + "\n"

    def diff(a, b_, left, right):
        return "".join(difflib.unified_diff(a.splitlines(True), b_.splitlines(True),
                                            fromfile=left, tofile=right))

    merged = None
    if opened is None:
        their = your = ""
        what = (f"the version this editor says it opened ({base[:12]}) is not in the "
                "repository, so the two changes cannot be shown")
    else:
        their = diff(opened, now, f"what you opened ({base[:8]})",
                     f"committed now ({current[:8]})")
        your = diff(opened, mine, f"what you opened ({base[:8]})", "your edit")
        what = "their change and yours are below"
        merged = merge3(opened, now, mine)
    return {"status": 409, "ok": False, "stage": "moved", "hostname": hostname,
            "base": base, "current": current, "last_commit": last,
            "their_change": their, "your_change": your, "merged": merged,
            "error": (f"Not saved: {hostname}'s intent changed after you opened it. You opened "
                      f"{base[:8]}; committed now is {current[:8]}, by {by}. Nothing was "
                      f"written; {what}. Reload the editor to make your edit on their "
                      "version.")}


def commit(list_name: str, hostname: str, text: str, summary: str, base: str,
           actor: str) -> dict:
    """Commit an edit to *hostname*'s intent as *actor*, bound to the version opened."""
    from modules.nsot import hostvars, repo as repo_service

    repo = _repo_for(list_name)
    summary = (summary or "").strip()
    base = (base or "").strip()
    if not isinstance(text, str) or not text.strip():
        return {"status": 400, "ok": False, "error": "No host_vars document sent"}
    if not summary:
        return {"status": 400, "ok": False, "error": (
            "A one-line summary is required — it becomes the commit subject, "
            "and 'host_vars: s4' on its own says nothing in a log.")}
    if not base:
        return {"status": 400, "ok": False, "stage": "base", "error": (
            f"Not saved: this editor did not say which version of {hostname}'s intent it "
            "opened, so the save could replace a commit made since. Nothing was written. "
            "Reload the page, open the editor again and make the edit there.")}
    checked = validate(hostname, text)
    if not checked["ok"]:
        return checked

    with repo_service.repo_lock(repo):
        current = hostvars.committed_blob(repo, hostname)
        if current is None:
            return {"status": 404, "ok": False, "error": (
                f"'{hostname}' has no committed intent yet. Commit the extraction "
                "first, so the edit has a reviewed baseline to diff against.")}
        if current != base:
            return moved(repo, hostname, base, current, text)
        committed_text = hostvars.blob_text(repo, current) or ""
        if (text if text.endswith("\n") else text + "\n") == committed_text:
            return {"status": 200, "ok": True, "hostname": hostname, "changed": False,
                    "commit": "", "base": current,
                    "message": "Nothing to commit: the document is what is already committed."}
        try:
            hostvars.write_committed_text(repo, hostname, text)
        except hostvars.SecretLeak as exc:
            log.error("intent edit: refused host_vars edit for %s: %s", hostname, exc)
            return {"status": 400, "ok": False, "error": str(exc)}
        except ValueError as exc:
            return {"status": 400, "ok": False, "error": str(exc)}
        result = repo_service.save_host_vars(list_name, [hostname], actor=actor,
                                             message=f"host_vars: {hostname} {summary}")
        after = hostvars.committed_blob(repo, hostname)
    return {"status": 200, "ok": result.get("ok", False), "hostname": hostname,
            "changed": bool(result.get("commit")), "commit": result.get("commit", ""),
            "base": after or current, "message": result.get("message", ""),
            "error": result.get("error", "")}


def acknowledge(text: str, lines) -> str:
    """*text* with its top-level ``unmodeled_ack`` block set to exactly *lines* (sorted), or
    removed when there are none. Everything else in the document is left byte for byte: the
    block is cut where it stood and written last, quoted by the YAML dumper."""
    import yaml

    keep, skipping = [], False
    for line in (text or "").splitlines():
        if line.startswith("unmodeled_ack:"):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "-", "\t")) or not line.strip()):
            continue
        skipping = False
        keep.append(line)
    while keep and not keep[-1].strip():
        keep.pop()
    out = "\n".join(keep) + "\n"
    chosen = sorted({str(l).rstrip() for l in (lines or []) if str(l).strip()})
    if chosen:
        out += yaml.safe_dump({"unmodeled_ack": {"lines": chosen}}, sort_keys=False,
                              default_flow_style=False, allow_unicode=False, width=4096)
    return out


def strip_status(result: dict) -> tuple:
    """``(body, status)`` for a JSON route: the dict without its ``status``."""
    body = {k: v for k, v in result.items() if k not in ("status", "parsed")}
    return body, result.get("status", 200)
