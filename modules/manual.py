"""The manual (NSOT_GUI_BRIEF section 10 and 10a; the operator, 2026-10-02).

Markdown in ``docs/manual/``, versioned with the code, rendered at
``/v2/help/<page>`` and, one section at a time, in the frame's side help panel
that every screen's info link opens. ONE source: the panel and the page render
the same file, never a second copy of the words.

**The renderer is a small, strict subset, written here** rather than
Python-Markdown: no Markdown library is on the deployment host or in
``requirements.lock``, and adding one is a host step (apt, then the lock
regenerated there, C37 and C40) that would hold the manual hostage to it. The
files are plain Markdown, so moving to Python-Markdown later changes no file.
What it renders: ``#``-``###`` headings (each an anchor), paragraphs, ``-`` and
``1.`` lists (one nested level), fenced code, inline code, ``**bold**``,
``*emphasis*``, links to another manual page or an app path, and a diagram line
``![description](diagrams/<name>.svg)``. Everything else is TEXT: every
character is escaped, there is no raw HTML, so the manual cannot inject markup.
A link of any other form is refused, so a typo cannot ship (the checks in
``tests/test_manual.py`` render every page).

**What the manual must cover is declared here and checked**: every sidebar
destination and device-page tab has a Screens page (``SCREENS``), every
operation has a How it works page (``OPERATIONS``), and an operation whose code
declares its steps has each step named in its page.
"""

import html
import importlib
import logging
import os
import re

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_DIR = os.path.join(ROOT, "docs", "manual")

#: Every page, in the Help navigation's order: (slug, title, group, file).
#: The slug is the URL (``/v2/help/<slug>``); "about" is the installation page.
H = "How it works"
PAGES = (
    ("getting-started", "The model: intent, golden, device", "Getting started", "getting-started.md"),
    ("third-party", "Third-party components and their licences", "Getting started", "third-party.md"),
    ("deploy", "Deploy a change", H, "how-it-works/deploy.md"),
    ("capture", "Capture and Save All", H, "how-it-works/capture.md"),
    ("restore", "Restore and re-apply a baseline", H, "how-it-works/restore.md"),
    ("removal", "Remove a line (Mode B)", H, "how-it-works/removal.md"),
    ("revert-retry", "Revert or retry after a rollback", H, "how-it-works/revert-retry.md"),
    ("rotate", "Rotate a credential", H, "how-it-works/rotate.md"),
    ("persist", "Persist", H, "how-it-works/persist.md"),
    ("seed", "Seed intent", H, "how-it-works/seed.md"),
    ("bulk-intent", "Edit intent in bulk", H, "how-it-works/bulk-intent.md"),
    ("onboard", "Onboard a device", H, "how-it-works/onboard.md"),
    ("adopt", "Adopt a device", H, "how-it-works/adopt.md"),
    ("retire", "Retire a device", H, "how-it-works/retire.md"),
    ("drift-check", "Check drift", H, "how-it-works/drift-check.md"),
    ("approvals", "Approve a queued action", H, "how-it-works/approvals.md"),
    ("netbox-import", "Import into NetBox, or remove", H, "how-it-works/netbox-import.md"),
    ("breakglass-export", "Export the break-glass record", H, "how-it-works/breakglass-export.md"),
    ("publish-remote", "Publish to the remote: push and verify", H, "how-it-works/publish-remote.md"),
    ("monitoring-templates", "Apply a monitoring template", H, "how-it-works/monitoring-templates.md"),
    ("update", "Update the app", H, "how-it-works/update.md"),
    ("edit-intent", "Edit a device's intent", H, "how-it-works/edit-intent.md"),
    ("approve-template", "Approve a template", H, "how-it-works/approve-template.md"),
    ("bring-template", "Bring in a shipped template", H, "how-it-works/bring-template.md"),
    ("show-commands", "Show commands: ask devices read-only commands", H,
     "how-it-works/show-commands.md"),
    ("settings-switch", "Inherit or stand alone: switch a network's settings", H,
     "how-it-works/settings-switch.md"),
    ("drift", "Drift", "Concepts", "concepts/drift.md"),
    ("baselines", "How a baseline is earned", "Concepts", "concepts/baselines.md"),
    ("merge-and-mode-b", "Merge-only, and Mode B", "Concepts", "concepts/merge-and-mode-b.md"),
    ("credentials-lifecycle", "Credentials: rotate and persist", "Concepts",
     "concepts/credentials-lifecycle.md"),
    ("needs-attention", "Needs attention", "Screens", "screens/needs-attention.md"),
    ("devices", "Devices", "Screens", "screens/devices.md"),
    ("device-page", "The device page", "Screens", "screens/device-page.md"),
    ("history", "History", "Screens", "screens/history.md"),
    ("monitoring", "Monitoring", "Screens", "screens/monitoring.md"),
    ("logs", "Logs", "Screens", "screens/logs.md"),
    ("dhcp", "DHCP", "Screens", "screens/dhcp.md"),
    ("templates", "Templates", "Screens", "screens/templates.md"),
    ("netbox", "NetBox", "Screens", "screens/netbox.md"),
    ("credentials", "Credentials", "Screens", "screens/credentials.md"),
    ("approvals-screen", "Approvals", "Screens", "screens/approvals.md"),
    ("backups", "Backups", "Screens", "screens/backups.md"),
    ("settings", "Settings", "Screens", "screens/settings.md"),
    ("help", "Help", "Screens", "screens/help.md"),
)
GROUPS = ("Getting started", "How it works", "Concepts", "Screens")

#: Pages whose action or screen is still on TODAY'S app (the redesign has not carried it
#: yet). Help's index marks each, so a person knows where to go (the operator, 2026-10-02:
#: onboarding's page existed and nothing said its action lived on today's app). A page
#: leaves this set in the commit that builds its screen in v2.
ON_TODAYS_APP = frozenset((
    "deploy", "capture", "restore", "removal", "revert-retry", "rotate", "persist", "seed",
    "bulk-intent", "onboard", "adopt", "retire", "drift-check", "approvals", "netbox-import",
    "logs", "dhcp", "netbox",
    "approvals-screen", "backups",
))

#: Every sidebar destination (its label in ``templates/v2/base.html``) and the
#: Screens page it opens.
SCREENS = {
    "Needs attention": "needs-attention", "Devices": "devices", "History": "history",
    "Monitoring": "monitoring", "Logs": "logs", "DHCP": "dhcp", "Templates": "templates",
    "NetBox": "netbox", "Credentials": "credentials", "Help": "help", "Settings": "settings",
}

#: Every device-page tab (``routes/device_v2.TABS``) and its anchor on the
#: device page's Screens page.
DEVICE_TABS = {
    "overview": "overview", "intent": "intent", "history": "history-tab",
    "monitoring": "monitoring-tab", "logs": "logs-tab", "netbox": "netbox-tab",
    "neighbours": "neighbours", "ask": "ask-the-device",
}

#: Every operation and the code that declares its steps: ``(module, attribute)``,
#: whose value is a sequence of step keys (or of ``(key, words)`` pairs), each of
#: which its page must name. ``None`` with a reason where the code declares no
#: step list yet: the stepper work (brief 10a) adds one, and this list only
#: shrinks (``UNDECLARED_CEILING`` in the test).
OPERATIONS = {
    "deploy": ("modules.pipeline", "STAGE_NAMES"),
    "capture": None,
    "restore": ("modules.pipeline", "STAGE_NAMES"),
    "removal": ("modules.pipeline", "STAGE_NAMES"),
    "rotate": ("modules.nsot.rotate_op", "STEPS"),
    "persist": None,
    "seed": None,
    "onboard": ("modules.nsot.onboard", "STEPS"),
    "onboard-phase-two": ("modules.nsot.onboard", "PHASE_TWO_STEPS"),
    "onboard-ztp": ("modules.nsot.onboard", "ZTP_STEPS"),
    "adopt": ("modules.nsot.adopt", "APPLY_STEPS"),
    "retire": None,
    "monitoring-templates": ("modules.pipeline", "STAGE_NAMES"),
    "update": ("modules.update_op", "STEPS"),
    "settings-switch": ("modules.list_settings", "SWITCH_STEPS"),
    "edit-intent": ("modules.nsot.intent_edit", "STEPS"),
    "approve-template": ("modules.nsot.approve_op", "STEPS"),
    "bring-template": ("modules.nsot.template_bring", "STEPS"),
    "show-commands": ("modules.nsot.reads", "STEPS"),
}
#: The page each operation's steps are named on (an operation may have two
#: declared sequences on one page: onboarding's two phases and its ZTP form).
OPERATION_PAGE = {"onboard-phase-two": "onboard", "onboard-ztp": "onboard"}
#: Why an operation has no declared step list yet, said rather than left blank.
UNDECLARED = {
    "capture": "the capture job reads, previews and records in code paths with no step tuple",
    "persist": "persist_op builds its step list in plan(), with the device's name in each",
    "seed": "seed's preview, confirm and apply are three routes with no step tuple",
    "retire": "retire builds its step list in plan(), per device",
}


class ManualError(ValueError):
    """A page that cannot be rendered: an unknown link form, a missing
    diagram, a page the manual does not declare."""


def page(slug: str) -> dict:
    """``{"slug", "title", "group", "file"}`` for a declared page, or raise."""
    for s, title, group, rel in PAGES:
        if s == slug:
            return {"slug": s, "title": title, "group": group, "file": rel}
    raise ManualError(f"no manual page named {slug!r}")


def nav() -> list:
    """The Help navigation: ``[{"group", "pages": [{"slug", "title", "todays_app"}]}]``."""
    return [{"group": g, "pages": [{"slug": s, "title": t, "todays_app": s in ON_TODAYS_APP}
                                   for s, t, gg, _f in PAGES if gg == g]}
            for g in GROUPS]


#: The manual names the product through this placeholder, filled from `modules.brand`, the one
#: place the name is kept (NSOT_STAGE7_PLAN 19): a rename is one change, never a sweep of prose.
PRODUCT = "{{product}}"
#: The third-party page's list, drawn from docs/THIRD_PARTY.json (its one owner) when read.
THIRD_PARTY_LIST = "{{third_party}}"


def third_party_markdown(path: str = None) -> str:
    """Every third-party component, from docs/THIRD_PARTY.json: the vendored front-end files,
    then the Python packages, each with its version and licence, as manual list items."""
    import json

    path = path or os.path.join(ROOT, "docs", "THIRD_PARTY.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    out = ["## In the interface {#vendored}", ""]
    for entry in sorted(doc.get("vendored", {}).values(), key=lambda e: e["component"].lower()):
        out.append(f"- **{entry['component']}** {entry['version']}: {entry['licence']}")
    out += ["", "## Python packages {#python}", ""]
    for name, entry in sorted(doc.get("python", {}).items(), key=lambda kv: kv[0].lower()):
        out.append(f"- **{name}** {entry['version']}: {entry['licence']}")
    return "\n".join(out)


def source(slug: str) -> str:
    """A page's markdown, with the product's name and any generated part filled in."""
    from modules import brand

    with open(os.path.join(MANUAL_DIR, page(slug)["file"]), encoding="utf-8") as fh:
        text = fh.read()
    if THIRD_PARTY_LIST in text:
        text = text.replace(THIRD_PARTY_LIST, third_party_markdown())
    return text.replace(PRODUCT, brand.PRODUCT_SHORT)


def declared_steps(op: str) -> list:
    """The step keys the code declares for *op*, read from the code itself."""
    ref = OPERATIONS[op]
    if ref is None:
        return []
    mod = importlib.import_module(ref[0])
    out = []
    for item in getattr(mod, ref[1]):
        out.append(item[0] if isinstance(item, (tuple, list)) else item)
    return out


# --------------------------------------------------------------------- render

def anchor_of(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


_INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\*(.+?)\*|\[([^\]]+)\]\(([^)\s]+)\)")


def _href(target: str) -> str:
    """A link's target: another manual page (``slug`` or ``slug#anchor``), an
    anchor on this page (``#anchor``) or an app path (``/v2/...``)."""
    if target.startswith("#"):
        return target
    if target.startswith("/v2/"):
        return target
    slug, _hash, anchor = target.partition("#")
    if any(s == slug for s, _t, _g, _f in PAGES):
        return f"/v2/help/{slug}" + (f"#{anchor}" if anchor else "")
    raise ManualError(f"a link the manual cannot resolve: {target!r} (a manual page slug, "
                      "slug#anchor, #anchor or a /v2/ path)")


def _inline(text: str, links: list) -> str:
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        code, bold, em, label, target = m.groups()
        if code is not None:
            out.append(f"<code>{html.escape(code)}</code>")
        elif bold is not None:
            out.append(f"<strong>{_inline(bold, links)}</strong>")
        elif em is not None:
            out.append(f"<em>{_inline(em, links)}</em>")
        else:
            href = _href(target)
            links.append(target)
            out.append(f'<a href="{html.escape(href)}">{_inline(label, links)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


_DIAGRAM = re.compile(r"^!\[([^\]]+)\]\(diagrams/([a-z0-9-]+)\.svg\)$")
_HEAD = re.compile(r"^(#{1,3}) (.+?)(?: \{#([a-z0-9-]+)\})?$")
_BULLET = re.compile(r"^( *)(?:- |(\d+)\. )(.*)$")


def diagram(name: str) -> str:
    """A diagram's SVG, read from ``docs/manual/diagrams``. The repository's
    own file, drawn with classes the stylesheet themes (no inline style, so
    the strict policy holds and dark mode applies)."""
    path = os.path.join(MANUAL_DIR, "diagrams", f"{name}.svg")
    if not os.path.isfile(path):
        raise ManualError(f"a diagram the manual names does not exist: diagrams/{name}.svg")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if re.search(r"<script|\son[a-z]+=|style=|javascript:", text, re.I):
        raise ManualError(f"diagrams/{name}.svg carries script or inline style")
    # The file is a standalone SVG (with its namespace); inline it without one.
    return text[text.index("<svg"):].replace(' xmlns="http://www.w3.org/2000/svg"', "", 1)


def render(text: str) -> dict:
    """``{"html", "title", "anchors", "links", "sections", "lead", "diagrams"}``.
    *sections* maps each anchor (an ``##`` heading) to its own HTML, for the side
    panel. *lead* is the page's first diagram when it comes before any section
    (the brief 10b: drawn first in the panel, and beside the text on the page);
    *diagrams* names every diagram the page draws."""
    lines = text.splitlines()
    blocks, anchors, links, drawn = [], [], [], []
    lead = ""
    title = ""
    current = None          # (anchor, [html]) of the open ## section
    sections = {}
    para, lst = [], []      # paragraph lines; list items [(indent, ordered, html)]
    i = 0

    def emit(h):
        blocks.append(h)
        if current is not None:
            current[1].append(h)

    def flush_para():
        if para:
            emit("<p>" + _inline(" ".join(para), links) + "</p>")
            para.clear()

    def flush_list():
        if not lst:
            return
        out, stack = [], []
        for indent, ordered, item in lst:
            level = 1 if indent >= 2 else 0
            tag = "ol" if ordered else "ul"
            while len(stack) > level + 1:
                out.append(f"</li></{stack.pop()}>")
            if len(stack) < level + 1:
                out.append(f"<{tag}>")
                stack.append(tag)
            elif out:
                out.append("</li>")
            out.append(f"<li>{item}")
        while stack:
            out.append(f"</li></{stack.pop()}>")
        emit("".join(out))
        lst.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            flush_para()
            flush_list()
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            emit("<pre><code>" + html.escape("\n".join(body)) + "</code></pre>")
            i += 1
            continue
        h = _HEAD.match(line)
        if h:
            flush_para()
            flush_list()
            level, words, explicit = len(h.group(1)), h.group(2), h.group(3)
            if level == 1:
                title = words
                i += 1
                continue
            anchor = explicit or anchor_of(words)
            if anchor in anchors:
                raise ManualError(f"two headings share the anchor {anchor!r}")
            anchors.append(anchor)
            if level == 2:
                current = (anchor, [])
                sections[anchor] = current
            emit(f'<h{level} id="{anchor}">{_inline(words, links)}</h{level}>')
            i += 1
            continue
        d = _DIAGRAM.match(line)
        if d:
            flush_para()
            flush_list()
            desc, name = d.groups()
            fig = (f'<figure class="diagram">{diagram(name)}<figcaption>'
                   f'<strong>The diagram in words.</strong> {_inline(desc, links)}'
                   "</figcaption></figure>")
            drawn.append(name)
            if current is None and not lead:
                lead = fig
            else:
                emit(fig)
            i += 1
            continue
        b = _BULLET.match(line)
        if b:
            flush_para()
            indent, number, rest = len(b.group(1)), b.group(2), b.group(3)
            # Continuation lines, indented past the marker.
            j = i + 1
            while j < len(lines) and lines[j].startswith(" " * (indent + 2)) \
                    and not _BULLET.match(lines[j]) and lines[j].strip():
                rest += " " + lines[j].strip()
                j += 1
            lst.append((indent, number is not None, _inline(rest, links)))
            i = j
            continue
        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue
        flush_list()
        para.append(line.strip())
        i += 1
    flush_para()
    flush_list()
    return {"html": "\n".join(blocks), "title": title, "anchors": anchors, "links": links,
            "lead": lead, "diagrams": drawn,
            "sections": {a: "\n".join(h for h in body) for a, (_a, body) in sections.items()}}


def load(slug: str) -> dict:
    """A declared page, rendered: its declared title, group and HTML."""
    p = page(slug)
    out = render(source(slug))
    out.update(slug=slug, group=p["group"], nav_title=p["title"])
    return out


def section(slug: str, anchor: str = "") -> dict:
    """What the side panel draws: the page's ``##`` section named by *anchor*,
    or the whole page when no anchor is given. An unknown anchor raises."""
    out = load(slug)
    if not anchor:
        return {"slug": slug, "title": out["title"], "html": out["html"], "anchor": "",
                "lead": out["lead"]}
    if anchor not in out["sections"]:
        raise ManualError(f"the manual page {slug!r} has no section {anchor!r}")
    return {"slug": slug, "title": out["title"], "html": out["sections"][anchor],
            "anchor": anchor, "lead": out["lead"]}
