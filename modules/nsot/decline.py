"""Decline a profile section on one device, with a reason, and undo it (C718; board C603's
"C718" page, APPROVED 2026-10-13).

A person chooses not to fill a gap Coverage shows (r6's IP SLA: a probe would load s3, which
carries the management path). The decline is one ``profile_exclude`` entry in the device's
committed intent, the shape `profile.excluded` and Coverage already read, which gains ``by``
and ``at``: who declined and when. No second list of declines.

Nothing is sent to the device: its configuration does not change, so there is no program, no
hold on the device's session and no verify. The preview is the intent change; the confirm is
bound to it by hash (the intent committed now, the document that would be committed, and the
person who would be recorded), and the apply recomputes it under the device's hold, so an
intent that moved, or another person confirming, is refused, naming what moved. One commit as
the verified person, ``Source: decline``; a failed commit puts the file back.

Undo is the same preview with the entry removed: a second commit, the first kept in history.
"""

import difflib
import logging
import time

from modules.nsot.intent_ops import _hash, _repo, public
#: A profile section a person may decline on one device: the profile's own sections.
from modules.nsot.profile import SECTIONS

log = logging.getLogger(__name__)

SOURCE = "decline"

#: The steps a decline (or its undo) takes, as the manual's How it works names them.
STEPS = (
    ("preview", "Preview", "the intent change: one profile_exclude entry with the section, your "
                           "reason, you and the time; the checks; nothing written"),
    ("hold", "Hold", "the device held, so no other operation changes its intent meanwhile"),
    ("recompute", "Recompute", "the change computed again and compared with the preview's hash; "
                               "a moved intent, or another person confirming, is refused"),
    ("write", "Write", "the device's intent file written"),
    ("record", "Record", "one commit as you, Source: decline; a failed commit puts the file "
                         "back"),
)

#: How each section is said on the page.
WORDS = {"snmp": "SNMP", "syslog": "Syslog", "ntp": "NTP", "management": "Management",
         "lldp": "LLDP", "cdp": "CDP", "telemetry": "Telemetry", "ip_sla": "IP SLA"}


def declines(intent: dict) -> dict:
    """``{section: {"reason", "by", "at"}}``: each section the device's intent excludes, with
    who and when when a person declined it (an entry without ``by`` predates C718 and says
    only its reason)."""
    out = {}
    for e in (intent or {}).get("profile_exclude") or []:
        if isinstance(e, dict) and e.get("section"):
            out[str(e["section"])] = {"reason": str(e.get("reason") or ""),
                                      "by": str(e.get("by") or ""), "at": str(e.get("at") or "")}
    return out


def now_at() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def entry(list_name: str, hostname: str, section: str, *, reason: str = "", actor: str = "",
          at: str = "", undo: bool = False) -> dict:
    """What declining (or, with *undo*, undoing the decline of) *section* on *hostname* would
    commit: ``{device, section, words, undo, reason, by, at, diff, checks, error, hash}``. A
    read: nothing is written. *at* is the preview's own time, carried to the confirm."""
    from modules.nsot import hostvars
    from modules.nsot.authorisation import reason_problem
    from modules.nsot.device_ops import busy_text

    reason = " ".join(str(reason or "").split())
    out = {"device": hostname, "section": section, "words": WORDS.get(section, section),
           "undo": undo, "reason": reason, "by": actor, "at": at or now_at(), "diff": [],
           "checks": [], "error": "", "hash": "", "ready": False, "blocked": "",
           "busy": busy_text(list_name, hostname)}
    if section not in SECTIONS:
        out["error"] = f"{section!r} is not a section of the monitoring profile ({', '.join(SECTIONS)})"
        return out
    repo = _repo(list_name)
    now_text, _state = hostvars.committed_at_head(repo, hostname)
    if now_text is None:
        out["error"] = f"{hostname} has no committed intent: nothing to {'undo' if undo else 'decline'} in"
        return out
    doc = hostvars.from_yaml(now_text)
    have = declines(doc)
    entries = [e for e in doc.get("profile_exclude") or [] if isinstance(e, dict)]
    if undo:
        if section not in have:
            out["error"] = f"{hostname}'s {out['words']} is not declined: nothing to undo"
            return out
        out.update(reason=have[section]["reason"], by=have[section]["by"],
                   at=have[section]["at"])
        kept = [e for e in entries if e.get("section") != section]
    else:
        out["checks"].append(("pass" if actor else "fail",
                              "you are a verified person" if actor else
                              "no verified person: a decline is recorded as the person who "
                              "makes it"))
        if section in have:
            out["error"] = (f"{hostname}'s {out['words']} is already declined: "
                            f"\"{have[section]['reason']}\"")
            return out
        problem = reason_problem({"line": section, "reason": reason})
        out["checks"].append(("fail", problem) if problem else
                             ("pass", "the reason has three words or more"))
        if section == "ip_sla":
            # An operation as intent holds it: its id and its settings, the first naming its
            # kind and target ("icmp-echo <target> source-interface Loopback0").
            probes = [f"ip sla {p.get('id')}: {str((p.get('settings') or [''])[0]).strip()}"
                      if isinstance(p, dict) else str(p) for p in doc.get("ip_sla") or [] if p]
            out["checks"].append(
                ("fail", f"{hostname}'s intent holds IP SLA operations ({', '.join(probes)}): "
                         "remove them first; a declined section with probes in intent is "
                         "refused") if probes else
                ("pass", f"{hostname} has no IP SLA operation in intent"))
        if section == "ip_sla" and doc.get("ip_sla"):
            out["error"] = out["checks"][-1][1]
            return out
        kept = entries + [{"section": section, "reason": reason, "by": actor, "at": out["at"]}]
    new = dict(doc)
    if kept:
        new["profile_exclude"] = kept
    else:
        new.pop("profile_exclude", None)
    document = hostvars.to_yaml(new)
    out["diff"] = [l for l in difflib.unified_diff(now_text.splitlines(), document.splitlines(),
                                                    lineterm="", n=1)
                   if not l.startswith(("---", "+++"))]
    # Ready when every check passes: the reason and the person are checks the card shows while
    # the reason is typed, and only a ready entry carries the hash a confirm is bound to.
    failed = [w for s, w in out["checks"] if s == "fail"]
    out["ready"] = not failed
    out["blocked"] = failed[0] if failed else ""
    if out["ready"]:
        out["hash"] = _hash(section, undo, actor, out["at"], now_text, document)
        out["_document"] = new
    return out


def apply(list_name: str, hostname: str, section: str, confirmed: str, *, actor: str,
          reason: str = "", at: str = "", undo: bool = False) -> dict:
    """Commit the confirmed decline (or its undo): recomputed under the device's hold and
    refused if it moved; one commit of this device's intent file as *actor*; a failed commit
    puts the file back. ``{device, outcome, reason, entry, save}``; outcome one of declined,
    undone, refused, moved, failed, busy."""
    from modules.nsot import device_ops, hostvars
    from modules.nsot.repo import save_host_vars

    repo = _repo(list_name)
    what = "undo a decline" if undo else "decline a profile section"
    try:
        with device_ops.hold(list_name, hostname, what, actor):
            e = entry(list_name, hostname, section, reason=reason, actor=actor, at=at,
                      undo=undo)
            if e["error"] or not e["ready"]:
                return {"device": hostname, "outcome": "refused",
                        "reason": e["error"] or e["blocked"], "entry": public(e)}
            if e["hash"] != confirmed:
                return {"device": hostname, "outcome": "moved", "entry": public(e),
                        "reason": (f"{hostname}'s intent, or who would be recorded, moved since "
                                   f"the preview ({confirmed} -> {e['hash']}); nothing was "
                                   "committed")}
            path = hostvars.committed_path(repo, hostname)
            try:
                hostvars.write_committed(repo, e["_document"])
            except (hostvars.SecretLeak, hostvars.NonPrintableContent) as exc:
                return {"device": hostname, "outcome": "refused", "reason": str(exc),
                        "entry": public(e)}
            words = e["words"]
            message = (f"host_vars: {hostname} undoes the decline of {words}" if undo else
                       f"host_vars: {hostname} declines {words}: {e['reason']}")
            save = save_host_vars(list_name, [hostname], actor=actor, source=SOURCE,
                                  message=message,
                                  extra_trailers=[f"Section: {section}"])
            if not save.get("ok"):
                hostvars.put_back_committed(repo, [path])
                return {"device": hostname, "outcome": "failed", "entry": public(e),
                        "reason": save.get("error") or "the commit failed", "save": save}
            return {"device": hostname, "outcome": "undone" if undo else "declined",
                    "entry": public(e), "save": save, "reason": ""}
    except device_ops.DeviceBusy as exc:
        return {"device": hostname, "outcome": "busy",
                "reason": f"{exc}. Nothing was committed."}
