"""Monitoring › Alerts' "Firing · N" moves with the list (C2251; PHASE8_PLAN 21.3's in-scope
list: "the stale Firing · N count").

The tab's count was drawn once with the page while the list (`#alert-evidence`) re-fetched on
`nmas:alerts`, so the list's own "N firing" moved and the tab kept the page-load count. The
list's redraw now carries the count out of band (`_alerts_firing_count.html`), the same number
from the same read. The read is the real `evidence_pack.tab` on test_ai_explain's world, its
firing count moved between the page and the redraw as an announcement would find it.
"""

import re
from html import unescape

from modules import evidence_pack
from tests.test_ai_explain import world  # noqa: F401 - the fixture
from tests.test_device_v2 import lab  # noqa: F401 - the fixture
from tests.test_evidence_pack import pack_lab  # noqa: F401 - the fixture

COUNT = r'<span id="alerts-firing-count"( hx-swap-oob="true")?> · (\d+)</span>'


def test_the_list_s_redraw_carries_the_tab_s_count_out_of_band(world, monkeypatch):  # noqa: F811
    real, firing = evidence_pack.tab, {"n": None}

    def tab(*a, **k):
        got = real(*a, **k)
        if firing["n"] is not None:
            got["counts"] = dict(got["counts"], firing=firing["n"])
        return got
    monkeypatch.setattr(evidence_pack, "tab", tab)
    c = world.lab["client"]
    page = unescape(c.get("/v2/monitoring/alerts").get_data(as_text=True))
    (oob_page, on_page), = re.findall(COUNT, page)
    assert oob_page == "", "the page draws the count in place"
    firing["n"] = int(on_page) + 2                      # two more began since the page drew
    region = unescape(c.get("/v2/monitoring/alerts/list").get_data(as_text=True))
    (oob, in_region), = re.findall(COUNT, region)
    assert oob == ' hx-swap-oob="true"', "the redraw sends it out of band"
    assert int(in_region) == firing["n"], (in_region, firing)
    # The same number the list itself draws.
    assert f"<strong>{firing['n']} firing</strong>" in region
