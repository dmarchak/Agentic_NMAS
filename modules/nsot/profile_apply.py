"""APPLY MONITORING PROFILE (NSOT_PLAN P.9 step b; docs/MONITORING_PROFILE.md 5).

A device's intent already inherits the network's profile (`profile.effective`),
so an existing device has simply not RECEIVED it. Applying it is a deploy plan
SCOPED to the profile's lines: the same preview, confirm by hash, push, verify
and rollback as any deploy, sending only what the profile supplies.

The scope is a computation on two renders of the device's committed intent,
never a list the browser sends back (the preview is masked, so a community
could never travel back as text):

- the EFFECTIVE render (intent with the profile) is what the device should be;
- the OWN render (intent alone) is what it would be without the profile;
- the profile's lines are the ones in the first and not the second, keyed on
  (section chain, line), as the merge program keys them (C76).

The SCOPED intended config is the effective render with every line the
device's OWN intent would add removed. The merge program built from it sends
exactly the profile's missing lines, and nothing the device's own pending
intent holds: those are named as held back, never sent by this action.

It is recomputed at plan, at apply and on the path that connects, from the
truthful renders each holds, so the confirm hash covers what is sent.
"""

import logging

log = logging.getLogger(__name__)

#: The scope that sends the profile's lines.
SCOPE = "profile"
#: Coverage's combined deploy (artboard A2): the profile's lines AND the device's own IP SLA
#: probes, one program per device, sending only what the device lacks.
TEMPLATES = "templates"


class ScopeRefused(ValueError):
    """The profile cannot be applied to this device alone; the message says why."""


def _keyed(config: str) -> list:
    from modules.nsot.deploy import _section_chains

    return [((tuple(chain), line)) for line, chain in _section_chains(config or "")]


def scoped(effective_render: str, own_render: str, captured: str, also=None) -> dict:
    """The scoped intended config and the groups a person reads.

    ``config``: the effective render less every line the device's own intent
    would add; ``to_send``: the profile's lines the device lacks (what the
    program sends); ``in_place``: the profile's lines it already holds;
    ``held_back``: the lines its own intent would add, NOT sent by this
    action. Each group is a list of ``{chain, line}``.

    *also* ``(chain, line) -> bool``: own-intent lines that join the scope
    (`TEMPLATES`: the device's IP SLA probes, `ip_sla_policy.is_ip_sla_line`).

    Refuses a profile line that sits under a stanza only the device's OWN
    intent adds: sending the line would send that stanza's header, which is
    not the profile's."""
    eff = _keyed(effective_render)
    own = set(_keyed(own_render))
    have = set(_keyed(captured))
    profile = [k for k in eff if k not in own or (also is not None and also(*k))]
    pkeys = set(profile)
    held = [k for k in eff if k not in pkeys and k not in have]
    held_keys = set(held)
    under = []
    for chain, line in profile:
        for depth in range(len(chain)):
            if (tuple(chain[:depth]), chain[depth]) in held_keys:
                under.append((chain, line))
                break
    if under:
        raise ScopeRefused(
            "a line the profile supplies sits under a stanza only this device's own intent "
            "adds, so it cannot be sent without that stanza: "
            + "; ".join(" > ".join(list(c) + [l.strip()]) for c, l in under)
            + ". Deploy the device's intent from a plan first.")
    text = "\n".join(line for (chain, line) in eff if (chain, line) not in held_keys)

    def _rows(keys):
        return [{"chain": list(c), "line": l} for c, l in keys]

    return {"config": text + "\n",
            "to_send": _rows(k for k in profile if k not in have),
            "in_place": _rows(k for k in profile if k in have),
            "held_back": _rows(held)}


def by_section(sections: dict, render_with, own_render: str) -> dict:
    """``{section: [(chain, line), ...]}``: which of the profile's sections
    supplies each line, measured by rendering the device's intent with that
    section ALONE (never guessed from a line's first word). *sections*:
    ``{name: data}`` as `profile.sections_for` returns; *render_with*:
    ``(sections) -> text``."""
    own = set(_keyed(own_render))
    out = {}
    for name in sections:
        try:
            text = render_with({name: sections[name]})
        except Exception as exc:              # noqa: BLE001
            log.warning("profile apply: the %s section alone did not render: %s", name, exc)
            continue
        out[name] = [k for k in _keyed(text) if k not in own]
    return out


def for_capture(list_name: str, hostname: str, platform: str, role: str, capture: str,
                *, repo: str = "", doc=None) -> dict:
    """THE PROFILE FOR A DEVICE WITH NO INTENT YET (P.9 step c): onboarding's
    phase 2 and adopt, which reach a device whose committed intent is
    onboarding's bootstrap or nothing. Computed from the device's CAPTURE,
    the way `template_report` measures a template: its own parse rendered
    alone, and rendered with the profile; the profile's missing lines are
    what `scoped()` keeps.

    ``{"applies", "why", "commands", "masked", "to_send", "in_place",
    "by_section", "sources", "template", "fingerprint"}``. ``commands`` is the
    TRUTHFUL program (the profile's secrets resolved, in memory): a caller
    returns ``masked`` and the fingerprint, never it. ``applies`` False is
    not an error: ``why`` says what was not done and what to do, and the
    device is onboarded without it (the coverage row and Apply remain).

    Refuses to guess: a template that does not reproduce the device as it
    is, a profile secret with no stored value and a scope the device's own
    stanzas would carry each leave ``applies`` False, naming why."""
    import hashlib
    import os

    from modules import credentials
    from modules.nsot import profile as _profile, roundtrip, templates_repo
    from modules.nsot.deploy import assert_sendable, command_fingerprint, merge_commands, \
        render_for_deploy
    from modules.nsot.parsers import get_parser
    from modules.redact import redact_positional

    out = {"applies": False, "why": "", "commands": [], "masked": [], "to_send": [],
           "in_place": [], "by_section": {}, "sources": {}, "template": {},
           "fingerprint": ""}
    if not repo:
        from modules.config import get_list_data_dir
        repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    if doc is None:
        doc = _profile.read_committed(repo)
    if not doc:
        out["why"] = (f"{list_name} has no committed monitoring profile, so there is nothing "
                      "to apply: propose the network's profile, then apply it from the "
                      "device's page")
        return out
    own = get_parser(platform).parse(capture or "")
    sections = _profile.sections_for(doc, platform, role, own)
    if not sections:
        out["why"] = (f"no section of {list_name}'s monitoring profile applies to "
                      f"{hostname} (platform {platform}, role {role or 'none'})")
        return out
    src = templates_repo.render_source(repo, hostname, platform)
    out["template"] = {"template": src["template"], "from": src["from"]}

    def render(doc_):
        return render_for_deploy(doc_, platform, template_root=src["root"],
                                 template_name=src["name"])

    own_render = render(own)
    rep = roundtrip.compare(capture, own_render, own)
    gaps = [f"{rep[k]} {words}" for k, words in (
        ("missing_from_render", "line(s) it does not reproduce"),
        ("extra_in_render", "line(s) it invents"),
        ("reordered_sections", "section(s) it reorders")) if rep.get(k)]
    if gaps:
        out["why"] = (f"the template {src['template']} does not reproduce {hostname} as it is ("
                      + ", ".join(gaps) + "), so a program computed from it is not trusted: "
                      "seed its intent once it is managed, then apply the profile from its page")
        return out

    values, missing = {}, []
    for ref in sorted(set().union(*(_profile.secret_refs(d) for d in sections.values()))):
        value = (credentials.get_template_secret(
                     credentials.template_secret_key(list_name, hostname, ref))
                 or credentials.get_template_secret(credentials.profile_secret_key(list_name, ref)))
        if value:
            values[ref] = value
        else:
            missing.append(ref)
    if missing:
        out["why"] = (f"the profile names secret(s) with no stored value: {', '.join(missing)}; "
                      "propose the profile again to store the network's value")
        return out

    def with_profile(doc_):
        eff = _profile.effective(own, doc_, platform, role)
        eff["secrets"] = {**(own.get("secrets") or {}), **values}
        return render(eff)

    try:
        sc = scoped(with_profile(doc), own_render, capture)
    except ScopeRefused as exc:
        out["why"] = str(exc)
        return out
    commands = merge_commands(sc["config"], capture)
    if commands:
        assert_sendable(commands)

    def render_with(secs):
        return with_profile({"version": doc.get("version"),
                             "sections": {k: doc["sections"][k] for k in secs}})

    def _masked_rows(rows):
        return [{"chain": [redact_positional(c) for c in r["chain"]],
                 "line": redact_positional(r["line"])} for r in rows]

    # Lines the parser does not model are left alone by this program (it sends
    # only the profile's lines), so they never block it; they are NAMED, masked,
    # because a monitoring line in a form the parser does not model is one the
    # profile's line will sit beside.
    out["unmodeled"] = [redact_positional(u.get("line", "")) for u in own.get("unmodeled") or []]
    out.update({
        "applies": True, "commands": commands,
        "masked": [redact_positional(c) for c in commands],
        # Masked: the caller returns these, and a community sits in a line.
        "to_send": _masked_rows(sc["to_send"]), "in_place": _masked_rows(sc["in_place"]),
        "by_section": {k: [{"chain": list(c), "line": redact_positional(l)} for c, l in rows]
                       for k, rows in by_section(sections, render_with, own_render).items()},
        "sources": {k: (doc["sections"][k].get("source") or "") for k in sections},
        "capture_hash": hashlib.sha256((capture or "").encode()).hexdigest()[:16],
    })
    # Bound to the program AND the capture it was computed against, so a
    # device that moved, or a profile that changed, refuses the confirm.
    out["fingerprint"] = command_fingerprint(commands + ["#capture " + out["capture_hash"]])
    if not commands:
        out["why"] = f"{hostname} already holds every line the profile supplies"
    return out


def superseded(profile_lines: list, removable: list) -> list:
    """The removable lines on the device that the profile SUPERSEDES: a line of
    the same measured removal shape as one the profile supplies (an old
    `logging host` beside the profile's, another community), judged by Mode
    B's own shape table (`removal.shape_for`), never by a prefix. Each keeps
    its removal ID and why it cannot be removed, where it cannot."""
    from modules.nsot.removal import shape_for

    shapes = set()
    for row in profile_lines:
        s = shape_for(tuple(row["chain"]), row["line"], "leaf") \
            or shape_for(tuple(row["chain"]), row["line"], "stanza")
        if s:
            shapes.add(s.key)
    out = []
    for c in removable or []:
        s = shape_for(tuple(c.get("chain") or ()), c.get("line", ""), c.get("kind") or "leaf")
        if s and s.key in shapes:
            out.append({"id": c.get("id", ""), "chain": list(c.get("chain") or []),
                        "line": c.get("line", ""), "shape": s.key,
                        "why_not": c.get("why_not", "")})
    return out
