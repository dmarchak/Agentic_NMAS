"""The manual against the product, both ways (C1844; the operator, 2026-10-27: the toolbar
assistant's how-to answers cite the manual, so what it names must be there, and what is there
must be named). Shared by tests/test_manual_references.py; not a test module.

**The product's controls** (`controls()`): every element a person presses in a v2 template,
read from the markup by what it is, never by its name:

- every ``<button>`` (a button is pressed, whatever its class);
- a ``<summary>`` used as a button: it carries the class token ``btn``, ``aria-haspopup``, or an
  ``hx-`` attribute (it fetches or opens something); a bare ``<summary>`` that only folds a
  section open is a disclosure, not a control;
- an ``<a>`` styled or marked as an action: the class token ``btn``, ``role="menuitem"``,
  ``data-op``, or words ending in an ellipsis (tests/manual_actions.py's population; a plain
  link to a page is navigation, the manual's routes check holds those).

Its label is what a person reads on it: comments dropped, the busy words (``op-busy``) and a
description beside the name (``<small>``, ``menu-sub``, ``muted``, ``faint``) dropped (the
control's name is its idle words, as tests/manual_actions.py reads it), each ``{% if %}``
branch read as its own label, an icon or help link (``icon()``, ``how()``, ``info()``) dropped,
and each ``{{ ... }}`` read for the words it can draw (`readings`: a literal, each arm of a
conditional, a join, a name the template binds to literals by a loop, a ``set`` or a macro's
calls), anything else a placeholder ``<x>``. Its ``aria-label`` and ``title`` are names too;
a control with no words is labelled by them.

**The manual's names** (`bold_names()`): every ``**bold**`` span outside code, read over a
paragraph's lines joined as the renderer joins them (`inline_text`, C2218), and each
segment of a bold path (``**Actions › Save…**``). The manual writes a value the page fills as
``<placeholder>``, a count as ``N``, and a plural as ``line(s)``; each is normalised to the
template's placeholder (`normal()`).

A control is ENTERED when one of its labels or names, normalised, is a bold name the manual
uses (a placeholder on either side stands for one value: a word, a name, an address).
Assumptions, stated: the manual's convention is that a control is named in bold
(NSOT_GUI_BRIEF 10); one bold mention anywhere enters every control with that label (where it
is placed is not checked: a reviewer's question); a control whose every label and name is data
(``<x>`` alone: a Python-built card's button words) cannot be named by text and is counted
apart, its number a ceiling (`data_labelled()`, ``DATA_LABELLED_CEILING``); a control a script
builds (static/js) is outside the population.

**What the manual names as a control** (`pressed_names()`): a bold label whose role in the
sentence is a control's, read from the prose: the object of a pressing verb ("Press **Save**",
"choose **Record the drill**"), a bold label joined to such a one ("press **A** or **B**",
", then **C**"), and a bold label followed by the word button, menu, link or chip; a keyboard
key ("press **Escape**", `KEYS`) is the keyboard's. A status word, a column, a field or a
run-in heading is never the object of a press, so the rule leaves them out without a list. The
ellipsis labels (``**Save…**``) and the bold paths are held by their own checks in
tests/test_manual_references.py. A bold label followed by the word tab (`tab_names()`) names
a navigation label.

**Screen names** (`paths()`): every ``A › B › C`` the manual writes, bold or in prose. The
segments between two separators are exact; the first is the longest run of words before the
first separator (at most five, not crossing punctuation) that names a navigation label (a
sidebar item, a tab, or a control), and the last the longest run after the last separator that
the product draws.
"""

import ast
import os
import re

from modules import manual
from tests import source_index

PLACEHOLDER = "<x>"

# ---------------------------------------------------------------- the manual's side

_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
#: The manual renderer's own inline grammar (modules/manual.py): code first, so a bold span
#: inside code is not bold.
_INLINE = manual._INLINE
_SEP = re.compile(r" (?:›|>) ")
_PRESS = re.compile(r"(?:^|[^\w])(?:press|presses|pressed|pressing|click|clicks|clicked|clicking|"
                    r"choose|chooses|chose|choosing|pick|picks|picked)\s+$", re.I)
_JOIN = re.compile(r"^\s*(?:,|;)?\s*(?:or|and|then|or then|and then|then press)?\s*$")
_NOUN = re.compile(r"^ (?:button|menu|link|chip)\b")
#: A keyboard key: what "press **Escape**" presses is the keyboard, not a control.
KEYS = frozenset(("Alt", "Control", "Ctrl", "Shift", "Escape", "Esc", "Enter", "Return", "Tab",
                  "Space", "Delete", "Backspace", "Meta", "Option", "Command"))


def prose(text: str) -> str:
    """A page without its fenced code blocks (their lines keep their places as blank lines)."""
    return _FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def inline_text(text: str) -> str:
    """A page as the renderer (modules/manual.py ``render``) hands its inline grammar the
    words: one block per line, a paragraph's lines stripped and joined by one space, a list
    item's continuation lines (indented past its marker) joined to it, a heading or a diagram
    line by itself, and a fenced block dropped (C2218: a bold label wrapped across a line break
    is one span to the renderer, so it is one here). The renderer does not expose its joining,
    so its loop is followed step for step; `TestTheBoldSpansAreTheRenderersOwn` holds the two
    together page by page."""
    lines = text.splitlines()
    out, para = [], []

    def flush():
        if para:
            out.append(" ".join(para))
            para.clear()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("```"):
            flush()
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                i += 1
            i += 1
            continue
        if manual._HEAD.match(line) or manual._DIAGRAM.match(line):
            flush()
            out.append(line)
            i += 1
            continue
        b = manual._BULLET.match(line)
        if b:
            flush()
            indent, item = len(b.group(1)), line
            j = i + 1
            while j < len(lines) and lines[j].startswith(" " * (indent + 2)) \
                    and not manual._BULLET.match(lines[j]) and lines[j].strip():
                item += " " + lines[j].strip()
                j += 1
            out.append(item)
            i = j
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


def bold_spans(text: str) -> list:
    """``[(start, end, label)]`` for each bold span of a page, as the renderer reads it: over
    `inline_text`, whose offsets `pressed_names` and `tab_names` read the words around."""
    return [(m.start(), m.end(), m.group(2)) for m in _INLINE.finditer(inline_text(text))
            if m.group(2) is not None]


def segments(label: str) -> list:
    return [s.strip() for s in _SEP.split(label) if s.strip()]


def bold_names(texts: dict) -> set:
    """Every bold name the manual uses, each path's segments as names of their own."""
    out = set()
    for text in texts.values():
        for _s, _e, label in bold_spans(text):
            out.add(label)
            out.update(segments(label))
    return out


def pressed_names(texts: dict) -> list:
    """``(slug, label)`` for each bold label the prose uses as a control (the module's rule),
    paths and ellipsis labels left to their own checks."""
    out = []
    for slug, text in sorted(texts.items()):
        body = inline_text(text)
        spans = bold_spans(text)
        pressed = False
        for i, (start, end, label) in enumerate(spans):
            before = body[max(0, start - 30):start]
            joined = i > 0 and _JOIN.match(body[spans[i - 1][1]:start]) is not None
            pressed = (_PRESS.search(before) is not None or (joined and pressed)
                       or _NOUN.match(body[end:end + 10]) is not None)
            if pressed and not _SEP.search(label) and not label.endswith("…") \
                    and label not in KEYS:
                out.append((slug, label))
    return sorted(set(out))


def tab_names(texts: dict) -> list:
    """``(slug, label)`` for each bold label the prose calls a tab ("the **Intent** tab")."""
    out = []
    for slug, text in sorted(texts.items()):
        body = inline_text(text)
        out += [(slug, label) for _s, end, label in bold_spans(text)
                if re.match(r" tabs?\b", body[end:end + 6]) and not _SEP.search(label)]
    return sorted(set(out))


def dead_tabs(found: list, nav: set) -> list:
    """The tab names that are no navigation label (any case: the sidebar's group heads are
    drawn in capitals)."""
    places = {n.casefold() for n in nav}
    return [(slug, label) for slug, label in found if label.casefold() not in places]


def normal(label: str) -> str:
    """A label as one form, the manual's and the template's alike: each ``<placeholder>``, a
    count written ``N`` or ``M``, and a template's ``<x>`` become ``<x>``; a plural ending
    (``line(s)``, ``line<x>``, ``lines``) is dropped; spaces collapse."""
    s = re.sub(r"<[^<>]{1,40}>", PLACEHOLDER, label)
    s = re.sub(r"\b[NM]\b", PLACEHOLDER, s)
    s = re.sub(r"(?<=\w)\(s\)", "", s)
    s = re.sub(r"(?<=\w)" + re.escape(PLACEHOLDER), "", s)
    s = re.sub(r"(?:" + re.escape(PLACEHOLDER) + r"\s*){2,}", PLACEHOLDER + " ", s)
    s = re.sub(r"(?<=\w\w)s\b", "", s)      # one device, two devices: one name
    s = re.sub(r"\s+…", "…", s)              # "Save (<x>) …": a count's span before the mark
    return " ".join(s.split())


def _wild(label: str):
    """A normalised label as a pattern whose each placeholder is one value (a word, a name or
    an address), never a run of words."""
    parts = label.split(PLACEHOLDER)
    return re.compile(r"\S+".join(re.escape(p) for p in parts) + r"\Z")


class Names:
    """The manual's bold names, normalised, ready to match a control's label."""

    def __init__(self, names):
        self.exact = {normal(s) for n in names for s in [n, *segments(n)]}
        self.wild = [_wild(n) for n in self.exact if PLACEHOLDER in n]

    def enter(self, label: str) -> bool:
        """Whether a control's label is a name the manual uses."""
        want = normal(label)
        if want in self.exact:
            return True
        if PLACEHOLDER in want and any(_wild(want).match(n) for n in self.exact):
            return True
        return any(w.match(want) for w in self.wild)


def data_labelled(label: str) -> bool:
    """A label drawn wholly by data: no words of its own to name."""
    return not re.sub(re.escape(PLACEHOLDER) + r"|[\W_]", "", normal(label))


# ---------------------------------------------------------------- the product's side

#: An opening tag's attributes: a quoted value whole (Alpine's ``() => x`` holds a ">"), a
#: Jinja expression or statement whole, or any other character.
_ATTRS = r"((?:\"[^\"]*\"|'[^']*'|\{\{.*?\}\}|\{%.*?%\}|[^>\"'{]|\{(?![{%]))*)"
_OPEN = re.compile(r"<(button|a|summary)\b" + _ATTRS + ">", re.S)
_COMMENT = re.compile(r"\{#.*?#\}|<!--.*?-->", re.S)
_BUSY = re.compile(r'<span class="op-busy">.*?</span>', re.S)
#: A control's description beside its name: a ``<small>``, or an element whose class carries
#: ``menu-sub``, ``muted`` or ``faint`` (a menu row's "to startup (write memory) and as golden").
_DESCRIPTION = re.compile(r"<small\b[^>]*>.*?</small>|<(span|em|div|p)\b[^>]*\bclass=\"[^\"]*"
                          r"\b(?:menu-sub|muted|faint)\b[^\"]*\"[^>]*>.*?</\1>", re.S)
_DROPPED_CALLS = ("icon", "how", "info")


def _attr(attrs: str, name: str) -> str:
    m = re.search(rf'(?<![\w:.-]){name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def _member(tag: str, attrs: str, words: str) -> bool:
    classes = re.sub(r"\{[{%].*?[}%]\}", " ", _attr(attrs, "class")).split()
    if tag == "button":
        return True
    if tag == "summary":
        return "btn" in classes or "aria-haspopup" in attrs or re.search(r"\shx-", attrs) is not None
    return ("btn" in classes or 'role="menuitem"' in attrs or "data-op=" in attrs
            or words.rstrip().endswith("…"))


def branches(text: str) -> list:
    """Each way a template fragment's ``{% if %}`` blocks can read, other ``{% %}`` dropped."""
    tokens = re.split(r"(\{%-?\s*(?:if|elif|else|endif)\b.*?-?%\})", text, flags=re.S)
    pos = 0

    def kind(tok):
        m = re.match(r"\{%-?\s*(if|elif|else|endif)\b", tok)
        return m.group(1) if m else None

    def seq():
        """The readings up to the next elif, else or endif of the enclosing block."""
        nonlocal pos
        outs = [""]
        while pos < len(tokens) and kind(tokens[pos]) not in ("elif", "else", "endif"):
            tok = tokens[pos]
            pos += 1
            if kind(tok) != "if":
                outs = [o + tok for o in outs]
                continue
            alts, closed = seq(), False
            while pos < len(tokens):
                k = kind(tokens[pos])
                pos += 1
                if k == "endif":
                    break
                closed = closed or k == "else"
                alts += seq()
            if not closed:
                alts.append("")       # no else: the block can draw nothing
            outs = [o + a for o in outs for a in alts][:64]
        return outs

    ways = seq()
    while pos < len(tokens):          # a branch word the control sits inside: read past it
        pos += 1
        ways = [r + s for r in ways for s in seq()][:64]
    return ways


_HOLE = "\x00"
_EXPR = re.compile(r"\{\{-?(.*?)-?\}\}", re.S)
_FOR = re.compile(r"\{%-?\s*for\s+([\w\s,]+?)\s+in\s+(.+?)\s*-?%\}", re.S)
_SET = re.compile(r"\{%-?\s*set\s+(\w+)\s*=\s*(.+?)\s*-?%\}", re.S)
_MACRO = re.compile(r"\{%-?\s*macro\s+(\w+)\((.*?)\)\s*-?%\}", re.S)
_CAP = 32


def _python(expr: str):
    """A Jinja expression as a Python expression tree (``~`` joins strings), or None."""
    out, quote = [], None
    for ch in expr.strip():
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "~":
            ch = "+"
        out.append(ch)
    try:
        return ast.parse("".join(out), mode="eval").body
    except SyntaxError:
        return None


def readings(node, env: dict) -> list:
    """Each string a Jinja expression can draw, a value it fills a hole: a literal, each arm of
    a conditional or an ``or``, a join of readings, a literal table's ``.get``, and a name the
    template binds to literals (*env*)."""
    if node is None:
        return [_HOLE]
    if isinstance(node, ast.Constant):
        return [node.value if isinstance(node.value, str) else _HOLE]
    if isinstance(node, ast.IfExp):
        out = readings(node.body, env) + readings(node.orelse, env)
    elif isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        # An empty string is false: `x or y` draws y in its place.
        out = [r for v in node.values[:-1] for r in readings(v, env) if r] + \
              readings(node.values[-1], env)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        out = [a + b for a in readings(node.left, env) for b in readings(node.right, env)]
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
            node.func.attr == "get" and isinstance(node.func.value, ast.Dict):
        out = [r for v in node.func.value.values for r in readings(v, env)]
        out += [r for a in node.args[1:2] for r in readings(a, env)]
    elif isinstance(node, ast.Name) and node.id in env:
        out = list(env[node.id])
    else:
        return [_HOLE]
    return list(dict.fromkeys(out))[:_CAP]


def _calls(name: str, text: str) -> list:
    """Each ``name(...)`` call's argument nodes in *text*: ``(args, keywords)``."""
    out = []
    for m in re.finditer(rf"(?<![\w.]){re.escape(name)}\(", text):
        if re.search(r"macro\s+$", text[max(0, m.start() - 12):m.start()]):
            continue                  # the definition, not a call
        depth, i = 0, m.end() - 1
        for i in range(m.end() - 1, len(text)):
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            if depth == 0:
                break
        node = _python(text[m.start():i + 1])
        if isinstance(node, ast.Call):
            out.append((node.args, {k.arg: k.value for k in node.keywords}))
    return out


def environment(text: str, templates: dict) -> dict:
    """``{name: [reading, ...]}`` for each name a template binds to literal words: a loop over
    a literal list, a ``set`` to an expression, and a macro's parameter, read from every call
    of the macro in any template and its default."""
    env = {}

    def add(name, values):
        env.setdefault(name, [])
        env[name] = list(dict.fromkeys(env[name] + list(values)))[:_CAP]

    for m in _FOR.finditer(text):
        targets = [t.strip() for t in m.group(1).split(",")]
        try:
            items = ast.literal_eval(m.group(2).strip())
        except (ValueError, SyntaxError):
            continue
        for item in items if isinstance(items, (list, tuple)) else ():
            row = item if isinstance(item, tuple) and len(targets) > 1 else (item,)
            for t, v in zip(targets, row):
                add(t, [v if isinstance(v, str) else _HOLE])
    for m in _SET.finditer(text):
        add(m.group(1), readings(_python(m.group(2)), {}))
    for m in _MACRO.finditer(text):
        sig = _python(f"f({m.group(2)})")
        if not isinstance(sig, ast.Call):
            continue
        params = [a.id for a in sig.args if isinstance(a, ast.Name)] + \
                 [k.arg for k in sig.keywords]
        defaults = {k.arg: k.value for k in sig.keywords}
        for p in defaults:
            add(p, readings(defaults[p], {}))
        for other in templates.values():
            if m.group(1) + "(" not in other:
                continue
            for args, kws in _calls(m.group(1), _COMMENT.sub("", other)):
                for i, p in enumerate(params):
                    if i < len(args):
                        add(p, readings(args[i], {}))
                    elif p in kws:
                        add(p, readings(kws[p], {}))
    return env


def _expand(fragment: str, env: dict) -> list:
    """The fragment once for each way its ``{{ }}`` expressions can read; an icon or help
    link (`_DROPPED_CALLS`) draws no words."""
    outs = [""]
    last = 0
    for m in _EXPR.finditer(fragment):
        node = _python(m.group(1))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                node.func.id in _DROPPED_CALLS:
            choices = [" "]
        else:
            choices = readings(node, env)
        lit = fragment[last:m.start()]
        outs = [o + lit + c for o in outs for c in choices][:_CAP * 2]
        last = m.end()
    return [o + fragment[last:] for o in outs]


def _words(fragment: str) -> str:
    """A fragment's words as a person reads them, each value it fills a placeholder."""
    s = _EXPR.sub(_HOLE, fragment)
    s = re.sub(r"\{%.*?%\}", " ", s, flags=re.S)
    # Two sibling elements read as two words ("AI" "reading spend…"); any other tag joins
    # what is either side of it, as visible() reads it ("Save (<span>3</span>)…").
    s = re.sub(r"</[^>]*>\s*<(?!/)[^>]*>", " ", s)
    s = re.sub(r"<[^>]*>", "", s)
    s = s.replace("&amp;", "&").replace("&#39;", "'").replace("&nbsp;", " ")
    s = re.sub(_HOLE + r"+", _HOLE, " ".join(s.split()))
    return s.replace(_HOLE, PLACEHOLDER)


def _readings(fragment: str, env: dict) -> list:
    return sorted({w for b in branches(fragment) for e in _expand(b, env) for w in [_words(e)] if w})


def controls(name: str, text: str, env=None) -> list:
    """``[{"template", "labels", "names"}]`` for each control (the module's population):
    *labels* each way its words read, *names* its ``aria-label`` and ``title`` (the name it
    gives a screen reader or a hover; the manual naming either names the control). A control
    with no words is labelled by those. *env*: the names the template binds, `environment`."""
    text = _COMMENT.sub("", text)
    env = env or {}
    out = []
    for m in _OPEN.finditer(text):
        tag, attrs = m.group(1), m.group(2)
        close = text.find(f"</{tag}>", m.end())
        if close < 0:
            continue
        inner = _DESCRIPTION.sub(" ", _BUSY.sub(" ", text[m.end():close]))
        if not _member(tag, attrs, _words(inner)):
            continue
        names = _readings(_attr(attrs, "aria-label"), env) + _readings(_attr(attrs, "title"), env)
        labels = _readings(inner, env) or names
        if labels:
            out.append({"template": name, "labels": labels, "names": names})
    return out


def template_texts() -> dict:
    """``{file name: text}`` for every v2 template."""
    out = {}
    for f in source_index.tracked("templates/v2", suffix=".html", recursive=False):
        with open(f, encoding="utf-8") as fh:
            out[os.path.basename(f)] = fh.read()
    return out


def all_controls(templates: dict) -> list:
    """Every control of every template, each label it can read."""
    return [c for name, text in sorted(templates.items())
            for c in controls(name, text, environment(_COMMENT.sub("", text), templates))]


def label_of(control: dict) -> str:
    """The one label a control is listed by: its first reading with words of its own, else its
    first name with words of its own."""
    worded = [l for l in control["labels"] + control["names"] if not data_labelled(l)]
    return (worded or control["labels"])[0]


def split(controls_: list, names: set) -> tuple:
    """``(entered, unentered, data)``: the controls the manual names (any reading of its words,
    or its aria-label or title, or that name's lead before a colon, "In progress: <x>"), those
    it does not, and those whose every reading is data (`data_labelled`) with no name."""
    known = Names(names)
    entered_, gap, data = [], [], []
    for c in controls_:
        said = c["labels"] + c["names"] + [n.split(":")[0] for n in c["names"] if ":" in n]
        if all(data_labelled(s) for s in said):
            data.append(c)
        elif any(known.enter(s) for s in said if not data_labelled(s)):
            entered_.append(c)
        else:
            gap.append(c)
    return entered_, gap, data


def unentered(controls_: list, names: set) -> dict:
    """``{template: [label, ...]}`` for each control the manual does not name (`split`)."""
    out = {}
    for c in split(controls_, names)[1]:
        out.setdefault(c["template"], set()).add(label_of(c))
    return {k: sorted(v) for k, v in sorted(out.items())}


# ---------------------------------------------------------------- navigation labels

#: The class tokens of the frame's and the pages' navigation: a sidebar item and its group's
#: heading, a tab, a Settings scope.
NAV_CLASSES = frozenset(("nav-item", "nav-head", "tab", "scope-item"))
#: The manual's own table of device tabs to its anchors, not words a page draws.
_NOT_DRAWN_TABS = ("modules/manual.py",)
_ANY_OPEN = re.compile(r"<(a|span|div|button|summary|p)\b" + _ATTRS + ">", re.S)


def nav_labels(templates: dict) -> set:
    """Every place a person moves to, by its words: an element carrying a navigation class
    (`NAV_CLASSES`), its words whole and each bold or span inside it, a page's breadcrumb
    (class ``crumbs``) one segment at a time, and every label of a module-level ``*TABS``
    table in routes/ and modules/ (the pages that draw their tabs from a loop)."""
    out = set()
    for text in templates.values():
        text = _COMMENT.sub("", text)
        for m in _ANY_OPEN.finditer(text):
            classes = set(re.sub(r"\{[{%].*?[}%]\}", " ", _attr(m.group(2), "class")).split())
            nav, crumbs = classes & NAV_CLASSES, "crumbs" in classes
            if not (nav or crumbs):
                continue
            close = text.find(f"</{m.group(1)}>", m.end())
            inner = text[m.end():close]
            for reading in branches(inner):
                pieces = [reading] + re.findall(r"<(?:b|span)\b[^>]*>(.*?)</(?:b|span)>",
                                                reading, re.S)
                for piece in pieces:
                    words = re.sub(r"\s*\(\s*<x>\s*\)", "", _words(piece)).strip()
                    for w in (_SEP.split(words) if crumbs else [words]):
                        if w and PLACEHOLDER not in w:
                            out.add(w.strip())
    for f in source_index.tracked("routes", "modules", suffix=".py"):
        if os.path.relpath(f, source_index.ROOT).replace(os.sep, "/") in _NOT_DRAWN_TABS:
            continue
        for node in source_index.tree(f).body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id.endswith("TABS") for t in node.targets):
                continue
            v = node.value
            if isinstance(v, ast.Dict):
                out.update(x.value for x in v.values
                           if isinstance(x, ast.Constant) and isinstance(x.value, str))
            elif isinstance(v, (ast.Tuple, ast.List)):
                for e in v.elts:
                    if isinstance(e, ast.Tuple) and len(e.elts) >= 2 and \
                            isinstance(e.elts[1], ast.Constant) and isinstance(e.elts[1].value, str):
                        out.add(e.elts[1].value)
    return out


# ---------------------------------------------------------------- paths

_STOP = re.compile(r"[,.;:()\[\]*`\"“”']|\*\*|'s\b|’s\b")


def _link_text(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", text)


def paths(texts: dict) -> list:
    """``(slug, [(lead words), seg, ..., (tail words)])`` for each path the manual writes: the
    words before the first separator (up to five, back to punctuation), each segment between
    separators, the words after the last (up to five, up to punctuation)."""
    out = []
    for slug, text in sorted(texts.items()):
        body = _link_text(prose(text))
        body = re.sub(r"`[^`\n]*`", " ", body)
        for line in body.splitlines():
            if " › " not in line:
                continue
            parts = line.split(" › ")
            idx = 0                   # each chain of separators on the line, in turn
            while idx < len(parts) - 1:
                lead = _STOP.split(parts[idx])[-1].split()[-5:]
                chain = []
                j = idx + 1
                while j < len(parts):
                    seg = parts[j]
                    cut = _STOP.search(seg)
                    if j < len(parts) - 1 and cut is None:
                        chain.append(seg.strip())
                        j += 1
                        continue
                    tail = (seg[:cut.start()] if cut else seg).split()[:5]
                    chain.append(tuple(tail))
                    break
                out.append((slug, tuple(lead), tuple(chain[:-1]) if chain else (),
                            chain[-1] if chain else ()))
                idx = j if j > idx else idx + 1
    return out


def _bounded(words: str):
    return re.compile(r"(?<![\w-])" + re.escape(words) + r"(?![\w-])")


def dead_paths(found: list, nav: set, drawn: str) -> list:
    """``(slug, path as written, why)`` for each path whose lead names no navigation label,
    whose middle segment the product does not draw, or whose tail the product does not draw."""
    bad = []
    places = {n.casefold() for n in nav}

    def is_drawn(words):
        return words in drawn and _bounded(words).search(drawn) is not None

    for slug, lead, middle, tail in found:
        shown = " › ".join([" ".join(lead), *middle, " ".join(tail)])
        heads = [" ".join(lead[k:]).casefold() for k in range(len(lead))]
        if not any(h in places for h in heads):
            bad.append((slug, shown, f"{' '.join(lead)!r} ends in no sidebar item, tab or control"))
            continue
        for seg in middle:
            if not is_drawn(seg):
                bad.append((slug, shown, f"{seg!r} is drawn nowhere"))
        prefixes = [" ".join(tail[:k]) for k in range(len(tail), 0, -1)]
        if tail and not any(is_drawn(p) for p in prefixes):
            bad.append((slug, shown, f"{' '.join(tail)!r} is drawn nowhere"))
    return bad


# ---------------------------------------------------------------- the ratchets

#: The controls whose every label and name is data (a Python-built card's button words, a
#: loop over a reader's choices): 9 when C1844 landed (2026-10-28). A ceiling: a new one is a
#: control no text can name, so the count may not rise (tests/ratchet_lists.py).
DATA_LABELLED_CEILING = 9

#: Each v2 control the manual does not name yet (C1844's gap, 2026-10-28: 121 of 538 controls;
#: 2 after C2144's burn-down, 2026-10-29),
#: by template, each listed by `label_of`. Only shrinks (tests/ratchet_lists.py): a control
#: added without a manual entry fails `test_every_control_has_a_manual_entry_or_is_known`, and
#: naming one in the manual (in bold, on the page for its screen or operation) fails the same
#: test until its line here is removed.
KNOWN_UNENTERED = {
    '_network_picker_items.html': ['<x> Opening <x>…'],
    'base.html': ['AI reading spend… …'],
}
