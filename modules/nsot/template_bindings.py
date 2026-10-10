"""nsot/template_bindings.py — which template renders which device, changed on v2 (cutover
blocker 5, 2026-10-10; drawn under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md).

A network's `templates/bindings.yml` holds two maps: each platform's template, and per-device
overrides. `templates_repo.template_for_device` is the one reader (an override, else its
platform's). Here: the view (both maps, each choice a committed template of the right
platform); the preview of a change (every device whose template moves, before and after, and
whether the template it moves to is approved, since a deploy renders only through an approved
one); and the apply, bound to the bindings file committed when the preview was read and to
the change previewed, under the repository's lock, as one commit with its reason. Nothing
here contacts a device; a device moved to another template is checked at its own deploy.
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

#: The steps, each named on the manual page (docs/manual/how-it-works/edit-template.md).
STEPS = ("view", "preview", "apply")


def _repo(list_name: str) -> str:
    from modules.nsot import approve_op
    return approve_op.repo_for(list_name)


def _templates(repo: str) -> list:
    """Every committed template a device can render through (shared macro files are not)."""
    from modules.nsot import approve_op

    return [p for p in approve_op.committed_templates(repo)
            if not p.split("/")[-1].startswith("_")]


def _devices(repo: str) -> list:
    """``[(name, platform)]`` for every device in the manifest, the platform as templates key it."""
    from modules.nsot import manifest, templates_repo

    out = []
    for _identity, entry in manifest.load(repo)["devices"].items():
        name = entry.get("name", "")
        if name:
            out.append((name, templates_repo._platform_slug(entry.get("platform", ""))))
    return sorted(out)


def view(list_name: str) -> dict:
    """``{"ok", "platforms", "overrides", "devices", "base", "error"}``: both maps, each entry
    with the templates it may choose (its own platform's), and the committed file's blob."""
    from modules.nsot import templates_repo

    repo = _repo(list_name)
    try:
        b = templates_repo.load_bindings(repo)
    except templates_repo.BindingsUnreadable as exc:
        return {"ok": False, "error": str(exc), "platforms": [], "overrides": [],
                "devices": [], "base": ""}
    templates = _templates(repo)
    devices = _devices(repo)
    platforms = sorted({p for _n, p in devices} | set(b["platforms"]))
    return {"ok": True, "error": "",
            "platforms": [{"platform": p, "template": b["platforms"].get(p, ""),
                           "choices": [t for t in templates if t.split("/")[0] == p]}
                          for p in platforms],
            "overrides": [{"device": d, "template": t,
                           "platform": dict(devices).get(d, ""),
                           "choices": [x for x in templates
                                       if x.split("/")[0] == dict(devices).get(d, "")]}
                          for d, t in sorted(b["overrides"].items())],
            "devices": [n for n, _p in devices],
            "base": templates_repo.committed_blob(repo, templates_repo.BINDINGS_FILE)}


def proposal(list_name: str, form) -> tuple:
    """``(bindings, problem)``: the bindings the form asks for, or why they cannot be.

    The form sends ``platform::<p>`` per platform, ``override::<device>`` per standing override
    (empty: remove it, so the device renders through its platform's), and one new override as
    ``add_device`` with ``add_template``. Each template must be committed and of the platform
    it is bound for: a device rendered through another platform's template is refused."""
    repo = _repo(list_name)
    templates = set(_templates(repo))
    devices = dict(_devices(repo))
    platforms, overrides = {}, {}
    for key in form.keys():
        value = (form.get(key) or "").strip()
        if key.startswith("platform::"):
            p = key[len("platform::"):]
            if value:
                platforms[p] = value
        elif key.startswith("override::"):
            d = key[len("override::"):]
            if value:
                overrides[d] = value
    add_d, add_t = (form.get("add_device") or "").strip(), (form.get("add_template") or "").strip()
    if add_d or add_t:
        if not (add_d and add_t):
            return None, "a new override needs both a device and a template"
        overrides[add_d] = add_t
    for p, t in platforms.items():
        if t not in templates:
            return None, f"{p}: {t!r} is not a committed template of this network"
        if t.split("/")[0] != p:
            return None, f"{p}: {t!r} is a {t.split('/')[0]} template, not a {p} one"
    for d, t in overrides.items():
        if d not in devices:
            return None, f"there is no device {d!r} in this network"
        if t not in templates:
            return None, f"{d}: {t!r} is not a committed template of this network"
        if t.split("/")[0] != devices[d]:
            return None, (f"{d} is a {devices[d] or 'platform-less'} device, and {t!r} is a "
                          f"{t.split('/')[0]} template")
    return {"platforms": platforms, "overrides": overrides}, ""


def fingerprint(bindings: dict) -> str:
    return hashlib.sha256(json.dumps(bindings, sort_keys=True).encode()).hexdigest()


def _moves(repo: str, proposed: dict) -> list:
    """Every device whose template changes: ``{"device", "before", "after", "approved"}``."""
    from modules.nsot import approval, templates_repo

    current = templates_repo.load_bindings(repo)

    def pick(b, name, platform):
        return b["overrides"].get(name) or b["platforms"].get(platform, f"{platform}/base.j2")

    out = []
    for name, platform in _devices(repo):
        before, after = pick(current, name, platform), pick(proposed, name, platform)
        if before != after:
            out.append({"device": name, "before": before, "after": after,
                        "approved": approval.is_approved(repo, after)})
    return out


def preview(list_name: str, form) -> dict:
    """The change: the bindings proposed, every device whose template moves, the fingerprint
    the apply is bound to, and the committed file's blob. Writes nothing."""
    from modules.nsot import templates_repo

    repo = _repo(list_name)
    proposed, problem = proposal(list_name, form)
    base = templates_repo.committed_blob(repo, templates_repo.BINDINGS_FILE)
    if problem:
        return {"ok": False, "refused": problem, "base": base}
    try:
        moves = _moves(repo, proposed)
    except templates_repo.BindingsUnreadable as exc:
        return {"ok": False, "refused": str(exc), "base": base}
    return {"ok": True, "refused": "", "proposed": proposed, "moves": moves,
            "unapproved": sorted({m["after"] for m in moves if not m["approved"]}),
            "fingerprint": fingerprint(proposed), "base": base}


def apply(list_name: str, form, base: str, shown: str, summary: str, actor: str) -> dict:
    """Commit the bindings previewed as *actor*: ``{"ok", "status", "commit", "moves", ...}``.
    Refused, nothing written, when the committed file moved since the preview (*base*), when
    the change is not the one previewed (*shown*), or with no reason."""
    from modules.nsot import repo as repo_service, templates_repo

    summary = " ".join((summary or "").split())
    if not summary:
        return {"ok": False, "status": 400, "error": "say why in one line: it is the commit's "
                                                      "subject"}
    proposed, problem = proposal(list_name, form)
    if problem:
        return {"ok": False, "status": 400, "error": problem}
    repo = _repo(list_name)
    with repo_service.repo_lock(repo):
        current = templates_repo.committed_blob(repo, templates_repo.BINDINGS_FILE)
        if current != (base or "").strip():
            return {"ok": False, "status": 409, "stage": "moved",
                    "error": (f"the bindings changed after your preview: you previewed "
                              f"{(base or '')[:8] or 'no committed file'}, committed now is "
                              f"{current[:8] or 'nothing'}. Preview again")}
        got = fingerprint(proposed)
        if got != (shown or "").strip():
            return {"ok": False, "status": 409, "stage": "changed",
                    "error": (f"this is not the change previewed (previewed "
                              f"{(shown or '')[:12]}, sent {got[:12]}). Preview again")}
        moves = _moves(repo, proposed)
        templates_repo.save_bindings(repo, proposed)
        out = repo_service.save_templates(list_name, [templates_repo.BINDINGS_FILE],
                                          actor=actor,
                                          message=f"template: bindings {summary}")
        if not out.get("ok"):
            # Put the committed file back: every render reads the file on disk, and a change
            # that is in no commit must not decide which template renders a device.
            rel = f"{templates_repo.TEMPLATES_REL}/{templates_repo.BINDINGS_FILE}"
            rc, _o, err = repo_service.git(repo, "checkout", "HEAD", "--", rel) if current \
                else (0, "", "")
            return {"ok": False, "status": 500, "error": (
                f"not committed ({out.get('error')}); the committed bindings are "
                + ("back in place" if rc == 0 else f"NOT restored ({err}): "
                   "repair templates/bindings.yml from history"))}
    return {"ok": True, "status": 200, "commit": out.get("commit", ""), "moves": moves}
