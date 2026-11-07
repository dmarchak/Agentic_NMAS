"""Controller conformance against the switches' platform profiles (the SDN platform design revision
6, section 10 H, "Controller conformance against D"; T17; C2593, C2598).

**What the controller offers.** Ryu offers the INTERSECTION of its loaded apps' OpenFlow versions
(C2593, measured in Ryu 4.34's `app_manager`), and its hello carries the highest of them. The
loaded apps are the enabled set plus Ryu's own `ofctl_rest` and `rest_topology`, which speak 1.0
to 1.5 (`BUILTIN_VERSIONS`), so they narrow nothing: an enabled set that pins no version offers
1.5, which is what refused the Aristas (C2598).

**The check, per expected switch** (`check`), against the profile entry covering its OS version
(`modules/platforms/profile.select`):
- the offered versions intersect the entry's `openflow.versions` (a common version to
  negotiate);
- the highest offered version is not above the entry's `openflow.hello.rejects_above`, when the
  entry names one (a switch that refuses a newer hello never answers).

A switch no profile covers is "can't tell" and refuses the deploy: a check Mercury cannot decide
is never drawn as a pass. Each refusal names the switch, its profile and entry, and both sides
of the comparison. Nothing here reads a device; the caller supplies each switch's selection.
"""

from modules.platforms.profile import OPENFLOW_VERSIONS

#: The OpenFlow versions Ryu's own apps speak (`ofctl_rest`, `topology/switches`: 1.0 to 1.5,
#: C2593's measurement of Ryu 4.34's source).
BUILTIN_VERSIONS = OPENFLOW_VERSIONS


def _key(version: str) -> tuple:
    return tuple(int(p) for p in version.split("."))


def offered(manifests) -> list:
    """The versions the controller offers with *manifests* (each an app's `Manifest`) loaded,
    in order: the intersection of theirs and the built-ins'."""
    out = set(BUILTIN_VERSIONS)
    for m in manifests:
        out &= set(m.openflow_versions)
    return sorted(out, key=_key)


def _apps_words(manifests) -> str:
    if not manifests:
        return "no managed app (Ryu's own apps alone)"
    return ", ".join(f"{m.name} {m.version} ({', '.join(m.openflow_versions)})"
                     for m in manifests)


def check(manifests, switches) -> dict:
    """``{"ok", "offered", "problems": [...], "checked": [...]}`` for the enabled *manifests*
    against *switches*, each ``{"name", "selected"}`` where *selected* is
    `profile.select(driver, version_text)`'s answer for that switch."""
    manifests = list(manifests)
    versions = offered(manifests)
    problems, checked = [], []
    if not versions:
        problems.append(f"the enabled apps share no OpenFlow version ({_apps_words(manifests)}),"
                        " so the controller offers none and no switch can connect")
    for sw in switches:
        name = sw.get("name") or "?"
        sel = sw.get("selected") or {}
        if not sel.get("ok"):
            problems.append(f"can't tell whether {name} can connect: "
                            f"{sel.get('error') or 'no platform profile was selected for it'}")
            continue
        entry = sel["entry"]
        theirs = list(entry["openflow"]["versions"])
        above = (entry["openflow"].get("hello") or {}).get("rejects_above")
        where = f"{name} ({sel.get('family')}, profile {sel.get('profile')} {entry.get('os')})"
        common = sorted(set(versions) & set(theirs), key=_key)
        if versions and not common:
            problems.append(f"{where} offers {', '.join(theirs)} and the controller offers "
                            f"{', '.join(versions)} ({_apps_words(manifests)}): no common "
                            "version")
        if versions and above is not None and _key(versions[-1]) > _key(above):
            problems.append(f"{where} refuses a hello above {above}, and the controller's hello "
                            f"is {versions[-1]} (it offers {', '.join(versions)}: "
                            f"{_apps_words(manifests)}); pin the set at or below {above}")
        checked.append({"switch": name, "common": common, "rejects_above": above})
    return {"ok": not problems, "offered": versions, "problems": problems, "checked": checked}
