"""Normalise: a hand-formatted intent document put in Mercury's own formatting, and proved to
change formatting only before anyone may commit it (C1693, board H-N; the operator's order of
2026-10-27).

**Why.** A document that does not round-trip through `hostvars.to_yaml` (a hand edit's
comments, indented lists, quoting) cannot be patched: feature 7 and bulk intent rewrite a
document through the serialiser, so they refuse one whose layout that would drop. Four of the
lab's twelve devices were such (measured 2026-10-27).

**The path.** The Intent tab offers "Normalise the formatting…" only for a document that does
not round-trip (:func:`offered`). It opens the intent editor on Mercury's own serialisation of
the committed document; nothing is written. The editor's check (`intent_edit.preview`) sees an
edit that changes formatting only (:func:`formatting_only`) and draws :func:`proof`'s five
lines in place of the diffs. The commit is the editor's own (`intent_edit.commit`), bound to
the version opened and made as the person with their reason; for a formatting-only edit it
runs the proof again, under the repository's lock, and refuses unless every line passes,
whatever the page showed.

**The proof** (:data:`PROOF`), each line a comparison with both operands read from what is
committed now:
1. ``document``: the parsed document is the same document (`hostvars.same_document`);
2. ``render``: the configuration the new text renders is byte-identical to the committed
   render, both masked, compared as text, never as a canonical diff;
3. ``device``: the device diff is empty: the new render against the committed golden, the
   preview's own comparison (`roundtrip.canonical_diff`), which leaves masked lines aside;
4. ``masked``: so the masked lines are compared by keyed hash (`secret_compare`), the TRUE
   renders of both documents, each secret hydrated from the credential store in memory and
   dropped at once: "N of N identical", a line that differs named by its number and masked
   text, never its value. A formatting change that altered a credential would lock a device
   out, and the masked render cannot see one;
5. ``round_trip``: the new text round-trips, the property a patch needs.

Every differing line is listed, masked by `redact_text`: the render's, the device diff's and
the keyed hash's.
"""

import difflib
import logging

log = logging.getLogger(__name__)

#: The proof's lines, in the order the editor draws them (board H-N).
PROOF = ("document", "render", "device", "masked", "round_trip")

#: Words for a masked value's kind, from the masking's own label (`redact._POSITIONAL`).
_KIND_WORDS = {"enable_secret": "the enable secret", "user_password": "a local user's secret",
               "snmp_community": "an SNMP community", "line_password": "a line password",
               "key_string": "a key string", "shared_key": "a server key",
               "pre_shared_key": "a pre-shared key", "ppp_password": "a PPP password",
               "http_client_password": "the HTTP client password"}


def offered(text) -> bool:
    """Whether the Intent tab offers Normalise for a committed document *text*: it parses to
    a mapping and does not round-trip."""
    from modules.nsot import hostvars

    if not isinstance(text, str) or not text.strip():
        return False
    try:
        return isinstance(hostvars.from_yaml(text), dict) and not hostvars.round_trips(text)
    except Exception:                          # noqa: BLE001 - unparseable: the editor says why
        return False


def normalised(text: str, hostname: str = "") -> str:
    """The committed document *text* in Mercury's own formatting (`hostvars.canonical`)."""
    from modules.nsot import hostvars

    return hostvars.canonical(text, hostname)


def changed_lines(before: str, after: str) -> int:
    """How many of *after*'s lines are not *before*'s, line for line."""
    a, b = (before or "").splitlines(), (after or "").splitlines()
    same = sum(n for _i, _j, n in
               difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return len(b) - same


def formatting_only(committed_text, text) -> bool:
    """Whether committing *text* over *committed_text* changes its formatting only: the two
    parse to the same document, and what a commit would write (Mercury's formatting of
    *text*) is not what is committed."""
    from modules.nsot import hostvars

    try:
        new, old = hostvars.from_yaml(text or ""), hostvars.from_yaml(committed_text or "")
        return hostvars.same_document(new, old) and \
            hostvars.canonical(text, "") != committed_text
    except Exception:                          # noqa: BLE001 - not a document: not formatting
        return False


def _line(key: str, passed: bool, words: str) -> dict:
    return {"key": key, "passed": bool(passed), "words": words}


def _kinds(masked_lines) -> str:
    """The kinds of the values on *masked_lines*, in words, from their placeholders."""
    import re

    seen = []
    for text in masked_lines:
        for label in re.findall(r"<redacted:([a-z_]+)>", text):
            words = _KIND_WORDS.get(label, label.replace("_", " "))
            if words not in seen:
                seen.append(words)
    return ", ".join(seen)


def _masked_compared(ctx: dict, hostname: str, list_name: str, old_doc: dict,
                     new_doc: dict) -> dict:
    """`secret_compare.compare` of the TRUE renders of *old_doc* and *new_doc*: each
    document's secrets hydrated from the credential store, rendered through the device's own
    template, compared, and dropped. Only counts and masked lines leave; no value, no hash."""
    from modules import secret_compare
    from modules.nsot import hostvars, roundtrip, templates_repo

    src = templates_repo.render_source(ctx["repo"], hostname, ctx["platform"])
    kwargs = {"template_name": (src["template"] or "base.j2").split("/")[-1]}
    if src["root"]:
        kwargs["template_root"] = src["root"]
    truthful = []
    for doc in (old_doc, new_doc):
        hydrated = hostvars.hydrate_secrets(ctx["eff"](doc), hostname, list_name)
        truthful.append(roundtrip.render(hydrated, hydrated.get("platform", ctx["platform"]),
                                         **kwargs))
        del hydrated
    got = secret_compare.compare(truthful[0], truthful[1])
    del truthful
    return got


def proof(list_name: str, hostname: str, text: str, committed_text: str, ctx: dict = None) -> dict:
    """The five lines (:data:`PROOF`) for committing *text* over *committed_text*, each with
    whether it passed and its words; ``ok`` only when all five pass. ``differs``: every
    differing line, masked, with where it differs (``render``, ``device``, ``masked``).
    ``changed``/``total``: how many of the new text's lines changed formatting. Writes
    nothing; nothing reaches the device."""
    from modules.nsot import hostvars, intent_edit, roundtrip
    from modules.redact import redact_text

    lines, differs = {}, []
    out = {"ok": False, "lines": [], "differs": differs, "rendered_lines": 0,
           "masked": {"compared": 0, "identical": 0}, "changed": 0, "total": 0}
    try:
        new_text = hostvars.canonical(text, hostname)
    except ValueError as exc:
        new_text = None
        lines["document"] = _line("document", False, f"Mercury's formatting of it is refused: "
                                                     f"{exc}.")
    old_doc = hostvars.from_yaml(committed_text or "")
    if new_text is not None:
        out.update(changed=changed_lines(committed_text, new_text),
                   total=len(new_text.splitlines()))
        new_doc = hostvars.from_yaml(new_text)
        same = hostvars.same_document(new_doc, old_doc)
        lines["document"] = _line("document", same, (
            "The parsed document is equal to the committed one." if same else
            "The parsed document differs from the committed one: "
            + ", ".join(sorted(k for k in set(new_doc) | set(old_doc)
                               if new_doc.get(k) != old_doc.get(k))) + "."))
        ctx = ctx or intent_edit.render_context(list_name, hostname)
        why = ("" if ctx.get("ok") and ctx.get("capture") else
               ctx.get("error") if not ctx.get("ok") else
               f"no golden is recorded for {hostname}, so its render cannot be compared")
        if why:
            for key, words in (("render", "The configuration it renders"),
                               ("device", "The device diff"),
                               ("masked", "The masked lines")):
                lines[key] = _line(key, False, f"{words} could not be compared: {why}.")
        else:
            from routes.templates import artifact_for

            def masked_render(doc):
                return artifact_for(hostname, ctx["capture"], ctx["repo"], ctx["platform"],
                                    ctx["template"],
                                    host_vars=hostvars.hydrate_secrets(
                                        ctx["eff"](doc), hostname, list_name)).rendered_masked
            try:
                old_render, new_render = masked_render(old_doc), masked_render(new_doc)
            except Exception as exc:              # noqa: BLE001 - said on its line
                old_render = new_render = None
                for key in ("render", "device", "masked"):
                    lines[key] = _line(key, False, f"Not rendered: {type(exc).__name__}: "
                                                   f"{exc}.")
            if new_render is not None:
                n = len(new_render.splitlines())
                out["rendered_lines"] = n
                identical = bool(new_render) and new_render == old_render
                rdiff = [] if identical else [
                    l for l in difflib.unified_diff(old_render.splitlines(),
                                                    new_render.splitlines(),
                                                    "committed", "normalised", lineterm="",
                                                    n=0)
                    if l[:1] in "+-" and l[:3] not in ("+++", "---")]
                differs.extend({"from": "render", "line": redact_text(l)} for l in rdiff)
                lines["render"] = _line("render", identical, (
                    f"The configuration it renders is byte-identical to the committed render "
                    f"({n} lines)." if identical else
                    f"The configuration it renders differs from the committed render in "
                    f"{len(rdiff)} lines."))
                vs_device, _masked = roundtrip.canonical_diff(
                    ctx["capture"], new_render, fromfile=f"device ({hostname})",
                    tofile=f"normalised ({hostname})", report_masked=True)
                dlines = [l for l in vs_device.splitlines()
                          if l[:1] in "+-" and l[:3] not in ("+++", "---")]
                differs.extend({"from": "device", "line": redact_text(l)} for l in dlines)
                lines["device"] = _line("device", not vs_device, (
                    f"The device diff is empty: the render against {hostname}'s committed "
                    "golden." if not vs_device else
                    f"The device diff is not empty: {len(dlines)} lines between the render "
                    f"and {hostname}'s committed golden."))
                try:
                    got = _masked_compared(ctx, hostname, list_name, old_doc, new_doc)
                except Exception as exc:          # noqa: BLE001 - said on its line
                    got = None
                    lines["masked"] = _line("masked", False, (
                        f"The masked lines could not be compared by keyed hash: "
                        f"{type(exc).__name__}."))
                if got is not None:
                    out["masked"] = {"compared": got["compared"], "identical": got["identical"]}
                    differs.extend({"from": "masked", "line": d["masked"], "number": d["line"]}
                                   for d in got["differs"])
                    differs.extend({"from": "masked", "line": u["masked"], "number": u["line"],
                                    "side": u["side"]} for u in got["unpaired"])
                    whole = got["compared"] == got["identical"] and not got["unpaired"]
                    kinds = _kinds(d["masked"] for d in got["paired"])
                    lines["masked"] = _line("masked", whole, (
                        f"The masked lines were compared by keyed hash: {got['identical']} of "
                        f"{got['compared']} identical" + (f" ({kinds})" if kinds else "")
                        + ". No value is shown or kept." if whole else
                        "A masked line differs by keyed hash: "
                        + "; ".join(f"line {d['line']}, {d['masked']}"
                                    for d in got["differs"] + got["unpaired"])
                        + ". Its value is not shown. Committing this could change the "
                          "device's credential."))
        rt = hostvars.round_trips(new_text)
        lines["round_trip"] = _line("round_trip", rt, (
            "The new text round-trips, so a patch can change it." if rt else
            "The new text does not round-trip through Mercury's serialiser."))
    for key in PROOF:
        lines.setdefault(key, _line(key, False, "Not compared: the document was refused."))
    out["lines"] = [lines[k] for k in PROOF]
    out["ok"] = all(l["passed"] for l in out["lines"])
    return out


def refusal_words(p: dict) -> str:
    """The commit's refusal when the proof fails: which lines failed, in their own words."""
    failed = [l["words"] for l in p.get("lines") or [] if not l.get("passed")]
    return ("Not committed: this is not formatting only. " + " ".join(failed)
            + " Nothing was written.")


def trailer(p: dict) -> str:
    """The commit's record that the proof passed, with its counts."""
    m = p.get("masked") or {}
    return (f"Formatting-Only: proved (parsed equal; render byte-identical, "
            f"{p.get('rendered_lines', 0)} lines; device diff empty; masked lines "
            f"{m.get('identical', 0)} of {m.get('compared', 0)} identical by keyed hash; "
            "round-trips)")
