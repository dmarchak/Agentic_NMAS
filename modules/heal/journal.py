"""A heal's NetBox journal entry (board H, part H6; docs/HEAL_TO_INTENT.md section 8, "The
NetBox journal entry"; C2376): the device's NetBox record says what self-healing did to it.

**Through the one write path** (`netbox_client.add_journal_entry`, which posts through
`_nb_post`): refused unless NetBox writes are allowed (the master switch,
``netbox_allow_writes``), and under a declared authority (`netbox_guard.for_list(...,
authority="heal policy <fingerprint> confirmed by <person>")`, C155), its actor the policy's
setter, recorded as created with both (its provenance); one NetBox writer per network at a
time (`netbox_guard.list_writer`, refused by name, never waited on).

**Not written, said, never failed:** when writes are off, when the device has no NetBox record
(its network's inventory is local, so no NetBox id: `netbox_id`), when NetBox is not set up or
another writer holds the network, or when nothing was sent (a refused heal changes nothing the
record should say). The heal's outcome is never changed by its journal entry.

**The entry's text** (`comments`): its first line names the heal in a fixed, parseable form,
``Mercury heal <decision id>`` (`HEAL_LINE`, read back by `heal_id`), so the NetBox census
reconciles every entry with its step record (`scripts/nmas-netbox-census`, H6: same device,
same heal); then the outcome in Mercury's words, the fix's kind, the program's hash and size,
the policy and who confirmed it, the incident and decision, and the link to the device's
History. A written entry's result names the NetBox device and the heal it was written for
(``device_id``, ``heal``), which the step log's ``act`` row keeps. Never a configuration value: no line, no unit's lines, and masked again by
the write. **Never deleted:** no remover walks ``extras/`` (`netbox_client._REMOVAL_ORDER`),
and deleting a network never deletes NetBox objects. **Tagged** ``nmas-managed`` like every
object Mercury creates: ``extras/journal-entries/`` is in `netbox_guard.TAGGABLE_ENDPOINTS`
(C2437: the lab NetBox 4.6.9's OPTIONS answer a writable, optional ``tags``, read 2026-11-04),
so `_nb_post` adds the tag and refuses an entry it cannot tag.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Each act outcome's journal kind; an outcome absent here sent nothing.
KINDS = {"healed": "success", "symptom_remains": "warning", "partial": "warning",
         "rolled_back": "danger", "failed": "danger", "interrupted": "danger"}

#: The comments' first line: the heal (its decision's id), and nothing else on that line.
HEAL_LINE = "Mercury heal {heal}"
_HEAL_LINE = re.compile(r"Mercury heal (\S+)")


def heal_id(text) -> str:
    """The heal an entry's comments name on their first line (`HEAL_LINE`), or ``""`` when the
    first line is not that form (a person's entry, or one written before the line existed)."""
    first = str(text or "").splitlines()[0] if str(text or "").strip() else ""
    m = _HEAL_LINE.fullmatch(first.strip())
    return m.group(1) if m else ""


def netbox_id(network: str, device: str, dev: dict):
    """The device's NetBox id, or None: the inventory's (``_netbox_id``), else the manifest's
    identity (``nb:<id>``), never looked up by name."""
    nb = (dev or {}).get("_netbox_id") or (dev or {}).get("netbox_id")
    if nb not in (None, ""):
        try:
            return int(nb)
        except (TypeError, ValueError):
            return None
    try:
        from modules.nsot import listref, manifest

        key, _entry = manifest.find_by_name(listref.resolve(network).repo_dir, device)
    except Exception as exc:
        log.info("heal: %s's NetBox id could not be read from its manifest: %s", device, exc)
        return None
    if isinstance(key, str) and key.startswith("nb:") and key[3:].isdigit():
        return int(key[3:])
    return None


def comments(network: str, device: str, decision: dict, outcome: str, *, link: str,
             approval: dict = None) -> str:
    """The entry's text, in Mercury's words only (the module's docstring). *approval* (H5): a
    Tier 2 proposal a person approved, named in place of the policy."""
    from modules.heal import act
    from modules.heal.kinds import KIND_WORDS

    pol = decision.get("policy") or {}
    kind = decision.get("kind") or ""
    under = (f"proposed and approved by {approval.get('by')}" if approval else
             f"under the policy {pol.get('fingerprint') or '(none)'} confirmed by "
             f"{pol.get('by') or 'nobody'}")
    return (HEAL_LINE.format(heal=decision.get("id") or "(none)") + "\n\n"
            f"Mercury self-healing on {network}: {device} {act.OUTCOME_WORDS.get(outcome, outcome)}"
            f". The fix: {KIND_WORDS.get(kind, kind) or 'no kind recorded'}, program "
            f"{(decision.get('program_hash') or '')[:12] or '(none)'} "
            f"({len(decision.get('program') or [])} line(s)), {under}. "
            f"Incident {decision.get('incident')}, decision {decision.get('id')}. "
            f"The step log, the receipt and the golden commit: {link}")


def not_written(words: str) -> dict:
    return {"state": "not_written", "id": None, "words": f"not written: {words}"}


def write(network: str, device: str, dev: dict, decision: dict, outcome: str, *,
          ready=None, nb_id=None, approval: dict = None) -> dict:
    """Write the journal entry for one heal: ``{"state": "written"|"not_written"|"failed",
    "id", "words"}``. Never raised. *ready* is `netbox_client._nb_ready` unless given.
    *approval* (H5): an approved Tier 2 proposal is written as the person who approved it,
    under the authority "heal proposal <decision> approved by <person>"."""
    from modules import netbox_client, netbox_guard
    from modules.notify.message import link_url

    kind = KINDS.get(outcome)
    if kind is None:
        return not_written(f"nothing was sent ({outcome or 'no outcome'}), so {device}'s NetBox "
                           "record has nothing to add")
    if not netbox_guard.writes_allowed():
        return not_written("NetBox writes are off for every network (Writes allowed, on "
                           "Settings › Installation › Connections, NetBox connection)")
    nb = nb_id if nb_id is not None else netbox_id(network, device, dev)
    if not nb:
        return not_written(f"{device} has no NetBox record Mercury knows (no NetBox id in its "
                           f"inventory or its manifest: {network}'s inventory is local)")
    ok, err, session, base = (ready or netbox_client._nb_ready)()
    if not ok:
        return not_written(err)
    pol = decision.get("policy") or {}
    if approval:
        by = approval.get("by") or ""
        if not by:
            return not_written("no person is recorded as having approved the proposal, so the "
                               "write has no authority to declare")
        authority = f"heal proposal {decision.get('id')} approved by {by}"
    else:
        by = pol.get("by") or ""
        if not by or not pol.get("fingerprint"):
            return not_written("no person is recorded as having confirmed the policy, so the "
                               "write has no authority to declare")
        authority = f"heal policy {pol['fingerprint']} confirmed by {by}"
    url, _said = link_url(f"/v2/device/{device}?tab=history")
    text = comments(network, device, decision, outcome, link=url, approval=approval)
    try:
        with netbox_guard.list_writer(network, f"the heal journal entry for {device}", by), \
                netbox_guard.for_list(network, actor=by, authority=authority):
            obj = netbox_client.add_journal_entry(session, base, nb, kind, text)
    except netbox_guard.NetBoxBusy as exc:
        return not_written(str(exc))
    except Exception as exc:
        log.error("heal: %s's journal entry for %s failed: %s", network, device, exc)
        return {"state": "failed", "id": None,
                "words": f"the write failed: {type(exc).__name__}: {exc}"}
    return {"state": "written", "id": obj.get("id"), "device_id": nb,
            "heal": decision.get("id") or "",
            "words": (f"written: NetBox journal entry {obj.get('id')} on device {nb}, kind "
                      f"{kind}, under {authority}")}
