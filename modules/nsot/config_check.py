"""The config repository's check (register C725; Obj 2.1, "configuration changes automatically
trigger a test").

ONE check, run in two places: `scripts/nmas-config-check` (on a laptop, on the host, and by the
config repository's GitHub Actions workflow, `deploy/config-repo/nmas-config-check.yml`, against
a bare checkout), and Mercury's own `repo.commit()`, which runs it on what a commit touches
BEFORE committing and refuses on a failure (:func:`precommit`: only what can fail is computed
there; a commit of goldens alone runs the golden check alone).

It needs NO device, NO secret and NO ``data/`` directory: it reads the repository's files as
they are on disk (a checkout's working tree; in Mercury, the tree the commit is about to take),
never HEAD, because the state under test is the one not yet committed. Every check reuses the
program's own code, so a pass here is the program's own answer:

``yaml``
    every intent (``host_vars/*.yml``) through the intent editor's checks
    (`intent_edit.validate`: YAML, its own device's name, unknown interface keys, the syslog
    block, descriptions), a top-level key holding something that no template in the device's
    closure names and Mercury does not read (`template_reads`, `MERCURY_KEYS`), the profile
    (`profile.problems`), the DHCP records (each writer's shape) and ``templates/bindings.yml``
    (`templates_repo.load_bindings`).
``golden``
    each golden is one configuration of its device, by `save_golden`'s own rule
    (`config_read.problems`, not strict): no second `end`, prompt, echoed command or second
    `hostname`.
``templates``
    every template parses (`templates_repo.check_syntax`).
``render``
    every device's intent, with what it inherits from the profile (`profile.effective`),
    renders through its BOUND template (`templates_repo.render_source`) by the deploy's own
    renderer (`roundtrip.render`). Secret references render as the mask, never resolved.
    The template's approval is reported beside it (a note: an approval is the deploy's gate,
    never a commit's, since a template is committed before it is approved).
``intent-match``
    each golden against its rendered intent, per device (`roundtrip.change_rows`, the masked
    values neutralised: with no secret to hand, a secret's VALUE is not compared). A NOTE,
    never a failure: intent ahead of its device is the normal state between an intent commit
    and its deploy, and a capture records what the device has.
``lint``
    the IOS pitfalls the deploy already refuses: a rendered line carrying a byte an IOS CLI
    cannot accept (`render_artifact._unsendable_lines`, `hostvars.assert_printable`). The lines
    a deploy will ask an authorisation for (`authorisation.flagged`) are NOTES: they are
    legitimate intent, authorised per deploy with a reason.
``secrets``
    no value in a secret position (`redact.replace_positional_values`, the one definition of
    "secret position") in any file but the goldens, no password hash by its shape anywhere
    (`_HASH`), and no ``secrets:`` mapping in an intent. A secret's VALUE outside any position
    (a password typed into a description) is found only where the values are: Mercury, which
    masks by every value it holds and checks intent against the credential store
    (`hostvars.assert_no_secret_values`). A bare checkout has no values, by design; and
    nothing a push made by hand puts on the remote reaches a device, since Mercury publishes
    to the remote and never takes from it.
    Goldens are EXCLUDED by design: they hold the device's own lines verbatim (redact.py's
    docstring: masking them would make ``golden/`` depend on ``data/key.key``). Every line this
    module prints is masked by position (and, in Mercury, by every value it holds).

A result is ``{"check", "status": "pass"|"fail"|"note", "file", "line", "device", "message",
"files"}``; ``files`` are the repository files a failure is attributed to, which is how the
pre-commit scope decides whether a commit caused it.
"""

import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)

#: The repository areas a change to which triggers the check (Mercury's commit, the workflow's
#: `paths`). `tests/test_config_check.py` holds the workflow's paths equal to these.
GOVERNED = ("golden/", "host_vars/", "templates/", "profiles/", "dhcp/")

CHECKS = ("yaml", "golden", "templates", "render", "intent-match", "lint", "secrets")

#: The DHCP records and the shape each writer gives them (modules/dhcp_*.py, `RECORD`).
DHCP_RECORDS = ("dhcp/exclusions.yml", "dhcp/reservations.yml", "dhcp/subnets.yml")

#: A file larger than this is not scanned for secrets (and said so): a config repository's
#: text files are kilobytes.
MAX_SCAN_BYTES = 2_000_000

#: A Jinja expression, statement or comment on one line.
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}")

#: A crypt-format password hash, by shape: IOS type 5 (`$1$`), 8 (`$8$`), 9 (`$9$`) and the
#: `$5$` and `$14$` forms, each `$<id>$<salt>$<hash>`. The value scan needs the credential
#: store's values; this needs none (B8, measured 2026-10-13: no host intent or template holds
#: one).
_HASH = re.compile(r"\$(?:1|5|8|9|14)\$[./A-Za-z0-9]{2,}\$[./A-Za-z0-9]{8,}")


class _Run:
    def __init__(self, repo: str, mask_values: bool, notes: bool = True):
        self.repo = os.path.abspath(repo)
        self.results = []
        #: `{templates/<base>: {device, ...}}`: each library template a device's render
        #: starts at, and the devices whose render did.
        self.rendered_by = {}
        self.mask_values = mask_values
        # False in Mercury's pre-commit: what can only ever be a note (approval, the lines a
        # deploy authorises, Intent-Match) is not computed, since it can never refuse.
        self.notes = notes

    def add(self, check, status, message, file="", line=None, device="", files=None):
        self.results.append({"check": check, "status": status, "file": file, "line": line,
                             "device": device, "message": self.mask(message),
                             "files": sorted(set(files or ([file] if file else [])))})

    def mask(self, text: str) -> str:
        """By position (and in Mercury by every value held), then any password hash by its
        shape: a hash outside a secret position (a comment a template renders, quoted by a
        note) is masked by nothing else."""
        from modules import redact
        if self.mask_values:
            return _HASH.sub("<hash>", redact.redact_text(text or ""))
        return _HASH.sub("<hash>", redact.redact_positional(text or ""))


# ---------------------------------------------------------------------------
# Reading the tree
# ---------------------------------------------------------------------------

def _read(repo: str, rel: str):
    try:
        with open(os.path.join(repo, rel), encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def tree_files(repo: str) -> list:
    """Every file in the repository as a commit would hold it: the tracked and staged ones
    (`git ls-files`), never the gitignored scratch; a folder that is not a git repository is
    walked whole."""
    if os.path.isdir(os.path.join(repo, ".git")):
        got = subprocess.run(["git", "-C", repo, "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], capture_output=True, timeout=60)
        if got.returncode == 0:
            names = [n for n in got.stdout.decode("utf-8", "replace").split("\0") if n]
            return sorted({n for n in names if os.path.isfile(os.path.join(repo, n))})
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            out.append(os.path.relpath(os.path.join(root, f), repo).replace(os.sep, "/"))
    return sorted(out)


def _manifest_entries(repo: str) -> dict:
    """``{name: entry}`` from the committed manifest (`.nsot/manifest.json`), ``{}`` absent."""
    from modules.nsot import manifest
    out = {}
    for _identity, entry in (manifest.load(repo).get("devices") or {}).items():
        if entry.get("name"):
            out[entry["name"]] = entry
    return out


def _yaml_error(exc) -> tuple:
    mark = getattr(exc, "problem_mark", None)
    return (mark.line + 1) if mark else None, getattr(exc, "problem", None) or str(exc)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def _check_intent(run: _Run, rel: str) -> dict:
    """One intent file: the schema rules every intent keeps, whoever wrote it; the parsed
    document, or None.

    The intent editor's AUTHORING rules (`intent_edit.validate`'s syslog block whole or
    absent, no run's notes as a description) are deliberately not applied: they judge what a
    person types, and `hostvars.write_committed` refuses to apply them to EXTRACTED intent,
    which records a device as it is (applied to every intent they refused the fleet's own
    extraction, measured on r2's real capture here). What is applied is what holds for any
    intent: it parses to a mapping, names its own device, has no interface key nothing reads,
    holds printable ASCII and no `secrets:` mapping (`hostvars.assert_no_secret_values`'s
    structural half; its value half needs the credential store, and runs where Mercury has
    one)."""
    import yaml

    from modules.nsot import hostvars, intent_edit

    text = _read(run.repo, rel)
    device = os.path.basename(rel)[:-4]
    if text is None:
        run.add("yaml", "fail", "the file could not be read as UTF-8 text", rel, device=device)
        return None
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        line, why = _yaml_error(exc)
        run.add("yaml", "fail", f"not YAML: {why}", rel, line, device=device)
        return None
    if not isinstance(doc, dict):
        run.add("yaml", "fail", "intent must be a YAML mapping", rel, 1, device=device)
        return None
    failed = False
    named = doc.get("hostname")
    if named and named != device:
        run.add("yaml", "fail", f"this document names {named!r}; a host_vars file names its own "
                f"device, and {rel} must say {device!r}", rel,
                intent_edit._line_of(text, "hostname:"), device=device)
        failed = True
    unknown = hostvars.unknown_interface_keys(doc)
    if unknown:
        names = ", ".join(sorted({f"{k!r} (interfaces[{i}])" for i, k in unknown}))
        run.add("yaml", "fail", f"nothing reads {names}: an interface key that is not one of "
                "the known ones does not render, silently", rel,
                intent_edit._line_of(text, f"{unknown[0][1]}:"), device=device)
        failed = True
    if "\nsecrets:" in "\n" + text:
        run.add("secrets", "fail", "a `secrets:` mapping: committed intent holds secret_refs "
                "(names); values live in the credential store", rel,
                intent_edit._line_of(text, "secrets:"), device=device)
        failed = True
    elif run.mask_values:
        try:
            hostvars.assert_no_secret_values(text, device)
        except hostvars.SecretLeak as exc:
            m = re.search(r"on line (\d+)", str(exc))
            run.add("secrets", "fail", str(exc), rel, int(m.group(1)) if m else None,
                    device=device)
            failed = True
    try:
        hostvars.assert_printable(text, device)
    except hostvars.NonPrintableContent as exc:
        bad = next((n for n, l in enumerate(text.splitlines(), 1)
                    if any(not (0x20 <= ord(c) <= 0x7E) and c != "\t" for c in l)), None)
        run.add("lint", "fail", str(exc), rel, bad, device=device)
        failed = True
    if not failed:
        run.add("yaml", "pass", "parses and matches the intent schema", rel, device=device)
    return doc


def _check_golden(run: _Run, rel: str) -> None:
    """One golden, by the rule `save_golden` applies to every golden it writes
    (`config_read.problems`, not strict): no second `end`, prompt, echoed command or second
    `hostname`, the evidence of a stitched or foreign text. Presence (an `end`, a `hostname`)
    stays the reader's that produced the text, as it is in Mercury. In Mercury this is the
    same verdict `save_golden` already reached; on a push made by hand it is the only one."""
    from modules import config_read

    device = os.path.basename(rel).rsplit(".", 1)[0]
    text = _read(run.repo, rel)
    if text is None:
        run.add("golden", "fail", "the file could not be read as UTF-8 text", rel,
                device=device)
        return
    found = config_read.problems(text, device, strict=False)
    for problem in found:
        run.add("golden", "fail", f"not one configuration of its device: {problem}", rel,
                device=device)
    if not found:
        run.add("golden", "pass", "one configuration of its device", rel, device=device)


def _parsed_or_none(text: str):
    import yaml
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _check_profile(run: _Run):
    """The profile document, or None; ``False`` when present and broken."""
    import yaml

    from modules.nsot import profile

    rel = profile.PROFILE_REL
    text = _read(run.repo, rel)
    if text is None:
        return None
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        line, why = _yaml_error(exc)
        run.add("yaml", "fail", f"not YAML: {why}", rel, line)
        return False
    bad = profile.problems(doc)
    if bad:
        run.add("yaml", "fail", "not a profile: " + "; ".join(bad), rel,
                _line_of(text, bad[0]))
        return False
    run.add("yaml", "pass", "parses and is a profile", rel)
    return doc


def _line_of(text: str, problem: str):
    """The line a profile problem names, by its section's key; None when not found."""
    m = re.match(r"'?([a-z_]+)", problem or "")
    if not m:
        return None
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(m.group(1) + ":"):
            return n
    return None


def _check_dhcp(run: _Run, rel: str) -> None:
    import yaml

    text = _read(run.repo, rel)
    if text is None:
        run.add("yaml", "fail", "the file could not be read as UTF-8 text", rel)
        return
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        line, why = _yaml_error(exc)
        run.add("yaml", "fail", f"not YAML: {why}", rel, line)
        return
    why = ""
    if not isinstance(doc, dict):
        why = "not a mapping"
    elif rel.endswith("exclusions.yml"):
        # dhcp_exclusions.read_committed's own refusal.
        if not isinstance(doc.get("exclusions", []), list) or \
                not isinstance(doc.get("pools", {}), dict):
            why = "not a list of exclusions and a table of pools"
    elif rel.endswith("reservations.yml"):
        if not isinstance(doc.get("reservations", []), list):
            why = "`reservations` is not a list"
    elif rel.endswith("subnets.yml"):
        bad = [k for k, v in doc.items() if not isinstance(v, (list, str))]
        if bad:
            why = f"{', '.join(map(str, bad))}: not a list of subnets"
    if why:
        run.add("yaml", "fail", f"not a DHCP record: {why}", rel, 1)
    else:
        run.add("yaml", "pass", "parses and has its record's shape", rel)


def _check_templates(run: _Run, rels: list) -> bool:
    """Every template parses; bindings readable. False when the bindings are unreadable."""
    from modules.nsot import templates_repo

    for rel in rels:
        if not rel.endswith(".j2"):
            continue
        text = _read(run.repo, rel) or ""
        ok, error = templates_repo.check_syntax(text)
        if ok:
            run.add("templates", "pass", "parses", rel)
        else:
            m = re.match(r"line (\d+): (.*)", error)
            run.add("templates", "fail", f"does not parse: {error}", rel,
                    int(m.group(1)) if m else None)
    try:
        templates_repo.load_bindings(run.repo)
    except templates_repo.BindingsUnreadable as exc:
        run.add("yaml", "fail", str(exc), "templates/bindings.yml", None)
        return False
    return True


#: Top-level intent keys Mercury itself reads, rendered or not (B8: a key outside these and
#: outside every name the device's template reads renders nothing, silently). Each names its
#: reader. Surveyed 2026-10-13: every literal key read off an intent-shaped variable in
#: `modules/`, less those the shipped templates name; a key Mercury starts reading joins here.
MERCURY_KEYS = {
    "hostname": "the document's own device (this check, `hostvars`)",
    "platform": "the dialect when the inventory has none (`_platform`)",
    "secret_refs": "the names of the device's secrets (`hostvars`, the render's `secret()`)",
    "unmodeled": "the lines no parser models, carried verbatim (`roundtrip`)",
    "unmodeled_ack": "a person's acknowledgement of the unmodeled lines (`intent_match`)",
    "profile_exclude": "the profile sections this device declines, each with a reason "
                       "(`profile.effective`)",
    "bootstrap": "onboarding's intent before any full intent (`onboard`, "
                 "`hostvars.is_bootstrap_only`)",
}


def template_reads(root: str, platform: str, name: str) -> set:
    """Every name the template *name* (and each template it includes, imports or extends)
    could read from intent: each attribute and constant subscript taken anywhere, and each
    constant argument of a ``.get(...)``. A name read off any object counts, so a key is
    called unread only when NO template in the closure names it at all (the lenient side:
    this check never refuses a key a template reads)."""
    from jinja2 import Environment, FileSystemLoader, meta, nodes

    env = Environment(loader=FileSystemLoader([os.path.join(root, platform), root]))
    names, seen, todo = set(), set(), [name]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        source = env.loader.get_source(env, current)[0]
        tree = env.parse(source)
        for node in tree.find_all((nodes.Getattr, nodes.Getitem, nodes.Call)):
            if isinstance(node, nodes.Getattr):
                names.add(node.attr)
            elif isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const):
                names.add(str(node.arg.value))
            elif (isinstance(node, nodes.Call) and isinstance(node.node, nodes.Getattr)
                  and node.node.attr == "get" and node.args
                  and isinstance(node.args[0], nodes.Const)):
                names.add(str(node.args[0].value))
        todo += [t for t in meta.find_referenced_templates(tree) if t]
    return names


def _platform(entry: dict, intent: dict) -> str:
    from modules.nsot.platform import is_dialect, platform_for_device
    for candidate in ((entry or {}).get("platform"), (intent or {}).get("platform")):
        dialect = platform_for_device({"platform": candidate}) if candidate else ""
        if is_dialect(dialect):
            return dialect
    return ""


def _check_device(run: _Run, device: str, intent: dict, entry: dict, profile_doc, role: str,
                  approvals: dict) -> None:
    """Render one device's intent; lint the render; compare it with the device's golden."""
    from modules.nsot import approval, hostvars, profile, roundtrip, templates_repo
    from modules.nsot.render_artifact import MASK, _unsendable_lines

    rel = hostvars.committed_rel(device)
    if hostvars.is_bootstrap_only(intent):
        run.add("render", "note", "bootstrap intent (onboarding's): nothing to render yet",
                rel, device=device)
        return
    platform = _platform(entry, intent)
    if not platform:
        # A NOTE: the platform is the inventory's fact (C452), which a bare checkout lacks,
        # and the deploy refuses a device whose platform is unknown, by name.
        run.add("render", "note", "not rendered: no known platform (neither the inventory, "
                "its manifest entry nor its intent names a config dialect)", rel,
                device=device)
        return
    src = templates_repo.render_source(run.repo, device, platform)
    template_rel = f"templates/{src['template']}"
    files = [rel, "templates/bindings.yml"]
    if src["from"] == "library":
        files += [f"templates/{r}" for r in approval.template_closure(run.repo,
                                                                      src["template"])]
    # A top-level key holding something that no template in the closure names, and Mercury
    # does not read, renders nothing, silently (B8; the interface keys' rule, one level up). An
    # empty value is the schema's own (`complete_schema` fills it), never a finding: measured
    # on the host 2026-10-13, the switches' intent carries four keys their template never names,
    # all four empty.
    try:
        reads = template_reads(src["root"], platform, src["name"])
    except Exception as exc:                   # noqa: BLE001 - the render below names it
        log.debug("config_check: %s's template reads unreadable: %s", device, exc)
        reads = None
    unread = sorted(k for k, v in intent.items()
                    if v and reads is not None and k not in reads and k not in MERCURY_KEYS)
    if unread:
        text = _read(run.repo, rel) or ""
        line = next((n for n, l in enumerate(text.splitlines(), 1)
                     if l.startswith(f"{unread[0]}:")), None)
        run.add("yaml", "fail", f"nothing reads {', '.join(repr(k) for k in unread)}: no "
                f"template {template_rel} renders through names it, and Mercury does not read "
                "it, so it renders nothing, silently", rel, line, device=device, files=files)
    if profile_doc:
        files.append(profile.PROFILE_REL)
    effective = profile.effective(intent, profile_doc, platform, role) if profile_doc \
        else intent
    try:
        rendered = roundtrip.render(effective, platform, secret_lookup=lambda _n: MASK,
                                    template_root=src["root"], template_name=src["name"])
    except Exception as exc:                   # noqa: BLE001 - the refusal names it
        run.add("render", "fail", f"its intent does not render through {template_rel} "
                f"({src['from']}): {exc}", rel, None, device=device, files=files)
        return
    where = (f"through {template_rel}" if src["from"] == "library"
             else f"through the built-in {src['template']} ({src.get('why', '')})")
    run.add("render", "pass", f"renders {where}", rel, device=device, files=files)
    if src["from"] == "library":
        # The template this device's render starts at (Lab 7: the config repository's
        # coverage). What it imports is read from the templates themselves, in
        # template_coverage: the closure here once took the templates folder where it takes
        # the repository, and no import counted (C768).
        run.rendered_by.setdefault(template_rel, set()).add(device)
    # lint: the deploy's own refusals, on the render (the mask stands for a printable value).
    for line in _unsendable_lines(rendered.replace(MASK, "x")):
        run.add("lint", "fail", f"the render of its intent has {line}", rel, device=device,
                files=files)
    if not run.notes:
        return                                  # what follows only ever notes
    if src["from"] == "library":
        if src["template"] not in approvals:
            try:
                approvals[src["template"]] = approval.is_approved(run.repo, src["template"])
            except Exception as exc:           # noqa: BLE001 - reported, never guessed
                log.warning("config_check: approval of %s unreadable: %s", src["template"], exc)
                approvals[src["template"]] = None
        state = approvals[src["template"]]
        run.add("render", "note",
                f"{template_rel} is " + ({True: "approved",
                                          False: "NOT approved: a deploy refuses until it is",
                                          None: "of unknown approval (unreadable)"}[state]),
                template_rel, device=device)

    from modules.nsot import authorisation
    try:
        dangerous = authorisation.flagged(rendered.splitlines())
    except Exception as exc:                   # noqa: BLE001
        dangerous = []
        log.warning("config_check: dangerous-line patterns unavailable: %s", exc)
    if dangerous:
        run.add("lint", "note", f"{len(dangerous)} line(s) a deploy sending them asks an "
                "authorisation with a reason for: " + "; ".join(dangerous[:5])
                + (f"; and {len(dangerous) - 5} more" if len(dangerous) > 5 else ""),
                rel, device=device)

    # intent-match: the golden against the render, masked values neutralised.
    golden_rel = (entry or {}).get("golden") or f"golden/{hostvars._safe_hostname(device)}.cfg"
    golden = _read(run.repo, golden_rel)
    if golden is None:
        run.add("intent-match", "note", "no golden: nothing captured to compare", golden_rel,
                device=device)
        return
    rows = roundtrip.change_rows(golden, rendered)
    removed, added = rows["removed"], rows["added"]
    if not removed and not added:
        run.add("intent-match", "pass", "the golden matches its rendered intent"
                + (f" ({rows['masked']} secret value(s) not compared)" if rows["masked"]
                   else ""), golden_rel, device=device)
        return
    shown = [f"- {s} / {l}" if l else f"- {s}" for s, l in removed[:3]] + \
            [f"+ {s} / {l}" if l else f"+ {s}" for s, l in added[:3]]
    run.add("intent-match", "note",
            f"differs (-{len(removed)} +{len(added)}): a `-` line is in the golden and not in "
            f"intent, a `+` line in intent and not in the golden: " + "; ".join(shown),
            golden_rel, device=device)


def _check_secrets(run: _Run, rels: list) -> None:
    """No value in a secret position in any file but the goldens."""
    from modules import redact
    from modules.nsot.render_artifact import MASK

    def placeholder(value: str) -> bool:
        return (not value.strip(MASK[:1]) or value.startswith("<")
                or "{{" in value or "{%" in value)

    for rel in rels:
        if rel.startswith("golden/") or rel.startswith(".git/"):
            continue
        path = os.path.join(run.repo, rel)
        try:
            if os.path.getsize(path) > MAX_SCAN_BYTES:
                run.add("secrets", "note", f"larger than {MAX_SCAN_BYTES} bytes: not scanned",
                        rel)
                continue
        except OSError:
            continue
        text = _read(run.repo, rel)
        if text is None:
            continue                            # binary: nothing typed into it
        found = 0
        for n, line in enumerate(text.splitlines(), 1):
            values = []
            # A template's expression is one token, never a value: `snmp-server host
            # {{ h.address }} {{ h.community }}` reads `{{` as the host otherwise.
            plain = _JINJA.sub("<jinja>", line)
            redact.replace_positional_values(
                plain, lambda label, value, _prefix: (values.append((label, value)), value)[1])
            real = [label for label, value in values if not placeholder(value)]
            if real:
                found += 1
                run.add("secrets", "fail", f"a value in a secret position ({', '.join(real)}): "
                        f"{redact.redact_positional(line.strip())}. Commit a secret "
                        "reference; the value belongs in the credential store", rel, n)
            elif _HASH.search(plain):
                # A hash where no keyword marks a secret (a YAML value, a comment): found by
                # its SHAPE, which needs no value, so it runs on a bare checkout (B8).
                found += 1
                shown = redact.redact_positional(_HASH.sub("<hash>", line.strip()))
                run.add("secrets", "fail", f"a password hash ({shown}): Commit a secret "
                        "reference; the value belongs in the credential store", rel, n)
        if not found and (rel.startswith(GOVERNED) and not rel.startswith("golden/")):
            run.add("secrets", "pass", "no value in a secret position", rel)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run(repo: str, *, touched=None, inventory=None, mask_values: bool = False,
        notes: bool = True) -> dict:
    """The check over *repo*'s files on disk. *touched* (repository-relative paths) scopes it
    to those files and the devices they affect; None is the whole repository. *inventory* is
    ``{device: row}`` (or a function returning it, called only when a device is rendered)
    where Mercury has one: the row's platform and role decide (C452, C225); without it (a bare
    checkout), the manifest's recorded platform and role, then the intent's own platform.
    *notes* False computes only what can fail. Returns ``{"ok", "results", "counts", "devices",
    "intent_match", "scope"}``."""
    import time

    started = time.monotonic()
    repo = os.path.abspath(repo)
    out = _Run(repo, mask_values, notes=notes)
    files = tree_files(repo)
    scoped = touched is not None
    touched = sorted({t.replace(os.sep, "/") for t in (touched or [])})
    present = set(files)
    from modules.nsot import profile as _profile
    manifest = _manifest_entries(repo)

    def in_scope(rel):
        return not scoped or rel in touched

    # The devices in scope: every one; else those a touched template or profile reaches (all),
    # else those whose intent or golden the change touches. Only their intent is read.
    shared = [t for t in touched if t.startswith("templates/") or t == _profile.PROFILE_REL]
    named = None
    if scoped and not shared:
        named = set()
        for t in touched:
            if t.startswith("host_vars/"):
                named.add(os.path.basename(t)[:-4])
            elif t.startswith("golden/") and notes:
                # A golden reaches its device's render only for Intent-Match, a note: with
                # *notes* off (Mercury's pre-commit) it is checked alone (B8), never rendered.
                named |= {n for n, e in manifest.items() if e.get("golden") == t}
                named.add(os.path.basename(t).rsplit(".", 1)[0])

    # 1. YAML and schema.
    intents = {}
    for rel in files:
        if rel.startswith("host_vars/") and rel.endswith(".yml") and rel.count("/") == 1:
            device = os.path.basename(rel)[:-4]
            if in_scope(rel):
                intents[device] = _check_intent(out, rel)
            elif named is None or device in named:
                intents[device] = _parsed_or_none(_read(repo, rel) or "")
    if in_scope(_profile.PROFILE_REL) and _profile.PROFILE_REL in present:
        profile_doc = _check_profile(out)
    else:
        profile_doc = _quiet_profile(repo)
    for rel in DHCP_RECORDS:
        if rel in present and in_scope(rel):
            _check_dhcp(out, rel)
    for rel in files:
        if rel.startswith("golden/") and rel.endswith(".cfg") and rel.count("/") == 1 \
                and in_scope(rel):
            _check_golden(out, rel)

    # 2. Templates.
    templates = [r for r in files if r.startswith("templates/") and in_scope(r)]
    bindings_ok = _check_templates(out, templates) if (templates or not scoped) else True

    # 3. Render, lint, intent-match, per device in scope.
    devices = sorted(d for d in intents if named is None or d in named)
    if callable(inventory):
        inventory = inventory() if devices else {}
    approvals = {}
    if profile_doc is False or not bindings_ok:
        pass                                    # refused above, by name; nothing renders
    else:
        for device in devices:
            intent = intents.get(device)
            if intent is None:
                continue                        # its YAML failure is already reported
            entry = dict(manifest.get(device) or {})
            row = (inventory or {}).get(device) or {}
            if row:
                from modules.nsot.platform import is_dialect, platform_for_device
                if is_dialect(platform_for_device(row)):
                    entry["platform"] = platform_for_device(row)
            role = (row.get("role") or "").strip() if row else (entry.get("role") or "")
            _check_device(out, device, intent, entry, profile_doc or None, role, approvals)

    # 4. Secrets, in every file in scope but the goldens.
    _check_secrets(out, [r for r in files if in_scope(r)])

    results = out.results
    if scoped:
        # A failure counts against THIS change when it is attributed to a file it touches.
        for r in results:
            if r["status"] == "fail" and not set(r["files"]) & set(touched):
                r["status"] = "note"
                r["message"] = "(not caused by this change) " + r["message"]
    counts = {s: sum(1 for r in results if r["status"] == s) for s in ("pass", "fail", "note")}
    match = {r["device"]: ("yes" if r["status"] == "pass" else "no")
             for r in results if r["check"] == "intent-match" and r["file"]
             and not r["message"].startswith("no golden")}
    return {"ok": counts["fail"] == 0, "results": results, "counts": counts,
            "devices": devices, "intent_match": match,
            "intent_match_trailer": _trailer(match),
            "templates": (template_coverage(repo, files, out.rendered_by) if not scoped
                          else None),
            "scope": "touched" if scoped else "whole repository", "touched": touched,
            "seconds": round(time.monotonic() - started, 2)}


def template_coverage(repo: str, files: list, rendered_by: dict) -> dict:
    """The config repository's template coverage (Lab 7), in two kinds:

    - a PARTIAL is imported or included by another of the repository's templates, or named
      with a leading underscore (the convention for a file meant only to be imported, as the
      seeded `_common.j2`); never rendered directly, it is judged by what imports it, and a
      partial nothing imports is the flag (`unimported`);
    - every other template is a BASE, a device's render starting point: each listed with the
      devices whose render started there (*rendered_by*), and one no device renders is the flag
      (`unrendered`: dead, or bound to a platform no device has).

    `{"total", "rendered", "unrendered"}` count and name the BASES only; `"bases"` is
    `{base: [device, ...]}`, `"partials"` `{partial: [importer, ...]}`, `"unimported"` the
    partials nothing imports. Information, never a failure: a person judges each flag."""
    from modules.nsot import approval

    templates = sorted(f for f in files if f.startswith("templates/") and f.endswith(".j2"))
    importers = {t: [] for t in templates}
    for t in templates:
        for name in approval.template_imports(_read(repo, t) or ""):
            target = f"templates/{name}"
            if target in importers and t not in importers[target]:
                importers[target].append(t)
    partials = {t: sorted(by) for t, by in importers.items()
                if by or os.path.basename(t).startswith("_")}
    bases = {t: sorted(rendered_by.get(t, ())) for t in templates if t not in partials}
    return {"total": len(bases), "rendered": [t for t, devs in bases.items() if devs],
            "unrendered": [t for t, devs in bases.items() if not devs],
            "bases": bases, "partials": partials,
            "unimported": [t for t, by in partials.items() if not by]}


#: Devices named per base template in the human summary; the rest are counted (a fleet's
#: template renders hundreds of devices, and the report holds every name).
NAMED_DEVICES = 10


def template_lines(tc: dict) -> list:
    """The template section, one line each: the headline (base templates only), each base with
    the devices that render it, each partial with what imports it, and the flags. Shared by
    `human()` and the config repository's job summary."""
    def short(path):
        return path[len("templates/"):] if path.startswith("templates/") else path

    def devices(names):
        shown = ", ".join(names[:NAMED_DEVICES])
        more = f", and {len(names) - NAMED_DEVICES} more" if len(names) > NAMED_DEVICES else ""
        return f"{len(names)} device(s): {shown}{more}"

    lines = [f"Base templates rendered by some device: {len(tc['rendered'])} of {tc['total']}"]
    for base, names in tc.get("bases", {}).items():
        lines.append(f"  {short(base)}: " + (devices(names) if names
                                               else "NOT RENDERED by any device"))
    for partial, by in tc.get("partials", {}).items():
        lines.append(f"Partial {short(partial)}: " + (
            f"imported by {', '.join(short(b) for b in by)}" if by
            else "NOT IMPORTED by any template"))
    return lines


def _quiet_profile(repo: str):
    import yaml

    from modules.nsot import profile
    text = _read(repo, profile.PROFILE_REL)
    if text is None:
        return None
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return False
    return False if profile.problems(doc) else doc


def _trailer(match: dict) -> str:
    """The check's Intent-Match, in the trailer's words (`intent_match.trailer`'s shape)."""
    total = len(match)
    off = sorted(d for d, v in match.items() if v != "yes")
    if not off:
        return f"Intent-Match: yes ({total} of {total})"
    return "Intent-Match: no: " + ", ".join(off)


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------

def where(r: dict) -> str:
    place = r["file"] + (f" line {r['line']}" if r.get("line") else "")
    return place + (f" ({r['device']})" if r.get("device") and r["device"] not in place else "")


def human(report: dict, verbose: bool = False) -> str:
    """The report as a person reads it: failures first, each with its check, file and line;
    then each check's counts; then the Intent-Match per device."""
    lines = []
    fails = [r for r in report["results"] if r["status"] == "fail"]
    for r in fails:
        lines.append(f"FAIL  {r['check']:<12} {where(r)}: {r['message']}")
    for r in report["results"]:
        if r["status"] == "note" and (verbose or r["check"] == "intent-match"):
            lines.append(f"NOTE  {r['check']:<12} {where(r)}: {r['message']}")
        elif verbose and r["status"] == "pass":
            lines.append(f"PASS  {r['check']:<12} {where(r)}: {r['message']}")
    lines.append("")
    for check in CHECKS:
        rs = [r for r in report["results"] if r["check"] == check]
        c = {s: sum(1 for r in rs if r["status"] == s) for s in ("pass", "fail", "note")}
        state = "FAIL" if c["fail"] else ("PASS" if rs else "----")
        lines.append(f"{state:<5} {check:<12} {c['pass']} passed, {c['fail']} failed, "
                     f"{c['note']} noted")
    lines.append(report["intent_match_trailer"])
    tc = report.get("templates")
    if tc:
        lines += template_lines(tc)
    lines.append(f"{'PASS' if report['ok'] else 'FAIL'}: {report['counts']['fail']} failure(s) "
                 f"over {report['scope']}, {len(report['devices'])} device(s), "
                 f"in {report['seconds']} s")
    return "\n".join(lines)


def refusal(report: dict) -> str:
    """Mercury's refusal of a commit: each failure with its check, file and line."""
    fails = [r for r in report["results"] if r["status"] == "fail"]
    head = (f"refused by the config check (scripts/nmas-config-check): {len(fails)} "
            f"failure(s) in what this commit changes")
    return head + "\n" + "\n".join(f"- {r['check']}: {where(r)}: {r['message']}"
                                   for r in fails)


# ---------------------------------------------------------------------------
# Mercury's pre-commit
# ---------------------------------------------------------------------------

def touched_paths(repo: str, paths=()) -> list:
    """What a commit is about to take in *repo*: the index's changes, and with *paths* (a
    `git commit -- <paths>`, which takes them from the working tree) those paths' changes and
    new files. Governed areas only."""
    def names(*args):
        got = subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=60)
        if got.returncode != 0:
            return []
        return [n for n in got.stdout.decode("utf-8", "replace").split("\0") if n]

    out = set(names("diff", "--cached", "--name-only", "-z"))
    if paths:
        out |= set(names("diff", "HEAD", "--name-only", "-z", "--", *paths))
        out |= set(names("ls-files", "-z", "--others", "--exclude-standard", "--", *paths))
    return sorted(p for p in out if p.startswith(GOVERNED))


def precommit(repo: str, paths=(), list_name: str = "") -> str:
    """The refusal for a commit about to be made in *repo*, or ``""``. Run by `repo.commit()`
    under the repository lock, before git commits: scoped to the files the commit touches and
    the devices they affect (measured 2026-10-12 in the suite: a scoped run 0.0 to 0.2 s, the
    most a template commit re-rendering its bound device; a whole run over r2's real repository
    0.25 s, per device, so a nine-device network's is a few seconds, not measured on the host
    yet), and it counts a failure only when it is attributed to a touched
    file, so a commit is never refused for a fault it did not make."""
    touched = touched_paths(repo, paths)
    if not touched:
        return ""
    # A commit of goldens alone is checked too (B8, the operator, 2026-10-13), by the golden
    # check only: with notes off a golden names no device to render (rendering each one
    # doubled the suite's time, measured 2026-10-12), and its Intent-Match is a note.

    def rows():
        try:
            from modules.nsot.repo import list_of_repo
            from modules.nsot.restore import _devices_of
            name = list_name or list_of_repo(repo)
            if name:
                return {d.get("hostname"): d for d in _devices_of(name) if d.get("hostname")}
        except Exception as exc:               # noqa: BLE001 - the manifest answers
            log.debug("config_check: inventory unavailable for %r: %s", list_name or repo, exc)
        return {}

    report = run(repo, touched=touched, inventory=rows, mask_values=True, notes=False)
    log.info("config_check: %s: %d touched, %s in %s s", repo, len(touched),
             report["counts"], report["seconds"])
    return "" if report["ok"] else refusal(report)
