"""Mercury's OpenFlow configuration templates, one per switch family (docs/LAB9_OPENFLOW.md).

Each template is a YAML file in `openflow_templates/` (vendor knowledge, product): its family,
the netmiko drivers it is for, its form (``ovs-vsctl``: one transaction; ``cli``: configuration
lines in order), the OpenFlow versions and transports the vendor's document says it supports,
whether a controller may be given by an IPv6 address, and its lines. **Every line cites its
vendor document** (``cite``: keys of the template's ``citations``, each naming the document,
the section or command entry, the release, the URL and the date it was read, and whether it
was read on the vendor's page, ``verified``). `problems` checks this, and `render` refuses a
template it finds a problem in.

**Rendered from NetBox values** (`modules/sdn/openflow_values.py`): a line's ``{name}`` is a
value; ``each: ports`` repeats it per OpenFlow port (``{port}``); ``when: <name>`` keeps it only
when that value is given. A missing value refuses the render, naming it and where in NetBox it
comes from (`openflow_values.WHERE`). A version, transport or IPv6 controller the template does
not support refuses too, naming both.

**Draft until confirmed, per network.** A template is ``draft`` until a verified person confirms
it on a network against a saved capture of one of its devices (`discovery.captures`): the
confirmation is committed in that network's repository (`openflow_confirmations/<name>.yml`)
naming the capture and the template's SHA-256, so a changed template is a draft again. Only a
CONFIRMED template is ever sent: `push_refusal` is ``""`` for a confirmed template and names the
template and its status otherwise, and every path that sends a template's lines asks it first
(`ovs_config.apply`; a vendor driver, when one exists). The discovery drivers refuse every write
at the session as well (`connection._guard_writes`).
"""

import hashlib
import logging
import os
import re

log = logging.getLogger(__name__)

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openflow_templates")
FORMS = ("ovs-vsctl", "cli")
CITATION_FIELDS = ("document", "section", "release", "url", "read")
DIR = "openflow_confirmations"
_PLACE = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)*)\}")
DRAFT, CONFIRMED = "draft", "confirmed"


class Refused(ValueError):
    """A render or a confirmation refused, naming what and why."""


def names() -> list:
    """The templates Mercury ships, by name."""
    return sorted(f[:-4] for f in os.listdir(HERE) if f.endswith(".yml"))


def _text(name: str) -> str:
    if name not in names():
        raise Refused(f"no OpenFlow template is named {name!r}: {', '.join(names())}")
    with open(os.path.join(HERE, f"{name}.yml"), encoding="utf-8") as fh:
        return fh.read()


def sha256(name: str) -> str:
    """The template file's SHA-256: what a confirmation is bound to."""
    return hashlib.sha256(_text(name).encode("utf-8")).hexdigest()


def load(name: str) -> dict:
    import yaml
    doc = yaml.safe_load(_text(name)) or {}
    doc.setdefault("lines", [])
    doc.setdefault("citations", {})
    return doc


def for_driver(driver: str):
    """The template for netmiko *driver*, or None."""
    for n in names():
        if driver in (load(n).get("drivers") or []):
            return n
    return None


def problems(t: dict) -> list:
    """What is wrong with template *t*: a line with no citation, a citation key it does not
    define, a citation missing a field, an unknown form."""
    out = []
    if t.get("form") not in FORMS:
        out.append(f"its form {t.get('form')!r} is not one of {', '.join(FORMS)}")
    cites = t.get("citations") or {}
    for i, line in enumerate(t.get("lines") or [], 1):
        keys = line.get("cite") or []
        if not keys:
            out.append(f"line {i} ({line.get('text', '')!r}) cites no vendor document")
        for k in keys:
            if k not in cites:
                out.append(f"line {i} cites {k!r}, which the template does not define")
    for k, c in sorted(cites.items()):
        missing = [f for f in CITATION_FIELDS if not str((c or {}).get(f) or "").strip()]
        if missing:
            out.append(f"citation {k!r} names no {', '.join(missing)}")
        if not isinstance((c or {}).get("verified"), bool):
            out.append(f"citation {k!r} does not say whether it was verified on the vendor's page")
    if t.get("support") == "unknown" and not t.get("support_why"):
        out.append("its support is unknown and it does not say why")
    return out


def citation_count(name: str) -> dict:
    """``{"lines", "cited", "citations", "verified"}`` for the report and the manual."""
    t = load(name)
    cites = t.get("citations") or {}
    return {"lines": len(t["lines"]), "cited": sum(1 for x in t["lines"] if x.get("cite")),
            "citations": len(cites), "verified": sum(1 for c in cites.values()
                                                     if (c or {}).get("verified") is True)}


# --------------------------------------------------------------------------- rendering

def derived(values: dict) -> dict:
    """*values* with the family-specific words the templates use, each from one NetBox value:
    the controller's host in an OVS target (an IPv6 address in brackets), OVSDB's protocol
    name, ArubaOS-Switch's version and fail-mode words, Comware's address family keyword, and
    the controller's id on the switch (Mercury configures one controller: 1)."""
    import ipaddress
    v = dict(values or {})
    addr = v.get("controller.address")
    if addr:
        six = ipaddress.ip_address(addr).version == 6
        v["controller.host"] = f"[{addr}]" if six else addr
        v["controller.family"] = "ipv6" if six else "ipv4"
        v["comware.family"] = "ipv6" if six else "ip"
    v.setdefault("controller.id", "1")
    version = v.get("openflow.version")
    if version in ("1.0", "1.3"):
        v["openflow.ovs_protocol"] = {"1.0": "OpenFlow10", "1.3": "OpenFlow13"}[version]
        v["aos_s.version"] = {"1.0": "1.0", "1.3": "1.3 only"}[version]
    mode = v.get("openflow.fail_mode")
    if mode in ("secure", "standalone"):
        v["aos_s.fail_mode"] = f"fail-{mode}"
    return v


def _lookup(values: dict, key: str):
    return values.get(key)


def render(name: str, values: dict) -> dict:
    """Template *name* with *values*: ``{"ok", "lines": [{"text", "cite"}], "program", "error",
    "missing"}``. ``program`` is what would be sent: for ``ovs-vsctl`` one invocation, the lines
    joined by ``" -- "`` after ``sudo -n ovs-vsctl``; for ``cli`` the lines. Sends nothing."""
    from modules.sdn import openflow_values
    t = load(name)
    out = {"ok": False, "name": name, "family": t.get("family", ""), "form": t.get("form"),
           "lines": [], "program": [], "error": "", "missing": [],
           # Each management interface left out of the OpenFlow ports, by name and why
           # (`openflow_values.management_reason`): said, never silent.
           "excluded": list((values or {}).get("excluded") or [])}
    bad = problems(t)
    if bad:
        out["error"] = f"the {name} template is refused: " + "; ".join(bad)
        return out
    if t.get("support") == "unknown":
        out["error"] = (f"{t.get('family')}'s OpenFlow support is UNKNOWN: {t['support_why']}. "
                        "Nothing is rendered.")
        return out
    v = derived(values)
    why = _supports(t, v)
    if why:
        out["error"] = why
        return out
    lines, missing = [], []
    for line in t["lines"]:
        if line.get("when") and not _lookup(v, line["when"]):
            continue
        items = [None]
        if line.get("each"):
            items = list(v.get(line["each"]) or [])
            if not items:
                missing.append(line["each"])
                continue
        for item in items:
            text = line["text"]
            for key in _PLACE.findall(text):
                got = item if key == "port" else _lookup(v, key)
                if got in (None, "", []):
                    missing.append(key)
                    continue
                text = text.replace("{" + key + "}", str(got))
            lines.append({"text": text, "cite": list(line["cite"])})
    if missing:
        names_ = sorted(set(missing))
        out["missing"] = names_
        out["error"] = "the render is refused: " + "; ".join(
            f"{k} is not given ({openflow_values.WHERE.get(k, 'derived from another value')})"
            for k in names_)
        return out
    out["lines"] = lines
    if t["form"] == "ovs-vsctl":
        from modules.sdn import ovs
        out["program"] = [" ".join(ovs.SUDO_VSCTL) + " " + " -- ".join(x["text"] for x in lines)]
    else:
        out["program"] = [x["text"] for x in lines]
    out["ok"] = True
    return out


def _supports(t: dict, v: dict) -> str:
    """Why the template cannot carry these values (both operands named), or ``""``."""
    import ipaddress
    family = t.get("family")
    version, transport = v.get("openflow.version"), v.get("openflow.transport")
    if version and version not in (t.get("versions") or []):
        return (f"{family} supports OpenFlow {', '.join(t.get('versions') or []) or 'none'} by "
                f"its vendor's document, and NetBox gives version {version}: nothing is rendered")
    if transport and transport not in (t.get("transports") or []):
        return (f"the {t['name']} template renders transport "
                f"{', '.join(t.get('transports') or []) or 'none'}, and NetBox gives {transport}: "
                "nothing is rendered")
    addr = v.get("controller.address")
    if addr and ipaddress.ip_address(addr).version == 6 and not t.get("ipv6_controller"):
        return (f"{family}'s controller address is IPv4 in its vendor's document (an IPv6 "
                f"controller is not documented), and NetBox gives {addr}: nothing is rendered")
    shape = t.get("instance_shape")
    inst = str(v.get("openflow.instance") or "")
    if shape == "number" and inst and not re.fullmatch(r"[0-9]{1,4}", inst):
        return (f"{family}'s OpenFlow instance is a number, and NetBox gives {inst!r}: nothing "
                "is rendered")
    return ""


# --------------------------------------------------------------------------- draft or confirmed

def _repo(network: str) -> str:
    from modules.nsot import listref
    return listref.resolve(network).repo_dir


def confirmation(network: str, name: str):
    """*network*'s committed confirmation of template *name* (read at HEAD), or None."""
    import yaml
    from modules.nsot.repo import git
    rc, text, _err = git(_repo(network), "show", f"HEAD:{DIR}/{name}.yml")
    if rc != 0:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def status(network: str, name: str) -> dict:
    """``{"status", "capture", "why"}``: ``confirmed`` only when *network* holds a confirmation
    bound to this template's current SHA-256; else ``draft``, saying why."""
    sha = sha256(name)
    c = confirmation(network, name)
    if c is None:
        return {"status": DRAFT, "capture": "", "why": f"{network} has not confirmed it"}
    if c.get("template_sha256") != sha:
        return {"status": DRAFT, "capture": c.get("capture", ""),
                "why": (f"it was confirmed at {str(c.get('template_sha256'))[:12]}, and the "
                        f"template is now {sha[:12]}: confirm it again")}
    return {"status": CONFIRMED, "capture": c.get("capture", ""), "why": "",
            "by": c.get("actor", ""), "at": c.get("at", "")}


def push_refusal(network: str, name: str) -> str:
    """``""`` only when template *name* is CONFIRMED on *network*; otherwise why nothing of it
    may be sent, naming the template and its status. Every path that sends a template's lines
    asks this first."""
    s = status(network, name)
    if s["status"] == CONFIRMED:
        return ""
    return (f"REFUSED: the {name} OpenFlow template is {s['status']} on {network} ({s['why']}), "
            "and only a confirmed template is ever sent: confirm it against a saved capture "
            "of one of its devices first. Nothing was sent.")


def confirm(network: str, name: str, capture_name: str, actor: str, actor_verified: str) -> dict:
    """A verified person confirms template *name* on *network* against *capture_name* (one of
    `discovery.captures`, of a device whose driver the template is for): committed as that
    person. ``{"ok", "error", "path", "commit"}``."""
    import time
    import yaml
    from modules import discovery
    from modules.nsot import repo as R

    if not actor or not actor_verified:
        return {"ok": False, "error": "a template is confirmed by a verified person"}
    t = load(name)
    cap = discovery.capture(network, capture_name)
    if cap is None:
        return {"ok": False, "error": f"{network} holds no capture named {capture_name!r}"}
    if cap["driver"] not in (t.get("drivers") or []):
        return {"ok": False, "error": (f"the capture {capture_name!r} was read with "
                                       f"{cap['driver']}, and the {name} template is for "
                                       f"{', '.join(t.get('drivers') or [])}")}
    if cap.get("archived"):
        return {"ok": False, "error": f"the capture {capture_name!r} is archived: read it again"}
    rel = f"{DIR}/{name}.yml"
    doc = {"template": name, "template_sha256": sha256(name), "capture": capture_name,
           "capture_sha256": cap.get("sha256", ""), "device": cap["device"],
           "actor": actor, "actor_verified": actor_verified,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    repo = _repo(network)
    from modules.filestore import write_atomic
    with R.repo_lock(repo):
        os.makedirs(os.path.join(repo, DIR), exist_ok=True)
        write_atomic(os.path.join(repo, rel), yaml.safe_dump(doc, sort_keys=False))
        got = R._commit_paths(network, [rel],                                  # noqa: SLF001
                              f"OpenFlow template confirmed: {name} against {capture_name}",
                              [f"Actor: {actor}", f"Actor-Verified: {actor_verified}"],
                              "openflow-template")
    if not got.get("ok"):
        return {"ok": False, "error": f"the confirmation's commit failed: {got.get('error')}",
                "path": rel}
    return {"ok": True, "error": "", "path": rel, "commit": got.get("commit", "")}
