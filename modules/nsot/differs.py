"""Why an Intent check that "differs" differs: P2's rules (docs/PHASE8_PLAN.md 15.9, card P2;
15.12: rules only this sprint, no AI step and no configuration leaving the host).

The Intent check (`intent_match`) compares a committed golden with the render of committed
intent and says "differs" with the lines. Some differences are not a configuration departure at
all, and the person had to work out why (C1646, C1649: a switch in VTP server mode keeps its
VLANs in vlan.dat and never prints them). Each differing line is classified here by rules, in
this order, the first that applies winning:

- ``certificate``: a line of the device's own self-signed trustpoint or certificate chain
  (``TP-self-signed-<digits>``, the opener `normalize.strip_self_signed_certs` drops; C302),
  which the device regenerates at boot;
- ``vtp_database``: a VLAN line (``vlan <N>`` and what is under it) that intent has and the
  golden lacks, on a switch whose VTP mode is server or client, so it keeps the VLAN in its
  VLAN database and its configuration never prints it;
- ``unmodelled``: a line the extractor does not model, carried verbatim either in intent's
  not-modelled list (``unmodeled`` or ``unmodeled_ack``) or only in the device's golden (its
  own parse's not-modelled list: a line on the device that intent does not carry at all); the
  class's words say which, line by line (C1812: they said "carried verbatim in intent" for a
  line intent does not carry);
- ``order_only``: a section holding the same lines in a different order (the comparison's
  ``reordered``: the same lines as a set);
- ``unexplained``: everything else.

A rule's class always wins: a line a rule classifies is never ``unexplained``, so it can never
reach a later step that labels only what no rule classifies (the card's success metric).

Pure: lines in, ``[{"class", "lines", "why"}]`` out, nothing read or written. A class is an
explanation, never a verdict: it does not turn "differs" into "matches" (a VLAN the golden
cannot show may still be absent from the switch's database; `show vlan id <N>` says).

Two classes are reached by the rules but not by today's Intent check, said so a reader does not
take their absence for a measurement: the comparison sets the device's self-signed blocks aside
on both sides before it compares (`normalize.strip_for_roundtrip`, C397), so ``certificate``
classifies only a difference made elsewhere; and the card's ``platform_default`` class is not a
rule here because the comparison already leaves those lines out of both sides
(`platform_defaults.strip`, C1401).
"""

import re

CERTIFICATE = "certificate"
VTP_DATABASE = "vtp_database"
UNMODELLED = "unmodelled"
ORDER_ONLY = "order_only"
UNEXPLAINED = "unexplained"

#: The classes in the order a reader is shown them; ``unexplained`` last.
CLASSES = (CERTIFICATE, VTP_DATABASE, UNMODELLED, ORDER_ONLY, UNEXPLAINED)

#: The VTP modes in which a switch keeps its VLANs in vlan.dat and does not print them (C1649,
#: measured: three switches in server mode printed no `vlan` line, two in transparent printed
#: theirs).
DATABASE_MODES = ("server", "client")

#: One VLAN, a list or a range, as a top-level line configures it: never `vlan internal
#: allocation policy ...`, `vlan dot1q tag native` or any other global `vlan` command.
VLAN_LINE = re.compile(r"vlan [1-9][0-9]{0,3}(?:\s*[,-]\s*[1-9][0-9]{0,3})*")

#: `show vtp status`'s mode line, and the same line in a capture's `! VTP:` header (measured,
#: tests/fixtures/console/vios_l2_*_show_vtp_status.txt and tests/fixtures/configs/fleet/).
_VTP_STATUS_MODE = re.compile(r"VTP Operating Mode\s*:\s*(\S+)", re.I)
#: A top-level `vtp mode` configuration line (a transparent switch prints one).
_VTP_MODE_LINE = re.compile(r"vtp mode (\S+)\s*$", re.I)

#: The few words each class is drawn in, beside its count.
SHORT = {
    CERTIFICATE: "the device's own self-signed certificate, regenerated at boot",
    VTP_DATABASE: "VLANs a VTP {mode} keeps in vlan.dat, never in its configuration",
    UNMODELLED: "lines Mercury does not model, carried verbatim in intent's not-modelled list",
    ORDER_ONLY: "the same lines in a different order",
    UNEXPLAINED: "not explained by a rule",
}

#: An ``unmodelled`` class whose lines are all carried only in the device's golden, and one
#: whose lines are carried in both places (C1812): where each line is carried, said.
UNMODELLED_GOLDEN = ("lines Mercury does not model, carried only in the device's golden: "
                     "intent does not carry them")
UNMODELLED_BOTH = ("lines Mercury does not model: {intent} carried verbatim in intent's "
                   "not-modelled list, {golden} only in the device's golden (intent does not "
                   "carry them)")

#: The Intent row's words when no rule explains any line of the departure (C1821, the
#: operator's words, Walk 3 2026-10-26): said, so it is told apart from a rule-explained one.
NO_RULE = "No rule explains this difference"

#: Where an ``unmodelled`` line is carried.
IN_INTENT = "intent"
IN_GOLDEN = "golden"


def vtp_mode(text) -> str:
    """The VTP mode *text* says, lower case (``server``, ``client``, ``transparent``, ``off``),
    or ``""`` when it says none. *text* is a `show vtp status` answer, or a configuration: its
    capture header's ``! VTP: VTP Operating Mode : <mode>`` line, else its top-level
    ``vtp mode <mode>`` line. A configuration printing neither says nothing: a switch in server
    or client mode prints no ``vtp mode`` line, and neither does a router, so its absence is
    never read as a mode."""
    lines = text if isinstance(text, list) else str(text or "").splitlines()
    for line in lines:
        m = _VTP_STATUS_MODE.search(line)
        if m:
            return m.group(1).lower()
    for line in lines:
        if line[:1].isspace():
            continue
        m = _VTP_MODE_LINE.match(line.strip())
        if m:
            return m.group(1).lower()
    return ""


def _norm(line: str) -> str:
    """A line as the comparison holds it (`roundtrip._norm`: interface names canonical,
    whitespace collapsed), so a not-modelled line matches the difference's own."""
    from modules.nsot import roundtrip
    return roundtrip._norm(line or "")


def unmodelled_of(*host_vars) -> set:
    """``{(top-level line, line)}``: every line each of *host_vars* carries verbatim because the
    extractor does not model it, keyed by the top-level line it sits under (a top-level line is
    its own key), normalised as the comparison normalises. A not-modelled block's header and
    each of its children; an interface's not-modelled lines under ``interface <name>``; and an
    acknowledged line at column 0 (`unmodeled_ack`), whose block an indented one does not name."""
    out = set()
    for hv in host_vars:
        hv = hv or {}
        for entry in hv.get("unmodeled") or []:
            head = _norm(entry.get("line", ""))
            out.add((head, head))
            out.update((head, _norm(c)) for c in entry.get("children") or [])
        for iface in hv.get("interfaces") or []:
            head = _norm(f"interface {iface.get('name', '')}")
            out.update((head, _norm(l)) for l in iface.get("unmodeled") or [])
        for line in ((hv.get("unmodeled_ack") or {}).get("lines") or []):
            if line[:1].isspace() or not line.strip():
                continue
            out.add((_norm(line), _norm(line)))
    return out


def _top(entry: dict) -> str:
    """The top-level line an entry of the difference sits under (itself at the top level)."""
    from modules.nsot.sections import PATH_SEPARATOR
    section = entry.get("section") or ""
    return section.split(PATH_SEPARATOR)[0] if section else entry.get("line", "")


def _self_signed(top: str) -> bool:
    """Is *top* the device's own self-signed trustpoint or chain opener? The one test
    `normalize.strip_self_signed_certs` applies: the line alone is dropped."""
    from modules.nsot import normalize
    return bool(top) and not normalize.strip_self_signed_certs([top])


def _order_significant(section: str) -> bool:
    from modules.nsot import roundtrip
    from modules.nsot.sections import PATH_SEPARATOR
    return any(rule.match(part) for part in section.split(PATH_SEPARATOR)
               for rule in roundtrip.ORDER_SIGNIFICANT_SECTIONS)


def _line_class(sign: str, entry: dict, mode: str, unmodelled: set, golden_unmodelled: set):
    """``(class, where)``: *where* is :data:`IN_INTENT` or :data:`IN_GOLDEN` for an
    ``unmodelled`` line (intent's not-modelled list first), ``""`` for every other class."""
    top = _top(entry)
    if _self_signed(top):
        return CERTIFICATE, ""
    if sign == "+" and mode in DATABASE_MODES and VLAN_LINE.fullmatch(top):
        return VTP_DATABASE, ""
    pair = (_norm(top), _norm(entry.get("line", "")))
    if pair in unmodelled:
        return UNMODELLED, IN_INTENT
    if pair in golden_unmodelled:
        return UNMODELLED, IN_GOLDEN
    return UNEXPLAINED, ""


def classify(difference: dict, vtp_mode: str = "", unmodelled=(),
             golden_unmodelled=()) -> list:
    """``[{"class", "lines", "why"}]``, one per class found, in :data:`CLASSES` order; the
    ``unmodelled`` class also carries ``carried``, ``{"intent": n, "golden": m}``: how many of
    its lines intent's not-modelled list carries and how many only the device's golden does.

    *difference* is the comparison's ``details`` (`roundtrip.compare`): ``extra`` (in intent,
    not in the golden: a ``+`` line), ``missing`` (in the golden, not in intent: ``-``) and
    ``reordered``, each entry with its ``section`` path and ``line``. *vtp_mode* is the switch's
    (:func:`vtp_mode`), ``""`` when not read; *unmodelled* is :func:`unmodelled_of`'s set of
    intent's, *golden_unmodelled* the same of the golden's own parse (a line only it carries is
    said as carried in the device's golden, never in intent: C1812).
    Each class's ``lines`` are signed as the Intent check signs them (``+ line``, ``- line``);
    ``order_only``'s are its sections. The lines are as the comparison holds them, unmasked:
    whoever draws them masks them on the way out, as every configuration line is."""
    difference = difference or {}
    mode = (vtp_mode or "").lower()
    unmodelled = set(unmodelled or ())
    golden_unmodelled = set(golden_unmodelled or ())
    found = {c: [] for c in CLASSES}
    carried = {IN_INTENT: 0, IN_GOLDEN: 0}
    vlans_unread = 0
    for sign, key in (("+", "extra"), ("-", "missing")):
        for entry in difference.get(key) or []:
            cls, where = _line_class(sign, entry, mode, unmodelled, golden_unmodelled)
            found[cls].append(f"{sign} {entry.get('line', '')}")
            if where:
                carried[where] += 1
            if cls == UNEXPLAINED and sign == "+" and not mode \
                    and VLAN_LINE.fullmatch(_top(entry)):
                vlans_unread += 1
    reordered = [r.get("section", "") for r in difference.get("reordered") or []]
    found[ORDER_ONLY] = reordered
    whys = {
        CERTIFICATE: ("the device's own self-signed trustpoint or certificate chain "
                      "(TP-self-signed-<digits>), which it makes again at every boot: its body "
                      "is the device's, never intent's (C302)"),
        VTP_DATABASE: (f"VLANs on a switch in VTP {mode} mode, which keeps them in its VLAN "
                       "database (vlan.dat) and never prints them in its configuration, so its "
                       "golden cannot hold them (C1646, C1649); whether the switch has each is "
                       "read with `show vlan id <N>`"),
        UNMODELLED: _unmodelled_why(carried),
        ORDER_ONLY: _order_why(reordered),
        UNEXPLAINED: ("no rule explains these lines: a departure until shown otherwise"
                      + (f"; {vlans_unread} of them are VLAN lines, and the switch's VTP mode "
                         "was not read (its golden carries no `VTP Operating Mode` or "
                         "`vtp mode` line), so whether it keeps them in vlan.dat is not known"
                         if vlans_unread else "")),
    }
    out = []
    for c in CLASSES:
        if found[c]:
            out.append({"class": c, "lines": found[c], "why": whys[c]})
            if c == UNMODELLED:
                out[-1]["carried"] = dict(carried)
    return out


def _unmodelled_why(carried: dict) -> str:
    """Where the not-modelled lines are carried, in the class's longer words (C1812)."""
    parts = []
    if carried.get(IN_INTENT):
        parts.append(f"{carried[IN_INTENT]} of them intent carries verbatim in its not-modelled "
                     "list (unmodeled), never rendered from a setting, so a change to one is "
                     "edited there")
    if carried.get(IN_GOLDEN):
        parts.append(f"{carried[IN_GOLDEN]} of them only the device's golden carries (its own "
                     "parse's not-modelled list): intent does not carry them at all, so each is "
                     "a line on the device that intent lacks, kept by adding it to intent's "
                     "not-modelled list (Edit intent) or removed in a Mode B plan")
    return "lines Mercury's extractor does not model: " + "; ".join(parts)


def _order_why(sections: list) -> str:
    if not sections:
        return ""
    significant = [s for s in sections if _order_significant(s)]
    why = (f"{len(sections)} section(s) hold the same lines as intent in a different order "
           "(the same lines as a set)")
    if significant:
        why += (f"; in {len(significant)} of them (an access list, prefix list, route map, "
                "class map, policy map or IP SLA) order decides what matches, so the order "
                "is a real change")
    return why


def explained(classes: list) -> bool:
    """Whether any rule classified a line (any class but ``unexplained``)."""
    return any(c["class"] != UNEXPLAINED for c in classes or [])


def words(classes: list, mode: str = "") -> str:
    """The classes in one short line for the Intent check's row: each class's count and its few
    words, the unexplained rest counted too, so a subset says it is one; and when no rule
    classified any line, :data:`NO_RULE`, said, so an unexplained departure is told apart from
    an explained one (C1821, the operator: it added no words). ``""`` only for no classes at
    all (a match, or a comparison not made)."""
    if not classes:
        return ""
    if not explained(classes):
        return NO_RULE
    parts = []
    for c in classes:
        n = len(c["lines"])
        unit = ("section" if c["class"] == ORDER_ONLY else "line") + ("" if n == 1 else "s")
        parts.append(f"{n} {unit}: {_short(c, mode)}")
    return "By rule: " + "; ".join(parts)


def _short(c: dict, mode: str) -> str:
    """A class's few words; a not-modelled class's name where its lines are carried (C1812)."""
    if c["class"] == UNMODELLED:
        carried = c.get("carried") or {IN_INTENT: len(c["lines"]), IN_GOLDEN: 0}
        if carried.get(IN_GOLDEN) and carried.get(IN_INTENT):
            return UNMODELLED_BOTH.format(intent=carried[IN_INTENT], golden=carried[IN_GOLDEN])
        if carried.get(IN_GOLDEN):
            return UNMODELLED_GOLDEN
    return SHORT[c["class"]].format(mode=f"{mode} switch" if mode else "switch")
