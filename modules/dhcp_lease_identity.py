"""modules/dhcp_lease_identity.py — a ZTP subnet matches a lease by the client's MAC, never its
client-id (C1403 part 2; the operator's design, 2026-10-19).

Kea matches a client to its lease by client-id when the client sends one (option 61) and
`match-client-id` is true, Kea's default and this installation's global setting. A configless
device redeployed with a new client-id (IOS-XE sends its serial) then meets its own old lease on
its reserved address as another client's: Kea logs `ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT`
and answers nothing (0d's run 2, 238 requests unanswered). Measured on this installation's Kea
2.4.1, a throwaway copy on loopback (tests/fixtures/kea/c1403_match_client_id_probe.txt): with
`match-client-id` true a reserved client back with the same MAC and a new client-id gets no
answer and its REQUEST is NAKed; with it false it is offered and acknowledged its reserved
address, and the old client-id is answered either way. ZTP's identity is the MAC its
reservation names, so a ZTP subnet says `"match-client-id": false` at the subnet itself:

- a subnet Mercury adds for ZTP behind a relay is written with it, and an edit of one writes it
  (`dhcp_subnets._declare_for_ztp`, `_plan_edit`);
- the directly attached ZTP subnet is onboarding's and Subnets › Edit refuses it, so a one-time
  host step writes it through board C's one write path with this module's planner (:func:`plan`;
  scripts/nmas-kea-lease-identity, scripts/host-steps/c1403-ztp-lease-identity.sh);
- job health asks Kea, for every ZTP subnet, which value it runs and where that value is set
  (:func:`rows`): a subnet matching by client-id is a row naming its fix, cleared when Kea runs
  false there.
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

KEY = "match-client-id"
#: What a ZTP subnet says (the measurement above).
WANTED = False
#: Why, in the words a row and a check say it.
WHY = ("a device redeployed with a new client-id meets its own old lease as another client's "
       "and is never answered (C1403); ZTP's identity is the MAC its reservation names")


class Refused(Exception):
    pass


def effective(dhcp4: dict, subnet: dict, net=None) -> tuple:
    """``(value, where)``: the `match-client-id` Kea runs for *subnet*, and the level that sets
    it: the subnet, its shared network, Kea's global level, or Kea's own default (true)."""
    if KEY in (subnet or {}):
        return bool(subnet[KEY]), f"subnet {subnet.get('id')}"
    if net and KEY in net:
        return bool(net[KEY]), f"shared network {net.get('name') or '(unnamed)'}"
    if KEY in (dhcp4 or {}):
        return bool(dhcp4[KEY]), "Kea's global level"
    return True, "Kea's default (no level sets it)"


def ztp_subnets(dhcp4: dict, addrs=None) -> list:
    """``[(subnet, shared_network_or_None, kind)]``: every ZTP subnet Kea runs, the directly
    attached ones (`ztp.ztp_subnets`, where this host is) and those declared relayed
    (`ztp_relayed.declared`), each once."""
    from modules.nsot import ztp, ztp_relayed

    out, seen = [], set()
    nets = {id(s): n for s, n in ztp._all_subnets(dhcp4)}                  # noqa: SLF001
    for subnet, _address in ztp.ztp_subnets(dhcp4, addrs):
        if subnet.get("id") not in seen:
            seen.add(subnet.get("id"))
            out.append((subnet, nets.get(id(subnet)), "direct"))
    for subnet, net in ztp._all_subnets(dhcp4):                            # noqa: SLF001
        if ztp_relayed.declared(subnet) and subnet.get("id") not in seen:
            seen.add(subnet.get("id"))
            out.append((subnet, net, "relayed"))
    return out


def rows(dhcp4: dict, addrs=None) -> list:
    """Job-health rows, one per ZTP subnet: ``ok`` when Kea runs `match-client-id` false there,
    ``client_id_matched`` (with the action that fixes it) when it does not."""
    what = ("A ZTP subnet matches a lease by the device's MAC, never its client-id, so a "
            "device redeployed with a new one is answered (C1403)")
    out = []
    for subnet, net, kind in ztp_subnets(dhcp4, addrs):
        value, where = effective(dhcp4, subnet, net)
        sid, prefix = subnet.get("id"), subnet.get("subnet")
        row = {"unit": f"ztp-lease-identity:subnet-{sid}", "what": what, "max_age_minutes": 0}
        if value is WANTED:
            row.update(state="ok", detail=f"{kind} ZTP subnet {sid} {prefix}: match-client-id "
                                          f"false, set at {where}")
        else:
            fix = ({"label": "Edit the subnet on DHCP › Subnets: its Edit… writes "
                             "match-client-id false (C1403)"} if kind == "relayed" else
                   {"label": "Run the one-time host step on the host (it writes "
                             "match-client-id false through Mercury's subnet write)",
                    "command": "bash scripts/host-steps/c1403-ztp-lease-identity.sh"})
            row.update(state="client_id_matched", action=fix,
                       detail=(f"{kind} ZTP subnet {sid} {prefix} matches leases by client-id "
                               f"(match-client-id true, from {where}): {WHY}"))
        out.append(row)
    return out


def ask(values) -> dict:
    return {"family": (values.get("family") or "IPv4").strip(),
            "id": str(values.get("id") or "").strip(), "op": "lease_identity", "ack": ""}


def plan(list_name: str, values, kea=None, file_text=None, intent=None) -> dict:
    """Board C's plan shape (`dhcp_subnets.plan`) for one change: ZTP subnet *id* says
    `match-client-id` false. A planner for `dhcp_subnets.apply_edit`, the one write path (Kea's
    own check, write, reload, read back, recorded in dhcp/subnets.yml). A read; refuses a subnet
    that is not ZTP's, and one that already says false."""
    from modules import dhcp_reservations as D
    from modules import dhcp_subnets as S
    from modules.nsot import ztp_relayed
    from modules.readers.dhcp import _ztp_ids

    s = ask(values)
    p = {"ok": False, "refused": "", "ask": s, "op": "edit", "family": s["family"],
         "id": None, "prefix": "", "title": "", "change": [], "checks": [], "leases": [],
         "survives": [], "ack": False, "before": None, "after": None, "path": "",
         "version": "", "hash": "", "subject": ""}
    try:
        if s["family"] != "IPv4":
            raise Refused(f"{s['family']!r}: ZTP serves IPv4 only (C1245)")
        try:
            sid = int(s["id"])
        except ValueError:
            raise Refused(f"{s['id']!r} is not a Kea subnet id") from None
        subnets, config, _kea = S._state(list_name, {"family": "IPv4"}, p, kea,  # noqa: SLF001
                                         file_text, D)
        hit = [x for x in subnets if x.get("id") == sid]
        if len(hit) != 1:
            raise Refused(f"subnet {sid} is in Mercury's IPv4 subnet file {len(hit)} times")
        before = hit[0]
        running = next((x for x in config.get("subnet4") or [] if x.get("id") == sid), {})
        if not (sid in _ztp_ids(config) or ztp_relayed.declared(running)
                or ztp_relayed.declared(before)):
            raise Refused(f"subnet {sid} is not a ZTP subnet: only ZTP's identity is the MAC "
                          "its reservation names")
        if before.get(KEY) is WANTED:
            raise Refused(f"nothing would change: subnet {sid} already says match-client-id "
                          "false")
    except (Refused, S.Refused, D.Refused) as exc:
        p["refused"] = str(exc)
        return p
    after = json.loads(json.dumps(before))
    after[KEY] = WANTED
    prefix = before.get("subnet", "")
    p.update(id=sid, prefix=prefix, before=before, after=after,
             title=f"Match leases by MAC on ZTP subnet {sid} ({prefix})",
             subject=f"dhcp: IPv4 subnet {sid} ({prefix}) matches leases by MAC (C1403)",
             change=S._change_lines(before, after, sid, prefix))           # noqa: SLF001
    p["leases"].append("every lease held there stays; from now on Kea matches each to its "
                       "client by MAC, so a device back with a new client-id keeps its address")
    p["checks"] += [("pass", f"subnet {sid} is ZTP's, and only {KEY} moves"),
                    ("pending", "kea-dhcp4 -t on the candidate, at confirm; the live file "
                                "untouched until then"),
                    ("pass", f"Mercury's subnet file is the version this preview read "
                             f"({p['version']})")]
    p["hash"] = hashlib.sha256(json.dumps(
        {k: p[k] for k in ("op", "family", "id", "before", "after", "version", "ack")},
        sort_keys=True).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p
