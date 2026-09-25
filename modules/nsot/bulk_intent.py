"""One structured change to N devices' committed intent, as ONE commit.

NSOT_PLAN.md **P.1b**. Batch *deploy* existed; batch *intent* did not, so the
same edit was typed into N host_vars files as N commits, and the only thing
that could catch one being typed differently was a render diff that "looked
wrong on one device".

**A change is a list of compare-and-set steps over schema paths, never text.**
Each step is ``(path, before, after)``: the value the path must hold now, and
the value it becomes. A path the change does not name is not touched, so
``logging.console`` existing on the switches and not on r2 is irrelevant
rather than a reason to refuse. Paths use the same keying as "Revert intent"
(``hostvars._walk``): dict keys, and list items that carry a ``name`` keyed by
that name.

**Refused per device, both operands named, never applied around:**

* a before-state that does not match -- the interesting case: a device whose
  intent has drifted from the others', which the same edit applied blindly
  would leave different in a way nobody notices;
* an after-state an authoring gate refuses (the syslog block whole-or-absent,
  unknown interface keys, printable, no secret values) or that will not
  RENDER against the device's template;
* a file that would be reformatted: the write goes through ``to_yaml``, so a
  hand-edited file's comments or layout would be lost silently;
* no committed intent, or a device that is pending or not in the inventory.

A path the schema does not know refuses the whole OPERATION, before any
device is read: that is a typo in the change, not a fact about a device.

**The preview groups devices by rendered effect.** Devices whose render
changes by exactly the same lines form one group. The headline is
``"7 device(s), 1 group"``: a claim checkable at a glance, and a second group
is a divergence made structural rather than spotted.

**Apply is one-shot.** It recomputes the preview and refuses unless its hash
-- every accepted device's current file blob and resulting text, and the set
refused -- equals the one the operator saw. Then one commit names the devices.
"""

import copy
import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

ABSENT = {"__absent__": True}

#: Second-level keys under a top-level key, where the schema defines them.
#: A top-level key not listed here is checked at the top level only; the
#: per-device before-state comparison still protects everything beneath.
KNOWN_CHILDREN = {
    "logging": {"console", "settings", "hosts", "syslog"},
    "snmp": {"communities", "settings", "hosts"},
    "routing": {"ospf", "ospfv3", "ripng", "rip", "bgp"},
}


def _is_absent(value) -> bool:
    return isinstance(value, dict) and value.get("__absent__") is True


def known_top_level() -> set:
    from modules.nsot.parsers.base import BaseParser

    base = {"hostname", "platform", "interfaces", "vlans", "users", "routing",
            "static_routes", "acls", "snmp", "logging", "ntp_servers",
            "lines", "tracks", "services", "flags", "spanning_tree",
            "unmodeled", "secret_refs", "unmodeled_ack", "bootstrap"}
    return base | set(BaseParser.SCHEMA_DEFAULTS)


def unknown_paths(steps: list) -> list:
    """Paths no schema knows. A typo in the change refuses the change."""
    from modules.nsot.parsers.base import BaseParser

    top = known_top_level()
    bad = []
    for step in steps:
        path = step["path"]
        if not path or path[0] not in top:
            bad.append(path)
        elif path[0] in KNOWN_CHILDREN and len(path) > 1 \
                and path[1] not in KNOWN_CHILDREN[path[0]]:
            bad.append(path)
        elif path[0] == "interfaces" and len(path) > 2 \
                and path[2] not in BaseParser.INTERFACE_DEFAULTS \
                and path[2] != "name":
            bad.append(path)
    return bad


def get_path(doc, path):
    node = doc
    for key in path:
        if isinstance(node, dict):
            if key not in node:
                return ABSENT
            node = node[key]
        elif isinstance(node, list):
            node = next((i for i in node
                         if isinstance(i, dict) and i.get("name") == key),
                        ABSENT)
            if _is_absent(node):
                return ABSENT
        else:
            return ABSENT
    return node


def set_path(doc, path, value) -> bool:
    """Set (or, for ABSENT, delete) *path*. Creates missing DICT levels; never
    invents a named list item, which would be a new interface nobody wrote."""
    node = doc
    for key in path[:-1]:
        if isinstance(node, dict):
            node = node.setdefault(key, {})
        elif isinstance(node, list):
            node = next((i for i in node
                         if isinstance(i, dict) and i.get("name") == key), None)
            if node is None:
                return False
        else:
            return False
    leaf = path[-1]
    if not isinstance(node, dict):
        return False
    if _is_absent(value):
        node.pop(leaf, None)
    else:
        node[leaf] = value
    return True


def _norm(value):
    """Canonical JSON for comparison, so key order never decides equality."""
    return json.dumps(value, sort_keys=True)


def _blob(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _render_delta(before: str, after: str) -> dict:
    b, a = before.splitlines(), after.splitlines()
    return {"added": [l for l in a if l not in set(b)],
            "removed": [l for l in b if l not in set(a)]}


def plan(repo: str, devices: list, steps: list, *, render, eligible=None,
         summary: str = "") -> dict:
    """The preview. Reads, computes and writes NOTHING.

    *render(hostname, host_vars) -> (rendered_masked, deployable, reasons)*
    is supplied by the caller (the route uses the same artifact the editor
    and the deploy path use). *eligible(hostname) -> reason or ""* refuses
    pending or stale devices.
    """
    from modules.nsot import hostvars

    report = {"ok": True, "summary": summary, "steps": steps,
              "accepted": [], "refused": [], "groups": [], "headline": ""}
    bad = unknown_paths(steps)
    if bad:
        report.update(ok=False, error=(
            "the change names path(s) the schema does not know: "
            + ", ".join(".".join(map(str, p)) for p in bad)
            + " -- refused before any device was read"))
        return report
    if not steps:
        report.update(ok=False, error="the change has no steps")
        return report

    groups = {}
    for host in sorted(set(devices)):
        def refuse(reason, **extra):
            report["refused"].append({"device": host, "reason": reason, **extra})

        why = eligible(host) if eligible else ""
        if why:
            refuse(why)
            continue
        path = hostvars.committed_path(repo, host)
        if not os.path.exists(path):
            refuse("no committed intent -- commit an extraction first")
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        doc = hostvars.from_yaml(text)
        if not isinstance(doc, dict):
            refuse("committed intent is not a YAML mapping")
            continue
        # EVERY reason at once, not the first: a device refused for its
        # formatting also has its before-state reported, or fixing one
        # reveals the next only on the following run. (Measured: r6 was
        # refused as hand-formatted and its empty logging went unreported.)
        reasons = []
        if hostvars.to_yaml(doc) != text:
            reasons.append("the file is hand-formatted (it does not round-trip "
                           "through to_yaml): writing it would silently drop "
                           "its comments or layout -- edit it in the editor")

        mismatched = []
        for step in steps:
            have = get_path(doc, step["path"])
            if _norm(have) != _norm(step["before"]):
                mismatched.append({
                    "path": ".".join(map(str, step["path"])),
                    "expected": step["before"], "has": have})
        if mismatched:
            reasons.append("its current intent is not what the change expects")
        if reasons:
            refuse("; ".join(reasons), mismatched=mismatched)
            continue

        after = copy.deepcopy(doc)
        unset = [".".join(map(str, s["path"])) for s in steps
                 if not set_path(after, s["path"], s["after"])]
        if unset:
            refuse("the change could not be applied at " + ", ".join(unset))
            continue
        new_text = hostvars.to_yaml(after)

        gate = hostvars.syslog_block_problems(after)
        gate += [f"unknown interface key {k!r} (interfaces[{i}])"
                 for i, k in hostvars.unknown_interface_keys(after)]
        try:
            hostvars.assert_printable(new_text, host)
            hostvars.assert_no_secret_values(new_text, host)
        except ValueError as exc:
            gate.append(str(exc))
        if gate:
            refuse("the result would be refused: " + "; ".join(gate))
            continue

        try:
            before_render, _d, _r = render(host, doc)
            after_render, deployable, reasons = render(host, after)
        except Exception as exc:               # noqa: BLE001
            refuse(f"the result does not render: {type(exc).__name__}: {exc}")
            continue

        delta = _render_delta(before_render, after_render)
        key = _norm(delta)
        groups.setdefault(key, {"delta": delta, "devices": []})["devices"].append(host)
        report["accepted"].append({
            "device": host, "blob": _blob(text), "text": new_text,
            "deployable": deployable, "blocking_reasons": list(reasons),
            "render_delta": delta})

    report["groups"] = sorted(
        ({"devices": g["devices"], **g["delta"]} for g in groups.values()),
        key=lambda g: (-len(g["devices"]), g["devices"]))
    n, k = len(report["accepted"]), len(report["groups"])
    report["headline"] = (
        f"{n} device(s), {k} group(s)"
        + (f", {len(report['refused'])} refused" if report["refused"] else ""))
    report["hash"] = _plan_hash(report)
    return report


def _plan_hash(report: dict) -> str:
    material = {"accepted": [(a["device"], a["blob"], a["text"])
                             for a in report["accepted"]],
                "refused": sorted(r["device"] for r in report["refused"]),
                "steps": report["steps"]}
    return hashlib.sha256(_norm(material).encode()).hexdigest()[:16]


def apply(list_name: str, repo: str, devices: list, steps: list,
          confirmed_hash: str, *, render, eligible=None, summary: str,
          actor: str) -> dict:
    """Recompute, compare with what the operator saw, write, ONE commit."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    if not (summary or "").strip():
        return {"ok": False, "error": "a one-line summary is required -- it "
                                      "becomes the commit subject"}
    report = plan(repo, devices, steps, render=render, eligible=eligible,
                  summary=summary)
    if not report["ok"]:
        return report
    if report["hash"] != confirmed_hash:
        return {"ok": False, "error": (
            "the intent changed since you previewed "
            f"({confirmed_hash} -> {report['hash']}). Nothing was written. "
            "Re-run the preview and confirm what it shows now."),
            "confirmed_hash": confirmed_hash, "current_hash": report["hash"]}
    if not report["accepted"]:
        return {"ok": False, "error": "no device accepted the change",
                "refused": report["refused"]}

    # The commit stages host_vars/ as a whole, so an uncommitted edit already
    # sitting there would ride into this commit under this change's name.
    from modules.nsot.repo import git
    rc, dirty, _err = git(repo, "status", "--porcelain", "--", "host_vars")
    if rc != 0 or dirty.strip():
        return {"ok": False, "error": (
            "host_vars/ has uncommitted changes, which this commit would "
            "carry under its own name: " + (dirty.strip() or "status failed")
            + ". Commit or discard them first.")}

    written = []
    for entry in report["accepted"]:
        hostvars.write_committed_text(repo, entry["device"], entry["text"])
        written.append(entry["device"])
    refused = sorted(r["device"] for r in report["refused"])
    message = (f"host_vars: {summary.strip()} ({len(written)} device(s), "
               f"{len(report['groups'])} group(s))")
    trailers = [f"Operation: {_norm(steps)[:500]}"]
    if refused:
        trailers.append(f"Refused: {','.join(refused)}")
    result = save_host_vars(list_name, written, actor=actor, message=message,
                            source="bulk-intent", extra_trailers=trailers)
    return {"ok": result.get("ok", False), "commit": result.get("commit", ""),
            "error": result.get("error", ""), "devices": written,
            "refused": refused, "headline": report["headline"]}
