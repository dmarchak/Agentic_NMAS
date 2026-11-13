"""One time zone per screen (docs/UI_RULES.md; the operator, 2026-11-11: "The card mixes "20:01
UTC" with steps in MST"; 2026-11-12: "The server draws times in the viewer's stored time zone
(a per-person setting like display names, defaulting from the browser on first visit), so no
UTC flashes before the script runs"): every time a v2 template draws for a person goes through
ONE macro, `_macros.clock`, drawn by the server in the viewer's kept zone
(modules/time_zones.py), the zone named once per response, the record's UTC instant on hover
and in ``datetime=``; a verified person with no zone kept sends their browser's once.

The scan parses each template (Jinja's lexer, and an HTML context tracker over the text it
yields), never a substring of prose: in a person's text (outside every attribute, comment and
the browser-written time elements) it refuses an ISO time sliced to its clock (``[11:16]``,
``[11:19]``, ``[5:10]``), an ISO time worded by replacing its ``T`` or ``Z``, and "UTC" set as
a time's suffix (``{{ t }} UTC``, ``~ ' UTC'``). What it leaves: "UTC" in prose about whole UTC
days or a typed field's unit (a time a person TYPES is Phase 2's), and a date cut to ``[:10]``
(which a commit's short hash shares). The words Python builds for a screen are not templates:
tests/test_no_utc_drawn.py reads them on every response the v2 walk receives (C3290)."""

import ast
import json
import os
import re
import stat
import time
from contextlib import contextmanager
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "templates" / "v2"

#: Where an element the browser writes in the viewer's zone is built: `clock` and
#: `clock_option` (every screen), and History › Query's answer (`when`, its spans and its
#: column heads' zone, static/js/nmas_logq.js), all the viewer's zone with UTC on hover.
BROWSER_WRITTEN = {"data-clock": {"_macros.html"}, "data-lq-when": {"_history_ask_parts.html"}}

CLOCK_SLICES = {(11, 16), (11, 19), (5, 10)}


class _Html:
    """The HTML context of the next character: text, a tag, an attribute's value, a comment,
    and whether it is inside a browser-written time element."""

    def __init__(self):
        self.state, self.tag, self.inside = "text", "", 0

    def copy(self):
        h = _Html()
        h.state, h.tag, h.inside = self.state, self.tag, self.inside
        return h

    def feed(self, s):
        for ch in s:
            st = self.state
            if st == "text":
                if ch == "<":
                    self.state, self.tag = "tag", ""
            elif st == "comment":
                self.tag = (self.tag + ch)[-3:]
                if self.tag == "-->":
                    self.state = "text"
            elif st in ("dq", "sq"):
                self.tag += ch
                if ch == ('"' if st == "dq" else "'"):
                    self.state = "tag"
            else:  # in a tag
                self.tag += ch
                if self.tag == "!--":
                    self.state, self.tag = "comment", ""
                elif ch == '"':
                    self.state = "dq"
                elif ch == "'":
                    self.state = "sq"
                elif ch == ">":
                    self.close_tag()

    def close_tag(self):
        self.state = "text"
        name = re.match(r"/?[\w-]*", self.tag).group(0).lower()
        if name == "time" and any(a in self.tag for a in BROWSER_WRITTEN):
            self.inside += 1
        elif name == "/time" and self.inside:
            self.inside -= 1

    def where(self):
        if self.state in ("dq", "sq", "tag"):
            return "attribute"
        if self.state == "comment":
            return "comment"
        return "browser-written" if self.inside else "text"


def _ints(tok):
    return int(tok[2]) if tok[1] == "integer" else None


def bare_utc_times(source: str) -> list:
    """Each place *source* draws a bare UTC time for a person, as ``(line, what)``."""
    env = jinja2.Environment()
    toks = list(env.lex(source))
    html, out, i = _Html(), [], 0
    after_expr = False
    while i < len(toks):
        line, kind, val = toks[i]
        if kind == "data":
            if after_expr and html.where() == "text" and re.match(r" UTC\b", val):
                out.append((line, '"UTC" after a time'))
            html.feed(val)
            after_expr = False
        elif kind in ("variable_begin", "block_begin"):
            end = "variable_end" if kind == "variable_begin" else "block_end"
            j, expr = i + 1, []
            while j < len(toks) and toks[j][1] != end:
                # The lexer's raw tokens: its whitespace dropped, a string's quotes read.
                l2, k2, v2 = toks[j]
                if k2 != "whitespace":
                    expr.append((l2, k2, ast.literal_eval(v2) if k2 == "string" else v2))
                j += 1
            if html.where() == "text":
                for k, (l2, k2, v2) in enumerate(expr):
                    if k2 == "string" and re.match(r"\s+UTC\b", v2):
                        out.append((l2, f"{v2!r} as a time's suffix"))
                    if (k2 == "name" and v2 == "replace" and k + 2 < len(expr)
                            and expr[k + 2][1] == "string" and expr[k + 2][2] in ("T", "Z")):
                        out.append((l2, f"an ISO time worded by replace({expr[k + 2][2]!r}, …)"))
                    if (k2 == "operator" and v2 == "[" and k + 4 < len(expr)
                            and expr[k + 2][2] == ":" and expr[k + 4][2] == "]"
                            and (_ints(expr[k + 1]), _ints(expr[k + 3])) in CLOCK_SLICES):
                        out.append((l2, f"an ISO time sliced [{expr[k + 1][2]}:{expr[k + 3][2]}]"))
            # An expression in a person's text may end in a time: a "UTC" right after it is
            # that time's suffix. A block ({% if %}) carries nothing of its own.
            after_expr = kind == "variable_begin" or after_expr
            i = j
        i += 1
    return out


def templates():
    """Every v2 template git tracks (an untracked copy is no program)."""
    from tests import source_index
    return [Path(p) for p in source_index.tracked("templates/v2", suffix=".html")]


class TestTheScanFindsWhatItRefuses:
    """The scan's planted cases: each refused form is found, each form it leaves is left."""

    @pytest.mark.parametrize("src, found", [
        ("<p>at {{ r.at[11:16] }}</p>", 1),
        ("<p>at {{ r.at[11:19] }} UTC</p>", 2),
        ("<p>{{ r.at | replace('T', ' ') }}</p>", 1),
        ("<p>{{ r.at | replace('Z', '') }}</p>", 1),
        ("<p>{{ stamp(c.at, c.at[11:19] ~ ' UTC') }}</p>", 2),
        ("<p>since {{ b.started }} UTC by</p>", 1),
        ("<td>{{ l.at_iso[5:10] }}</td>", 1),
        ('<time datetime="{{ x }}" title="{{ x }}">{{ x[11:16] }} UTC</time>', 2),
    ])
    def test_a_bare_utc_time_is_found(self, src, found):
        assert len(bare_utc_times(src)) == found, bare_utc_times(src)

    @pytest.mark.parametrize("src", [
        '<span title="{{ r.at[11:19] }} UTC">x</span>',
        "<p>{{ clock(r.at) }}, summed by UTC day</p>",
        "<p>from {{ x.first_day }} to {{ x.last_day }} (UTC).</p>",
        '<time class="clock" datetime="{{ w.iso }}" data-clock>{{ w.iso[11:16] }} UTC</time>',
        '<time datetime="{{ w.iso }}" data-lq-when="dt">{{ w.words }}{% if 1 %} UTC{% endif %}</time>',
        "{#- {{ r.at[11:16] }} UTC -#}<p>{{ sha[:10] }}</p>",
        "<!-- {{ r.at[11:16] }} UTC -->",
        '<input placeholder="2026-11-20 18:00 UTC">',
    ])
    def test_what_is_not_a_drawn_utc_time_is_left(self, src):
        assert bare_utc_times(src) == []


class TestEveryTemplate:
    """Every v2 template, the whole population: none draws a bare UTC time."""

    def test_the_population_is_every_v2_template(self):
        found = templates()
        assert len(found) >= 250, f"{len(found)} templates read under {V2}"
        uses = sum(len(re.findall(r"\bclock\(", p.read_text())) for p in found)
        assert uses >= 100, f"only {uses} calls of the one clock: the conversion went backwards"

    def test_no_template_draws_a_bare_utc_time(self):
        bare = {str(p.relative_to(ROOT)): got for p in templates()
                if (got := bare_utc_times(p.read_text()))}
        assert not bare, ("a time drawn for a person goes through _macros.clock (local time, "
                          "the zone named once, UTC on hover):\n"
                          + "\n".join(f"{f}:{n}: {w}" for f, g in bare.items() for n, w in g))

    def test_the_browser_written_time_is_built_in_its_one_place(self):
        """A template writes ``data-clock`` (or History › Query's ``data-lq-when``) only in
        the macro that owns it: every other template calls `clock`."""
        stray = []
        for p in templates():
            src = p.read_text()
            for attr, homes in BROWSER_WRITTEN.items():
                for m in re.finditer(r"<(?:time|option)\b[^>]*\b" + attr + r"\b", src):
                    if p.name not in homes:
                        stray.append(f"{p.relative_to(ROOT)}:{src[:m.start()].count(chr(10)) + 1}")
        assert not stray, stray


@contextmanager
def zone(tz):
    was = os.environ.get("TZ")
    os.environ["TZ"] = tz
    time.tzset()
    try:
        yield
    finally:
        if was is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = was
        time.tzset()


class TestTheServersWords:
    """`routes.v2.clock_words` outside a request, or for a viewer with no zone kept: the
    instant, the UTC for the hover, and the words in the host's zone, named."""

    def test_an_instant_in_the_hosts_zone_with_utc_kept(self):
        from routes.v2 import clock_words
        with zone("America/Denver"):
            got = clock_words("2026-11-08T19:41:07Z", "seconds")
        assert got == {"iso": "2026-11-08T19:41:07Z", "utc": "2026-11-08 19:41:07 UTC",
                       "words": "12:41:07 MST"}

    @pytest.mark.parametrize("mode, words", [
        ("", "19:41 UTC"), ("seconds", "19:41:07 UTC"), ("date", "Nov 8 19:41 UTC"),
        ("date-seconds", "Nov 8 19:41:07 UTC"), ("day", "Nov 8 2026")])
    def test_each_mode(self, mode, words):
        from routes.v2 import clock_words
        with zone("UTC"):
            assert clock_words("2026-11-08T19:41:07Z", mode)["words"] == words

    @pytest.mark.parametrize("value", ["2026-11-08T19:41:07Z", "2026-11-08T19:41:07+00:00",
                                       "2026-11-08T19:41:07", "2026-11-08 19:41:07",
                                       1794166867, 1794166867.0])
    def test_every_recorded_shape_is_the_one_instant_in_utc(self, value):
        from routes.v2 import clock_words
        with zone("Asia/Kolkata"):
            got = clock_words(value, "seconds")
        assert got["utc"] == "2026-11-08 19:41:07 UTC" and got["words"] == "01:11:07 IST"
        assert got["iso"].startswith("2026-11-08T19:41:07")

    @pytest.mark.parametrize("value", [None, "", "not a time", False])
    def test_no_instant_is_none(self, value):
        from routes.v2 import clock_words
        assert clock_words(value) is None

    def test_the_macro_draws_it_with_utc_on_its_hover(self):
        from flask import render_template_string
        import app as A
        with zone("America/Denver"), A.app.test_request_context("/v2/"):
            got = render_template_string(
                '{% from "v2/_macros.html" import clock %}'
                '{{ clock("2026-11-08T19:41:07Z", "seconds", note="as read") }}|{{ clock("") }}'
                '|{{ clock(none, missing="—") }}|{{ clock("soon") }}')
        assert got == ('<time class="clock" datetime="2026-11-08T19:41:07Z" data-clock="seconds" '
                       'title="2026-11-08 19:41:07 UTC · as read">12:41:07 MST</time>|'
                       '<span class="clock">at an unrecorded time</span>|'
                       '<span class="clock">—</span>|<span class="clock">soon</span>')


# ── The viewer's kept zone (modules/time_zones.py, routes/settings_v2.time_zone) ─────────────

from tests.conftest import TEST_PERSON  # noqa: E402
from tests.test_settings_v2 import networks  # noqa: E402,F401 (the fixture: a temporary store)

CARD = "/v2/settings/installation/time-zone"
JUL, NOV = "2026-07-08T19:41:07Z", "2026-11-08T19:41:07Z"


def TZ():
    from modules import time_zones
    return time_zones


@pytest.fixture
def kept(networks):  # noqa: F811
    """The test's own data folder, and the file the store keeps."""
    return {"client": networks["client"], "path": networks["dir"] / "time_zones.json"}


@contextmanager
def kept_zone(zone_name, person=TEST_PERSON):
    """*person* reads every screen in *zone_name* while the block runs (their kept zone, set
    as their Change… sets it); the store this made is removed after."""
    path = TZ()._path()
    was = open(path, "rb").read() if os.path.exists(path) else None
    try:
        _keep(zone_name, person=person)
        yield
    finally:
        if was is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "wb") as fh:
                fh.write(was)


@contextmanager
def first_visit(person=TEST_PERSON, bound_s=10.0):
    """After a browser test has opened a page as *person*'s first visit: wait (by the store,
    at most *bound_s*: the send measured under 1 s, 2026-11-12) until the page has kept the
    browser's zone, and yield it; the test opens its page again, drawn by the server in that
    zone. The store the visit made is removed after, so no later test of this process reads
    it. (The test names each page it opens itself, so tests/presence_only.py reads them.)"""
    path = TZ()._path()
    try:
        end = time.time() + bound_s
        while not TZ().stored(person):
            assert time.time() < end, f"no zone was kept within {bound_s} s of the first visit"
            time.sleep(0.1)
        yield TZ().stored(person)
    finally:
        if os.path.exists(path):
            os.remove(path)


def _keep(zone_name, source="person", person=TEST_PERSON):
    return TZ().set_zone(person, zone_name, by=person, actor_verified="access", source=source)


def _draw(src, headers=None):
    from flask import render_template_string
    import app as A
    with A.app.test_request_context("/v2/", headers=headers or {}):
        return render_template_string('{% from "v2/_macros.html" import clock %}' + src)


def _words(html):
    return re.findall(r"<time [^>]*>([^<]*)</time>", html)


class TestTheViewersZone:
    """Every time a page draws is in the viewer's kept zone, the zone named once per response."""

    def test_a_kept_zone_draws_the_page_in_it_naming_it_once(self, kept):
        _keep("Asia/Kolkata")
        with zone("America/Denver"):
            got = _draw('{{ clock("%s", "seconds") }} {{ clock("%s") }}' % (NOV, NOV))
        assert _words(got) == ["01:11:07 IST", "01:11"], got
        assert got.count('title="2026-11-08 19:41:07 UTC"') == 2
        assert got.count(f'datetime="{NOV}"') == 2

    def test_a_time_across_a_daylight_saving_change_names_its_own_zone(self, kept):
        _keep("America/Denver")
        got = _draw('{{ clock("%s") }} {{ clock("%s") }} {{ clock("%s") }}' % (NOV, JUL, NOV))
        assert _words(got) == ["12:41 MST", "13:41 MDT", "12:41"], got

    def test_a_fragment_names_only_a_zone_unlike_its_page_s(self, kept):
        _keep("UTC")
        got = _draw('{{ clock("%s") }} {{ clock("%s", "day") }}' % (NOV, NOV),
                    headers={"HX-Request": "true"})
        assert _words(got) == ["19:41", "Nov 8 2026"], got

    def test_a_picker_s_choice_names_its_zone_and_leaves_the_page_s_naming(self, kept):
        _keep("UTC")
        got = _draw('{% from "v2/_macros.html" import clock_option %}'
                    '{{ clock_option("run-1", "run-1 · started {at}", "' + NOV + '") }}'
                    '{{ clock("' + NOV + '") }}')
        assert ">run-1 · started Nov 8 19:41:07 UTC</option>" in got, got
        assert _words(got) == ["19:41 UTC"], got

    @pytest.mark.real_identity
    def test_a_viewer_with_no_identity_reads_the_host_s_zone_named(self, kept):
        _keep("Asia/Kolkata")
        with zone("America/Denver"):
            got = _draw('{{ clock("%s") }}' % NOV)
        assert _words(got) == ["12:41 MST"], got

    def test_an_unreadable_store_draws_the_host_s_zone(self, kept):
        kept["path"].write_text("not json", encoding="utf-8")
        with zone("America/Denver"):
            got = _draw('{{ clock("%s") }}' % NOV)
        assert _words(got) == ["12:41 MST"], got


class TestTheStore:
    def test_a_zone_is_kept_with_who_set_it_and_where_from_owner_only(self, kept):
        out = _keep("Europe/London")
        assert (out["zone"], out["was"], out["nothing"]) == ("Europe/London", "", False)
        table = json.loads(kept["path"].read_text())
        assert set(table[TEST_PERSON]) == {"zone", "set_by", "actor_verified", "at", "source"}
        assert (table[TEST_PERSON]["source"], table[TEST_PERSON]["set_by"]) == ("person",
                                                                               TEST_PERSON)
        assert stat.S_IMODE(os.stat(kept["path"]).st_mode) == 0o600

    @pytest.mark.parametrize("bad", ["Mars/Olympus", "Mountain Time", "../etc/passwd",
                                     "/etc/localtime", "", "  "])
    def test_a_zone_zoneinfo_does_not_know_is_refused_naming_it(self, kept, bad):
        with pytest.raises(TZ().Refused) as said:
            _keep(bad)
        assert (f"'{bad}'" in str(said.value)) if bad.strip() else "none was given" in str(
            said.value)
        assert not kept["path"].exists()

    def test_the_browser_s_zone_never_replaces_one_kept(self, kept):
        _keep("Europe/London")
        out = _keep("America/Denver", source="browser")
        assert out["nothing"] and TZ().stored(TEST_PERSON) == "Europe/London"

    def test_the_browser_s_zone_is_kept_on_a_first_visit(self, kept):
        out = _keep("America/Denver", source="browser")
        assert not out["nothing"] and TZ().stored(TEST_PERSON) == "America/Denver"
        assert json.loads(kept["path"].read_text())[TEST_PERSON]["source"] == "browser"

    def test_another_person_s_zone_is_refused(self, kept):
        with pytest.raises(TZ().Refused) as said:
            TZ().set_zone("sam@example.invalid", "UTC", by=TEST_PERSON, actor_verified="access")
        assert "one person's own" in str(said.value)

    def test_an_unreadable_store_refuses_the_write_and_keeps_its_bytes(self, kept):
        kept["path"].write_text("not json", encoding="utf-8")
        with pytest.raises(TZ().Unreadable):
            _keep("UTC")
        assert kept["path"].read_text() == "not json"


class TestTheRoute:
    def test_change_saves_the_viewer_s_own_and_says_so(self, kept):
        r = kept["client"].post(CARD + "/save", data={"zone": "Asia/Kolkata"},
                                headers={"HX-Request": "true"})
        body = r.get_data(as_text=True)
        assert r.status_code == 200 and "now drawn in <strong>Asia/Kolkata</strong>" in body
        assert TZ().stored(TEST_PERSON) == "Asia/Kolkata"

    def test_an_unknown_zone_is_refused_in_place_naming_it(self, kept):
        r = kept["client"].post(CARD + "/save", data={"zone": "Mars/Olympus"},
                                headers={"HX-Request": "true"})
        body = r.get_data(as_text=True)
        assert r.status_code == 409 and "&#39;Mars/Olympus&#39; is not one" in body, body
        assert 'value="Mars/Olympus"' in body and not kept["path"].exists()

    def test_the_first_visit_s_send_keeps_the_browser_s_and_then_nothing_more(self, kept):
        page = kept["client"].get("/v2/").get_data(as_text=True)
        assert f'data-tz-first="{CARD}/save"' in page, "a first visit asks for the browser's zone"
        r = kept["client"].post(CARD + "/save", data={"zone": "America/Denver",
                                                      "source": "browser"})
        assert r.status_code == 200 and TZ().stored(TEST_PERSON) == "America/Denver"
        again = kept["client"].get("/v2/").get_data(as_text=True)
        assert "data-tz-first" not in again, "once kept, no page asks again"

    def test_the_card_says_where_the_zone_came_from(self, kept):
        assert "none is kept for you yet" in kept["client"].get(CARD).get_data(as_text=True)
        kept["client"].post(CARD + "/save", data={"zone": "America/Denver", "source": "browser"})
        body = kept["client"].get(CARD).get_data(as_text=True)
        assert "<strong>America/Denver</strong>" in body and "from your browser" in body
        r = kept["client"].post(CARD + "/save", data={"zone": "Europe/London"},
                                headers={"HX-Request": "true"})
        assert "in place of America/Denver" in r.get_data(as_text=True)
        body = kept["client"].get(CARD).get_data(as_text=True)
        assert "<strong>Europe/London</strong>" in body and "chosen by you" in body
