"""Committing a network's NSOT export as one operation (C2777; the operator's decision 8 of
2026-11-08; board docs/boards/nsot-export.html, self-signed under the Phase 7 mode): SDN ›
Apps' Export from NetBox… reads NetBox now (`export.build`), previews the export's hash and
what it changes against the committed one (`export.changes`), and, confirmed by the preview's
hash as a verified person, commits it (`export.write`) and announces it, so every screen
reading the export reads it again.

**The steps** (`STEPS`, named on the manual's page, docs/manual/how-it-works/nsot-export.md):
- ``read``: NetBox's records for the network, read only (`export.collect`'s whole lists);
- ``compare``: the export against the committed one, by kind (added, removed, changed), and
  the hash the confirm binds: the new export's SHA-256 and the committed file's blob id
  together (`plan_hash`), so a commit made since by anyone is seen;
- ``confirm``: a verified person's, carrying that hash;
- ``check``: NetBox read again and the hash made again; one that moved commits nothing and
  names what moved (the export's hash, or the committed file), both values each;
- ``commit``: ``nsot/export.json`` in the network's configuration repository, one commit as
  the person (``Actor:``, ``Actor-Verified:``, ``Export-Sha256:``, ``Source: nsot_export``),
  the committed file checked again inside the repository's lock (`export.write`'s
  *base_blob*);
- ``announce``: `ANNOUNCE_KEYS`, so SDN › Apps and every page reading the export redraw.

**The record is the commit.** It changes no device and writes nothing to NetBox, so there is
no verify or rollback of a device: a wrong export is corrected by committing the next one
(`operation_stages`: changes no device; a commit, corrected forward). `last` reads the newest
export commit from the repository's history, so the card says the same later; History ›
Commits lists it with its Actor and its Export-Sha256.

A preview whose export is the committed one, byte for byte, says so and offers no confirm.
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

KIND = "nsot export"
STEPS = ("read", "compare", "confirm", "check", "commit", "announce")
ANNOUNCER = "nsot-export"
ANNOUNCE_KEYS = ("nsot_export",)
#: How many of a kind's names the preview draws open; the rest are counted (a large fleet's
#: first export adds every object).
SHOWN = 12


def plan_hash(network: str, sha256: str, base_blob: str) -> str:
    """What the confirm binds: the network, the new export's hash and the committed file's blob
    id ("" when none is committed)."""
    return hashlib.sha256(f"{network}\0{sha256}\0{base_blob}".encode()).hexdigest()


def last(network: str) -> dict:
    """The card at rest: the committed export (``{"state": "ok"|"none"|"unreadable", "sha256",
    "commit", "at", "actor", "netbox_version", "counts", "error"}``) and whether the network's
    devices are NetBox's (``source``)."""
    from modules.inventory import source_config
    from modules.nsot import export as X

    try:
        src = source_config.load(network).get("source") or ""
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        src, src_error = "", f"its inventory source could not be read ({exc})"
    else:
        src_error = ""
    netbox = src == source_config.SOURCE_NETBOX
    out = {"network": network, "netbox": netbox,
           "source_words": src_error or ("" if netbox else
                                         f"{network}'s devices come from {src!r}, not NetBox: "
                                         "an NSOT export is NetBox's view of a network")}
    # The export as the tab's readers take it (`export.read`, HEAD), so the card says what they
    # read; a file there that does not read is unreadable, never none.
    got = X.read(network)
    if not got["ok"] and not X.committed_blob(network):
        return dict(out, state="none", sha256="", commit="", at="", actor="",
                    netbox_version="", counts={}, error="")
    rec = X.last_commit(network)
    base = dict(out, commit=rec.get("commit", ""), at=rec.get("at", ""),
                actor=rec.get("actor", ""))
    if not got["ok"]:
        return dict(base, state="unreadable", sha256="", netbox_version="", counts={},
                    error=got["error"])
    body = got["export"].get("body") or {}
    return dict(base, state="ok", sha256=got["sha256"], error="",
                netbox_version=got["export"].get("netbox_version", ""),
                counts={k: len(body.get(k) or []) for k in X.KINDS})


def preview(network: str, **kw) -> dict:
    """``read`` and ``compare``: ``{"ok", "state" ("preview", "nothing", "refused"), "network",
    "sha256", "base_blob", "hash", "committed", "changes", "netbox_version", "error"}``.
    Writes nothing. *kw* (``get``, ``version``) replaces the NetBox client in tests."""
    from modules.nsot import export as X

    refused = {"ok": False, "state": "refused", "network": network}
    built = X.build(network, **kw)
    if not built["ok"]:
        return dict(refused, error=built["error"])
    new = json.loads(built["bytes"])
    base_blob = X.committed_blob(network)
    committed = X.read(network) if base_blob else {"ok": False, "export": None, "sha256": ""}
    old = committed["export"] if committed.get("ok") else None
    ch = X.changes(old, new)
    for k in ch["kinds"]:
        for part in ("added", "removed", "changed"):
            k[f"{part}_n"] = len(k[part])
            k[f"{part}_more"] = max(0, len(k[part]) - SHOWN)
            k[part] = k[part][:SHOWN]
    rec = X.last_commit(network) if base_blob else {}
    same = bool(old) and committed.get("sha256") == built["sha256"]
    return {"ok": True, "state": "nothing" if same else "preview", "network": network,
            "sha256": built["sha256"], "bytes": built["bytes"], "base_blob": base_blob,
            "hash": plan_hash(network, built["sha256"], base_blob),
            "committed": {"sha256": committed.get("sha256", ""), "blob": base_blob,
                          "readable": bool(old), "error": "" if old or not base_blob
                          else committed.get("error", ""),
                          "commit": rec.get("commit", ""), "at": rec.get("at", ""),
                          "actor": rec.get("actor", "")},
            "changes": ch, "netbox_version": new.get("netbox_version", ""), "error": ""}


def moved_words(then_sha: str, then_blob: str, now: dict) -> list:
    """What moved between the preview a person confirmed and the export read again, each with
    both values."""
    out = []
    if then_sha and now.get("sha256") != then_sha:
        out.append(f"NetBox's export now hashes sha256:{now.get('sha256', '')[:12]}, and the "
                   f"preview showed sha256:{then_sha[:12]}")
    if then_blob is not None and now.get("base_blob") != then_blob:
        out.append(f"the committed export moved since the preview (now "
                   f"{_blob(now.get('base_blob', ''))}; previewed {_blob(then_blob)})")
    return out


def _blob(b: str) -> str:
    return f"blob {b[:4]}…{b[-4:]}" if b else "none committed"


def apply(network: str, confirmed: str, *, actor: str, actor_verified: str,
          then_sha: str = "", then_blob: str = None, **kw) -> dict:
    """``confirm`` to ``announce``: ``{"outcome" ("committed", "unchanged", "refused"),
    "network", "sha256", "before_sha256", "commit", "changes", "error"}``. *then_sha* and
    *then_blob*: the preview's export hash and committed blob as its form carried them, to name
    what moved when the hash did."""
    from modules.nsot import export as X

    out = {"outcome": "refused", "network": network, "sha256": "", "before_sha256": "",
           "commit": "", "changes": None, "error": ""}
    if not actor or actor_verified in ("", "none"):
        return dict(out, error="an NSOT export is committed by a verified person")
    if len(confirmed or "") != 64:
        return dict(out, error="the form carries no preview hash, so what you confirmed "
                               "cannot be told")
    now = preview(network, **kw)
    if not now["ok"]:
        return dict(out, error=f"{now['error']}: nothing was committed")
    if now["hash"] != confirmed:
        why = moved_words(then_sha, then_blob, now) or [
            f"the preview's hash is now {now['hash'][:12]}, and you confirmed {confirmed[:12]}"]
        return dict(out, sha256=now["sha256"], moved=True,
                    error="; ".join(why) + ": nothing was committed; preview again")
    if now["state"] == "nothing":
        return dict(out, outcome="unchanged", sha256=now["sha256"],
                    before_sha256=now["committed"]["sha256"], changes=[])
    got = X.write(network, actor, actor_verified, data=now["bytes"],
                  base_blob=now["base_blob"])
    if not got.get("ok"):
        return dict(out, sha256=now["sha256"], moved=bool(got.get("moved")),
                    error=got.get("error") or "the export was not committed")
    log.info("nsot export: %s committed %s's export %s in %s", actor, network,
             got["sha256"][:12], (got.get("commit") or "")[:12])
    _announce(network)
    return dict(out, outcome="committed" if got.get("changed") else "unchanged",
                sha256=got["sha256"], before_sha256=now["committed"]["sha256"],
                commit=got.get("commit", ""), changes=summary(now["changes"]), actor=actor,
                actor_verified=actor_verified)


def summary(changes: dict) -> list:
    """What a commit changed, as its result says it: ``[{"kind", "added_n", "removed_n",
    "changed_n"}]`` for each kind that changed."""
    return [{"kind": k["kind"], "added_n": k["added_n"], "removed_n": k["removed_n"],
             "changed_n": k["changed_n"]} for k in (changes or {}).get("kinds") or []
            if k["added_n"] or k["removed_n"] or k["changed_n"]]


def _announce(network: str) -> None:
    from modules import invalidation

    try:
        invalidation.announce(ANNOUNCE_KEYS, by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (counted in the log)
        log.warning("nsot export: %s's commit was not announced: %s", network, exc)
