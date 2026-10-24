"""Out-of-band onboarding in one decision: Add device's **Out-of-band (console)** source, its
one review and its one background run (the operator's approved design of 2026-10-23, with his
changes: no Kea object at all, a switch's way back by ``ip default-gateway`` (and, since a
blank vIOS-L2 was measured routing, ``ip route 0.0.0.0 0.0.0.0`` too: C1606), the copy
allowing for the key generation, the run's last device step honouring Verify's key settle).

**Eligible** (`eligibility`) only when NetBox holds a console path for the device's Planned
record (`console_path.read_console_path`) AND Mercury holds a port record for that path's
console-server port (`console_servers.get_port`); otherwise the reason, and what fixes it.

**Derived, asked only when it cannot be** (`derive`): the address and mask (NetBox IPAM's
address for the Planned record), the VLAN (the interface that address is on, ``Vlan<N>``; else
1), the management interface (``Vlan<vlan>`` for a switch), the relay and the default gateway
(the relay's own address on the link, from committed intent: `ztp_relayed.link_for_address`),
the uplink (the device's interface NetBox cables to the relay; asked when NetBox shows none:
Mercury keeps no LLDP table to read it from), and where the bootstrap is copied from (the
relay's IPv4 helper target, which Create's own plan must agree with, and the device's boot
file).

**The review** (`preview`) contacts no device: the device, its profile and hash, the console
path with the console server's full host-key fingerprint, the static address, what the run
creates (Create's own plan, its fingerprint), the EXACT console program, the stop rules, what
it will not do, and the hash over all of it. Nothing is excepted from the hash: the MAC is not
in it because nothing written depends on it (no reservation); it is READ BACK and recorded.

**The run** (`run`), one background job holding the device (`OP`) and its console-server port
(the transport's own lock), in order: hold, wake, the blank check, Create (the static
bootstrap, the pending static intent and the manifest entry with the NetBox id; undone in full
on any later failure, `undo`), the kick-start (the blank check again, then each line, its
answer read: any IOS refusal stops it, naming the line), the read-back (each typed line in the
running configuration, and the MAC the management interface uses, recorded in the manifest),
the copy (verified), the console released, then Answering (the SSH key's settle,
`onboard.KEY_SETTLE_S`, waited out and SHOWN, then SSH at the static address answers), and the
record. Every stop names the comparison and both operands, what was sent and what was undone.

The five console pieces the run types and judges are Phase A's, reached only through
`modules/nsot/oob_steps.py`, the adapter.
"""

import hashlib
import ipaddress
import json
import logging
import os
import re
import time
from dataclasses import dataclass

from modules.nsot import oob_steps
from modules.nsot.onboard import KEY_SETTLE_S

log = logging.getLogger(__name__)

#: The record's kind, in the console runs' own folder and index (`console_ztp.record`), so
#: History, Needs attention and Retire read it with the survey's and the kick-start's.
KIND = "onboard"
#: The hold's operation (`device_ops.OPERATION_WORDS` words it; the responder's narrowed gate
#: serves the pending device's bootstrap only while a hold of this name is on it).
OP = "console onboard"
#: The form's fields the review and the confirm read (Add device's, then the asked ones, each
#: drawn only when its value could not be derived).
FORM_FIELDS = ("list_name", "hostname", "platform", "role", "domain", "mgmt_interface")
ASKED_FIELDS = ("uplink",)
FIELDS = FORM_FIELDS + ASKED_FIELDS + ("reason", "hash")

#: Each step, in order: the manual's How it works names each (`modules/manual.OPERATIONS`).
STEPS = (
    ("preview", "Read NetBox (the Planned record, its console path, its planned address and "
                "cable), Mercury's port record and committed intent; derive every field and "
                "contact no device"),
    ("confirm", "A verified person confirms the review's hash with a reason; it is recomputed "
                "now and refused, naming both hashes, if it moved"),
    ("hold", "Hold the device and its console-server port, refused by name if either is held"),
    ("wake", "One carriage return, or the prompt the console printed first; signed in or a "
             "login prompt stops it with nothing typed"),
    ("blank", "To the privileged prompt, the pager off for the session, and the blank check: a "
              "saved startup configuration stops it with nothing created"),
    ("create", "The static bootstrap, the pending static intent and the manifest entry with its "
               "NetBox id, in one commit; undone in full on any later failure"),
    ("kickstart", "The blank check again, then each line, each answer read: any IOS refusal "
                  "stops it, naming the line"),
    ("readback", "Each typed line read back from the running configuration (the VLAN from the "
                 "VLAN database), and the MAC its management interface uses, recorded in the "
                 "manifest"),
    ("copy", "The bootstrap copied from Mercury's TFTP responder into the running "
             "configuration; success only on [OK - N bytes] with N over 0"),
    ("release", "The console closed and its console-server port freed"),
    ("answering", "The SSH key's settle waited out, then SSH at the static address answers"),
    ("record", "One record, masked, on History; Verify stays its own decision"),
)
BEFORE_RUN = ("preview", "confirm")
STEP_LABELS = {"preview": "Preview", "confirm": "Confirm", "hold": "Hold", "wake": "Wake",
               "blank": "Blank check", "create": "Create", "kickstart": "Kick-start",
               "readback": "Read back", "copy": "Copy the bootstrap", "release": "Release",
               "answering": "Answering", "record": "Record"}
#: The progress notes each step makes as it BEGINS (`device_ops.note`; the stepper's names).
STEP_NOTES = {"hold": ("opening the console",), "wake": ("waking the console",),
              "blank": ("onboard: blank",), "create": ("onboard: create",),
              "kickstart": ("onboard: kick-start",), "readback": ("onboard: read-back",),
              "copy": ("onboard: copy",), "release": ("onboard: release",),
              "answering": ("onboard: answering",), "record": ("onboard: record",)}

#: The stops (design section 4): each rule's outcome and its words for the review.
STOPS = (
    ("busy", "busy", "the device or its console-server port is held by another operation: "
                     "named, nothing sent"),
    ("unreachable", "unreachable", "the console cannot be opened: nothing sent"),
    ("signed_in", "signed_in", "the console answers signed in (a # or configuration prompt): "
                               "nothing typed, nothing created"),
    ("login", "login", "the console asks for a login: nothing typed, nothing created"),
    ("not_blank", "not_blank", "nvram holds a startup configuration (blank needs 0 bytes or "
                               "none): nothing typed, nothing created"),
    ("unexpected", "unexpected", "the console prints a prompt the step does not expect: "
                                 "stopped there"),
    ("create", "create_failed", "Create refuses or fails: what it made is undone"),
    ("refused_line", "refused_line", "a line is refused (% ...): stopped at that line; what "
                                     "Create made is undone"),
    ("read_back", "read_back", "a typed line is not in the running configuration, or the MAC "
                               "cannot be read: what Create made is undone"),
    ("copy", "copy_failed", "the copy does not answer [OK - N bytes] with N over 0, or answers "
                            "%Error, or a copied line is refused: what Create made is undone"),
    ("not_answering", "not_answering", "SSH at the static address does not answer within the "
                                       "bound: the pending device is kept for Verify or "
                                       "Abandon"),
)
OUTCOME = {rule: outcome for rule, outcome, _w in STOPS}


@dataclass(frozen=True)
class Timings:
    """The session's intervals (as `console_ztp.Timings`), the console part's whole budget, the
    copy's own step bound, the SSH key's settle and the answer's wait, in seconds. The console
    intervals are the survey's (not measured on this path); the settle is Verify's measured one
    (`onboard.KEY_SETTLE_S`, C1400); the answer's bound is 2.5 times about a minute for SSH to
    come up after a fetch, not yet measured on a console onboarding."""
    settle_s: float = 0.5
    quiet_s: float = 5.0
    step_timeout_s: float = 120.0
    poll_s: float = 0.2
    bound_s: float = 1800.0
    #: None: the console kick-start's own copy bound (`oob_steps.copy_timeout_s`, one home).
    copy_timeout_s: float = None
    key_settle_s: float = float(KEY_SETTLE_S)
    answer_bound_s: float = 150.0
    answer_every_s: float = 10.0


DEFAULT_TIMINGS = Timings()


class Refused(ValueError):
    """Refused before anything was sent; the text names what was compared and both values."""


def run_stepper_steps() -> tuple:
    """The run's steps for THE stepper (C1579): ``((key, label, waits, names), ...)``."""
    return tuple((key, STEP_LABELS[key], words[0].lower() + words[1:], STEP_NOTES[key])
                 for key, words in STEPS if key not in BEFORE_RUN)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, default=str).encode()).hexdigest()


def _clock(epoch) -> str:
    return time.strftime("%H:%M:%S", time.gmtime(epoch)) + " UTC"


# ── the profile ────────────────────────────────────────────────────────────────────────────

def profile_for(platform: str, role: str) -> str:
    """The shipped console profile for a device of *platform* (a dialect) and *role*: the one
    whose platform is the device's and whose name ends with its role; else the platform's only
    one; else ``""``. The one home: Add device's console offer reads it too."""
    from modules.nsot import console_profiles as P

    fits = []
    for name in P.shipped():
        try:
            if P.load(name).platform == platform:
                fits.append(name)
        except P.ProfileError:
            continue
    by_role = [n for n in fits if role and n.endswith("_" + role)]
    if len(by_role) == 1:
        return by_role[0]
    return fits[0] if len(fits) == 1 else ""


def _dialect(slug: str) -> str:
    from modules.nsot.platform import platform_for_device

    value = (slug or "").strip()
    return platform_for_device({"platform": value}) if value else ""


# ── NetBox reads ───────────────────────────────────────────────────────────────────────────

def _planned(session, base, hostname: str) -> tuple:
    """``(record, why)``: NetBox's Planned record named *hostname* (its list brief), or None and
    why not (none, more than one, another status, unreadable)."""
    from modules.netbox_client import _nb_get

    try:
        hits = [d for d in _nb_get(session, base, "dcim/devices", name=hostname)
                if d.get("name") == hostname]
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        return None, f"NetBox could not be asked for {hostname}: {type(exc).__name__}: {exc}"
    if not hits:
        return None, (f"NetBox holds no device named {hostname}: plan it there (a Planned "
                      "record with its console port cabled to a console server's port)")
    if len(hits) > 1:
        return None, (f"NetBox holds {len(hits)} devices named {hostname} (ids "
                      + ", ".join(str(d.get("id")) for d in hits) + ")")
    dev = hits[0]
    status = dev.get("status")
    status = (status.get("value") if isinstance(status, dict) else status) or ""
    if str(status).lower() != "planned":
        return None, (f"NetBox holds {hostname} (id {dev.get('id')}) with status {status or 'none'}"
                      ", not Planned: only a Planned record is onboarded")
    return dev, ""


def _ui(base: str, rel: str) -> str:
    return f"{(base or '').rstrip('/')}/{rel.lstrip('/')}"


def eligibility(list_name: str, hostname: str, *, session=None, base: str = "") -> dict:
    """Whether Add device offers **Out-of-band (console)** for *hostname*, and why not, with
    what fixes it: ``{"state": "ok" | "no_name" | "no_record" | "no_path" | "no_port" |
    "unreadable", "why", "fix": {"href", "words", "where"}, "netbox_id", "port_id"}``. *where*
    is ``netbox`` (an absolute NetBox link) or ``console_servers`` (Settings › Installation ›
    Console servers, the route draws its link). Reads NetBox and Mercury's store; writes
    nothing."""
    from modules.nsot import console_path, console_servers

    out = {"state": "no_name", "why": "", "fix": {}, "netbox_id": None, "port_id": None,
           "hostname": hostname, "list_name": list_name}
    if not hostname:
        out["why"] = "give the device's name first: its console path is read from NetBox by it"
        return out
    session, base, err = console_path._ready(session, base)      # noqa: SLF001 - the one reader
    if err:
        return dict(out, state="unreadable", why=err)
    dev, why = _planned(session, base, hostname)
    if dev is None:
        state = "unreadable" if why.startswith("NetBox could not") else "no_record"
        return dict(out, state=state, why=why,
                    fix={"href": _ui(base, "dcim/devices/"), "words": "Open NetBox's devices",
                         "where": "netbox"})
    out["netbox_id"] = dev_id = dev.get("id")
    path = console_path.read_console_path(dev_id, session=session, base=base)
    page = {"href": _ui(base, f"dcim/devices/{dev_id}/"),
            "words": f"Open {hostname} in NetBox", "where": "netbox"}
    if path.get("state") == "unreadable":
        return dict(out, state="unreadable", why=path.get("error") or "the console path could "
                                                                       "not be read", fix=page)
    if path.get("state") != "path" or len(path.get("paths") or []) != 1:
        n = len(path.get("paths") or [])
        why = (f"No console path in NetBox for {hostname}: "
               + (path.get("why") or "no console port cabled to a console server's port")
               if not n else f"NetBox shows {n} console paths for {hostname}, and a run "
                             "reaches exactly one")
        return dict(out, state="no_path", why=why, fix=page)
    one = path["paths"][0]
    out["port_id"] = port_id = one["server_port"]["id"]
    got = console_servers.get_port(port_id)
    if got["state"] == "unreadable":
        return dict(out, state="unreadable",
                    why=f"Mercury's console-server store could not be read: {got['error']}",
                    fix={"href": "", "words": "Open Console servers", "where": "console_servers"})
    if got["state"] != "read":
        return dict(out, state="no_port",
                    why=(f"{one['server']['name']}'s port {one['server_port']['name']} (NetBox "
                         f"{port_id}) has no record in Mercury, so Mercury does not know how to "
                         "reach it"),
                    fix={"href": "", "words": "Open Console servers", "where": "console_servers"})
    return dict(out, state="ok", why="")


def _planned_address(session, base, dev: dict) -> dict:
    """NetBox IPAM's address for the Planned record: its primary IPv4 address when set, else
    the one address assigned to it. ``{"address", "mask", "prefix_len", "family", "on",
    "from", "why"}``; *why* when none can be chosen (none, several and no primary)."""
    from modules.netbox_client import _nb_get

    out = {"address": "", "mask": "", "prefix_len": None, "family": None, "on": "",
           "from": "", "why": ""}
    try:
        rows = _nb_get(session, base, "ipam/ip-addresses", device_id=dev.get("id"))
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        out["why"] = f"NetBox's addresses for {dev.get('name')} could not be read: {exc}"
        return out
    primary = (dev.get("primary_ip4") or {}).get("id") if isinstance(dev.get("primary_ip4"),
                                                                      dict) else None
    chosen = [r for r in rows if primary and r.get("id") == primary]
    how = "its primary IPv4 address"
    if not chosen:
        chosen, how = rows, "the one address assigned to it"
    if len(chosen) != 1:
        out["why"] = (f"NetBox assigns {len(chosen)} addresses to {dev.get('name')} and marks no "
                      "primary IPv4 one" if chosen else
                      f"NetBox assigns no address to {dev.get('name')}: plan its management "
                      "address in NetBox IPAM, on its management interface")
        return out
    row = chosen[0]
    try:
        iface = ipaddress.ip_interface(str(row.get("address") or ""))
    except ValueError:
        out["why"] = f"NetBox's address {row.get('address')!r} is not an address with a prefix"
        return out
    on = row.get("assigned_object") or {}
    out.update(address=str(iface.ip), prefix_len=iface.network.prefixlen,
               family=iface.version, on=str(on.get("name") or ""),
               mask=str(iface.netmask) if iface.version == 4 else "",
               **{"from": f"NetBox IPAM, {how} ({row.get('address')}, id {row.get('id')})"})
    if iface.version == 6:
        out["why"] = (f"NetBox's address for {dev.get('name')} is IPv6 ({row.get('address')}), "
                      "and the console's static path types an IPv4 address and mask only "
                      "(C1245): plan an IPv4 management address, or onboard it another way")
    return out


def _uplink(session, base, dev: dict, relay_device: str) -> tuple:
    """``(interface, from, why)``: the device's interface NetBox cables to *relay_device*."""
    from modules.netbox_client import _nb_get, _nb_read_by_id

    try:
        ifaces = _nb_get(session, base, "dcim/interfaces", device_id=dev.get("id"))
    except Exception as exc:                          # noqa: BLE001 - said, never raised
        return "", "", f"NetBox's interfaces for {dev.get('name')} could not be read: {exc}"
    hits = []
    for iface in ifaces:
        cable = iface.get("cable")
        cable_id = cable.get("id") if isinstance(cable, dict) else cable
        if not isinstance(cable_id, int):
            continue
        state, body = _nb_read_by_id(session, base, "dcim/cables", cable_id)
        if state != "ok":
            continue
        for end in (body or {}).get("a_terminations", []) + (body or {}).get("b_terminations",
                                                                            []):
            obj = end.get("object") or {}
            peer = (obj.get("device") or {}).get("name")
            if peer and peer == relay_device and end.get("object_type") == "dcim.interface":
                hits.append((iface.get("name"), cable_id, obj.get("name")))
    if len(hits) == 1:
        name, cable_id, far = hits[0]
        return name, f"NetBox: cable {cable_id} to {relay_device} {far}", ""
    if hits:
        return "", "", (f"NetBox cables {len(hits)} of {dev.get('name')}'s interfaces to "
                        f"{relay_device} ({', '.join(h[0] for h in hits)}): name the one it "
                        "reaches the relay on")
    return "", "", (f"NetBox shows no cable from {dev.get('name')} to {relay_device}, and "
                    "Mercury keeps no LLDP table to read it from: name the port it reaches the "
                    "relay on")


_VLAN_IFACE = re.compile(r"^[Vv]lan(\d{1,4})$")


def derive(list_name: str, hostname: str, role: str, asked: dict = None, *, session=None,
           base: str = "", facts=None) -> dict:
    """Every field the run needs, derived; asked only when it cannot be (*asked*: the asked
    fields the review's form sent). ``{"netbox_id", "device", "address", "mask", "prefix_len",
    "vlan", "interface", "uplink", "gateway", "relay", "server", "filename", "from": {field:
    words}, "asked": [fields to ask], "why": {field: why}, "refused_by": {key: why}}``.
    Contacts no device: NetBox, committed intent."""
    from modules.nsot import console_path, ztp_relayed

    asked = dict(asked or {})
    out = {"netbox_id": None, "device": hostname, "address": "", "mask": "", "prefix_len": None,
           "vlan": 1, "interface": "", "uplink": "", "gateway": "", "relay": None, "server": "",
           "filename": "", "from": {}, "asked": [], "why": {}, "refused_by": {}}

    def refuse(key, text):
        out["refused_by"].setdefault(key, text)

    session, base, err = console_path._ready(session, base)      # noqa: SLF001 - the one reader
    if err:
        refuse("netbox", err)
        return out
    dev, why = _planned(session, base, hostname)
    if dev is None:
        refuse("device", why)
        return out
    out["netbox_id"] = dev.get("id")
    got = _planned_address(session, base, dev)
    if got["why"]:
        refuse("address", got["why"])
        return out
    out.update(address=got["address"], mask=got["mask"], prefix_len=got["prefix_len"])
    out["from"]["address"] = got["from"]
    m = _VLAN_IFACE.match(got["on"] or "")
    if m:
        out["vlan"] = int(m.group(1))
        out["from"]["vlan"] = f"NetBox: the address is on {got['on']}"
    else:
        out["from"]["vlan"] = ("1, the default: NetBox's address is on "
                               + (got["on"] or "no interface") + ", not a VLAN interface")
    try:
        link = ztp_relayed.link_for_address(out["address"], facts if facts is not None
                                            else ztp_relayed.intent_everywhere())
    except ztp_relayed.Refused as exc:
        refuse("relay", str(exc))
        return out
    relay = link["relay"]
    out["relay"] = relay
    out["gateway"] = relay["address"]
    out["from"]["gateway"] = (f"committed intent: {relay['device']} {relay['iface']}'s own "
                              f"address on {link['prefix']}")
    uplink, said, why = _uplink(session, base, dev, relay["device"])
    if uplink:
        out["uplink"], out["from"]["uplink"] = uplink, said
    else:
        typed = str(asked.get("uplink") or "").strip()
        out["asked"].append("uplink")
        out["why"]["uplink"] = why
        if typed:
            from modules.nsot import console_survey as V
            try:
                out["uplink"] = V.check_param("uplink", "interface", typed)
                out["from"]["uplink"] = "asked: typed in the review"
            except ValueError as exc:
                refuse("uplink", str(exc))
        else:
            refuse("uplink", why)
    if role == "switch":
        out["interface"] = f"Vlan{out['vlan']}"
        out["from"]["interface"] = f"a switch's management interface is Vlan{out['vlan']}"
    else:
        out["interface"] = out["uplink"]
        out["from"]["interface"] = "a router's management address is on its routed uplink"
    # Where the copy fetches from: the relay's IPv4 helper target, the config server a relayed
    # device is served by (Create's own plan derives it too, and the review refuses a
    # disagreement), and the device's boot file.
    helpers = [h for h in relay.get("relays") or [] if ":" not in str(h)]
    out["server"] = helpers[0] if helpers else ""
    out["filename"] = oob_steps.boot_file(hostname)
    if not out["server"]:
        refuse("responder", f"the relay {relay['device']} {relay['iface']} names no IPv4 helper "
                            "target in committed intent, so the config server the device "
                            "copies its bootstrap from is not known")
    return out


def _static_params(device: str, d: dict) -> dict:
    """The static kick-start's parameters, every one derived (the profile's names)."""
    return {"hostname": device, "interface": d["uplink"], "vlan": d["vlan"],
            "address": d["address"], "mask": d["mask"], "gateway": d["gateway"]}


def _programmed(profile, device: str, d: dict) -> tuple:
    """``(lines, readback plan, copy line)`` through the adapter; ValueError naming what it
    refuses."""
    lines = oob_steps.static_lines(profile, _static_params(device, d))
    return lines, oob_steps.readback_plan(lines), oob_steps.copy_line(d["server"], d["filename"])


# ── the review ─────────────────────────────────────────────────────────────────────────────

def _host_key(port: dict) -> dict:
    """The console server's SSH host key Mercury holds, in full: ``{"host", "port", "state":
    "held" | "none" | "no_ssh" | "unreadable", "type", "fingerprint", "kept_at"}``."""
    from modules import host_keys
    from modules.nsot import console_rekey

    host, ssh_port, why = console_rekey.ssh_endpoint(port or {})
    out = {"host": host, "port": ssh_port, "state": "no_ssh" if why else "none", "type": "",
           "fingerprint": "", "kept_at": "", "error": ""}
    if why:
        return out
    try:
        rec = host_keys.held(host)
    except host_keys.HostKeyStoreUnreadable as exc:
        return dict(out, state="unreadable", error=str(exc))
    if not rec:
        return out
    return dict(out, state="held", type=rec.get("type") or "",
                fingerprint=rec.get("fingerprint") or "", kept_at=rec.get("kept_at") or "")


def _program(profile, typed_lines, rb_plan: dict, copy: str) -> dict:
    """The whole console program, by state: every byte the run may send."""
    from modules.nsot import console_profiles as P
    from modules.nsot import console_session as S
    from modules.nsot import console_ztp as Z

    lines = Z.SESSION_LINES[profile.platform]
    typed = list(typed_lines)
    return {"wake": [[S.IDLE, "\r"]],
            "prelude": Z._preludes(lines),                        # noqa: SLF001 - one home
            "reads": [[P.PRIV_EXEC, lines["pager_off"] + "\r"],
                      [P.PRIV_EXEC, profile.blank_command + "\r"]],
            "recheck": [[P.PRIV_EXEC, profile.blank_command + "\r"]],
            "lines": ([[P.PRIV_EXEC, typed[0] + "\r"]]
                      + [[P.CONFIG, line + "\r"] for line in typed[1:]]),
            "read_back": [[P.PRIV_EXEC, cmd + "\r"] for cmd in rb_plan["reads"]],
            "copy": [[state, text + "\r"] for state, text in oob_steps.copy_steps(copy)],
            "ends": P.PRIV_EXEC}



def _plan(list_name: str, fields: dict, d: dict, secret: str):
    """Create's own plan for the derived fields (`onboard.build_plan`, the console source)."""
    from modules.nsot.onboard import build_plan

    source_kind = "local"
    try:
        from modules.inventory.source_config import load

        source_kind = load(list_name).get("source") or "local"
    except Exception:                                 # noqa: BLE001 - the plan refuses
        log.warning("oob onboard: the inventory source of %r could not be read", list_name)
    return build_plan(
        hostname=fields.get("hostname", ""), platform=_dialect(fields.get("platform")),
        platform_slug=(fields.get("platform") or "").strip(), list_name=list_name,
        mgmt_ip=d["address"], mgmt_mask=d["mask"], manager_interface=d["interface"],
        manager_gateway=d["gateway"], address_source=oob_steps.address_source(),
        role=(fields.get("role") or "").strip().lower(), source_kind=source_kind,
        domain=(fields.get("domain") or "").strip() or "rcn.lab",
        mgmt_interface=(fields.get("mgmt_interface") or "").strip(), secret=secret)


def _norm(fields) -> dict:
    return {k: str((fields or {}).get(k) or "").strip() for k in FIELDS}


def preview(list_name: str, fields: dict, *, session=None, base: str = "", values=None,
            facts=None, plan_builder=None) -> dict:
    """The one review: everything the run would do, contacting no device and writing nothing;
    its hash binds every byte the console may be sent, the derived values, the console path,
    the port's record and the server's host key, the profile, and Create's own plan."""
    from modules.nsot import console_ztp as Z
    from modules.nsot.onboard import plan_fingerprint, plan_shown

    f = _norm(fields)
    hostname, role = f["hostname"], f["role"].lower()
    d = derive(list_name, hostname, role, {k: f[k] for k in ASKED_FIELDS}, session=session,
               base=base, facts=facts)
    profile_name = profile_for(_dialect(f["platform"]), role)
    t = Z._target(list_name, d["netbox_id"] or 0, profile_name or None,  # noqa: SLF001
                  session=session, base=base) if d["netbox_id"] else \
        {"refused_by": {}, "device": hostname, "path": None, "port_id": None, "port": None,
         "transport": None, "profile": None}
    refused = dict(d["refused_by"])
    for key, why in t["refused_by"].items():
        refused.setdefault(key, why)
    if not profile_name:
        refused.setdefault("profile", f"no shipped console profile fits platform "
                                      f"{f['platform'] or '(none)'} and role {role or '(none)'}")
    prof = t["profile"]
    out = {"ok": False, "list_name": list_name, "device_id": d["netbox_id"],
           "device": t["device"] or hostname, "role": role, "platform": f["platform"],
           "fields": {k: f[k] for k in FORM_FIELDS + ASKED_FIELDS},
           "profile": ({"name": prof.name, "version": prof.version, "sha256": prof.sha256}
                       if prof else None),
           "path": ({k: t["path"][k] for k in ("console_port", "cable", "server", "server_port")}
                    if t["path"] else None),
           "port_id": t["port_id"], "port": t["port"],
           "transport": t["transport"].describe() if t["transport"] else "",
           "host_key": _host_key(t["port"]) if t["port"] else None, "derived": d,
           "plan": None, "program": None, "lines": [], "read_back": [], "copy": "",
           "gate": "", "creates": [], "stops": [w for _r, _o, w in STOPS],
           "not_doing": list(NOT_DOING), "hash": ""}
    made = None
    if role != "switch":
        refused.setdefault("role", f"the out-of-band static path is built for a switch, and "
                                   f"the form chose {role or 'no role'}: a router's routed-port "
                                   "program is not built yet")
    elif prof is not None and not d["refused_by"]:
        try:
            made = _programmed(prof, out["device"], d)
        except ValueError as exc:
            refused.setdefault("program", str(exc))
    plan = None
    if not d["refused_by"]:
        try:
            plan = (plan_builder or _plan)(list_name, f, d, "PLACEHOLDER-not-the-real-credential")
        except Exception as exc:                      # noqa: BLE001 - a refusal, named
            log.exception("oob onboard: Create's plan failed for %s", hostname)
            refused.setdefault("plan", f"Create's plan could not be made: {exc}")
    if plan is not None:
        shown = plan_shown(plan)
        out["plan"] = {"summary": plan.summary, "shown": shown,
                       "fingerprint": plan_fingerprint(shown),
                       "bootstrap_lines": len((plan.bootstrap_config or "").splitlines())}
        if plan.blocking_reasons:
            refused.setdefault("plan", "; ".join(plan.blocking_reasons))
        if d["netbox_id"] and plan.planned_netbox_id != d["netbox_id"]:
            refused.setdefault("plan", f"Create's plan read NetBox record "
                                       f"{plan.planned_netbox_id}, and the console path is "
                                       f"record {d['netbox_id']}'s")
        planned_server = getattr(plan, "ztp_server", "") or ""
        if planned_server and planned_server != d["server"]:
            refused.setdefault("plan", f"Create's plan copies from config server "
                                       f"{planned_server}, and the relay's helper target is "
                                       f"{d['server']}")
    program = None
    if made is not None and prof is not None:
        lines, rb_plan, copy = made
        program = _program(prof, lines, rb_plan, copy)
        from modules.nsot import console_ztp as Z
        out["program"] = Z._masked_program(program, values)       # noqa: SLF001 - one home
        from modules.redact import redact_text
        out["lines"] = [redact_text(line, values) for line in lines]
        out["read_back"] = list(rb_plan["reads"])
        out["not_read"] = [list(x) for x in rb_plan.get("not_read") or ()]
        out["copy"] = copy
        out["gate"] = oob_steps.gate_words(out["device"], d["address"], d["filename"],
                                           d["server"])
    if plan is not None:
        out["creates"] = [
            f"the static bootstrap for {out['device']} ({out['plan']['bootstrap_lines']} lines,"
            " its one-time credential minted at Create, never on the console), served only by "
            "the responder's narrowed gate",
            f"its pending intent, static: {d['address']} {d['mask']} on {d['interface']}, "
            f"default gateway {d['gateway']}",
            f"its manifest entry, pending, with NetBox id {d['netbox_id']}",
            "no Kea subnet, reservation or MAC rule; nothing in NetBox until Verify",
        ]
    out["refused_by"] = refused
    out["refusals"] = list(refused.values())
    out["ok"] = not refused
    if out["ok"]:
        hk = out["host_key"] or {}
        out["hash"] = _digest({
            "kind": KIND, "list": list_name, "device_id": d["netbox_id"],
            "device": out["device"], "role": role, "profile": out["profile"],
            "path": out["path"], "port_id": out["port_id"], "port": out["port"],
            "host_key": [hk.get("type"), hk.get("fingerprint")],
            "derived": {k: d[k] for k in ("address", "mask", "vlan", "interface", "uplink",
                                          "gateway", "relay", "server", "filename")},
            "plan": out["plan"]["fingerprint"], "program": program})
    return out


#: What the run will not do, said on the review.
NOT_DOING = (
    "save: nothing is written to startup (no write memory), so a reload returns the device to "
    "its factory state; Verify's persist step saves it",
    "send a credential over the console: the one-time credential is only in the bootstrap the "
    "device copies from the responder",
    "write any Kea object, or change NetBox: the Planned record and its console path are only "
    "read, and Verify records the device in NetBox",
    "touch any other device: the relay is read from committed intent, never reached",
)


# ── the record ─────────────────────────────────────────────────────────────────────────────

def _new_record(p: dict, actor: str, actor_verified: str, reason: str, run_id: str) -> dict:
    from modules.nsot import console_ztp as Z

    rec = Z._new_record(KIND, p, actor, actor_verified, run_id)  # noqa: SLF001 - one shape
    d = p["derived"]
    rec.update(reason_given=reason, address=d["address"], mask=d["mask"],
               interface=d["interface"], uplink=d["uplink"], gateway=d["gateway"],
               server=d["server"], filename=d["filename"], lines=list(p["lines"]),
               plan_fingerprint=(p.get("plan") or {}).get("fingerprint", ""),
               host_key=p.get("host_key"), mac=None, created=None, stop=None, copy=None,
               settle_until=None, answering=None)
    return rec


def get_run(list_name: str, run_id: str):
    """One run's record, or None (the console runs' one folder)."""
    from modules.nsot import console_ztp as Z

    return Z.get_run(list_name, run_id)


def latest_run(list_name: str, hostname: str):
    """The newest console run of *hostname* in *list_name* (any kind), or None: the run page
    and the In progress list open it by the device's name."""
    from modules.nsot import console_ztp as Z

    for r in Z.runs(list_name, limit=200)["runs"]:
        if (r.get("device") or "").lower() == (hostname or "").lower():
            return r
    return None


# ── the run ───────────────────────────────────────────────────────────────────────────────

class _Stop(Exception):
    """A stop inside the console phases: its rule and the comparison, both operands named."""

    def __init__(self, rule: str, compared: str):
        super().__init__(compared)
        self.rule, self.compared = rule, compared


def _create(list_name: str, fields: dict, d: dict, previewed: str, actor: str) -> dict:
    """Create, as reviewed: the plan rebuilt now (secret minted by its credentials step), refused
    when its fingerprint is not the review's, then onboarding's own phase 1 (credentials,
    commit, render). ``{"ok", "reason", "completed", "commit"}``."""
    from modules.nsot.onboard import plan_fingerprint, plan_shown, real_steps, run_onboarding

    plan = _plan(list_name, fields, d, "")
    now = plan_fingerprint(plan_shown(plan))
    if now != previewed:
        return {"ok": False, "completed": [], "commit": "",
                "reason": (f"Create's plan moved since the review (reviewed {previewed[:12]}, now "
                           f"{now[:12]})")}
    from modules.config import get_list_data_dir
    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    got = run_onboarding(plan, repo=repo, **real_steps(repo, actor=actor))
    return {"ok": bool(got.get("ok")) and not got.get("failed_at"),
            "completed": list(got.get("completed") or []), "commit": got.get("commit", ""),
            "reason": got.get("reason", "")}


def _netbox_untouched(*_a, **_k) -> dict:
    """Abandon's NetBox step for a console onboarding's undo: the run created nothing in NetBox
    (Verify is the only creator), so the Planned record and its console path are kept."""
    return {"ok": True, "deleted": [], "skipped": [],
            "message": "this onboarding created nothing in NetBox; the Planned record and its "
                       "console path are kept"}


def undo_created(list_name: str, hostname: str, actor: str) -> dict:
    """Everything Create made, removed in the reverse order, through Abandon's own steps (its
    dry run, then the run bound to it), NetBox kept: Abandon keeps the Planned record Create
    read and gives the name back with it retained (C1613), and `_netbox_untouched` stands for
    the remover so nothing in NetBox is deleted on any other path. ``{"ok", "undone":
    [words], "remaining": [words]}``."""
    from modules.config import get_list_data_dir
    from modules.nsot.onboard import abandon_fingerprint, abandon_onboarding

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    try:
        dry = abandon_onboarding(repo, hostname, list_name, actor=actor, dry_run=True,
                                 remove_netbox=_netbox_untouched)
        got = abandon_onboarding(repo, hostname, list_name, actor=actor,
                                 remove_netbox=_netbox_untouched,
                                 confirmed=abandon_fingerprint(dry))
    except Exception as exc:                          # noqa: BLE001 - said in the stop
        log.exception("oob onboard: the undo of %s raised", hostname)
        return {"ok": False, "undone": [], "remaining": [f"the undo raised: {exc}"]}
    return {"ok": bool(got.get("ok")),
            "undone": [f"{s['step']}: {s['detail']}" for s in got.get("steps") or [] if s["ok"]],
            "remaining": ([f"{r['step']}: {r['detail']}" for r in got.get("remaining") or []]
                          + ([got["error"]] if got.get("error") else []))}


def _record_mac(list_name: str, hostname: str, mac: str, actor: str) -> str:
    """The MAC read back, recorded on the pending manifest entry and committed. ``""`` or why
    it could not be."""
    from modules.config import get_list_data_dir
    from modules.nsot import manifest
    from modules.nsot import repo as R

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")
    try:
        with R.repo_lock(repo):
            identity, entry = manifest.find_by_name(repo, hostname)
            if not identity:
                return f"{hostname} is not in {list_name}'s manifest"
            manifest.upsert_device(repo, identity, hostname, mgmt_mac=mac)
            rel = os.path.relpath(manifest.manifest_path(repo), repo)
            rc, _sha, err = R.commit(
                repo, f"onboarding: {hostname}'s MAC {mac}, read back over its console\n\n"
                      f"Source: onboarding\nActor: {actor or 'unknown'}\n",
                list_name=list_name, paths=(rel,), source="onboarding", actor=actor)
            return "" if rc == 0 else f"the manifest commit failed: {err}"
    except Exception as exc:                          # noqa: BLE001 - said on the record
        log.exception("oob onboard: %s's MAC could not be recorded", hostname)
        return f"{type(exc).__name__}: {exc}"


def _sent_lines(console) -> list:
    from modules.redact import redact_text

    text = console.sent().decode("ascii", "replace") if console is not None else ""
    return [redact_text(l, console.values) for l in text.split("\r") if l.strip()]


def stop_words(rule: str, compared: str, sent: list, undo: dict) -> str:
    """A stop in words: the comparison with both operands, what was sent, what was undone and
    what was kept (design section 4)."""
    parts = [compared.rstrip(".") + "."]
    parts.append("Sent: " + "; ".join(sent) + "." if sent else "Nothing was typed.")
    if undo is None:
        if rule in ("busy", "unreachable", "signed_in", "login", "not_blank"):
            parts.append("Nothing was created.")
        elif rule == "not_answering":
            parts.append("Kept: the pending device, its static intent and its bootstrap, so "
                         "Verify reaches it once it answers; Abandon removes them.")
    else:
        parts.append(("Undone: " + "; ".join(undo["undone"]) + ".") if undo["undone"]
                     else "Nothing needed undoing.")
        if undo["remaining"]:
            parts.append("Not undone: " + "; ".join(undo["remaining"]) + ".")
        parts.append("Nothing was saved on the device: a reload returns it to its factory "
                     "state.")
    return " ".join(parts)


def run(list_name: str, fields: dict, *, confirmed_hash: str, actor: str, actor_verified: str,
        reason: str, run_id: str = "", timings: Timings = DEFAULT_TIMINGS,
        clock=time.monotonic, wall=time.time, sleep=time.sleep, session=None, base: str = "",
        values=None, facts=None, probe=None, create=None, undo=None, plan_builder=None,
        record_mac=None) -> dict:
    """The one background run, holding the device and its console-server port: the record,
    written. Raises `Refused` with nothing sent: an actor who is not a verified person, no
    reason, a review that refuses, a hash that moved (both named), or the device held."""
    from modules.nsot import console_ztp as Z
    from modules.nsot import console_profiles as P
    from modules.nsot import console_transport as T
    from modules.nsot import device_ops

    why = Z.verified_person(actor, actor_verified).replace("a kick-start", "an out-of-band "
                                                                          "onboarding")
    if why:
        raise Refused(why + ". Nothing was sent.")
    if not str(reason or "").strip():
        raise Refused("an out-of-band onboarding types on a device and is given a reason, and "
                      "none was. Nothing was sent.")
    p = preview(list_name, fields, session=session, base=base, values=values, facts=facts,
                plan_builder=plan_builder)
    if not p["ok"]:
        raise Refused("; ".join(p["refusals"]) + ". Nothing was sent.")
    if confirmed_hash != p["hash"]:
        raise Refused(f"the onboarding changed since the review you confirmed "
                      f"({confirmed_hash or 'no hash'} -> {p['hash']}): its derived fields, "
                      "console path, port, host "
                      "key, profile, program or Create's plan moved. Nothing was sent; review "
                      "it again.")
    prof = P.load(p["profile"]["name"])
    d = p["derived"]
    lines, rb_plan, copy = _programmed(prof, p["device"], d)
    program = _program(prof, lines, rb_plan, copy)
    rec = _new_record(p, actor, actor_verified, reason, run_id)
    ctx = {"list": list_name, "fields": _norm(fields), "p": p, "rb_plan": rb_plan,
           "program": program, "actor": actor, "timings": timings,
           "create": create or _create, "undo": undo or undo_created,
           "record_mac": record_mac or _record_mac, "created": False}
    console = None
    try:
        with device_ops.hold(list_name, p["device"], OP, actor,
                             detail=f"console-server port {p['port_id']}"):
            Z.record(list_name, rec)
            device_ops.note("opening the console")
            try:
                transport = Z._open(p, actor)                     # noqa: SLF001 - one opener
            except T.PortBusy as exc:
                _finish_stop(rec, None, "busy", str(exc), None)
            except T.ConsoleRefused as exc:
                _finish_stop(rec, None, "unreachable",
                             f"the console could not be opened: {exc}", None)
            except OSError as exc:
                _finish_stop(rec, None, "unreachable",
                             f"the console could not be opened: {type(exc).__name__}: {exc}",
                             None)
            else:
                copied = False
                try:
                    console = Z._Console(transport, prof, timings, clock,  # noqa: SLF001
                                         (list_name, p["device"]), timings.bound_s, values)
                    copied = _console_phases(console, rec, ctx, wall)
                finally:
                    transport.close()
                if copied:
                    device_ops.note("onboard: release")
                    rec["released_at"] = wall()
                    _answering(rec, ctx, wall, sleep, probe, console)
            Z.record(list_name, rec)
    except device_ops.DeviceBusy as exc:
        raise Refused(f"{exc}. Nothing was sent.") from None
    Z._announce()                                                 # noqa: SLF001 - one announcer
    log.info("console onboard: %s/%s by %s: %s", list_name, p["device"], actor, rec["outcome"])
    return rec


def _finish_stop(rec: dict, console, rule: str, compared: str, undo) -> None:
    from modules.nsot import console_ztp as Z
    from modules.redact import redact_text

    sent = _sent_lines(console)
    # The comparison can carry what the device printed (a refusal's words): masked at rest, as
    # the reason and the sent lines are.
    compared = redact_text(compared, console.values if console is not None else None)
    rec["stop"] = {"rule": rule, "compared": compared, "sent": sent,
                   "undone": (undo or {}).get("undone", []),
                   "remaining": (undo or {}).get("remaining", []),
                   "undo_ran": undo is not None}
    Z._finish(rec, console, outcome=OUTCOME[rule],              # noqa: SLF001 - one shape
              reason=stop_words(rule, compared, sent, undo))


def _then(console, steps, final, what: str, refused_as=None):
    """One phase; a session that did not end where it should is the `unexpected` stop, unless
    it stopped at a line the device refused (C1593: the session stops there, `session.refused`)
    and *refused_as* ``(rule, words(refused))`` names the caller's own stop for it."""
    got = console.then(steps, final)
    if got.outcome != "done":
        refused = console.session.refused if console.session is not None else None
        if refused and refused_as:
            raise _Stop(refused_as[0], refused_as[1](refused))
        raise _Stop("unexpected", f"expected {' or '.join(final)} after {what}; the session "
                                  f"ended {got.outcome}: {got.reason}")
    return console.output()


def _console_phases(console, rec: dict, ctx: dict, wall) -> bool:
    """Wake to copy. True when the copy was verified; otherwise the stop is on *rec* (and what
    Create made, undone)."""
    try:
        return _phases(console, rec, ctx, wall)
    except _Stop as stop:
        undo = None
        # Every stop once Create has begun undoes it, whatever stopped the run (a device found
        # configured at the blank check again included); a stop before it created nothing.
        if ctx["created"]:
            from modules.nsot import device_ops
            device_ops.note("onboard: undo")
            undo = ctx["undo"](ctx["list"], ctx["p"]["device"], ctx["actor"])
        _finish_stop(rec, console, stop.rule, stop.compared, undo)
        return False


def _phases(console, rec: dict, ctx: dict, wall) -> bool:
    from modules.nsot import console_profiles as P
    from modules.nsot import console_survey as V
    from modules.nsot import device_ops

    program, p, prof = ctx["program"], ctx["p"], console.profile
    device_ops.note("waking the console")
    state = console.attach(program["wake"])
    found = console.attach_state
    if state is None and found not in V.SIGNED_IN + V.LOGIN:
        raise _Stop("unexpected", f"expected a prompt answering the wake; "
                                  f"{console.last.reason or console.last.outcome}")
    if state not in program["prelude"]:
        if found in V.SIGNED_IN:
            raise _Stop("signed_in", f"the console answered at {found} (blank needs the setup "
                                     "dialog, Press RETURN or the user prompt)")
        if found in V.LOGIN:
            raise _Stop("login", f"the console asked for a login ({found})")
        # A deliberate backup stop, unreachable today by design: `attach` returns None or a
        # FINAL state, and every state that reaches here stops above as signed_in or login. It
        # stays so that a change to `attach` or those sets still refuses, never types on. Not
        # dead code (run #25's equivalents, C1622; the operator, 2026-10-23).
        raise _Stop("unexpected", f"expected the setup dialog, Press RETURN or the user prompt "
                                  f"after the wake; the console was at {found}")
    device_ops.note("onboard: blank")
    out = _then(console, program["prelude"][state] + program["reads"], (P.PRIV_EXEC,),
                "the prelude and the blank check",
                refused_as=("not_blank", lambda r: f"blank is unknown: {r['line']!r} was "
                                                   f"refused: {r['words']!r}"))
    check = V.blank_check(out, prof)
    rec["blank"] = {"blank": check.blank, "size": check.size, "reason": check.reason}
    if check.blank is not True:
        raise _Stop("not_blank", f"nvram holds a startup configuration of {check.size} bytes "
                                 f"(blank needs 0 or none): {check.reason}"
                    if check.size else f"blank is unknown: {check.reason}")
    device_ops.note("onboard: create")
    ctx["created"] = True                  # from here, anything Create made is undone
    made = ctx["create"](ctx["list"], ctx["fields"], p["derived"],
                         p["plan"]["fingerprint"], ctx["actor"])
    rec["created"] = made
    if not made.get("ok"):
        raise _Stop("create", f"Create did not complete: {made.get('reason') or 'no reason'}"
                              f" (completed: {', '.join(made.get('completed') or []) or 'none'})")
    from modules.nsot import console_ztp as Z
    Z.record(ctx["list"], rec)
    device_ops.note("onboard: kick-start")
    out = _then(console, program["recheck"], (P.PRIV_EXEC,), "the blank check again",
                refused_as=("not_blank", lambda r: f"the blank check again found {r['line']!r} "
                                                   f"refused: {r['words']!r} (blank needs 0 or "
                                                   "none)"))
    again = V.blank_check(out, prof)
    rec["recheck"] = {"blank": again.blank, "size": again.size, "reason": again.reason}
    if again.blank is not True:
        raise _Stop("not_blank", f"the blank check again found {again.reason} (blank needs 0 "
                                 "or none)")
    steps = program["lines"]
    for i, (state_, text) in enumerate(steps):
        final = (steps[i + 1][0],) if i + 1 < len(steps) else (program["ends"],)
        got = console.then([[state_, text]], final)
        said, _before = oob_steps.refused_in(console.output(), prof)
        line = text.rstrip("\r")
        if said:
            raise _Stop("refused_line", f"{line.strip()!r} was refused: {said!r}. Stopped there")
        if got.outcome != "done":
            raise _Stop("unexpected", f"expected {final[0]} after {line.strip()!r}; the session "
                                      f"ended {got.outcome}: {got.reason}")
    device_ops.note("onboard: read-back")
    answers = {}
    for _state, text in program["read_back"]:
        cmd = text.rstrip("\r")
        out = _then(console, [[P.PRIV_EXEC, text]], (P.PRIV_EXEC,), repr(cmd),
                    refused_as=("read_back", lambda r, cmd=cmd: f"the read-back {cmd!r} was "
                                                                f"refused: {r['words']!r}"))
        # A deliberate backup stop, unreachable today by design: `_then` returns only a session
        # that ended done, which the session's own refusal check (C1593) has already passed on
        # this text with this profile. It stays so that a change there still stops the
        # read-back. Not dead code (run #25's equivalents, C1622; the operator, 2026-10-23).
        said, _before = oob_steps.refused_in(out, prof)
        if said:
            raise _Stop("read_back", f"the read-back {cmd!r} was refused: {said!r}")
        answers[cmd] = out
    rb = oob_steps.readback_verdict(ctx["rb_plan"], answers)
    from modules.redact import redact_text
    # A difference quotes what the device showed, and the copy's verdict what it printed:
    # masked at rest, as the kick-start's are (console_ztp `_readback`, `_copy`).
    rec["read_back"] = {"ok": rb["ok"],
                        "differs": [redact_text(d_["why"], console.values)
                                    for d_ in rb["differs"]],
                        "mac_why": redact_text(rb["mac_why"], console.values)}
    if not rb["ok"]:
        raise _Stop("read_back", "; ".join(d_["why"] for d_ in rb["differs"])
                    or f"the MAC in use could not be read: {rb['mac_why']}")
    rec["mac"] = rb["mac"]
    rec["mac_record_error"] = ctx["record_mac"](ctx["list"], p["device"], rb["mac"],
                                                ctx["actor"])
    Z.record(ctx["list"], rec)
    device_ops.note("onboard: copy")
    got = oob_steps.then_with_timeout(console, program["copy"], (program["ends"],),
                                      ctx["timings"].copy_timeout_s
                                      or oob_steps.copy_timeout_s())
    verdict = oob_steps.verify_copy(console.output(), prof)
    rec["copy"] = {k: redact_text(v, console.values) if isinstance(v, str) else v
                   for k, v in verdict.items()}
    if got.outcome != "done" or not verdict["ok"]:
        raise _Stop("copy", f"{p['copy']!r}: {verdict['why']} (needs one [OK - N bytes], N "
                            "over 0, and no refusal)"
                    + ("" if got.outcome == "done" else f"; the session ended {got.outcome}: "
                                                         f"{got.reason}"))
    rec["copied_at"] = wall()
    return True


def _answering(rec: dict, ctx: dict, wall, sleep, probe, console) -> None:
    """Answering: the SSH key's settle waited out (shown: the record holds when it ends), then
    the address probed until SSH answers or the bound passes. Nothing is reached but port 22."""
    from modules.nsot import console_ztp as Z
    from modules.nsot import device_ops

    t = ctx["timings"]
    device_ops.note("onboard: answering")
    until = rec["copied_at"] + t.key_settle_s
    rec["settle_until"] = until
    Z.record(ctx["list"], rec)
    left = until - wall()
    if left > 0:
        sleep(left)
    if probe is None:
        from modules.readers.reachability import probe
    address = rec["address"]
    deadline = wall() + t.answer_bound_s
    tries = 0
    while True:
        tries += 1
        answered, claim = probe(address)
        if answered:
            rec["answering"] = {"ok": True, "claim": claim, "tries": tries, "at": wall()}
            device_ops.note("onboard: record")
            Z._finish(rec, console, outcome="done",              # noqa: SLF001 - one shape
                      reason=f"{rec['device']} answers at {address}: ready to Verify")
            return
        if wall() >= deadline:
            rec["answering"] = {"ok": False, "claim": claim, "tries": tries, "at": wall()}
            relay = (ctx["p"]["derived"]["relay"] or {}).get("device") or "the relay"
            _finish_stop(rec, console, "not_answering",
                         f"SSH to {address} through {relay} "
                         f"did not answer within {int(t.answer_bound_s)} s of the key's settle "
                         f"({tries} tries; the last: {claim})", None)
            return
        sleep(t.answer_every_s)


def settle_words(rec: dict, now: float = None) -> str:
    """What the Answering step waits on, in words, from its record: the key's settle until a
    time, then SSH at the address."""
    now = time.time() if now is None else now
    until = (rec or {}).get("settle_until")
    if until and now < until:
        return (f"waiting for {rec.get('device')}'s SSH key to settle, until "
                f"{_clock(until)}")
    return f"SSH at {(rec or {}).get('address') or 'its address'} to answer"
