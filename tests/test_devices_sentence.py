"""The Devices list's one sentence (the operator's GUI pick, 2026-11-25: C; Stage 5 step 6),
`device_list.sentence`, from the rows the list draws under it.

- The devices that need a look are named first: not answering, then differing from intent.
- The rest are counted by what keeps them from "answers and runs its intent"; only when every
  row is reachable and at its intent does it say so.
- A search or filter says the sentence speaks of the rows shown.
- On the page, the sentence is the one the list's own rows make.
"""
import re

from modules import device_list as DL
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)


def _r(name, status, intent):
    return {"name": name, "status": {"state": status}, "intent": {"state": intent}}


def _d(rows, total=None):
    return {"rows": rows, "total": len(rows) if total is None else total, "error": ""}


def test_the_devices_to_look_at_are_named_first():
    got = DL.sentence(_d([_r("r1", "danger", "at_intent"), _r("r2", "ok", "departs"),
                          _r("r3", "unknown", "intent_moved"), _r("r4", "ok", "at_intent")]))
    assert got == {"lead": "1 device not answering (r1) and 1 device differing from its intent "
                           "(r2).",
                   "rest": "Besides: 1 not probed yet, 1 with intent changed since measured."}


def test_with_nothing_to_look_at_the_rest_are_counted():
    got = DL.sentence(_d([_r("r1", "unknown", "intent_moved"), _r("r2", "warn", "pending"),
                          _r("r3", "planned", "at_intent")]))
    assert got == {"lead": "Nothing known to be wrong.",
                   "rest": "1 under an operation, 1 waiting to be onboarded, 1 not probed yet, "
                           "1 with intent changed since measured."}


def test_only_every_row_reachable_at_intent_says_all_run_their_intent():
    assert DL.sentence(_d([_r("r1", "ok", "at_intent"), _r("r2", "ok", "at_intent")])) == {
        "lead": "All 2 devices answer and run their intent.", "rest": ""}
    got = DL.sentence(_d([_r("r1", "ok", "at_intent"), _r("r2", "ok", "no_intent")]))
    assert "All" not in got["lead"], got


def test_a_filtered_list_speaks_of_the_rows_shown_and_none_draws_nothing():
    got = DL.sentence(_d([_r("r1", "danger", "at_intent")], total=5))
    assert got["lead"] == "Of the 1 shown, 1 device not answering (r1).", got
    assert DL.sentence(_d([])) == {} and DL.sentence({"rows": [1], "error": "x"}) == {}


def test_the_list_opens_with_the_sentence_of_its_rows(lab):  # noqa: F811
    _r_, html = _get(lab, "/v2/devices/table")
    said = re.search(r'<p class="doc-summary devices-said" data-sentence><strong>(.*?)</strong>'
                     r'(?: (.*?))?</p>', html)
    import app as A
    from routes import v2
    with A.app.test_request_context("/v2/devices/table"):
        from flask import request
        d = v2._devices_ctx(request)["d"]
    assert d["rows"] and said, html[:800]
    assert (said.group(1), said.group(2) or "") == tuple(DL.sentence(d).values())


def test_the_platform_column_says_the_platform_in_words_its_key_on_hover(lab):  # noqa: F811
    """Stage 5 step 6: the Platform column drew the dialect's key ("cisco_iosxe") where the
    device's own title says it in words ("IOS-XE", `platform.FACT_WORDS`); the column says the
    words with the key on hover, and a key the table has no words for is drawn as itself."""
    import app as A
    from modules.nsot.platform import FACT_WORDS
    from routes import v2
    _r_, html = _get(lab, "/v2/devices/table")
    with A.app.test_request_context("/v2/devices/table"):
        from flask import request
        d = v2._devices_ctx(request)["d"]
    keyed = [r for r in d["rows"] if r.get("platform")]
    assert keyed, "the fixture's devices name a platform"
    for r in keyed:
        words = FACT_WORDS.get(r["platform"], r["platform"])
        assert f'<td title="{r["platform"]}">{words}</td>' in html, (r["platform"], words)
