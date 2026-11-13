"""Money is shown as "$0.25", through one formatter (the operator, 2026-11-13: "money shown as
$"): `modules.money.usd`, the `usd` filter every v2 template draws an amount by.

- **The formatter:** the sign first, always cents, thousands grouped; a figure to the cent
  (under a cent, four places, never "$0.00" for something spent); an exact amount to four
  places when it is no whole number of cents. Each expectation is written out, not computed.
- **The templates** (the population, by property: every file under templates/v2/): none
  types a "$" before an expression (an amount formatted in place, which the filter replaces),
  and none says an amount as "0.25 USD" or "USD 0.25". What the scan assumes stays true: an
  amount is drawn by an expression, and a "$" a template types before one is an amount's,
  unless it is a quoted variable's name (Grafana's `"$device"`), which is left.
- **The scan is shown able to see:** planted lines, each drawing an amount one wrong way, are
  each found; the filter's own form and a quoted variable are not.
"""

import os
import re

import pytest

from modules.money import usd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A "$" typed before an expression (not a quoted variable's name), and "USD" beside a number
#: or an expression, either side.
TYPED = re.compile(r'(?<!")\$\{\{[^}]*\}\}')
WORDED = re.compile(r"(?:\d|\}\})\s?USD\b|\bUSD\s?(?:\d|\{\{)")


def wrong_ways(text: str) -> list:
    """Each place *text* (a template's source) draws an amount other than by the filter."""
    return [m.group(0) for pattern in (TYPED, WORDED) for m in pattern.finditer(text)]


class TestTheFormatter:
    @pytest.mark.parametrize("value, figure, exact", [
        (0, "$0.00", "$0.00"),
        (0.25, "$0.25", "$0.25"),
        (1, "$1.00", "$1.00"),
        (1.5, "$1.50", "$1.50"),
        (80, "$80.00", "$80.00"),
        (2400, "$2,400.00", "$2,400.00"),
        (1234567.891, "$1,234,567.89", "$1,234,567.8910"),
        (0.654, "$0.65", "$0.6540"),
        (0.1251, "$0.13", "$0.1251"),
        (0.0125, "$0.01", "$0.0125"),
        # Under a cent and not nothing: four places, so spend never reads as "$0.00".
        (0.004, "$0.0040", "$0.0040"),
        (0.0003, "$0.0003", "$0.0003"),
        # Below the fourth place there is nothing to say.
        (0.00004, "$0.00", "$0.00"),
        # A float's own noise is not a fifth place: 0.1 + 0.2 is thirty cents.
        (0.1 + 0.2, "$0.30", "$0.30"),
        ("0.0015", "$0.0015", "$0.0015"),
        (-0.5, "-$0.50", "-$0.50"),
        (-0.00001, "$0.00", "$0.00"),
    ])
    def test_an_amount_reads_as_dollars(self, value, figure, exact):
        assert usd(value) == figure
        assert usd(value, exact=True) == exact

    def test_the_two_older_formatters_are_this_one(self):
        """`installation_settings.money` (a cap; None is no cap) and `fixit.policy.money`
        (a spent amount beside its cap) say an amount the same way."""
        from modules import installation_settings as I
        from modules.fixit import policy as P
        for value in (0.92, 1, 50, 5000, 0.0257):
            assert I.money(value) == P.money(value) == usd(value, exact=True)
        assert I.money(None) == "no cap"
        assert (I.money(80), P.money(1.0), I.money(2400)) == ("$80.00", "$1.00", "$2,400.00")

    def test_a_field_holds_the_number_without_its_sign(self):
        from modules import installation_settings as I
        assert [I.amount_text(v) for v in (1.5, 1.0, 5000, 0.0125, None, "1,5")] == [
            "1.50", "1.00", "5000.00", "0.0125", "", "1,5"]


class TestTheFilter:
    def test_a_template_draws_an_amount_by_it(self):
        import app as A
        from flask import render_template_string
        with A.app.test_request_context("/v2/history"):
            out = render_template_string(
                "{{ a | usd }} {{ a | usd(true) }} {{ b | usd }} {{ c | usd(true) }}",
                a=0.1251, b=2400, c="0.0015")
        assert out == "$0.13 $0.1251 $2,400.00 $0.0015"


class TestNoTemplateDrawsAnAmountAnotherWay:
    def _templates(self):
        from tests import source_index
        return source_index.tracked("templates/v2", suffix=".html", recursive=False)

    def test_the_scan_sees_each_wrong_way_and_leaves_the_right_one(self):
        for planted in ("<td>${{ '%.4f' | format(x.cost_usd) }}</td>",
                        "<td>${{ r.price.input }}</td>",
                        "<p>{{ x.cost_usd }} USD</p>", "<p>USD {{ x.cost_usd }}</p>",
                        "<p>0.25 USD a call</p>", "<p>USD 0.25</p>"):
            assert wrong_ways(planted), planted
        for fine in ("<td>{{ x.cost_usd | usd(true) }}</td>",
                     '<span class="mono">{{ v }}="${{ v }}"</span>',
                     "<span>US dollars per million tokens</span>"):
            assert wrong_ways(fine) == [], fine

    def test_no_template_does(self):
        files = self._templates()
        # 274 templates on 2026-11-13: a scan reading far fewer reads the wrong folder.
        assert len(files) >= 240, len(files)
        found, drawn = [], 0
        for path in files:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            drawn += len(re.findall(r"\|\s*usd\b", text))
            found += [f"{os.path.relpath(path, ROOT)}: {w}" for w in wrong_ways(text)]
        assert found == [], (
            "an amount is drawn by the `usd` filter (\"{{ x | usd }}\", or usd(true) for one "
            "call's cost), never a \"$\" typed before an expression or the word USD:\n"
            + "\n".join(found))
        # 41 amounts drawn through the filter on 2026-11-13: a scan that stopped seeing the
        # filter, or templates that stopped drawing amounts, would fall below this.
        assert drawn >= 35, drawn

    def test_the_settings_amount_fields_carry_their_sign(self):
        """A field that takes an amount draws its "$" (`.in-usd`), so the number in it is
        never bare: the installation's caps and each background feature's."""
        for name, fields in (("_install_card.html", 1), ("_settings_ai_caps.html", 2),
                             ("_settings_ai_on.html", 2)):
            with open(os.path.join(ROOT, "templates", "v2", name), encoding="utf-8") as fh:
                text = fh.read()
            assert text.count('<span class="in-usd">') == fields, name
        with open(os.path.join(ROOT, "static", "css", "nmas-v2.css"), encoding="utf-8") as fh:
            css = fh.read()
        assert re.search(r'\.in-usd::before\s*\{\s*content:\s*"\$"', css)
