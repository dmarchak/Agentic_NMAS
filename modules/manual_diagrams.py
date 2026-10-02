"""The manual's diagrams, drawn from ONE key (NSOT_GUI_BRIEF 10b; the operator signed the
mockup off on 2026-10-02).

Every diagram in ``docs/manual/diagrams/`` is GENERATED here, never drawn by hand, so each
uses only the key's shapes and arrows (``KEY_CLASSES``) and follows the light or dark choice
through the stylesheet's ``dg-*`` rules. ``scripts/nmas-manual-diagrams`` writes the files;
``tests/test_manual.py`` holds each committed file equal to what this module draws, so a hand
edit is caught, and holds every How it works page to at least one diagram.

The key:
- a DEVICE (ports along its foot; dashed when not reached), INTENT (a green document), a
  GOLDEN (a gold document), any other document, the REPOSITORY (a cylinder), one of the
  tool's own RECORDS (a bar on its left), an INTEGRATION (a pill), a LAB INTEGRATION (dashed,
  tagged LAB), a PERSON confirming;
- arrows: SENT to a device (solid accent), READ from a device (dashed), copied into a RECORD
  (solid ink), a rollback's UNDO (dashed amber); a crossed circle marks "nothing is sent";
- numbered circles carry the step list's numbers.

Each diagram carries its description in words (``aria-label``), and the page's diagram line
says the same, so a reader without the picture loses nothing.
"""

import math
from html import escape as _e

#: Every class a diagram may use: the key, and nothing else.
KEY_CLASSES = frozenset((
    "dg-box", "dg-dev", "dg-devoff", "dg-intent", "dg-golden", "dg-repo", "dg-store", "dg-bar",
    "dg-svc", "dg-labf", "dg-labtag", "dg-labtx", "dg-band", "dg-lane", "dg-tx", "dg-tb",
    "dg-sm", "dg-hd", "dg-send", "dg-sendh", "dg-read", "dg-readh", "dg-rec", "dg-rech",
    "dg-undo", "dg-undoh", "dg-no", "dg-nol", "dg-num", "dg-numt", "dg-person", "dg-clock",
))
WIDTH = 400
MID = 212


def t(x, y, s, cls="tx", anchor="start"):
    return f'<text class="dg-{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{_e(s)}</text>'


def _label(x, y, w, h, title, sub, anchor="middle"):
    cx = x + w / 2 if anchor == "middle" else x + 10
    if sub:
        return t(cx, y + h / 2 - 2, title, "tb", anchor) + t(cx, y + h / 2 + 12, sub, "sm", anchor)
    return t(cx, y + h / 2 + 4, title, "tb", anchor)


def _docpath(x, y, w, h, f=10):
    return f"M{x},{y} H{x + w - f} L{x + w},{y + f} V{y + h} H{x} Z"


def doc(kind, x, y, w, h, title, sub=""):
    """A document: ``intent``, ``golden`` or ``box`` (any other document)."""
    c = f"dg-{kind}"
    return (f'<path class="{c}" d="{_docpath(x, y, w, h)}"/>'
            f'<path class="{c}" d="M{x + w - 10},{y} V{y + 10} H{x + w}"/>'
            + _label(x, y, w, h, title, sub))


def device(x, y, w, h, title, sub="", off=False, top=False):
    c = "dg-devoff" if off else "dg-dev"
    ports = "".join(f'<rect class="{c}" x="{x + 12 + i * 14}" y="{y + h - 1}" width="8" height="5"/>'
                    for i in range(3))
    if top:
        lab = t(x + w / 2, y + 18, title, "tb", "middle") + (
            t(x + w / 2, y + 32, sub, "sm", "middle") if sub else "")
    else:
        lab = _label(x, y, w, h, title, sub)
    return f'<rect class="{c}" x="{x}" y="{y}" width="{w}" height="{h}" rx="5"/>' + ports + lab


def repo(x, y, w, h, title, sub=""):
    ry = 6
    return (f'<path class="dg-repo" d="M{x},{y + ry} V{y + h - ry} A{w / 2},{ry} 0 0 0 '
            f'{x + w},{y + h - ry} V{y + ry}"/>'
            f'<ellipse class="dg-repo" cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}"/>'
            + _label(x, y + 7, w, h, title, sub))


def store(x, y, w, h, title, sub=""):
    return (f'<rect class="dg-store" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>'
            f'<rect class="dg-bar" x="{x}" y="{y}" width="4" height="{h}" rx="1"/>'
            + _label(x + 2, y, w, h, title, sub))


def labtag(x, y):
    return (f'<rect class="dg-labtag" x="{x}" y="{y}" width="28" height="13" rx="3"/>'
            + t(x + 14, y + 10, "LAB", "labtx", "middle"))


def svc(x, y, w, h, title, sub="", lab=False):
    c = "dg-labf" if lab else "dg-svc"
    return (f'<rect class="{c}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}"/>'
            + _label(x, y, w, h, title, sub) + (labtag(x + w - 30, y - 7) if lab else ""))


def labfile(x, y, w, h, title, sub=""):
    return (f'<path class="dg-labf" d="{_docpath(x, y, w, h)}"/>' + _label(x, y, w, h, title, sub)
            + labtag(x + w - 34, y - 7))


def num(x, y, n):
    return f'<circle class="dg-num" cx="{x}" cy="{y}" r="9"/>' + t(x, y + 3.6, str(n), "numt", "middle")


def _head(kind, x, y, ang):
    ln, wd = 8, 4.5
    pts = [(x, y),
           (x - ln * math.cos(ang) + wd * math.sin(ang), y - ln * math.sin(ang) - wd * math.cos(ang)),
           (x - ln * math.cos(ang) - wd * math.sin(ang), y - ln * math.sin(ang) + wd * math.cos(ang))]
    p = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    return f'<polygon class="dg-{kind}h" points="{p}"/>'


def arrow(kind, x1, y1, x2, y2, via=None):
    """``send`` (to a device), ``read`` (from one), ``rec`` (into a record), ``undo``."""
    if via:
        cx, cy = via
        ang = math.atan2(y2 - cy, x2 - cx)
    else:
        ang = math.atan2(y2 - y1, x2 - x1)
    sx, sy = x2 - 6 * math.cos(ang), y2 - 6 * math.sin(ang)
    d = (f"M{x1},{y1} Q{via[0]},{via[1]} {sx:.1f},{sy:.1f}" if via
         else f"M{x1},{y1} L{sx:.1f},{sy:.1f}")
    return f'<path class="dg-{kind}" d="{d}"/>' + _head(kind, x2, y2, ang)


def nosend(x, y, words=()):
    s = (f'<circle class="dg-no" cx="{x}" cy="{y}" r="11"/>'
         f'<line class="dg-nol" x1="{x - 7.5}" y1="{y + 7.5}" x2="{x + 7.5}" y2="{y - 7.5}"/>')
    for i, w in enumerate(words):
        s += t(x, y + 26 + i * 13, w, "sm", "middle")
    return s


def person(x, y, w, h, words):
    return (f'<rect class="dg-person" x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}"/>'
            f'<circle class="dg-person" cx="{x + 16}" cy="{y + h / 2 - 3}" r="4"/>'
            f'<path class="dg-person" d="M{x + 9},{y + h / 2 + 8} Q{x + 16},{y + h / 2 - 1} '
            f'{x + 23},{y + h / 2 + 8}"/>' + t(x + 32, y + h / 2 + 4, words))


def clock(x, y):
    return (f'<circle class="dg-clock" cx="{x}" cy="{y}" r="8"/>'
            f'<path class="dg-clock" d="M{x},{y - 5} V{y} L{x + 4},{y + 2}"/>')


def band(y, h, title, w=WIDTH):
    return (f'<rect class="dg-band" x="0" y="{y}" width="{w}" height="{h}" rx="6"/>'
            + t(30, y + 16, title.upper(), "hd"))


def lanes(y1, y2, left="IN THE TOOL", right="THE DEVICE", mid=MID):
    return (f'<line class="dg-lane" x1="{mid}" y1="{y1}" x2="{mid}" y2="{y2}"/>'
            + t(mid / 2, 12, left, "hd", "middle") + t(mid + (WIDTH - mid) / 2, 12, right, "hd", "middle"))


def rows(spec, dev_x=262):
    """Numbered rows in the tool's lane, each with its arrow to or from the device."""
    out = []
    for y, kind, n, title, sub in spec:
        if n is not None:
            out.append(num(22, y - 4, n))
        out.append(t(36, y, title, "tb"))
        if sub:
            out.append(t(36, y + 12, sub, "sm"))
        if kind in ("send", "undo"):
            out.append(arrow(kind, 202, y - 4, dev_x - 2, y - 4))
        elif kind == "read":
            out.append(arrow("read", dev_x - 2, y - 4, 202, y - 4))
        elif kind == "clock":
            out.append(clock(214, y - 4))
    return out


def svg(height, words, parts, width=WIDTH):
    """A standalone SVG file's text: the key's classes, its description in words."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{_e(words)}">' + "".join(parts) + "</svg>\n")


# ------------------------------------------------------------------ the diagrams

def deploy():
    return svg(600, (
        "A deploy. The plan sends nothing: committed intent is rendered through the approved "
        "template and compared with the device's golden, giving the program, the lines intent "
        "has and the golden lacks; you confirm its hash. The run holds the device: it checks "
        "the dangerous lines before any session, reads the device, sends the program "
        "merge-only, reads it again on a new session and verifies within each protocol's "
        "settle window. If verify fails it undoes what landed and reads it back. The golden is "
        "recorded as you, and a receipt whatever happened."), [
        lanes(20, 594),
        band(20, 212, "Before · the plan · nothing sent"),
        doc("intent", 14, 42, 58, 44, "Intent", "committed"),
        doc("box", 78, 42, 58, 44, "Template", "approved"),
        doc("golden", 142, 42, 58, 44, "Golden", "captured"),
        arrow("rec", 43, 87, 78, 124), arrow("rec", 107, 87, 107, 124), arrow("rec", 171, 87, 136, 124),
        '<rect class="dg-box" x="14" y="126" width="186" height="42" rx="4"/>',
        t(107, 144, "Program", "tb", "middle"), t(107, 158, "what intent has, the golden lacks", "sm", "middle"),
        person(14, 182, 186, 32, "You confirm its hash"),
        device(240, 56, 140, 48, "The device", "not contacted", off=True),
        nosend(310, 150, ("nothing is sent:", "stored records only")),
        band(238, 356, "The run · holding the device"),
        device(262, 262, 118, 222, "The device", "", top=True),
        *rows([
            (276, None, 3, "Dangerous lines", "checked before any session"),
            (310, "read", 4, "Read before", "config, neighbours, routes"),
            (342, "send", 6, "Send the program", "merge-only, as confirmed"),
            (374, "read", 7, "Read after", "on a new session"),
            (406, "clock", 8, "Verify", "OSPF 45 s, BGP 60 s, RIP 90 s"),
            (446, "undo", None, "If verify fails: undo", "what landed, then read back"),
        ]),
        doc("golden", 14, 506, 110, 42, "Golden", "recorded as you"), num(14, 506, 9),
        store(134, 506, 120, 42, "Receipt", "whatever happened"), num(134, 506, 10),
        t(14, 576, "Stages 1, 2 and 5 read records only and send nothing.", "sm"),
    ])


def onboard():
    return svg(612, (
        "Onboarding in two phases. Phase one, Create, sends nothing: it stages a bootstrap "
        "credential, commits the device as pending with its bootstrap intent, writes a Kea "
        "reservation for ZTP, and renders the bootstrap config. The device boots on that "
        "config. Phase two, Verify, holds the device: it signs in and reads its configuration, "
        "sends a new credential, the RW community's removal, the monitoring profile and a save, "
        "reads it again for its first golden, records it in NetBox and adds it to the inventory "
        "last."), [
        lanes(20, 606),
        band(20, 232, "Phase one · Create · nothing sent"),
        store(14, 46, 186, 34, "Credential store", "bootstrap credential, staged"), num(14, 46, 1),
        repo(14, 90, 186, 46, "Repository", "bootstrap intent · pending"), num(14, 96, 2),
        svc(14, 146, 186, 32, "Kea  (ZTP only)", "the reservation, tested first"), num(14, 146, 3),
        doc("box", 14, 188, 186, 40, "Bootstrap config", "rendered, with the credential"), num(14, 188, 4),
        device(240, 64, 140, 48, "The device", "not booted yet", off=True),
        nosend(310, 158, ("nothing is sent", "in phase one")),
        band(258, 74, "Between · the device boots"),
        arrow("rec", 200, 214, 240, 292, via=(226, 214)),
        device(240, 272, 140, 48, "The device", "boots on the bootstrap"),
        t(14, 290, "Static, DHCP: a person applies the file.", "sm"),
        t(14, 303, "ZTP: the tool's TFTP responder serves it.", "sm"),
        t(14, 320, "Pending: in git, not in the inventory.", "sm"),
        band(338, 268, "Phase two · Verify · holding the device"),
        device(262, 360, 118, 172, "The device", "one session", top=True),
        *rows([
            (380, "read", 1, "Sign in", "with the staged credential"),
            (408, "read", 2, "Capture", "held in memory, not recorded"),
            (436, "send", 3, "Rotate", "a credential the device hashes"),
            (462, "send", 4, "Remove RW community", ""),
            (484, "send", 5, "Monitoring profile", ""),
            (506, "send", 6, "Save", "then read startup back"),
            (534, "read", 7, "Read again", ""),
        ]),
        doc("golden", 14, 552, 88, 40, "Golden", "the first one"),
        svc(110, 555, 84, 34, "NetBox", ""), num(110, 555, 8),
        store(204, 552, 130, 40, "Inventory", "promoted, last"), num(204, 552, 9),
    ])


def _down(x, y1, y2):
    """A record arrow straight down the tool's lane."""
    return arrow("rec", x, y1, x, y2)


def revert_retry():
    return svg(560, (
        "The two ways out of a rollback. The rollback left a block against the device's "
        "intent, and the device unchanged. Revert says the change was wrong: it reads the "
        "intent history, computes intent with that one commit undone, you confirm its hash, it "
        "commits as you, then measures the block and lifts it only if the failed lines are "
        "gone. Retry says the change was right: you state a reason, it is recorded in the retry "
        "log, and the block is lifted. Neither sends anything; the next deploy does."), [
        lanes(20, 554),
        band(20, 96, "The rollback left"),
        doc("intent", 14, 46, 90, 40, "Intent", "at HEAD"),
        store(112, 46, 88, 40, "Block", "on the plan"),
        device(240, 44, 140, 44, "The device", "unchanged", off=True),
        band(122, 238, "Revert · the change was wrong"),
        repo(14, 148, 186, 44, "Intent history", "the commit to undo"), num(14, 154, 1),
        _down(107, 194, 214),
        doc("intent", 14, 216, 186, 40, "Intent after the revert", "later commits kept"), num(14, 216, 2),
        person(14, 266, 186, 30, "You confirm its hash"), num(14, 266, 3),
        _down(107, 298, 316),
        store(14, 318, 186, 34, "Commit, Source: revert", "block lifted only if gone"), num(14, 318, 4),
        nosend(310, 236, ("nothing is sent:", "intent only")),
        band(366, 160, "Retry · the change was right"),
        person(14, 392, 186, 30, "You state a reason"), num(14, 392, 1),
        _down(107, 424, 444),
        store(14, 446, 186, 36, "Retry log", "who, why, when"), num(14, 446, 2),
        t(14, 504, "The block is lifted; the program is unchanged.", "sm"),
        nosend(310, 440, ("nothing is sent:", "a record only")),
        t(14, 548, "Then plan and deploy: the device changes only there.", "sm"),
    ])


def bulk_intent():
    return svg(470, (
        "Editing intent in bulk sends nothing. A change file names each setting's path, its "
        "value before and after; each device's intent at HEAD is checked against the before "
        "value, and a device that differs is refused by name with both values. The rest are "
        "rendered before and after through the template and the monitoring profile and grouped "
        "by identical change; you confirm the preview's hash; one commit records every device "
        "changed, and names those refused."), [
        lanes(20, 464, mid=284, right="DEVICES"),
        band(20, 64, "The change"),
        doc("box", 14, 40, 256, 38, "Change file", "summary, then path · before · after"), num(14, 40, 1),
        band(90, 150, "Compare and set · per device"),
        repo(14, 112, 120, 40, "Repository", "intent at HEAD"),
        arrow("rec", 136, 132, 160, 132),
        doc("intent", 162, 112, 108, 40, "Intent", "before matches?"), num(162, 112, 2),
        t(14, 178, "Matches: rendered before and after,", "sm"),
        t(14, 191, "template and profile, then grouped by", "sm"),
        t(14, 204, "identical change. Differs: refused by", "sm"),
        t(14, 217, "name, with both values.", "sm"),
        band(246, 210, "Confirm and commit"),
        doc("box", 14, 270, 256, 40, "Preview", "groups · refused · one hash"), num(14, 270, 3),
        person(14, 322, 256, 30, "You confirm the summary and hash"), num(14, 322, 4),
        _down(142, 354, 374),
        repo(14, 376, 256, 46, "One commit", "Source: bulk-intent · Refused: …"), num(14, 382, 5),
        t(14, 444, "A failed commit puts every file back as committed.", "sm"),
        nosend(342, 250, ("nothing is", "sent")),
    ])


def approvals():
    return svg(540, (
        "The approval queue. The drift check and the AI agent ADD items; nothing resolves one "
        "without a person. Approving a drift item opens the capture preview, which reads the "
        "device now; approving a revert item opens the restore preview at HEAD, which computes "
        "the program now. The queued diff is context only and is never sent. You confirm the "
        "preview's hash; the operation runs and records; the item closes only for the devices "
        "it recorded. An item can also be withdrawn by a newer golden or expire after 48 hours, "
        "running nothing."), [
        lanes(20, 534),
        band(20, 110, "Queued · nothing runs"),
        svc(14, 44, 88, 30, "Drift check", ""), svc(110, 44, 90, 30, "AI agent", ""),
        arrow("rec", 58, 76, 80, 96), arrow("rec", 155, 76, 130, 96),
        store(14, 98, 186, 26, "Approval queue", ""),
        device(240, 50, 140, 44, "The device", "not contacted", off=True),
        band(136, 120, "Approve"),
        person(14, 160, 186, 30, "You approve"), num(14, 160, 1),
        t(14, 212, "Drift item: the capture preview.", "sm"),
        t(14, 226, "Revert item: the restore preview,", "sm"),
        t(14, 239, "at HEAD. The queued diff is context only.", "sm"),
        nosend(310, 196, ("approving sends", "nothing")),
        band(262, 196, "The operation, previewed now"),
        device(262, 284, 118, 150, "The device", "", top=True),
        *rows([
            (304, "read", 2, "Read now", "capture: the device as it is"),
            (344, None, 3, "Confirm the hash", "of the preview you read"),
            (384, "send", 4, "Restore only:", "the confirmed program"),
            (424, None, 5, "Recorded as you", "golden commit, receipt"),
        ]),
        band(464, 64, "Close"),
        store(14, 482, 186, 36, "Item closed", "only for devices recorded"), num(14, 482, 6),
        t(214, 504, "Or withdrawn, or expired:", "sm"), t(214, 517, "runs nothing", "sm"),
    ])


def drift():
    return svg(430, (
        "Three things the tool compares. Intent is what the device should run, committed by a "
        "person. The golden is what the device did run, recorded at its last capture. The "
        "device is what it runs now. The device differing from its golden is drift. The golden "
        "differing from intent is a departure from intent. Capture moves the golden to the "
        "device, saying the device is right; a restore or a deploy moves the device back, "
        "saying the record is right."), [
        lanes(20, 424, left="THE RECORD", right="THE NETWORK"),
        doc("intent", 14, 40, 186, 46, "Intent", "what it should run"),
        doc("golden", 14, 180, 186, 46, "Golden", "what it ran, last capture"),
        device(240, 180, 140, 46, "The device", "what it runs now"),
        t(107, 122, "differ: a departure from intent", "sm", "middle"),
        '<line class="dg-lane" x1="107" y1="88" x2="107" y2="176"/>',
        t(310, 160, "differ: drift", "tb", "middle"),
        '<line class="dg-lane" x1="202" y1="203" x2="238" y2="203"/>',
        band(250, 174, "Resolving drift: two answers, opposite claims"),
        device(262, 274, 118, 90, "The device", "", top=True),
        *rows([
            (298, "read", 1, "Capture", "the device is right: a new golden"),
            (342, "send", 2, "Restore", "the record is right: sent, verified"),
        ]),
        t(14, 392, "A regenerated self-signed certificate is not drift;", "sm"),
        t(14, 405, "a CA-signed trustpoint that changes is.", "sm"),
    ])


def drift_check():
    return svg(470, (
        "The drift check. It reads the inventory, never the golden store, so every device lands "
        "in exactly one bucket: checked, no golden, stale, or not read. For each device it "
        "reads the running configuration and compares it with its committed golden, ignoring "
        "what is volatile and a regenerated self-signed certificate. It sends nothing. It "
        "records the run, with its coverage, and queues one item for each drifted device, "
        "which a person approves into a capture."), [
        lanes(20, 464),
        band(20, 118, "Population"),
        store(14, 44, 186, 34, "Inventory", "every device, not the store"), num(14, 44, 1),
        t(14, 100, "checked · no golden · stale · not read:", "sm"),
        t(14, 113, "every device in exactly one bucket.", "sm"),
        device(240, 44, 140, 44, "The device", "read, never changed"),
        band(144, 170, "Each device"),
        device(262, 168, 118, 126, "The device", "", top=True),
        *rows([
            (190, "read", 2, "Read running config", "one session, bounded"),
            (228, None, 3, "Compare with golden", "committed, volatile stripped"),
            (262, None, 4, "Bucket the result", "clean, drifted, or why not"),
        ]),
        t(14, 298, "Nothing is sent to any device.", "sm"),
        band(320, 138, "Recorded"),
        store(14, 344, 186, 36, "The run", "checked N of M, named"), num(14, 344, 5),
        store(14, 392, 186, 36, "One queue item", "per drifted device"), num(14, 392, 6),
        t(214, 366, "Needs attention reads it;", "sm"), t(214, 379, "the device page too.", "sm"),
    ])


def netbox_import():
    return svg(540, (
        "Importing into NetBox, and removing. The import builds every object from committed "
        "goldens, never from a live device. Its preview is a dry run against NetBox that writes "
        "nothing and issues a one-time confirmation bound to the plan's hash, valid five "
        "minutes. Confirming re-plans, refuses if NetBox moved, then writes, tagging what it "
        "creates and recording what it created and what it changed. Remove deletes only objects "
        "both tagged and recorded as created by the tool, and names what NetBox would take "
        "with them."), [
        lanes(20, 534, left="THE TOOL", right="NETBOX"),
        band(20, 134, "Preview · writes nothing"),
        repo(14, 44, 186, 44, "Goldens", "committed, never a device"), num(14, 50, 1),
        _down(107, 90, 108),
        doc("box", 14, 110, 186, 36, "Plan", "and its hash"), num(14, 110, 2),
        svc(250, 70, 130, 36, "NetBox", "read: the dry run"),
        arrow("read", 248, 88, 202, 128),
        band(160, 210, "Confirm and write"),
        person(14, 184, 186, 30, "You confirm (one-time)"), num(14, 184, 3),
        t(14, 234, "Re-planned; refused if NetBox moved.", "sm"),
        t(14, 247, "The master switch must be on.", "sm"),
        svc(250, 256, 130, 36, "NetBox", "writes"),
        arrow("rec", 202, 270, 248, 274),
        store(14, 268, 186, 34, "Created", "tagged nmas-managed"), num(14, 268, 4),
        store(14, 312, 186, 34, "Modified", "with what it was before"), num(14, 312, 5),
        band(376, 150, "Remove"),
        doc("box", 14, 400, 186, 40, "Preview", "tagged AND recorded only"), num(14, 400, 6),
        t(14, 462, "Each delete names what NetBox takes", "sm"),
        t(14, 475, "with it; a person's objects are skipped.", "sm"),
        svc(250, 420, 130, 36, "NetBox", "deletes"),
        arrow("rec", 202, 438, 248, 438),
        t(14, 506, "No device is contacted by either.", "sm"),
    ])


def baselines():
    return svg(470, (
        "How a baseline is earned. A Save All, a deploy of the whole fleet or a restore reads "
        "every device in the inventory. The baseline is earned only when every device was "
        "captured and each capture matches its committed intent: then the commit is tagged "
        "baseline with its time. Otherwise the commit records the denial and names the device "
        "and its lines, and no tag is made. A baseline that predates a credential rotation can "
        "no longer be re-applied without changing that credential."), [
        lanes(20, 464, left="THE RECORD", right="THE FLEET"),
        band(20, 196, "Every device in the inventory"),
        device(240, 46, 64, 40, "Router", ""), device(316, 46, 64, 40, "Switch", ""),
        device(240, 112, 140, 40, "… every one", "captured"),
        arrow("read", 238, 92, 202, 104),
        doc("golden", 14, 46, 186, 40, "Goldens", "every capture, one commit"), num(14, 46, 1),
        doc("intent", 14, 104, 186, 40, "Intent", "committed, per device"), num(14, 104, 2),
        t(14, 168, "Each capture compared with its intent:", "sm"),
        t(14, 181, "the Intent-Match trailer.", "sm"),
        band(222, 120, "Earned"),
        repo(14, 246, 186, 46, "Tag baseline/<time>", "every device, every match"), num(14, 252, 3),
        t(214, 266, "A restore point you", "sm"), t(214, 279, "can re-apply.", "sm"),
        band(348, 116, "Denied"),
        store(14, 372, 186, 40, "The decision, recorded", "names the device and lines"), num(14, 372, 4),
        t(14, 438, "No tag. Resolve the departure, then save again.", "sm"),
    ])


def merge_and_mode_b():
    return svg(470, (
        "Merge-only, and Mode B. The tool compares intent with the device, section by section. A "
        "line intent has and the device lacks is sent, inside its section: that is all a "
        "deploy does. A line the device has and intent lacks is residue: merge-only leaves it, "
        "and names it. Mode B removes residue only when a person chooses the unit and states a "
        "reason, and only in a shape measured on that platform to remove exactly itself; verify "
        "reads it gone, and the undo puts back the device's own line."), [
        lanes(20, 464, left="INTENT", right="THE DEVICE"),
        band(20, 150, "Merge-only · every deploy"),
        doc("intent", 14, 44, 186, 40, "A line intent has", "the device lacks"),
        device(240, 44, 140, 40, "Sent", "inside its section"),
        arrow("send", 202, 64, 238, 64), num(22, 112, 1),
        t(36, 116, "Added, never negated by default.", "tb"),
        t(36, 130, "A replaced value is sent; the device keeps", "sm"),
        t(36, 143, "the rest.", "sm"),
        band(176, 120, "Residue · named, left"),
        device(240, 200, 140, 40, "A line it has", "intent lacks"),
        t(14, 216, "Not in intent: left in place", "tb"),
        t(14, 230, "and named by the preview.", "sm"),
        t(14, 266, "No baseline while residue stands.", "sm"),
        band(302, 162, "Mode B · a person chooses"),
        person(14, 326, 186, 30, "You choose it, with a reason"), num(14, 326, 2),
        t(14, 376, "Only a shape measured on the platform", "sm"),
        t(14, 389, "to remove exactly itself.", "sm"),
        device(262, 326, 118, 112, "The device", "", top=True),
        arrow("send", 202, 404, 260, 404), t(14, 408, "Its negation, verbatim", "tb"),
        arrow("read", 260, 428, 202, 428), t(14, 432, "Read back: gone", "tb"),
        t(14, 452, "The undo re-adds the device's own line.", "sm"),
    ])


def credentials_lifecycle():
    return svg(530, (
        "Every place a device's credential lives, and what keeps each current. The device runs "
        "it and boots from its startup configuration; the tool holds it, encrypted, in the "
        "inventory or its override store; a person keeps the break-glass record on their own "
        "machine. On the lab, the lab startup file and Oxidized's copy hold it too. Rotate "
        "changes the device and the tool's copy together, proven by a fresh login. Persist "
        "saves it to startup and reads it back. A new break-glass export follows every "
        "rotation."), [
        lanes(20, 524, left="THE TOOL AND PEOPLE", right="THE DEVICE"),
        band(20, 216, "Rotate · one operation"),
        store(14, 46, 186, 40, "Inventory or override", "encrypted, the one copy"), num(14, 46, 1),
        device(240, 46, 140, 40, "Running config", "what it runs"),
        arrow("send", 202, 58, 238, 58), arrow("rec", 238, 76, 202, 76),
        t(14, 112, "A new credential, sent on a held session;", "sm"),
        t(14, 125, "a fresh login proves it; then recorded.", "sm"),
        store(14, 146, 186, 40, "Break-glass record", "on a person's laptop"), num(14, 146, 2),
        t(14, 206, "Stale after a rotation: export again.", "sm"),
        band(242, 128, "Persist · the boot copy"),
        device(240, 266, 140, 40, "Startup config", "what it boots"),
        arrow("send", 202, 286, 238, 286),
        t(36, 282, "Save, then read the startup", "tb"), num(22, 278, 3),
        t(36, 296, "config back: every account line.", "sm"),
        t(14, 336, "The hourly startup check keeps asking.", "sm"),
        band(376, 148, "On the lab only"),
        labfile(14, 404, 186, 40, "Lab startup file", "a redeploy boots it"),
        svc(14, 462, 186, 40, "Oxidized's copy", "replayed by a redeploy", lab=True),
        t(214, 426, "Built by the lab sync,", "sm"), t(214, 439, "not by the product.", "sm"),
    ])


def lanes3(y1, y2, a="IN THE TOOL", b="A PERSON", c="THE DEVICE", x1=150, x2=268):
    return (f'<line class="dg-lane" x1="{x1}" y1="{y1}" x2="{x1}" y2="{y2}"/>'
            f'<line class="dg-lane" x1="{x2}" y1="{y1}" x2="{x2}" y2="{y2}"/>'
            + t(x1 / 2, 12, a, "hd", "middle") + t((x1 + x2) / 2, 12, b, "hd", "middle")
            + t((x2 + WIDTH) / 2, 12, c, "hd", "middle"))


def intent_golden_device():
    return svg(330, (
        "The model. Intent is what a device should run, committed by a person. The golden is "
        "what it did run, recorded at its last capture. The device is what it runs now. A "
        "deploy moves the device toward intent; a capture moves the golden toward the device; "
        "seeding moves intent from the golden, once, for a device that has none."), [
        lanes(20, 324, left="THE RECORD", right="THE NETWORK"),
        doc("intent", 14, 40, 186, 46, "Intent", "what it should run"),
        doc("golden", 14, 236, 186, 46, "Golden", "what it ran, last capture"),
        device(240, 138, 140, 50, "The device", "what it runs now"),
        arrow("send", 202, 70, 300, 134, via=(290, 70)), t(248, 90, "deploy", "tb"),
        arrow("read", 300, 192, 202, 258, via=(290, 258)), t(248, 232, "capture", "tb"),
        arrow("rec", 60, 234, 60, 90), t(68, 166, "seed, once", "tb"),
        t(14, 312, "Every change is a commit; every commit names who.", "sm"),
    ])


def capture():
    return svg(560, (
        "A capture, and Save All its fleet form. The preview runs as a job: it reads every "
        "chosen device now, judges each read, compares it with the golden and with committed "
        "intent, and shows whether a baseline would be earned; nothing is recorded. You "
        "confirm; the devices are held and read again, refused if anything moved; one commit "
        "records every changed golden as you and decides the baseline. Nothing is sent to a "
        "device at any step."), [
        lanes(20, 554),
        band(20, 228, "The preview · a job, nothing recorded"),
        device(262, 44, 118, 160, "The device", "each one, at once", top=True),
        *rows([
            (64, "read", 2, "Read now", "one session each, bounded"),
            (100, None, 3, "Judge the read", "one config, not stitched"),
            (136, None, 4, "Compare twice", "with golden, with intent"),
            (172, None, 5, "Baseline decision", "earned, or why not"),
        ]),
        band(254, 70, "Confirm"),
        person(14, 278, 186, 30, "You confirm its hash"),
        band(330, 224, "The apply · holding the devices"),
        device(262, 352, 118, 80, "The device", "", top=True),
        *rows([(380, "read", 2, "Read again", "moved since? refused")]),
        repo(14, 410, 186, 46, "One commit", "every changed golden, as you"), num(14, 416, 3),
        store(14, 470, 186, 34, "Baseline decided", "tag, or the denial"), num(14, 470, 4),
        t(214, 470, "Published; queue and", "sm"), t(214, 483, "drift items closed.", "sm"),
        t(14, 534, "Nothing is sent to any device.", "sm"),
    ])


def restore():
    return svg(560, (
        "Restoring a moment. You choose the moment and which devices. The preview reads only "
        "the repository at that moment, golden and intent, and computes each device's program "
        "against its stored golden: lines the moment has and the golden lacks. A line that "
        "would change or re-add a credential is refused or needs a stated reason. You confirm "
        "the hash; the run is the deploy's ten stages, merge-only, verified; residue is left. "
        "The moment's intent is committed with the device's new golden, in one commit."), [
        lanes(20, 554),
        band(20, 230, "The preview · nothing sent"),
        repo(14, 44, 186, 46, "The moment", "a baseline or a golden tag"), num(14, 50, 1),
        _down(107, 92, 110),
        doc("golden", 14, 112, 90, 40, "Golden", "then"), doc("intent", 110, 112, 90, 40, "Intent", "then"),
        _down(107, 154, 172),
        '<rect class="dg-box" x="14" y="174" width="186" height="40" rx="4"/>',
        t(107, 190, "Program", "tb", "middle"), t(107, 204, "against today's stored golden", "sm", "middle"),
        num(14, 174, 5),
        device(240, 60, 140, 44, "The device", "not contacted", off=True),
        nosend(310, 150, ("credentials: refused", "or a stated reason")),
        band(256, 56, "Confirm"),
        person(14, 276, 186, 30, "You confirm its hash"),
        band(318, 236, "The run · the deploy's ten stages"),
        device(262, 340, 118, 120, "The device", "", top=True),
        *rows([
            (364, "read", None, "Read before", "the snapshot"),
            (396, "send", None, "Send the program", "merge-only; residue stays"),
            (428, "read", None, "Read after, verify", "settle windows"),
        ]),
        repo(14, 478, 186, 46, "One commit", "new golden + the moment's intent"),
        t(214, 498, "A baseline only if every", "sm"), t(214, 511, "device equals the moment.", "sm"),
    ])


def removal():
    return svg(470, (
        "Removing a line (Mode B). A line the device has and intent lacks is residue. You tick "
        "the unit and state a reason; only a shape measured on that platform to remove exactly "
        "itself is offered, and the management path, accounts and used objects are refused. "
        "The removal is the device's own line negated, at the end of the deploy's program, in "
        "its hash. Verify reads it gone; a rollback puts back the device's own line from the "
        "snapshot."), [
        lanes(20, 464),
        band(20, 168, "Choose · nothing sent"),
        device(240, 44, 140, 44, "A line it has", "intent lacks: residue"),
        person(14, 50, 186, 30, "You tick it, with a reason"), num(14, 50, 1),
        t(14, 104, "Offered only for a shape measured on", "sm"),
        t(14, 117, "the platform; the management path,", "sm"),
        t(14, 130, "accounts and used objects refused.", "sm"),
        t(14, 156, "In the program's hash with its reason.", "sm"),
        band(194, 196, "The run · the deploy's stages"),
        device(262, 216, 118, 150, "The device", "", top=True),
        *rows([
            (240, "send", 2, "The negation", "the device's own line, verbatim"),
            (284, "read", 3, "Verify: read it gone", "still there fails"),
            (330, "undo", None, "Rollback: put it back", "the snapshot's own line"),
        ]),
        band(396, 68, "Recorded"),
        store(14, 416, 186, 36, "Receipt", "each removal, its reason"),
        doc("golden", 214, 416, 166, 36, "Golden", "without the line"),
    ])


def rotate():
    return svg(560, (
        "Rotating a device's credential. The preview reads the account's line on the device "
        "and shows the program with the password masked; you confirm its fingerprint. The "
        "apply generates a password and stages it before anything is sent, holds one session, "
        "sends the change, and proves it on a fresh login before trusting it, putting the old "
        "line back on the held session if the login fails. Then it records the new credential, "
        "clears the staged copy and persists. On the lab, persist also updates Oxidized and the "
        "lab startup file."), [
        lanes(20, 554),
        band(20, 110, "Preview"),
        device(262, 40, 118, 60, "The device", "", top=True),
        *rows([(70, "read", 1, "Read the account", "the line, live")]),
        person(14, 92, 186, 28, "You confirm it"),
        band(136, 300, "The apply · one held session"),
        store(14, 158, 186, 34, "Staged copy", "before anything is sent"), num(14, 158, 3),
        device(262, 206, 118, 210, "The device", "", top=True),
        *rows([
            (234, "send", 7, "Push", "the new secret"),
            (270, "read", 8, "Fresh login", "proves it works"),
            (306, "undo", None, "If it fails", "the old line, put back"),
            (346, None, 11, "Record", "the inventory or override"),
            (380, None, 12, "Clear the staged copy", ""),
            (414, "send", 13, "Persist", "save and read back"),
        ]),
        band(442, 112, "On the lab only"),
        svc(14, 466, 186, 34, "Oxidized's row and fetch", "", lab=True),
        labfile(214, 466, 166, 40, "Lab startup file", "re-synced"),
        t(14, 534, "Without the lab, persistence reads unverified.", "sm"),
    ])


def persist():
    return svg(420, (
        "Persist. The device runs one configuration and boots from another. From the device "
        "page, persist saves the running configuration to startup on a held session, reads the "
        "startup configuration back and checks every account line is there verbatim, then "
        "records the outcome where job health reads it. The host chain after a rotation also "
        "updates Oxidized's copy and the lab's startup file: lab integrations, off the "
        "product's path."), [
        lanes(20, 414),
        band(20, 210, "From the device page"),
        device(262, 44, 118, 150, "The device", "", top=True),
        *rows([
            (80, "send", 1, "Save", "running to startup"),
            (124, "read", 2, "Read startup back", "every account line"),
        ]),
        store(14, 158, 186, 36, "Recorded", "where job health reads it"), num(14, 158, 3),
        band(236, 178, "The host chain, after a rotation"),
        t(14, 270, "The device's own save first, then:", "sm"),
        svc(14, 284, 186, 34, "Oxidized's copy", "row, reload, fetch", lab=True),
        labfile(14, 332, 186, 40, "Lab startup file", "synced, hash checked"),
        t(214, 290, "A redeploy boots", "sm"), t(214, 303, "these, not NVRAM.", "sm"),
        t(14, 392, "Without the lab, these stages cannot pass.", "sm"),
    ])


def seed():
    return svg(330, (
        "Seeding a device's first full intent. The committed golden is parsed into intent, "
        "shown beside the intent committed now, and offered only when that is absent or only "
        "onboarding's bootstrap. You confirm a hash of the document and the golden; at apply "
        "the golden is parsed again, its secrets stored, and exactly that device's intent file "
        "is committed as you. Nothing is sent."), [
        lanes(20, 324),
        doc("golden", 14, 40, 186, 40, "Golden", "committed"), num(14, 40, 1),
        _down(107, 82, 102),
        doc("intent", 14, 104, 186, 40, "Intent, parsed", "beside intent now"), num(14, 104, 2),
        person(14, 160, 186, 30, "You confirm its hash"), num(14, 160, 4),
        _down(107, 192, 212),
        repo(14, 214, 186, 46, "One commit", "host_vars/<device>, as you"),
        store(14, 272, 186, 34, "Secrets stored", "the credential store"),
        device(240, 60, 140, 44, "The device", "not contacted", off=True),
        nosend(310, 160, ("nothing is sent", "intent only")),
    ])


def adopt():
    return svg(540, (
        "Adopting a device the tool did not build. The preview reads the device with the "
        "supplied login, which is held in memory and never written, and shows every refusal, "
        "what a save would make permanent and what NetBox would import. The apply holds the "
        "device: it adds the tool's own account and proves it on a fresh login, sends the "
        "monitoring profile, saves, commits the first golden, records what already existed in "
        "NetBox as adopted, and adds the device to the inventory last. No screen starts it "
        "yet."), [
        lanes(20, 534),
        band(20, 150, "Preview · the supplied login, in memory"),
        device(262, 44, 118, 116, "The device", "", top=True),
        *rows([
            (76, "read", 2, "Read the device", "supplied login"),
            (116, None, None, "Refusals, all at once", "accounts, AAA, names"),
        ]),
        t(14, 152, "The supplied credential is never written.", "sm"),
        band(176, 294, "The apply · holding the device"),
        device(262, 198, 118, 150, "The device", "", top=True),
        *rows([
            (222, "send", 2, "The tool's account", "proven on a fresh login"),
            (262, "send", 4, "Monitoring profile", "read back"),
            (302, "send", 5, "Save", "startup read back"),
        ]),
        doc("golden", 14, 360, 120, 40, "First golden", "Source: adopt"), num(14, 360, 6),
        svc(142, 362, 110, 36, "NetBox", "adopted"), num(142, 362, 7),
        store(260, 362, 120, 36, "Inventory", "last"), num(260, 362, 8),
        t(14, 430, "A stopped run resumes on the tool's own", "sm"),
        t(14, 443, "record; no second account.", "sm"),
        band(476, 58, "Today"),
        t(14, 506, "No screen or route starts it yet; onboard instead.", "sm"),
    ])


def retire():
    return svg(470, (
        "Retiring a device: the whole exit, sending nothing to it. The preview checks the "
        "break-glass export holds its current credential. The apply masks credentials NetBox "
        "holds in its context where the tool wrote them, clears the credential override, "
        "declares its lab startup file unmapped, commits the exit as you, removes its legacy "
        "file only if its content survives, and deletes its inventory row last. NetBox keeps "
        "the device, Oxidized keeps polling, history is kept."), [
        lanes(20, 464),
        band(20, 70, "Preview"),
        store(14, 40, 186, 36, "Break-glass export", "holds the current credential?"),
        device(240, 36, 140, 40, "The device", "never contacted", off=True),
        band(96, 300, "The apply · in order"),
        svc(14, 118, 186, 34, "NetBox context", "credentials masked"), num(14, 118, 1),
        store(14, 162, 186, 34, "Credential override", "cleared"), num(14, 162, 2),
        labfile(14, 206, 186, 36, "Lab startup file", "declared unmapped"), num(14, 206, 3),
        repo(14, 252, 186, 44, "One commit", "the exit, as you"), num(14, 258, 4),
        store(14, 306, 186, 34, "Legacy file", "removed if it survives"), num(14, 306, 5),
        store(14, 350, 186, 34, "Inventory row", "deleted last"), num(14, 350, 6),
        nosend(310, 240, ("nothing is sent", "to the device")),
        band(402, 62, "Kept, by design"),
        t(14, 434, "NetBox's record, Oxidized polling, history,", "sm"),
        t(14, 447, "backups: each named in the commit.", "sm"),
    ])


def monitoring_templates():
    return svg(520, (
        "Applying the network's monitoring profile. Coverage reads each device's committed "
        "golden and marks what it is configured for. You tick devices; the preview plans each "
        "from its stored golden and the profile, sending only the profile's lines, and you "
        "set the rollout order and confirm. The apply runs one device after another in that "
        "order, each through the deploy's ten stages, and records the goldens in one commit and "
        "a receipt per device."), [
        lanes(20, 514),
        band(20, 130, "Coverage · stored records only"),
        doc("box", 14, 44, 90, 40, "Profile", "committed"),
        doc("golden", 110, 44, 90, 40, "Goldens", "committed"),
        t(14, 112, "Each cell: configured, not, or not", "sm"),
        t(14, 125, "reporting.", "sm"),
        device(240, 50, 140, 40, "Devices", "not contacted", off=True),
        band(156, 120, "Preview and confirm"),
        doc("box", 14, 178, 186, 40, "Program per device", "the profile's lines only"), num(14, 178, 1),
        person(14, 228, 186, 30, "You set the order, confirm"), num(14, 228, 2),
        nosend(310, 216, ()),
        band(282, 182, "The run · one device after another"),
        device(262, 304, 118, 140, "The device", "each, in order", top=True),
        *rows([
            (336, "read", 3, "Read before", "the snapshot"),
            (372, "send", 4, "Send the profile lines", "merge-only"),
            (408, "read", 5, "Read after, verify", "quick or full"),
        ]),
        store(14, 474, 186, 34, "Goldens and receipts", "one commit, a receipt each"),
        t(214, 494, "A failing device stops the batch.", "sm"),
    ])


def update():
    return svg(540, (
        "Updating the app. The preview is the stored comparison with the pushed tip: the "
        "commits between, CI's verdict and the host steps. You confirm; the app writes a "
        "request file and nothing else. A root-owned updater, started by a systemd path unit, "
        "validates it, re-checks CI itself, moves the checkout as the service user, restarts "
        "the app and waits for the new commit to answer; if it does not within 120 seconds it "
        "rolls back. No device is involved."), [
        lanes(20, 534, left="THE APP", right="THE HOST, AS ROOT"),
        band(20, 120, "Preview and confirm"),
        doc("box", 14, 44, 186, 40, "Stored comparison", "commits, CI, host steps"),
        person(14, 96, 186, 30, "You confirm its hash"),
        band(146, 72, "The request"),
        store(14, 166, 186, 36, "Request file", "the app writes only this"), num(14, 166, 1),
        svc(240, 166, 140, 36, "Path unit", "starts the updater"), num(240, 166, 2),
        arrow("rec", 202, 184, 238, 184),
        band(224, 250, "The updater"),
        *[x for i, (y, w1, w2) in enumerate([
            (250, "Checkout clean, fetch", "as the service user"),
            (290, "CI, again", "its own copy of the gate"),
            (330, "Move and restart", "systemctl, as root"),
            (370, "Wait: the new commit", "/health, 120 s"),
            (410, "Running, or rolled back", "recorded"),
        ]) for x in (num(232, y - 4, i + 3), t(246, y, w1, "tb"), t(246, y + 12, w2, "sm"))],
        t(14, 290, "The page waits on /health,", "sm"), t(14, 303, "never on a timer.", "sm"),
        band(480, 54, "Never"),
        t(14, 508, "No device is contacted by an update.", "sm"),
    ])


def publish_remote():
    return svg(500, (
        "Publishing the record to the remote. Every commit hands itself to the push hook, which "
        "holds a push carrying a new secret value or kind until a person acknowledges it; "
        "otherwise it pushes the branch and the tags it was told about, records the push and "
        "asks the remote again. Push now does the same on request. Verify the remote reads it "
        "with the key: readable, private, the right repository. The remote is never "
        "force-pushed."), [
        lanes(20, 494, left="THE TOOL", right="THE REMOTE"),
        band(20, 230, "Every commit"),
        repo(14, 44, 186, 44, "A commit", "handed to the push hook"), num(14, 50, 1),
        store(14, 100, 186, 36, "Publication gate", "new secret value or kind?"), num(14, 100, 2),
        t(14, 156, "Held: acknowledge, then Push now.", "sm"),
        svc(240, 170, 140, 36, "The remote", "branch and tags"),
        arrow("rec", 202, 188, 238, 188), num(220, 178, 3),
        store(14, 206, 186, 36, "Push recorded", "the remote asked again"), num(14, 206, 5),
        band(256, 120, "Push now · Verify"),
        person(14, 280, 186, 30, "You press Push now"),
        arrow("rec", 202, 296, 238, 296), svc(240, 280, 140, 34, "The remote", ""),
        arrow("read", 238, 346, 202, 346), t(14, 350, "Verify: read and private", "tb"),
        band(382, 112, "Never"),
        t(14, 408, "Never force-pushed, never unpublished.", "sm"),
        t(14, 421, "Whether history is on the remote is read", "sm"),
        t(14, 434, "from the remote's own branch.", "sm"),
    ])


def breakglass_export():
    return svg(470, (
        "Exporting the break-glass record. The preview names every device and the key the "
        "record would hold and reveals nothing. You type a passphrase twice; the record is "
        "built, sealed and verified in memory, opened with the passphrase and every device and "
        "the escrowed key checked, before anything is sent. A reveal row is written first; "
        "then it downloads to your browser and the export log records who and its hash. It "
        "never touches the host's disk."), [
        lanes(20, 464, left="THE HOST", right="YOUR BROWSER"),
        band(20, 100, "Preview"),
        doc("box", 14, 44, 186, 40, "What it would hold", "devices and the key, no value"),
        person(14, 90, 186, 26, "A passphrase, twice"),
        band(126, 210, "Built in memory"),
        store(14, 150, 186, 34, "Sealed record", "never on the host's disk"), num(14, 150, 3),
        store(14, 194, 186, 34, "Verified", "opened, every device checked"), num(14, 194, 4),
        store(14, 238, 186, 34, "Reveal row", "before anything leaves"), num(14, 238, 5),
        arrow("rec", 202, 296, 238, 296), doc("box", 240, 276, 140, 40, "The file", "on your laptop"),
        store(14, 290, 186, 34, "Export log", "who, when, its hash"), num(14, 290, 6),
        band(342, 122, "Afterwards"),
        t(14, 374, "A rotation makes it stale: job health", "sm"),
        t(14, 387, "names the device until you export again.", "sm"),
        t(14, 413, "Keep the file and the passphrase apart.", "sm"),
    ])


def onboard_static():
    return svg(360, (
        "Static address: a person applies the bootstrap configuration. The tool renders it on "
        "request, as a recorded reveal, carrying the one-time bootstrap credential in the clear. "
        "You download it and paste it at the device's console, or place it as its startup "
        "configuration. The device boots on its static address; Verify then reaches it over "
        "SSH. The tool sends nothing to the device until Verify."), [
        lanes3(20, 354),
        band(20, 140, "Get the file"),
        doc("box", 8, 44, 136, 40, "Bootstrap config", "rendered now"), num(8, 44, 1),
        store(8, 96, 136, 34, "Reveal row", "who, when"),
        arrow("rec", 146, 64, 156, 64), person(158, 50, 104, 28, "You"),
        band(166, 110, "Apply it"),
        arrow("send", 262, 200, 274, 200),
        device(276, 184, 118, 44, "The device", "console paste"), num(276, 184, 2),
        t(158, 246, "Paste, or place as", "sm"), t(158, 259, "its startup config.", "sm"),
        band(282, 72, "Then Verify"),
        arrow("read", 274, 326, 146, 326), t(8, 322, "Verify reaches it", "tb"), t(8, 336, "over SSH", "sm"),
        nosend(335, 96, ("nothing sent", "by the tool")),
    ])


def onboard_dhcp():
    return svg(380, (
        "DHCP reservation: Kea gives the device an address, not a configuration. A person "
        "writes the reservation in Kea for the device's MAC before the plan; the tool only "
        "reads it, at the plan and again at Verify to find the lease. The configuration still "
        "arrives as on the static path: a person applies the file the tool renders."), [
        lanes3(20, 374, b="A PERSON · KEA"),
        band(20, 110, "Before the plan"),
        person(158, 44, 104, 28, "You"), arrow("rec", 210, 74, 210, 92),
        svc(158, 94, 104, 30, "Kea", "reservation"),
        arrow("read", 156, 108, 146, 108), t(8, 104, "Plan reads it", "tb"), t(8, 118, "reserved?", "sm"),
        band(136, 120, "Boot"),
        svc(158, 160, 104, 30, "Kea", "address only"),
        arrow("send", 262, 176, 274, 176),
        device(276, 160, 118, 44, "The device", "leases its address"),
        t(158, 216, "No file, no server", "sm"), t(158, 229, "option on this path.", "sm"),
        band(262, 112, "The configuration"),
        person(158, 282, 104, 28, "You paste it"), arrow("send", 262, 296, 274, 296),
        device(276, 280, 118, 40, "The device", ""),
        t(8, 300, "Rendered as static", "tb"), t(8, 314, "a recorded reveal", "sm"),
        t(8, 352, "Verify reads the lease, then SSH.", "sm"),
    ])


def onboard_ztp_iosxe():
    return svg(520, (
        "ZTP on IOS-XE: the tool delivers the configuration. At Create it writes the device's "
        "Kea reservation with options 12 (hostname), 66 (the tool's address) and 67 (the file "
        "name), and never a route or resolver. The configless device asks DHCP, gets them, and "
        "asks the tool's read-only TFTP responder for that one file. The responder serves it "
        "only to the reserved address, only while the device is pending, renders it per "
        "request and writes a reveal row first. TFTP is cleartext: the bootstrap credential is "
        "one-time, replaced at Verify. AutoInstall gives up after about 2.5 minutes."), [
        lanes(20, 514),
        band(20, 110, "Create"),
        svc(14, 44, 186, 34, "Kea reservation", "12 · 66 · 67, never 3, 6, 33, 121"), num(14, 44, 3),
        t(14, 100, "Written by the tool, tested first.", "sm"),
        device(240, 44, 140, 44, "The device", "configless, not booted", off=True),
        band(136, 100, "Boot"),
        device(262, 156, 118, 64, "The device", "", top=True),
        *rows([(192, "send", None, "Kea answers", "address and options")]),
        band(242, 196, "Fetch · TFTP"),
        device(262, 262, 118, 150, "The device", "", top=True),
        *rows([
            (290, "read", None, "Asks for <device>.cfg", "from option 66's address"),
            (330, None, None, "Responder checks", "reserved, named, pending"),
            (366, None, None, "Reveal row written", "its hash, never the text"),
            (402, "send", None, "Serves the file", "rendered now, cleartext"),
        ]),
        clock(214, 438), t(230, 442, "gives up after about 2.5 min", "sm"),
        band(444, 70, "Then Verify"),
        t(14, 478, "The tool reads Kea's lease, reaches it", "sm"),
        t(14, 491, "over SSH, rotates the bootstrap credential.", "sm"),
    ])


#: name -> function drawing it. The file is ``docs/manual/diagrams/<name>.svg``.
DIAGRAMS = {
    "deploy": deploy,
    "onboard": onboard,
    "revert-retry": revert_retry,
    "bulk-intent": bulk_intent,
    "approvals": approvals,
    "drift": drift,
    "drift-check": drift_check,
    "netbox-import": netbox_import,
    "baselines": baselines,
    "merge-and-mode-b": merge_and_mode_b,
    "credentials-lifecycle": credentials_lifecycle,
    "intent-golden-device": intent_golden_device,
    "capture": capture,
    "restore": restore,
    "removal": removal,
    "rotate": rotate,
    "persist": persist,
    "seed": seed,
    "adopt": adopt,
    "retire": retire,
    "monitoring-templates": monitoring_templates,
    "update": update,
    "publish-remote": publish_remote,
    "breakglass-export": breakglass_export,
    "onboard-static": onboard_static,
    "onboard-dhcp": onboard_dhcp,
    "onboard-ztp-iosxe": onboard_ztp_iosxe,
}


def draw(name: str) -> str:
    return DIAGRAMS[name]()
