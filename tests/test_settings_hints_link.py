"""A page that says where something is set up links there (Stage 5 step 6): "(Settings >
Integrations)" stood in plain text on nine pages, one of them naming a tab that holds no such
card (a device's NetBox tab, C4277). Each now links the network's own Integrations tab
(`integrations_link` in _macros.html) or the page it names.

- No v2 template names Settings' Integrations as plain text: every mention is inside a link
  (Jinja comments aside). The scan has a floor on the links drawn and finds a planted mention.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates", "v2")
COMMENT = re.compile(r"\{#.*?#\}", re.S)
LINK = re.compile(r"<a\b[^>]*>.*?</a>", re.S)
PLAIN = re.compile(r"Settings\s*(?:›|&gt;|>|&rsaquo;)\s*(?:\{\{[^}]*\}\}\s*›\s*)?Integrations")


def _plain(text: str) -> list:
    """The plain-text mentions in *text*, comments and links taken out first."""
    return PLAIN.findall(LINK.sub("", COMMENT.sub("", text)))


def test_every_mention_of_settings_integrations_is_a_link():
    found, links = [], 0
    for name in sorted(os.listdir(TEMPLATES)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as fh:
            text = fh.read()
        links += len(re.findall(r"integrations_link\(", text))
        found += [name for _m in _plain(text)]
    assert links >= 10, f"integrations_link is drawn at {links} sites, under the 10 measured"
    assert found == [], f"Settings' Integrations named as plain text, not a link: {found}"
    assert _plain("<p>cannot be read here (Settings &gt; Integrations).</p>")
    assert not _plain('<p>Set it up on <a href="/x">Settings › Lab › Integrations</a>.</p>')
