"""No v2 response shows a person a time in UTC: every time a person sees, on the page or in a
record's details, is in the viewer's zone, its UTC instant on the hover (one time zone per
screen, docs/UI_RULES.md; the operator, 2026-11-13, C3290: "every time a person sees, in the
page or in record details, goes through the viewer's zone").

**The population, by property:** every HTML response the v2 walk receives (tests/v2_context.py's
measurement: every page tests/interface_pages.py reaches from its starts, every fragment a page
or a fragment asks for, its records' lazily loaded parts among them, and every request its
providers make, GET and POST, with their planted records), read once by tests/utc_drawn.py as
each response arrives, in a viewer zone that is not UTC (`WALK_ZONE`). A record drawn closed is
read whole: it is what a person sees when they open it.

**What it assumes stays true:** the walk's viewer has a kept zone (the walk sets it as
`viewer_zone` reads it); a response the walk never makes is not read (the walk's own floors,
tests/test_v2_context_is_drawn.py, hold what it reaches); a time written by the browser's script
after the page arrives is not seen (v2 draws on the server). What is not Mercury's words, and is
left: a hover (``title``) and every other attribute, and an element that declares it quotes a
source's own text verbatim (``data-verbatim``: a device's configuration, a log line as sent).

The scan is shown able to see: planted pages, each showing a UTC time in one way a page can,
are each found; a hover, a machine field, a declared quotation and an offset zone are not.
"""

import pytest

from tests import v2_context as V2
from tests.utc_drawn import scan


#: The templates whose responses still show a UTC time, each with its row and why it is not
#: done here. ONLY SHRINKS: a template fixed leaves the list (`test_each_known_gap_is_still_one`
#: says when), and a new one is never added to get a change through.
KNOWN_GAPS = {
    # History › Query's answers write their own times in the browser over UTC words.
    "v2/history_ask_logs.html": "C3291: History › Query's own way of drawing a time",
    "v2/_history_ask_logs.html": "C3291: History › Query's own way of drawing a time",
    # The manual quotes screens' words, and the screens it quotes that the walk does not reach
    # still write UTC words (C3290's remainder): its examples change with them.
    "v2/help.html": "C3290: the manual quotes screens whose words are still in UTC",
    "v2/_help_panel.html": "C3290: the manual quotes screens whose words are still in UTC",
}


def _walked():
    """The walk's measurement, once per test process (`V2.measure` keeps it), taken inside each
    test's own body, never in a fixture: a walk that cannot run fails the test that needs it,
    rather than erroring in its setup."""
    return V2.measure()


def _gap(templates: str) -> str:
    return next((t for t in templates.split(", ") if t in KNOWN_GAPS), "")


class TestEveryResponse:
    def test_the_walk_read_its_responses_and_reached_clocks(self):
        walked = _walked()
        # 1763 HTML responses read on 2026-11-11 (tests/test_display_names_drawn.py's floor):
        # a walk that stopped reading most of them would fall below this.
        assert walked["bodies"] >= 1500, walked["bodies"]
        # Responses drawing at least one time through the clock (119 on 2026-11-13): a walk
        # whose records stopped carrying times, or a clock that stopped writing its element,
        # would fall below this.
        assert walked["clocked"] >= 95, walked["clocked"]

    def test_none_shows_a_utc_time(self):
        walked = _walked()
        found = sorted(
            f"{route} [{templates}] shows {time} in {where}: “{words}”"
            for (route, templates), hits in walked["utc"].items() if not _gap(templates)
            for time, where, words in hits)
        assert found == [], (
            f"{len(found)} place(s) show a person a time in UTC. Draw the instant through "
            "`_macros.clock` (the viewer's zone, its UTC on the hover): a builder carries the "
            "instant as an ISO field, and a record's value that is an instant is drawn by the "
            "clock; words Python must build say the time through `clock_words`' `in_zone`:\n"
            + "\n".join(found))

    def test_each_known_gap_is_still_one(self):
        """A known gap the walk no longer finds is fixed: it leaves `KNOWN_GAPS`."""
        walked = _walked()
        still = {_gap(templates) for (_route, templates) in walked["utc"]} - {""}
        assert set(KNOWN_GAPS) <= still, (
            f"no longer a gap, so remove it from KNOWN_GAPS: {sorted(set(KNOWN_GAPS) - still)}")


class TestTheScanSees:
    """Each way a page can show a UTC time, planted: found, with where it is."""

    @pytest.mark.parametrize("page, time, where", [
        ("<p>Saved in Grafana 2026-11-12T02:33:45Z</p>", "2026-11-12T02:33:45Z", "p"),
        ("<dl><dt>Seen</dt><dd>2026-11-12T02:33:45.120+00:00</dd></dl>",
         "2026-11-12T02:33:45.120+00:00", "dl > dd"),
        ("<p>since 14:02 UTC</p>", "14:02 UTC", "p"),
        ("<td>2026-11-12 02:33:45 UTC</td>", "2026-11-12 02:33:45 UTC", "td"),
        # A log line's recorded time, UTC with no zone named: the worst of them.
        ('<td class="mono">2026-11-12 02:33:45</td>', "2026-11-12 02:33:45", "td"),
        ("<p>Seen by Mercury 2026-11-12T02:33:45</p>", "2026-11-12T02:33:45", "p"),
        ("<li>back by ~01:12 (UTC)</li>", "01:12 (UTC", "li"),
        # An instant before a sentence's colon (a hand-over's "Attempt 1, <iso>: …", C3290).
        ("<li>Attempt 1, 2026-11-12T02:33:45Z: Re-subscribe</li>", "2026-11-12T02:33:45Z",
         "li"),
        ("<p>from UTC 09:30 to 10:30</p>", "UTC 09:30", "p"),
        # A record a person opens is on the screen too.
        ('<details class="tl-record-d"><summary>Details</summary><dl><dd>'
         "2026-11-12T02:33Z</dd></dl></details>", "2026-11-12T02:33Z", "details > dl > dd"),
        # A clock whose words say UTC in the walk's zone is a time no clock drew.
        ('<time class="clock" datetime="2026-11-12T02:33:45Z" title="x">02:33 UTC</time>',
         "02:33 UTC", "time"),
        # A "UTC" some code left after an instant the clock now draws.
        ('<p>until <time class="clock" datetime="2026-11-12T02:33:45Z" data-clock '
         'title="2026-11-12 02:33:45 UTC">08:03 IST</time> UTC) or 600 passes</p>',
         "08:03 IST UTC", "p"),
    ])
    def test_a_utc_time_is_found(self, page, time, where):
        got = scan(page)
        assert [(t, w) for t, w, _words in got] == [(time, where)], got

    @pytest.mark.parametrize("page", [
        '<time class="clock" datetime="2026-11-12T02:33:45Z" data-clock '
        'title="2026-11-12 02:33:45 UTC">08:03 IST</time>',
        '<span title="2026-11-12T02:33:45Z">just now</span>',
        '<div data-at="2026-11-12T02:33:45Z" hx-vals=\'{"at": "14:02 UTC"}\'>x</div>',
        "<script>const at = '2026-11-12T02:33:45Z'; // 14:02 UTC</script>",
        "<style>/* 14:02 UTC */</style>",
        '<pre data-verbatim="the device\'s configuration">! Last configuration change at '
        "13:31:54 UTC Mon Sep 29 2025</pre>",
        "<p>12:41 UTC+05:45, summed by UTC day, a 2026-11-12 cap</p>",
        '<input value="2026-11-12T02:33:45Z">',
        # An SVG element's <title> is its hover.
        '<svg><g><title>switch s1, read 2026-11-12T02:33:45Z</title><circle r="3"/></g></svg>',
    ])
    def test_what_a_person_does_not_read_as_a_utc_time_is_left(self, page):
        assert scan(page) == []


# ── The one way a builder's words reach a screen: `times` (routes/v2.py) ───────────────────

def _times(src, zone_name="America/Denver"):
    """*src* rendered by the app's environment in a request whose viewer reads *zone_name*."""
    from flask import render_template_string

    import app as A
    from modules import time_zones
    from tests.test_local_times import zone

    with zone(zone_name), A.app.test_request_context("/v2/"):
        was = time_zones.zone_of
        time_zones.zone_of = lambda _actor: None          # the host's zone, *zone_name*
        try:
            return render_template_string(src)
        finally:
            time_zones.zone_of = was


class TestTimes:
    def test_an_instant_in_words_is_drawn_by_the_clock_with_its_utc_on_the_hover(self):
        got = _times('{{ "held by Deploy since 2026-11-08T19:41:07Z, by Sam & co" | times }}')
        assert got == ('held by Deploy since <time class="clock" datetime="2026-11-08T19:41:07Z"'
                       ' data-clock="date" title="2026-11-08 19:41:07 UTC">Nov 8 12:41 MST</time>'
                       ', by Sam &amp; co'), got

    def test_an_instant_before_a_sentence_s_colon_is_drawn(self):
        # A hand-over's "Attempt 1, <iso>: …" and its AI line "<iso>: proposed …" (C3290): a
        # colon that ends the instant's words is no part of a time, as ":40" would be.
        got = _times('{{ "Attempt 1, 2026-11-08T19:41:07Z: Re-subscribe" | times }}')
        assert got.count("<time ") == 1 and got.endswith("</time>: Re-subscribe"), got
        assert _times('{{ "2026-11-08T19:41Z:07" | times }}') == "2026-11-08T19:41Z:07"

    def test_a_value_that_is_an_instant_is_drawn_with_its_seconds(self):
        got = _times('{{ "2026-11-08T19:41:07Z" | times }}')
        assert ">Nov 8 12:41:07 MST</time>" in got and 'data-clock="date-seconds"' in got, got

    @pytest.mark.parametrize("iso, utc", [
        ("2026-11-08T12:41:07-07:00", "2026-11-08 19:41:07 UTC"),
        ("2026-11-08T19:41:07+00:00", "2026-11-08 19:41:07 UTC"),
        ("2026-11-08T19:41:07.250Z", "2026-11-08 19:41:07 UTC")])
    def test_every_recorded_shape_is_the_one_instant(self, iso, utc):
        got = _times('{{ "at %s." | times }}' % iso)
        assert f'title="{utc}"' in got and got.endswith("</time>."), got

    def test_a_block_s_attributes_times_and_quotations_are_left(self):
        at = "2026-11-08T19:41:07Z"
        head = f'<p title="read {at}" data-at="{at}">'
        got = _times("{% filter times %}" + head + f'read {at}</p><pre data-verbatim="a log '
                     f'line"><b>{at}</b></pre><textarea>{at}</textarea>' + "{% endfilter %}")
        assert got.count("<time ") == 1 and got.count(at) == 5, got
        assert got.startswith(head + 'read <time class="clock"'), got

    @pytest.mark.parametrize("value", ["", "no time here", 42, "r3 1.2.3.4 2026-11-08"])
    def test_words_with_no_instant_are_left_as_they_came(self, value):
        assert _times("{{ v | times }}".replace("v", repr(value))) == str(value), value
