"""C3581 (the operator, 2026-11-14: "on "Self-healing holds r4… departs (-2)", the Open… button
opens r4's whole intent page and never shows the 2 departing lines. A departure row (and the
device's Overview check) shows the exact lines: each with "in intent, not on the device" or "on
the device, not in intent", and the action that resolves each"; provisional, operator review
pending).

From r4's real departure (its golden held two lines its intent did not: "privilege exec level
3 show telemetry ietf" and "privilege exec level 3 show telemetry", the read-only account's
telemetry privileges, tests/test_read_account_intent.py):

- **The decision reads the lines** (`heal.decide.Sources.golden`): a golden that departs, by
  its newest measurement standing or compared now, carries intent_match's own lines (masked
  there, once); one at intent carries none and is never compared again.
- **Guard 4 records them** in its operands, capped, the rest counted.
- **Needs attention's held row draws each line on the row**, never only under Details for the
  record: the line, its side in those words, and the two ways out of that side
  (`intent_match.resolutions`), each a link to where it is done on v2 (the device's Deploy plan,
  its intent editor).
"""
import re
from html import unescape

from tests.test_heal_guard4_measured import repo  # noqa: F401  (the fixture)
from tests.test_heal_decide import lab  # noqa: F401  (the fixture)
from tests.test_heal_mark_and_held import DS, _held, _rows
from tests.test_heal_proposal_v2 import app_client  # noqa: F401  (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

#: r4's departure as intent_match reads it: on the device, not in intent.
R4 = ["- privilege exec level 3 show telemetry ietf", "- privilege exec level 3 show telemetry"]
DEPARTS = {"state": "differs", "adds": 0, "removes": 2, "reordered": 0, "lines": list(R4),
           "why": "", "classes": [], "vtp_mode": ""}


def _compared(monkeypatch, result):
    calls = []

    def now(repo_dir, network, host, text, platform=""):
        calls.append(host)
        return dict(result)
    monkeypatch.setattr("modules.nsot.intent_match.intent_match", now)
    return calls


class TestTheDecisionReadsTheLines:
    def test_a_departure_its_measurement_states_carries_intent_match_s_lines(self, repo,  # noqa: F811
                                                                            monkeypatch):
        from modules.heal import decide

        calls = _compared(monkeypatch, DEPARTS)
        got = decide.Sources("Default").golden("r4", {"ip": "192.0.2.4"})
        assert got["state"] == "departs" and got["words"] == "departs (+2 -2)", got
        assert got["lines"] == R4 and calls == ["r4"]

    def test_a_golden_at_intent_carries_no_lines_and_is_not_compared(self, repo, monkeypatch):  # noqa: F811
        from modules.heal import decide
        from tests.test_heal_guard4_measured import _commit

        _commit(repo.path, "Save All\n\nSource: save_all\nDevices-Measured: r4\nIntent-Match: "
                "yes (1 of 1)\n", 1794111310, empty=True)
        calls = _compared(monkeypatch, DEPARTS)
        got = decide.Sources("Default").golden("r4", {"ip": "192.0.2.4"})
        assert got["state"] == "at_intent" and got.get("lines", []) == [] and calls == []

    def test_guard_4_records_them_capped_and_counts_the_rest(self):
        from modules.heal import guards

        many = [f"- line {n}" for n in range(guards.G4_LINES + 3)]
        g = guards.g4_golden({"state": "departs", "words": "departs (-13)", "commit": "c0",
                              "lines": many, "adds": 0, "removes": len(many)})
        assert g["operands"]["lines"] == many[:guards.G4_LINES]
        assert g["operands"]["lines_more"] == 3
        g = guards.g4_golden({"state": "departs", "words": "departs (-2)", "commit": "c0",
                              "lines": R4, "adds": 0, "removes": 2})
        assert (g["operands"]["lines"], g["operands"]["lines_more"]) == (R4, 0)


class TestTheHeldRowDrawsEachLine:
    OPS = {"golden_commit": "c0ffee", "intent_match": "departs", "lines": list(R4),
           "lines_more": 0}

    def test_each_line_with_its_side_and_the_ways_out_of_it(self, lab):  # noqa: F811
        from modules.nsot import intent_match

        _held(4, device="r4", operands=self.OPS)
        (r,) = _rows("held")
        dep = r["departure"]
        assert [(l["line"], l["side"]) for l in dep["lines"]] == [
            ("privilege exec level 3 show telemetry ietf", "on the device, not in intent"),
            ("privilege exec level 3 show telemetry", "on the device, not in intent")]
        (group,) = dep["groups"]
        assert group["side"] == "on the device, not in intent"
        assert [a["do"] for a in group["actions"]] == [
            x["do"] for x in intent_match.resolutions({"state": "differs", "removes": 1})]
        assert (group["sign"], [a["open"] for a in group["actions"]]) == (
            "-", ["deploy", "intent_edit"])
        # Drawn on the row, so not again under Details for the record.
        assert "lines" not in r["operands"] and "lines_more" not in r["operands"]

    def test_a_line_in_intent_and_not_on_the_device_offers_its_own_two(self, lab):  # noqa: F811
        _held(4, device="r4", operands=dict(self.OPS, lines=["+ logging host 192.0.2.10"]))
        (r,) = _rows("held")
        from modules.nsot import intent_match

        (group,) = r["departure"]["groups"]
        assert (group["side"], group["sign"]) == ("in intent, not on the device", "+")
        assert [a["do"] for a in group["actions"]] == [
            x["do"] for x in intent_match.resolutions({"state": "differs", "adds": 1})]

    def test_the_list_draws_them_on_the_row_with_their_links(self, lab, app_client):  # noqa: F811
        d = _held(4, device="r4", operands=self.OPS)
        body = app_client.get("/v2/attention?list=Default").get_data(as_text=True)
        mine = body.split(f'data-attention-row="heal:{d["id"]}"', 1)[1].split(
            'data-attention-row="', 1)[0]
        row = mine.split('<details class="att-more"', 1)[0].split('<details class="att-record"',
                                                                  1)[0]
        dep = re.search(r'<div class="att-departs".*?</div>', row, re.S)
        assert dep, "the departing lines are on the row, above Details"
        drawn = [(unescape(c), unescape(s)) for c, s in re.findall(
            r'<li[^>]*><code>([^<]+)</code> <span class="att-dep-side">([^<]+)</span>',
            dep.group(0))]
        recorded = DS.decisions("Default")[-1]["guard"]["operands"]["lines"]
        assert drawn == [(l[2:], "on the device, not in intent") for l in recorded]
        ways = re.findall(r'<a class="btn[^"]*" data-op="([a-z-]+)"[^>]*href="([^"]+)"[^>]*>'
                          r'([^<]+)</a>', dep.group(0))
        assert [(op, unescape(h), w) for op, h, w in ways] == [
            ("deploy", "/v2/device/r4?list=Default&op=deploy", "Remove it from the device…"),
            ("edit-intent", "/v2/device/r4?list=Default&tab=intent&edit=1",
             "Adopt it into intent…")]
        # A read: drawing the list recorded no decision.
        assert DS.decisions("Default")[-1]["id"] == d["id"]
