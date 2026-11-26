"""The document page's parts (templates/v2/_doc.html; the operator's GUI pick, 2026-11-25: C,
"Document"): the title and what it is a page of, the one sentence, and the outline beside the
sections. Each part rendered through the app's own template environment, as a page that adopts
it renders it.
"""
import re

import pytest

PAGE = """{% from "v2/_doc.html" import doc_page, doc_head, doc_summary %}
{% call doc_page(outline) %}
{% call doc_head("Settings", "Default · 12 devices") %}<a class="btn" href="#x">Act</a>{% endcall %}
{% call doc_summary() %}<strong>Two settings differ</strong> from the defaults.{% endcall %}
<section id="heal">body-heal</section><section id="ai">body-ai</section>
{% endcall %}"""


@pytest.fixture()
def render():
    import app as A

    def go(**kw):
        ctx = {"outline": None}
        ctx.update(kw)
        with A.app.test_request_context("/"):
            return A.app.jinja_env.from_string(PAGE).render(**ctx)
    return go


def _render(source, **ctx):
    import app as A
    with A.app.test_request_context("/"):
        return A.app.jinja_env.from_string(source).render(**ctx)


def test_the_head_draws_the_title_what_it_is_of_and_its_actions(render):
    html = render()
    head = re.search(r'<div class="doc-head">(.*?)</div>\s*<p', html, re.S).group(1)
    assert '<h1>Settings<span class="doc-kind">Default · 12 devices</span></h1>' in head
    assert '<div class="doc-acts"><a class="btn" href="#x">Act</a></div>' in head


def test_a_head_without_actions_draws_no_empty_actions():
    html = _render('{% from "v2/_doc.html" import doc_head %}{{ doc_head("Fixes") }}')
    assert "<h1>Fixes</h1>" in html and "doc-acts" not in html and "doc-kind" not in html


def test_the_summary_is_its_own_line(render):
    html = render()
    assert '<p class="doc-summary"><strong>Two settings differ</strong> from the defaults.</p>' in html


def test_the_outline_links_each_section_and_is_absent_without_one(render):
    html = render(outline=[{"key": "heal", "title": "Self-healing", "state": "Dry run"},
                           {"key": "ai", "title": "AI"}])
    assert '<div class="doc-page doc-page-outlined">' in html
    nav = re.search(r'<nav class="doc-outline" aria-label="On this page">(.*?)</nav>', html, re.S)
    links = re.findall(r'<a href="#(\w+)">(.*?)</a>', nav.group(1))
    assert links == [("heal", 'Self-healing<span class="doc-outline-st">Dry run</span>'),
                     ("ai", "AI")]
    for key, _t in links:
        assert f'id="{key}"' in html, "every outline link has its section"
    bare = render()
    assert '<div class="doc-page">' in bare and "doc-outline" not in bare


def test_a_wide_page_says_so_and_a_page_is_the_reading_measure_unless_asked():
    page = ('{% from "v2/_doc.html" import doc_page %}'
            '{% call doc_page(none, wide=w) %}x{% endcall %}')
    assert '<div class="doc-page doc-page-wide">' in _render(page, w=True)
    narrow = _render(page, w=False)
    assert '<div class="doc-page">' in narrow and "doc-page-wide" not in narrow
