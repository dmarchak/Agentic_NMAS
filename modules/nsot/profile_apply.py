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

#: The one scope a deploy plan accepts besides the whole intent.
SCOPE = "profile"


class ScopeRefused(ValueError):
    """The profile cannot be applied to this device alone; the message says why."""


def _keyed(config: str) -> list:
    from modules.nsot.deploy import _section_chains

    return [((tuple(chain), line)) for line, chain in _section_chains(config or "")]


def scoped(effective_render: str, own_render: str, captured: str) -> dict:
    """The scoped intended config and the groups a person reads.

    ``config``: the effective render less every line the device's own intent
    would add; ``to_send``: the profile's lines the device lacks (what the
    program sends); ``in_place``: the profile's lines it already holds;
    ``held_back``: the lines its own intent would add, NOT sent by this
    action. Each group is a list of ``{chain, line}``.

    Refuses a profile line that sits under a stanza only the device's OWN
    intent adds: sending the line would send that stanza's header, which is
    not the profile's."""
    eff = _keyed(effective_render)
    own = set(_keyed(own_render))
    have = set(_keyed(captured))
    profile = [k for k in eff if k not in own]
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
