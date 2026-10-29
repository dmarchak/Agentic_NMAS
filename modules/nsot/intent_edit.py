"""Editing a device's committed intent: ONE code path for every editor (board H, 7.3).

The v2 device page's Intent tab (`routes/intent_v2.py`) calls these, so the checks, the two
diffs, the save bound to the version opened and the refusal when intent moved are one
implementation (today's editor, `/templatize/committed/<host>`, which called them too, left at
7.8 on 2026-10-17, P7-23). Each function returns a plain dict with an HTTP ``status``; the tab
draws it as a card.

- :func:`open_doc`: the committed document and the blob it was read from (the ``base`` the
  save sends back, CONCURRENCY_AUDIT R2).
- :func:`validate`: parse, the document names its device, no unknown interface key, the syslog
  block whole, no run's notes as a description, printable, no secret value. Line and column.
- :func:`preview`: what the edit changes in the render, what a deploy would send, whether it
  is deployable, the document's unmodelled lines with whether each is acknowledged, and, for
  an edit adding a VLAN, the commit's VLAN check (C2061).
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
#: The commit's `Source:`: a person's edit of committed intent (C365: it was recorded as
#: `extraction`, `save_host_vars`' default then, and History drew a hand edit as one).
SOURCE = "intent-edit"


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


def _section_words(section: str) -> str:
    return section or "the top level"


def _key_mark(text: str, path: tuple, key: str) -> tuple:
    """``(line, column)``, 1-based, of *key* inside the mapping at *path* (a list item by its
    index), read from the YAML's own node marks; ``(1, 1)`` when it cannot be found."""
    import yaml

    try:
        node = yaml.compose(text)
        for part in path:
            if isinstance(part, int):
                node = node.value[part]
            else:
                node = next(v for k, v in node.value if k.value == part)
        mark = next(k for k, _v in node.value if k.value == key).start_mark
        return mark.line + 1, mark.column + 1
    except Exception:                          # noqa: BLE001 - the refusal still names it
        return 1, 1


def _template_reads(list_name: str, hostname: str):
    """The names *hostname*'s own template (and every template it includes) reads, or None
    when they cannot be read (then no unknown key is let through on a template's word)."""
    try:
        from modules.nsot import templates_repo
        from modules.nsot.config_check import template_reads
        from routes.templates import _platform_for

        platform = _platform_for(hostname, list_name)
        src = templates_repo.render_source(_repo_for(list_name), hostname, platform)
        return template_reads(src["root"], platform, src["name"])
    except Exception as exc:                   # noqa: BLE001
        log.debug("intent_edit: %s's template reads unreadable: %s", hostname, exc)
        return None


def validate(hostname: str, text: str, list_name: str = "") -> dict:
    """``{"ok": True, "parsed"}`` or a refusal ``{"ok": False, "status": 400, "stage",
    "line", "column", "error"}``: the editor's checks, run by the preview AND the save (R2:
    a check only the preview ran was skipped by a save never previewed). *list_name* names
    the device's network, whose template's reads may let through a key no section knows."""
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

    # 2b'. Every key of every section intent knows is one it reads THERE (C1183, W4 step 48:
    #      a BGP block one level up passed the interface check and rendered nothing).
    #      A key no section reads anywhere may be one the device's own template reads.
    unknown = hostvars.unknown_keys(parsed)
    if list_name and any(not where for _p, _k, where in unknown):
        unknown = hostvars.unknown_keys(parsed, reads=_template_reads(list_name, hostname))
    if unknown:
        line, column = _key_mark(text, *unknown[0][:2])
        names = "; ".join(
            f"{hostvars.dotted(path, key)} (line {_key_mark(text, path, key)[0]}): "
            + (f"intent reads {key!r} under "
               + ", ".join(_section_words(s) for s in where[:4])
               + (f" and {len(where) - 4} more" if len(where) > 4 else "")
               if where else f"no section reads {key!r}")
            for path, key, where in unknown[:6])
        more = f"; and {len(unknown) - 6} more" if len(unknown) > 6 else ""
        return refuse("schema", (
            f"nothing reads {names}{more}. A key where intent does not read it renders "
            "nothing — its lines simply do not appear — so it is refused here rather than at "
            "the device. Move it to where it is read, or remove it."), line, column)

    # 2c. The syslog block is whole or absent (NSOT_PLAN P.1).
    problems = hostvars.syslog_block_problems(parsed)
    if problems:
        return refuse("schema", "; ".join(problems), _line_of(text, "syslog:"), 1)

    # 2c'. No interface holds two keys that undo each other (C1429): both lines render and the
    #      device keeps the template's later one, silently.
    problems = hostvars.contradiction_problems(parsed)
    if problems:
        line, column = _key_mark(text, ("interfaces", problems[0][0]), "name")
        return refuse("schema", "; ".join(m for _n, m in problems[:6])
                      + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""),
                      line, column)

    # 2d. No run's notes as a description (C428).
    problems = hostvars.description_problems(parsed)
    if problems:
        bad = problems[0].split(" is ", 1)[1].split(":", 1)[0].strip("'\"")
        return refuse("schema", "; ".join(problems), _line_of(text, "description:", bad), 1)

    # 2e. The feature packs' fields (K7, docs/FEATURE_PACKS.md): an area that is no area, a
    #     network that is no network, a protocol a pack does not redistribute. Each names the
    #     field, its value and what it was compared with; the render refuses the same.
    from modules.nsot import features
    problems = features.problems(parsed)
    if problems:
        path, key, _message = problems[0]
        line, column = _key_mark(text, path, key) if isinstance(key, str) \
            else _key_mark(text, path[:-1], path[-1]) if path else (1, 1)
        return refuse("schema", "; ".join(m for _p, _k, m in problems[:6])
                      + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""),
                      line, column)

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
    from modules.nsot.render_artifact import ack_form, acknowledged_lines, unmodeled_lines

    acked = {ack_form(l) for l in acknowledged_lines(parsed)}
    return [{"line": l, "acknowledged": ack_form(l) in acked} for l in unmodeled_lines(parsed)]


def render_context(list_name: str, hostname: str) -> dict:
    """What a render of *hostname*'s intent needs, read once, for the preview and Normalise's
    proof alike: ``{"ok": True, "repo", "capture", "platform", "template", "eff"}`` (*eff*
    gives a document what it inherits from the network's monitoring profile, P.9); ``capture``
    None when no golden is recorded; or the refusal for a platform no dialect renders."""
    from routes.templates import _captured_golden, _platform_for as _platform_of_host
    from modules.nsot import templates_repo

    repo = _repo_for(list_name)
    # Its committed golden only (C683): the backup store this fell back to retires at 7.8, and
    # what Mercury renders against is what it recorded, never a file beside it.
    capture, _at = _captured_golden(hostname, list_name)
    if not capture:
        return {"ok": True, "repo": repo, "capture": None}

    # The platform from THIS list's inventory (C495): the active list's held no row for a
    # device of another network, and the refusal said its row named no platform.
    platform = _platform_of_host(hostname, list_name)
    from modules.nsot.platform import is_dialect
    if not is_dialect(platform):
        from routes.templates import unknown_platform_words
        return {"status": 409, "ok": False, "stage": "render",
                "error": unknown_platform_words(hostname, list_name)}
    from modules.nsot import profile as _profile

    def _eff(doc_):
        return _profile.effective_for(repo, list_name, hostname, doc_, platform)

    return {"ok": True, "repo": repo, "capture": capture, "platform": platform,
            "template": templates_repo.template_for_device(repo, hostname, platform),
            "eff": _eff}


def vlan_check(list_name: str, hostname: str, committed, parsed, capability=None):
    """The VLAN check the commit runs (C2044), run by the preview too (C2061), so an edit the
    commit would refuse never shows as committable: None when the edit adds no VLAN to what
    is committed (the device's answer then not read at all), else ``{"ok", "added",
    "words"}``, *words* the refusal's (`vlan_capability.refusal`, the commit's own) or, on a
    yes, where the answer came from. *capability* is the answer its caller read already this
    request (the intent patch's preview), so it is read once."""
    from modules.nsot import vlan_capability

    got = vlan_capability.judge(list_name, hostname, committed, parsed, subject="this edit",
                                capability=capability)
    if not got["added"]:
        return None
    return {"ok": got["ok"], "added": list(got["added"]),
            "words": (got.get("capability") or {}).get("words", "") if got["ok"]
            else got["error"]}


def preview(list_name: str, hostname: str, text: str, *, vlan_databases: dict = None) -> dict:
    """Validate an edit and say what it would DO. Writes nothing.

    ``vs_intent``: the render of the edit against the render of what is committed (what the
    edit changes); ``vs_device``: the render of the edit against the device's capture (what
    a deploy would send). Both render what the device inherits from the network's monitoring
    profile (P.9), and both read git, never a working file. An edit that changes the
    committed document's formatting only (Normalise, C1693) carries ``proof``, the five lines
    `intent_normalise.proof` draws; ``canonical`` says whether the text is Mercury's own
    formatting, which is what a commit writes.

    ``vlan_database`` (C2061) is the commit's VLAN check (:func:`vlan_check`) against what is
    committed at HEAD, present only when the edit adds a VLAN: the device's answer is read
    only then, once per request, or not at all when *vlan_databases* (``{hostname: answer}``,
    as `commit` takes it) hands in the answer its caller read."""
    from modules.nsot import hostvars, roundtrip

    if not isinstance(text, str) or not text.strip():
        return {"status": 400, "ok": False, "error": "No host_vars document sent"}
    repo = _repo_for(list_name)
    checked = validate(hostname, text, list_name)
    if not checked["ok"]:
        return checked
    parsed = checked["parsed"]
    lines = unmodelled(parsed)

    ctx = render_context(list_name, hostname)
    if not ctx["ok"]:
        return ctx
    committed_raw, intent_state = hostvars.committed_at_head(repo, hostname)
    committed = hostvars.from_yaml(committed_raw) if committed_raw is not None else None
    vlans = vlan_check(list_name, hostname, committed, parsed,
                       capability=(vlan_databases or {}).get(hostname))
    checks = {"vlan_database": vlans} if vlans else {}
    capture = ctx["capture"]
    if not capture:
        return {"status": 200, "ok": True, "valid": True, "rendered": "", "unmodelled": lines,
                **checks,
                "message": ("Valid. No golden is recorded for this device yet (its page's "
                            "Capture records one), so there is nothing to render against.")}
    platform, template, _eff = ctx["platform"], ctx["template"], ctx["eff"]

    # `artifact_for()`, never `build_artifact()` directly, which reports every device as not
    # deployable without consulting the approval store.
    from routes.templates import artifact_for

    try:
        edited = artifact_for(hostname, capture, repo, platform, template,
                              host_vars=hostvars.hydrate_secrets(_eff(parsed), hostname,
                                                                 list_name))
    except Exception as exc:                  # noqa: BLE001
        return {"status": 400, "ok": False, "stage": "render",
                "error": f"{type(exc).__name__}: {exc}"}

    document_changed = committed_raw is not None and committed_raw != text

    from modules.nsot import intent_normalise
    if committed_raw is not None and intent_normalise.formatting_only(committed_raw, text):
        # Formatting only (C1693, board H-N): the proof in place of the diffs (which a passing
        # proof says are empty), and the checks the column draws beside it.
        return {"status": 200, "ok": True, "canonical": True,
                "proof": intent_normalise.proof(list_name, hostname, text, committed_raw,
                                                ctx=ctx),
                "deployable": edited.deployable,
                "blocking_reasons": list(edited.blocking_reasons),
                "template": template, "unmodelled": lines, **checks}

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
            "canonical": hostvars.round_trips(text if text.endswith("\n") else text + "\n"),
            "deployable": edited.deployable,
            "blocking_reasons": list(edited.blocking_reasons),
            "vs_intent": vs_intent, "vs_intent_changed": bool(vs_intent),
            "intent_state": intent_state, "intent_note": intent_note,
            "document_changed": document_changed,
            "vs_device": vs_device, "masked_not_compared": masked,
            # The v2 editor's right column (C500): the same two diffs as rows, compared.
            "diffs": diffs(repo, hostname, current_render, edited.rendered_masked, capture),
            "captured_from": "golden",
            "rendered": edited.rendered_masked, "template": template,
            "unmodelled": lines, **checks}


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


def _kept(removed, added) -> list:
    """The (section, line) pairs of *removed* a merge-only deploy of *added* leaves in place:
    every one but a one-setting line an added line in its section replaces (C500's rule)."""
    replaced = {(sec, _setting(line)) for sec, line in added if _setting(line)}
    return [(sec, line) for sec, line in removed
            if not (line and (sec, _setting(line)) in replaced)]


def _masked_rows(rows: list) -> list:
    """*rows* with each text masked (`redact_text`): a device's side is its golden, verbatim."""
    from modules.redact import redact_text

    return [dict(r, text=redact_text(r["text"])) for r in rows]


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
    not_removed = _kept(edit["removed"], edit["added"])
    # How the device departs from this intent in lines a deploy keeps (C884): the device's
    # lines the render lacks, but those a line the deploy sends replaces. A merge-only deploy
    # sends nothing for them; only a removal (Mode B) takes them off.
    departs = _kept(deploy["removed"], deploy["added"])
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
        # Everything a deploy would send, and how the device departs in lines it keeps.
        "deploy_rows": _rows_of(deploy["added"]),
        "departs_rows": _masked_rows(_rows_of(departs, "keep")),
        # Lines: a section's own line counts only when none of its lines is listed.
        "departs": len([p for p in departs
                        if p[1] or not any(s == p[0] and l for s, l in departs)]),
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
           actor: str, *, source: str = SOURCE, extra_trailers: list = None,
           vlan_databases: dict = None) -> dict:
    """Commit an edit to *hostname*'s intent as *actor*, bound to the version opened.
    *source* and *extra_trailers* name the workflow (feature 7's draft commits as
    ``ai-draft`` with its ``AI-Call:``); a typed edit is ``intent-edit``. One device's case of
    `commit_many`, its answer in the one-device shape."""
    got = commit_many(list_name, [(hostname, text, base)], summary, actor, source=source,
                      extra_trailers=extra_trailers, vlan_databases=vlan_databases)
    return {k: v for k, v in got.items() if k not in ("hostnames", "bases", "each")}


def commit_many(list_name: str, edits: list, summary: str, actor: str, *,
                source: str = SOURCE, extra_trailers: list = None,
                vlan_databases: dict = None) -> dict:
    """Commit edits to several devices' intent (``[(hostname, text, base)]``) as ONE commit
    (one `repo.save_host_vars`, so one `repo.commit()`), as *actor*, each bound to the version
    it opened: refused, nothing written, when any document is missing or refused by the
    editor's check, or any device's intent moved since (`moved`, naming that device). A
    two-ended change drafted in words commits both ends this way (C1908). The answer carries
    the first device's ``hostname`` and ``base`` (the one-device shape `commit` returns), and
    ``hostnames`` and ``bases`` for all. Each device is written in Mercury's own formatting
    (C1693, `hostvars.canonical`): one whose canonical text is what is committed changes
    nothing; one whose change is formatting only must pass Normalise's proof under the lock
    (409, stage "proof", naming the device), its trailer added to the one commit; and the
    answer says, for the first device, ``formatting_only`` and ``reformatted`` (``each`` for
    every device changed).

    A document that ADDS a VLAN to what is committed (C2044) is refused (409, stage
    "capability", naming the device, its platform and device type and where the answer came
    from) unless the device's VLAN database is declared or measured: the one check every
    intent write path asks (`vlan_capability.judge`). *vlan_databases* is ``{hostname:
    vlan_capability.of's answer}`` for a device its caller read already this request (the
    intent patch), so it is read once; any other device adding a VLAN is read here. Removing a
    VLAN, or leaving the list as it was, is never asked about."""
    from modules.nsot import hostvars, repo as repo_service, vlan_capability

    repo = _repo_for(list_name)
    summary = (summary or "").strip()
    if not edits:
        return {"status": 400, "ok": False, "error": "No host_vars document sent"}
    for hostname, text, base in edits:
        if not isinstance(text, str) or not text.strip():
            return {"status": 400, "ok": False, "error": "No host_vars document sent"}
    if not summary:
        return {"status": 400, "ok": False, "error": (
            "A one-line summary is required — it becomes the commit subject, "
            "and 'host_vars: s4' on its own says nothing in a log.")}
    for hostname, text, base in edits:
        if not (base or "").strip():
            return {"status": 400, "ok": False, "stage": "base", "error": (
                f"Not saved: this editor did not say which version of {hostname}'s intent it "
                "opened, so the save could replace a commit made since. Nothing was written. "
                "Reload the page, open the editor again and make the edit there.")}
        checked = validate(hostname, text, list_name)
        if not checked["ok"]:
            return checked
    names = [h for h, _t, _b in edits]
    first = names[0]

    with repo_service.repo_lock(repo):
        changed, currents, trailers = [], {}, list(extra_trailers or [])
        from modules.nsot import intent_normalise
        for hostname, text, base in edits:
            current = hostvars.committed_blob(repo, hostname)
            if current is None:
                return {"status": 404, "ok": False, "error": (
                    f"'{hostname}' has no committed intent yet. Commit the extraction "
                    "first, so the edit has a reviewed baseline to diff against.")}
            if current != (base or "").strip():
                return moved(repo, hostname, (base or "").strip(), current, text)
            currents[hostname] = current
            committed_text = hostvars.blob_text(repo, current) or ""
            typed = text if text.endswith("\n") else text + "\n"
            try:
                # What is written (C1693): the document in Mercury's own formatting.
                written = hostvars.canonical(typed, hostname)
            except ValueError as exc:
                return {"status": 400, "ok": False, "error": str(exc)}
            if written == committed_text:
                continue
            # A VLAN added where no VLAN database is declared or measured (C2044): refused
            # before anything is written, the person's text kept by the editor.
            vlans = vlan_capability.judge(
                list_name, hostname, hostvars.from_yaml(committed_text),
                hostvars.from_yaml(typed), subject="this edit",
                capability=(vlan_databases or {}).get(hostname))
            if not vlans["ok"]:
                return {k: vlans[k] for k in ("status", "ok", "stage", "hostname", "error")}
            formatting = intent_normalise.formatting_only(committed_text, typed)
            if formatting:
                # Normalise (board H-N): refused unless the five lines prove it formatting
                # only, whatever the button showed; proved against what is committed now,
                # under the lock, for each such document.
                proved = intent_normalise.proof(list_name, hostname, typed, committed_text)
                if not proved["ok"]:
                    return {"status": 409, "ok": False, "stage": "proof", "hostname": hostname,
                            "proof": proved, "error": intent_normalise.refusal_words(proved)}
                trailers.append(intent_normalise.trailer(proved))
            changed.append((hostname, typed, written, formatting))
        if not changed:
            layout = any((t if t.endswith("\n") else t + "\n")
                         != (hostvars.blob_text(repo, currents[h]) or "") for h, t, _b in edits)
            return {"status": 200, "ok": True, "hostname": first, "changed": False,
                    "commit": "", "base": currents[first], "hostnames": names,
                    "bases": dict(currents), "message": (
                        ("Nothing to commit: the document is what is already committed."
                         if len(edits) == 1 else
                         "Nothing to commit: each document is what is already committed.")
                        + (" Intent is committed in Mercury's own formatting, so a change of "
                           "comments or layout alone changes nothing." if layout else ""))}
        written_paths = []
        try:
            for hostname, typed, _w, _f in changed:
                written_paths.append(hostvars.write_committed_text(repo, hostname, typed))
        except (hostvars.SecretLeak, ValueError) as exc:
            # A later device refused after an earlier one was written: each written file is
            # put back as committed, so nothing is left half done (C106's rule).
            hostvars.put_back_committed(repo, written_paths)
            if isinstance(exc, hostvars.SecretLeak):
                log.error("intent edit: refused host_vars edit for %s: %s", hostname, exc)
            return {"status": 400, "ok": False, "error": str(exc)}
        hosts = [h for h, _t, _w, _f in changed]
        result = repo_service.save_host_vars(list_name, hosts, actor=actor, source=source,
                                             message=f"host_vars: {', '.join(hosts)} {summary}",
                                             extra_trailers=trailers)
        after = {h: hostvars.committed_blob(repo, h) or currents[h] for h in names}
    each = {h: {"formatting_only": f, "reformatted": w != t} for h, t, w, f in changed}
    mine = each.get(first, {"formatting_only": False, "reformatted": False})
    return {"status": 200, "ok": result.get("ok", False), "hostname": first,
            "changed": bool(result.get("commit")), "commit": result.get("commit", ""),
            "base": after[first], "message": result.get("message", ""),
            "error": result.get("error", ""),
            # Said on the result: what was typed is not byte for byte what was written.
            "formatting_only": mine["formatting_only"], "reformatted": mine["reformatted"],
            "hostnames": names, "bases": after, "each": each}


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
