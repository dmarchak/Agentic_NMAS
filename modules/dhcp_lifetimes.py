"""DHCP lease lifetimes by kind of address (E19, docs/DHCP_LIFETIMES_PROPOSAL.md; the operator's
decisions, 2026-10-13: "pool 4 h, reserved 7 days ..., management 7 days; T1/T2 at 50%/80%.
Build it.").

Three kinds, three places Kea holds them:

- **A pool address** takes Kea's GLOBAL lifetime, which every subnet inherits (no subnet in
  Mercury's files sets its own, measured 2026-10-13): 4 hours, IPv6 preferred 2 hours.
- **A reserved address** takes the class ``mercury-reserved`` (test ``member('KNOWN')``: the
  client has a reservation): 7 days, IPv6 preferred 3.5 days. Kea's classes are global and a
  class's lifetime beats every subnet's (measured on Kea 2.4.1 for the discovery classes,
  dhcp_discovery), so one class covers every reserved client in every subnet with nothing added
  to each reservation. The discovery classes test ``not member('KNOWN')``, so the two never meet.
- **The management segment** (the ZTP subnet, where a device's path to Mercury is): every
  client there takes a class's lifetime, so its 7 days need no edit of the subnet (which is
  onboarding's, and Subnets › Edit refuses it): a reserved device `mercury-reserved`'s 7 days,
  an unreserved one discovery's 300 s, since its only pools are the discovery classes'
  (measured 2026-10-13; the step's verify refuses a pool there that serves any client). A lapse
  there cuts Mercury off the device, so a week rides out a Kea outage.

Renew and rebind are Kea's to compute, 50% and 80% of each lease's own lifetime
(``calculate-tee-times``; IPv6 from the preferred lifetime): fixed timers would send a 7-day
reserved lease back at the pool's 2 hours. So the global fixed timers go.

Kea's main files are root's. The one-time host step `scripts/host-steps/e19-dhcp-lifetimes.sh`
installs the candidate this module builds: the global lifetime and timers changed in place, and
``client-classes`` moved into Mercury's own file (``nmas/classes4.json``, ``classes6.json``)
through an include, as the subnets were (C529), the discovery classes carried over unchanged.
"""

import json
import os
import re

from modules import dhcp_subnets as S

RESERVED = "mercury-reserved"
RESERVED_TEST = "member('KNOWN')"
DAY = 86400
RESERVED_VALID = 7 * DAY
POOL_VALID = 4 * 3600
#: IPv6's preferred lifetime: half the valid one, so a renumbering deprecates an address before
#: it ends; T1 and T2 are then computed from it (Kea's rule for IPv6).
PREFERRED_SHARE = 0.5
TEE = (("calculate-tee-times", "true"), ("t1-percent", str(S.T1_PERCENT)),
       ("t2-percent", str(S.T2_PERCENT)))
CLASS_FILES = {"IPv4": "classes4.json", "IPv6": "classes6.json"}
SUBNET_KEYS = {"IPv4": "subnet4", "IPv6": "subnet6"}
_NUMBER_LINE = re.compile(r'^[ \t]*"(?P<key>[a-z0-9-]+)"[ \t]*:[ \t]*(?P<value>[0-9.]+|true|false)'
                          r'[ \t]*(?P<comma>,?)[ \t]*$')


class Refused(Exception):
    pass


def classes_file(main: str, family: str) -> str:
    """Mercury's file holding every client class of *family*, beside its subnet file."""
    return os.path.join(os.path.dirname(main), "nmas", CLASS_FILES[family])


def reserved_class(family: str) -> dict:
    c = {"name": RESERVED, "test": RESERVED_TEST, "valid-lifetime": RESERVED_VALID}
    if family == "IPv6":
        c["preferred-lifetime"] = int(RESERVED_VALID * PREFERRED_SHARE)
    return c


def globals_wanted(family: str) -> dict:
    """The global keys this step sets, as Kea reports them (config-get)."""
    out = {"valid-lifetime": POOL_VALID, "calculate-tee-times": True,
           "t1-percent": S.T1_PERCENT, "t2-percent": S.T2_PERCENT}
    if family == "IPv6":
        out["preferred-lifetime"] = int(POOL_VALID * PREFERRED_SHARE)
    return out


def _line_of(text: str, at: int) -> tuple:
    """``(start, end)`` of the line holding index *at*, end after its newline."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    return start, (len(text) if end < 0 else end + 1)


def _number_line(text: str, key: str, main: str):
    """The one line setting *key* to a number or boolean: ``(start, end, match)`` or None when
    the key is absent. Refused when it is set more than once or not alone on its line."""
    hits = S._keys(text, key)                                                  # noqa: SLF001
    if not hits:
        return None
    if len(hits) > 1:
        raise Refused(f'"{key}" is set {len(hits)} times in {main} outside its subnets and '
                      "classes; expected once (the global value)")
    start, end = _line_of(text, hits[0][0])
    m = _NUMBER_LINE.match(text[start:end].rstrip("\r\n"))
    if not m:
        raise Refused(f'"{key}" in {main} is not alone on its line with a plain value '
                      f"({text[start:end].strip()[:60]!r})")
    return start, end, m


def _classes(text: str, main: str, family: str) -> tuple:
    """``(text without the class array, the classes file's list)``: an existing
    ``client-classes`` array is replaced by the include of Mercury's file and carried into it
    whole; with none, the include is added before the subnets' key. Already the include: the
    file's own content is read."""
    path = classes_file(main, family)
    include = f'<?include "{path}"?>'
    hits = S._keys(text, "client-classes")                                     # noqa: SLF001
    if len(hits) > 1:
        raise Refused(f'"client-classes" is found {len(hits)} times as a key in {main}')
    if hits:
        i = hits[0][1]
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if text.startswith(include, i):
            try:
                with open(path, encoding="utf-8") as fh:
                    return text, S.load(fh.read())
            except (OSError, S.Refused) as exc:
                raise Refused(f"{path}, which {main} includes, could not be read: {exc}") \
                    from None
        if not text.startswith("[", i):
            raise Refused(f'"client-classes" in {main} is not an array or the include of {path}')
        end = S._array_end(text, i)                                            # noqa: SLF001
        try:
            have = S.load(text[i:end + 1])
        except S.Refused as exc:
            raise Refused(f"the client classes in {main} could not be read: {exc}") from None
        return text[:i] + include + text[end + 1:], have
    key = SUBNET_KEYS[family]
    found = S._keys(text, key)                                                 # noqa: SLF001
    if len(found) != 1:
        raise Refused(f'"{key}" is found {len(found)} times as a key in {main}; expected once')
    start, _end = _line_of(text, found[0][0])
    indent = text[start:found[0][0]]
    if indent.strip():
        raise Refused(f'"{key}" in {main} does not start its own line')
    return text[:start] + f'{indent}"client-classes": {include},\n' + text[start:], []


def plan(main_text: str, main: str, family: str) -> dict:
    """The change to one family's main file: ``{"state": "change"|"done"|"refused",
    "refused", "candidate", "classes", "classes_file", "changes"}``. *candidate* is the main
    file to install, *classes* the classes file's list (the classes Kea runs now, any
    ``mercury-reserved`` replaced by the wanted one). A read: nothing is written."""
    out = {"state": "refused", "refused": "", "candidate": main_text, "classes": [],
           "classes_file": classes_file(main, family), "changes": []}
    try:
        text, have = _classes(main_text, main, family)
        if text != main_text:
            out["changes"].append(f"client-classes: moved to {out['classes_file']}")
        want_class = reserved_class(family)
        others = [c for c in have if not (isinstance(c, dict) and c.get("name") == RESERVED)]
        classes = others + [want_class]
        if classes != have:
            out["changes"].append(f"class {RESERVED}: {json.dumps(want_class)}")
        for key in ("renew-timer", "rebind-timer"):
            hit = _number_line(text, key, main)
            if hit:
                start, end, m = hit
                if not m.group("comma"):
                    raise Refused(f'"{key}" in {main} ends its map (no comma after it): '
                                  "removing it would leave the line before with a trailing "
                                  "comma")
                text = text[:start] + text[end:]
                out["changes"].append(f"{key}: removed (Kea computes it)")
        wanted = [(k, str(v).lower() if isinstance(v, bool) else str(v))
                  for k, v in globals_wanted(family).items()]
        if not _number_line(text, "valid-lifetime", main):
            raise Refused(f'{main} sets no global "valid-lifetime" to change')
        added = []
        for key, value in wanted:
            hit = _number_line(text, key, main)
            if hit:
                start, end, m = hit
                if m.group("value") == value:
                    continue
                text = text[:start + m.start("value")] + value + text[start + m.end("value"):]
                out["changes"].append(f"{key}: {m.group('value')} -> {value}")
            else:
                added.append((key, value))
        if added:
            # One block after the global valid lifetime, in the order wanted.
            start, end, _m = _number_line(text, "valid-lifetime", main)
            indent = re.match(r"[ \t]*", text[start:end]).group(0)
            text = text[:end] + "".join(f'{indent}"{k}": {v},\n' for k, v in added) + text[end:]
            out["changes"] += [f"{k}: {v} (added)" for k, v in added]
    except (Refused, ValueError) as exc:
        out["refused"] = str(exc)
        return out
    out.update(candidate=text, classes=classes,
               state="change" if out["changes"] else "done")
    return out


def running(config: dict, family: str) -> dict:
    """``{"state": "on"|"partial", "missing": [words]}``: whether Kea RUNS the lifetimes,
    read from its configuration (config-get): the global lifetime and computed timers, no
    global fixed timer, and the reserved class with its lifetimes."""
    missing = []
    for key, value in globals_wanted(family).items():
        if config.get(key) != value:
            missing.append(f"{key} is {config.get(key)!r}, not {value!r}")
    for key in ("renew-timer", "rebind-timer"):
        if config.get(key) is not None:
            missing.append(f"a global {key} ({config.get(key)}) beats the computed one")
    want = reserved_class(family)
    got = next((c for c in config.get("client-classes") or []
                if isinstance(c, dict) and c.get("name") == RESERVED), None)
    if not got:
        missing.append(f"Kea runs no class {RESERVED}")
    elif any(got.get(k) != v for k, v in want.items()):
        missing.append(f"the class {RESERVED} is not {json.dumps(want)}")
    return {"state": "partial" if missing else "on", "missing": missing}
