"""History › Remote set-up on v2 (C631, 2026-10-10; the agent's board under the Phase 7 mode,
docs/STANDING_APPROVAL_LOG.md). Connecting a network's existing remote, the write probe, what a
first push would publish and its typed acknowledgement, and automatic pushing: the set-up acts
CUTOVER once called CLI-only through a command that never existed. They need a verified person
(`publish_remote`), which a host command cannot carry; a v2 card can.

Every act is `modules/nsot/remote.py`'s own function, the one today's `/remote/*` routes call
(one home per action): `adopt` (each field one token of its shape, C636), `verify` with the
write probe, `first_push_preview` and `gated_summary`, `acknowledge` (bound to the fingerprints
the card SHOWED, R41), `enable_auto_push` (only after a successful push). This module shapes
what the card draws, never a value: a secret is a kind, a count and a salted fingerprint.
"""

import logging

log = logging.getLogger(__name__)


class Refused(ValueError):
    """Nothing was done; the message names what was compared."""


def network(name: str) -> str:
    """The network a form names, refused when there is none (a write carries its list)."""
    from modules.nsot import listref

    if not (name or "").strip() or not listref.exists(name):
        raise Refused(f"there is no network {name!r}")
    return listref.resolve(name).name


def view(list_name: str) -> dict:
    """The card: the remote as recorded (no remote, unreadable, or its facts), what was
    acknowledged, and each field's shape for the form."""
    from modules.nsot import remote as R

    config, unreadable = R.config_or_refusal(list_name)
    ack = (config or {}).get("acknowledged_secrets") or None
    last = (config or {}).get("last_push") or None
    return {
        "list": list_name, "unreadable": unreadable, "configured": bool(config),
        "remote": None if not config else {
            "owner_repo": f"{config.get('owner')}/{config.get('repo')}",
            "branch": config.get("branch") or "main", "ssh_alias": config.get("ssh_alias", ""),
            "key_path": config.get("key_path", ""), "managed": bool(config.get("managed_by_nmas")),
            "adopted_at": config.get("adopted_at", ""), "adopted_by": config.get("adopted_by", ""),
            "verified_at": config.get("verified_at", ""),
            "auto_push": bool(config.get("auto_push")),
            "last_push": {"at": last.get("at", ""), "by": last.get("by", "")} if last else None},
        "acknowledged": None if not ack else {
            "at": ack.get("at", ""), "by": ack.get("by", ""), "kinds": list(ack.get("kinds") or []),
            "counts": dict(ack.get("counts") or {})},
        "shapes": {k: words for k, (_shape, words) in R.SETUP_SHAPES.items()},
    }


def connect(list_name: str, form: dict, actor: str) -> dict:
    """Record the network's existing remote (`remote.adopt`). Raises `Refused` naming why."""
    from modules.nsot import remote as R

    out = R.adopt(list_name, ssh_alias=(form.get("ssh_alias") or "").strip(),
                  owner=(form.get("owner") or "").strip(), repo=(form.get("repo") or "").strip(),
                  branch=(form.get("branch") or "").strip() or "main",
                  key_path=(form.get("key_path") or "").strip(), actor=actor)
    if not out.get("ok"):
        raise Refused(out.get("error") or "the remote was not recorded")
    return out


def write_probe(list_name: str, actor: str) -> dict:
    """Every pre-push check and the write probe (`remote.verify`): ``{"ok", "checks": [{"name",
    "ok", "detail"}]}``, each detail masked."""
    from modules.nsot import remote as R
    from modules.redact import redact_text

    out = R.verify(list_name, with_write_probe=True, actor=actor)
    if "checks" not in out:
        raise Refused(out.get("error") or "the remote could not be verified")
    return {"ok": bool(out.get("ok")),
            "checks": [{"name": c.get("name", ""), "ok": bool(c.get("ok")),
                        "detail": redact_text(str(c.get("detail") or ""))[:300]}
                       for c in out["checks"]]}


def publication(list_name: str) -> dict:
    """What a first push would publish (`remote.first_push_preview`): commits, tags and notes
    counted, the gated secrets by kind, count and fingerprint, the reported ones (dead values,
    hashes) counted, and the words an acknowledgement must type. Never a value."""
    from modules.nsot import remote as R

    out = R.first_push_preview(list_name)
    if not out.get("ok"):
        raise Refused(out.get("error") or "the history could not be read")
    gated = R.gated_summary(out["secrets"])
    reported: dict = {}
    for row in out["secrets"].get("rows") or []:
        if not (row.get("recoverable") and row.get("live")):
            reported[row["kind"]] = reported.get(row["kind"], 0) + (row.get("distinct") or 0)
    return {"owner_repo": out["owner_repo"], "branch": out["branch"],
            "commits": out["commits"], "commits_touching_golden": out["commits_touching_golden"],
            "tags": out["tags"], "tags_by_prefix": out["tags_by_prefix"], "notes": out["notes"],
            "gated": gated, "expected": " ".join(gated["kinds"]), "reported": reported}


def acknowledge(list_name: str, typed: str, shown: list, actor: str, actor_kind: str) -> dict:
    """A person accepts publishing the gated material: the typed words must name the gated
    kinds as the history holds them NOW, and the fingerprints the card showed must be the ones
    there now (`remote.acknowledge`). Raises `Refused` naming what differed."""
    from modules.nsot import remote as R

    now = publication(list_name)
    if not now["gated"]["kinds"]:
        raise Refused("nothing in the history needs an acknowledgement")
    if (typed or "").strip() != now["expected"]:
        raise Refused(f"the words typed were {typed.strip()!r}; the gated kinds are "
                      f"{now['expected']!r}, typed exactly")
    out = R.acknowledge(list_name, actor=actor, actor_kind=actor_kind, shown=list(shown))
    if not out.get("ok"):
        raise Refused(out.get("error") or "not acknowledged")
    log.info("remote_setup: '%s' publication acknowledged by %s (%s)", list_name, actor,
             actor_kind)
    return out


def auto_push(list_name: str, actor: str) -> dict:
    """Turn automatic pushing on (`remote.enable_auto_push`): only after a successful push."""
    from modules.nsot import remote as R

    out = R.enable_auto_push(list_name, actor=actor)
    if not out.get("ok"):
        raise Refused(out.get("error") or "automatic pushing was not turned on")
    return out
