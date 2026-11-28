"""An AI answer's words as the page draws them (the assistant's chat, the operator's order of
2026-11-28: "the answer text, markdown rendered: lists, code, tables"): a small markdown subset
rendered on the server, every character of the model's words escaped first, so no HTML the model
wrote reaches the page.

**What it draws:** paragraphs (a blank line between), line breaks inside one, ``-``/``*`` and
``1.`` lists (one level of nesting by indent), fenced code blocks (````` ``` `````), headings
(``#`` to ``###``, drawn as strong lines: an answer has no page outline), pipe tables (a header
row, its ``---`` rule, then rows), and inline ``code``, ``**strong**`` and ``*emphasis*``.

**What it never draws:** a link or an image. A markdown link is drawn as its words with its
target after them as text, so nothing the model wrote becomes an address the page follows; the
answer's links are its sources', which Mercury's check built (`assistant.drawn`). No raw HTML: a
tag the model wrote is drawn as the characters it is.

Why not the manual's renderer (`manual.render`): it resolves the manual's own links into
addresses, inlines the manual's diagram files and raises on what a manual page must not hold;
an answer needs every construct escaped and no address or file followed.
"""
import html
import re

from markupsafe import Markup

_INLINE = re.compile(r"`([^`\n]+)`|\*\*([^*\n]+)\*\*|(?<![\w*])\*([^*\n]+)\*(?![\w*])"
                     r"|\[([^\]\n]+)\]\(([^)\s]+)\)")
_BULLET = re.compile(r"^( *)(?:[-*] |(\d+)[.)] )(.*)$")
_HEAD = re.compile(r"^#{1,3} (.+)$")
_RULE = re.compile(r"^\|? *:?-{3,}:? *(\| *:?-{3,}:? *)*\|? *$")


def _inline(text: str) -> str:
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        code, strong, em, label, target = m.groups()
        if code is not None:
            out.append(f"<code>{html.escape(code)}</code>")
        elif strong is not None:
            out.append(f"<strong>{_inline(strong)}</strong>")
        elif em is not None:
            out.append(f"<em>{_inline(em)}</em>")
        else:
            out.append(f"{_inline(label)} ({html.escape(target)})")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _cells(line: str) -> list:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def render(text) -> Markup:
    """*text* (an AI answer's words) as escaped HTML: the subset above, nothing else."""
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    out, para, items = [], [], []

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def flush_list():
        if not items:
            return
        stack, html_ = [], []
        for indent, ordered, body in items:
            level = 1 if indent >= 2 and stack else 0
            tag = "ol" if ordered else "ul"
            while len(stack) > level + 1:
                html_.append(f"</li></{stack.pop()}>")
            if len(stack) < level + 1:
                html_.append(f"<{tag}>")
                stack.append(tag)
            else:
                html_.append("</li>")
            html_.append(f"<li>{_inline(body)}")
        while stack:
            html_.append(f"</li></{stack.pop()}>")
        out.append("".join(html_))
        items.clear()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.lstrip().startswith("```"):
            flush_para()
            flush_list()
            code = []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _RULE.match(lines[i + 1].strip()):
            flush_para()
            flush_list()
            head = _cells(line)
            i += 2
            body = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body.append(_cells(lines[i]))
                i += 1
            rows = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                           for r in body)
            out.append('<div class="md-table"><table><thead><tr>'
                       + "".join(f"<th>{_inline(c)}</th>" for c in head)
                       + f"</tr></thead><tbody>{rows}</tbody></table></div>")
            continue
        m = _BULLET.match(line)
        if m:
            flush_para()
            items.append((len(m.group(1)), m.group(2) is not None, m.group(3)))
            i += 1
            continue
        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue
        h = _HEAD.match(line)
        if h:
            flush_para()
            flush_list()
            out.append(f'<p class="md-head"><strong>{_inline(h.group(1))}</strong></p>')
            i += 1
            continue
        if items and line.startswith("  "):
            # A list item's continued line.
            indent, ordered, body = items[-1]
            items[-1] = (indent, ordered, body + " " + line.strip())
            i += 1
            continue
        flush_list()
        para.append(line)
        i += 1
    flush_para()
    flush_list()
    return Markup("".join(out))
