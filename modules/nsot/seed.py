"""Seed intent: a device's first full intent, taken from its committed golden (C148).

**What it closes.** Onboarding commits a bootstrap-shaped intent (hostname,
logging, secret refs; no interfaces, routing or users), and a deploy needs
full intent. The only path from one to the other was extract, review, commit:
three routes with no screen, and the commit refuses anything without a
verified person, so no onboarded device could be deployed to from the
interface. The tool did it once (r6, 2026-09-24) through the commit route
before P.3 gated it, with `Actor: user` typed into the request body. So "the
tool can onboard and deploy" was true of the FLEET, whose intent was
extracted before the gate, and never of the PRODUCT.

**The operation**, with the treatment capture got (7.1 step 4):
  preview  parse each device's COMMITTED golden through the platform parser,
           and show the intent document that would be committed, as a diff
           against the intent committed now, with what the template cannot
           reproduce and which secrets would move into the credential store;
  confirm  bound to a hash of the document AND the golden it came from (the
           document carries secret refs, never values, so a golden whose only
           change is a secret value would otherwise hash the same);
  apply    each device parsed AGAIN, one that moved refused, the secrets
           stored, and ONE commit of exactly the seeded files, as the verified
           person, `Source: seed`;
  result   drawn by the result component; the record is the commit.

**Only a device with no intent, or only the bootstrap, is seeded.** Seeding
over full intent would replace what the device SHOULD be with what it IS,
erasing every intended change not yet deployed: the diff a deploy plans from
would be empty by construction (Phase 3c's rule: intent is committed, never
inferred). A device with full intent is shown, not selectable, and pointed at
its intent editor.

**A template that cannot reproduce the device does not block the seed.** The
deploy gates on template fidelity per device (`template_report`), which is
where it belongs; refusing here would leave the device with bootstrap intent,
which blocks the deploy anyway and says less. So the preview SAYS what the
template does not reproduce, line by line, and that the device will not be
deployable until those lines are modelled or acknowledged.

Nothing here opens a session: the golden is read from git.
"""

import difflib
import hashlib
import logging

log = logging.getLogger(__name__)

SOURCE = "seed"

#: The states a device's committed intent can be in, as the seed sees it.
NEVER = "never_committed"
BOOTSTRAP = "bootstrap_only"
FULL = "full"


def _repo(list_name: str) -> str:
    import os

    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def seed_hash(document: str, golden: str) -> str:
    """What the confirm binds: the document committed and the golden it was
    parsed from, so a secret value changing in the golden (absent from the
    document, which holds only refs) still moves the hash."""
    h = hashlib.sha256()
    h.update(document.encode("utf-8"))
    h.update(b"\0")
    h.update(golden.encode("utf-8"))
    return h.hexdigest()[:16]


def intent_state(repo: str, hostname: str) -> tuple:
    """``(state, text)``: the committed intent, as COMMITTED (C104)."""
    from modules.nsot import hostvars

    text, _committed = hostvars.committed_at_head(repo, hostname)
    if text is None:
        return NEVER, ""
    try:
        doc = hostvars.from_yaml(text)
    except Exception:                           # noqa: BLE001
        # Unparseable committed intent is not "only the bootstrap": a person
        # may have written it, so it is never replaced by a seed.
        return FULL, text
    return (BOOTSTRAP if hostvars.is_bootstrap_only(doc) else FULL), text


def _unmodeled_lines(host_vars: dict) -> list:
    lines = [e.get("line", "") for e in host_vars.get("unmodeled") or []]
    for iface in host_vars.get("interfaces") or []:
        lines += [f"{iface.get('name', '?')}: {l}" for l in iface.get("unmodeled") or []]
    return [l for l in lines if l]


def entry_for(list_name: str, device: dict) -> dict:
    """One device's seed: what would be committed and why it may or may not be.

    The parse result's secret VALUES stay in ``_host_vars``, which the route
    never sends; everything else is safe to draw (the document holds refs)."""
    from modules.nsot import manifest as _m
    from modules.nsot.device_ops import busy_text
    from modules.nsot.hostvars import to_yaml
    from modules.nsot.platform import platform_for_device
    from modules.nsot.repo import committed_golden_for
    from modules.nsot.roundtrip import validate_device

    repo = _repo(list_name)
    host = device.get("hostname", "")
    platform = platform_for_device(device)
    state, current = intent_state(repo, host)
    base = {"device": host, "platform": platform, "intent_state": state,
            "busy": busy_text(list_name, host), "error": "", "seedable": False}
    record = committed_golden_for(repo, _m.find_by_name(repo, host)[1])
    if record["text"] is None:
        return {**base, "golden": "",
                "error": (f"refused: {record['refused']}" if record.get("refused") else
                          "no committed golden: capture it first (Capture as golden), "
                          "then seed its intent from that")}
    base["golden"] = (record.get("commit") or "")[:12]
    result = validate_device(record["text"], platform)
    if result.get("error"):
        return {**base, "error": f"the {platform} parser could not read its golden: {result['error']}"}
    host_vars = result["host_vars"]
    document = to_yaml(host_vars)
    diff = [l for l in difflib.unified_diff(current.splitlines(), document.splitlines(),
                                             lineterm="", n=2)
            if not l.startswith(("---", "+++"))]
    details = result.get("details") or {}
    unmodeled = _unmodeled_lines(host_vars)
    return {**base,
            "seedable": state in (NEVER, BOOTSTRAP),
            "hash": seed_hash(document, record["text"]),
            "document": document, "diff": diff,
            "fidelity": result.get("round_trip_fidelity"),
            "coverage": result.get("modeled_coverage"),
            # Fully modelled, not only round-tripped: an unmodelled line is
            # rendered verbatim (100% round-trip) and still blocks a deploy
            # until it is acknowledged (render_artifact's gate), measured on
            # r2 with one planted line: ok, 100.0%, 99.3% modelled.
            "reproduced": bool(result.get("ok")) and not unmodeled,
            "unmodeled": unmodeled,
            "missing": [m["line"] for m in details.get("missing", [])],
            "extra": [e["line"] for e in details.get("extra", [])],
            "secret_refs": sorted((host_vars.get("secrets") or {}).keys()),
            "_host_vars": host_vars}


def public(entry: dict) -> dict:
    """The entry without the parse result (it carries secret values)."""
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def apply(list_name: str, inventory: list, confirmations: dict, actor: str) -> dict:
    """Seed each confirmed device. ``{"outcomes", "save"}``.

    Holds every confirmed device for the whole apply (C98): a seed that parses
    a golden while a capture or deploy rewrites it would commit intent from a
    half-made state. ONE commit of exactly the seeded files; a failed commit
    puts each file back as it was committed (C106's rule), and says so."""
    import os

    from modules.nsot import device_ops, hostvars
    from modules.nsot.repo import save_host_vars

    repo = _repo(list_name)
    by_host = {d.get("hostname", ""): d for d in inventory}
    wanted = [h for h in confirmations if h in by_host]
    outcomes = [{"device": h, "outcome": "unknown_device",
                 "reason": f"not in {list_name}'s inventory"}
                for h in confirmations if h not in by_host]
    held, refused = device_ops.acquire_many(list_name, wanted, "seed intent", actor)
    busy = {r["device"]: r["reason"] for r in refused}
    written, previous = [], {}
    try:
        seeded = []
        for host in wanted:
            if host in busy:
                outcomes.append({"device": host, "outcome": "busy", "reason": busy[host]})
                continue
            e = entry_for(list_name, by_host[host])
            if e["error"]:
                outcomes.append({"device": host, "outcome": "refused", "reason": e["error"]})
                continue
            if not e["seedable"]:
                outcomes.append({"device": host, "outcome": "refused",
                                 "reason": "it has full committed intent now: a seed would "
                                           "replace it with the device as captured"})
                continue
            if e["hash"] != confirmations[host]:
                outcomes.append({"device": host, "outcome": "moved",
                                 "reason": (f"its golden or the parse of it moved since the "
                                            f"preview ({confirmations[host]} -> {e['hash']})")})
                continue
            secrets = hostvars.store_secrets(e["_host_vars"], host, dry_run=False,
                                             list_name=list_name)
            path = hostvars.committed_path(repo, host)
            previous[path] = e["intent_state"]
            try:
                hostvars.write_committed(repo, e["_host_vars"])
            except hostvars.SecretLeak as exc:
                log.error("seed: refused to write intent for %s: %s", host, exc)
                outcomes.append({"device": host, "outcome": "refused", "reason": str(exc)})
                continue
            written.append(path)
            seeded.append(host)
            outcomes.append({"device": host, "outcome": "pending", "entry": public(e),
                             "secrets": [m["ref"].rsplit(":", 1)[-1] for m in secrets["moved"]]})
        save = {}
        if seeded:
            goldens = [f"Seeded-From: {o['device']}@{o['entry']['golden']}"
                       for o in outcomes if o["outcome"] == "pending"]
            save = save_host_vars(
                list_name, seeded, actor=actor, source=SOURCE,
                message=f"host_vars: seed {', '.join(seeded)} from the committed golden",
                extra_trailers=goldens,
                paths=[hostvars.committed_rel(h) for h in seeded])
            if not save.get("ok"):
                _put_back(repo, written)
            for o in outcomes:
                if o["outcome"] == "pending":
                    o["outcome"] = "seeded" if save.get("ok") else "failed"
                    if not save.get("ok"):
                        o["reason"] = save.get("error") or "the commit failed"
        return {"outcomes": outcomes, "save": save}
    finally:
        device_ops.release_many(list_name, held)


def _put_back(repo: str, paths: list) -> None:
    """A failed commit leaves each written file as it was committed, or
    removes one nothing had committed (`hostvars.put_back_committed`)."""
    from modules.nsot.hostvars import put_back_committed
    put_back_committed(repo, paths)
