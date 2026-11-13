"""History groups what repeats (C3399; the operator, 2026-11-13: "History groups Grafana saves
whose definition hash didn't change into one row per save burst ("Grafana re-saved 27 rules: no
change to what they evaluate"), and only real changes stand alone"; "Also: group runs of
identical History rows (e.g. "Show commands ×25"), not only Grafana's no-op saves").

- **A save burst** (`history_sources.alert_rule_changes`): the saves one read of Grafana's
  ruler found, by one account, whose definition hash did not move, are one row naming the
  count, each rule listed where it opens; a save whose hash moved stands alone.
- **A run** (`history_sources.runs`, drawn by templates/v2/_timeline.html): ADJACENT rows alike
  in kind, what, devices and who (and outcome and marks) are one row "×N" with the first and
  last times, opening to each row; never across a row that differs, and never a commit.

The Grafana records are made by the real recorder (`alert_rule_changes.record`) from the real
ruler capture, tests/fixtures/grafana/ruler.json (sixteen rules), through
tests/test_alert_rule_changes.py's own helpers. The 27 rules of the operator's words are those
sixteen and eleven more heartbeat rules, each a copy of the captured "NMAS heartbeat missing:
r1" with its uid, title and ``device`` label naming another device (a MINIMAL EDIT: Mercury
generates one such rule per device, so a larger fleet's ruler holds more of them). Each save is
`saved`'s (version moved by one, ``updated`` and ``updated_by`` as Grafana sets them) with the
editor's layout changed, the captured no-op save of test_alert_rule_changes. The Show commands
runs are made by the real run (`reads.run`) over test_show_commands' fleet, whose ``show
clock`` answer is a capture's.
"""

import copy
import html as html_mod
import re

import pytest

from modules import alert_rule_changes as ARC
from modules import history_sources as HS
from tests.test_alert_rule_changes import STORE, _ctx, load, saved
from tests.test_alert_rule_changes import store  # noqa: F401  (the fixture)
from tests.test_show_commands import _fingerprint, _run, sc  # noqa: F401  (sc: the fixture)
from tests.test_device_v2 import lab  # noqa: F401  (the fixture sc builds on)

NOW = 1792950000.0          # 2026-10-26T22:20:00Z, after every captured `updated`
LATER = NOW + 600


#: Who saves a file-provisioned rule, as the capture records it.
SERVICE = {"name": "", "uid": "service"}
PROVISIONING = "Grafana's file provisioning (as service)"


def _ruler34():
    """The captured ruler with eighteen more heartbeat rules (x1 to x18): 34 rules, 27 of them
    heartbeat rules (the captured nine and the eighteen)."""
    ruler = load("ruler")
    group = next(g for g in ruler["NMAS"] if g["name"] == "nmas-heartbeat")
    model = next(r for r in group["rules"]
                 if r["grafana_alert"]["title"] == "NMAS heartbeat missing: r1")
    for i in range(1, 19):
        rule = copy.deepcopy(model)
        rule["grafana_alert"]["uid"] = f"nmas-hb-x{i}"
        rule["grafana_alert"]["title"] = f"NMAS heartbeat missing: x{i}"
        rule["labels"]["device"] = f"x{i}"
        group["rules"].append(rule)
    return ruler


def _titles(ruler, heartbeat=True):
    return [r["grafana_alert"]["title"] for gs in ruler.values() for g in gs for r in g["rules"]
            if r["grafana_alert"]["title"].startswith("NMAS heartbeat") == heartbeat]


HEARTBEATS = _titles(_ruler34())
OTHERS = _titles(_ruler34(), heartbeat=False)


def _resaved(networks=("Default",), moved=None, others=False):
    """A baseline read of the 34 rules, then one read finding the 27 heartbeat rules saved
    again by their file provisioning with only the editor's layout changed, a second apart;
    *moved*: a heartbeat rule whose window label changed too in that save (its hash moved);
    *others*: the seven other rules saved the same way by a login (``admin``) in that read."""
    ARC.record(STORE, ARC.from_ruler(_ruler34()), list(networks), now=NOW)
    ruler = _ruler34()
    for i, title in enumerate(HEARTBEATS + (OTHERS if others else [])):
        rule = saved(ruler, title=title, by=SERVICE if title in HEARTBEATS else None,
                     at=f"2026-10-26T22:30:{i:02d}Z")
        rule["grafana_alert"].setdefault("metadata", {})["editor_settings"] = {}
        if title == moved:
            rule["labels"]["window_seconds"] = "800"
    ARC.record(STORE, ARC.from_ruler(ruler), list(networks), now=LATER)


def _not_baseline(events):
    return [e for e in events if e["outcome"] != "baseline"]


class TestTheSaveBurst:
    def test_27_saves_that_moved_no_hash_are_one_row_listing_each_rule(self, store):  # noqa: F811
        _resaved()
        got = HS.alert_rule_changes(_ctx())
        assert got["errors"] == []
        (e,) = _not_baseline(got["events"])
        assert e["what"] == "Grafana re-saved 27 rules: no change to what they evaluate"
        assert e["outcome"] == "unchanged" and e["who"] == PROVISIONING
        listed = [k for k, _v in e["record"] if k in HEARTBEATS]
        assert sorted(listed) == sorted(HEARTBEATS) and len(listed) == 27
        assert all(v.endswith("unchanged") for k, v in e["record"] if k in listed)
        assert len(e["devices"]) == 27
        # Its time is the burst's last save; its first is said where it opens.
        assert e["at"] == "2026-10-26T22:30:26Z"
        assert e["detail"] == "Saved from 2026-10-26T22:30:00Z to 2026-10-26T22:30:26Z"

    def test_a_save_whose_hash_moved_stands_alone_and_the_rest_are_grouped(self, store):  # noqa: F811
        moved = "NMAS heartbeat missing: x5"
        _resaved(moved=moved)
        rows = _not_baseline(HS.alert_rule_changes(_ctx())["events"])
        alone = [e for e in rows if e["outcome"] == "changed"]
        group = [e for e in rows if e["outcome"] == "unchanged"]
        assert len(rows) == 2 and len(alone) == 1 and len(group) == 1
        assert alone[0]["what"].startswith(f"Alert rule changed in Grafana: {moved}, ")
        assert alone[0]["what"].endswith("labels: window_seconds 750 → 800")
        assert group[0]["what"].startswith("Grafana re-saved 26 rules")
        assert moved not in dict(group[0]["record"])

    def test_saves_by_two_accounts_in_one_read_are_two_rows(self, store):  # noqa: F811
        _resaved(others=True)
        rows = sorted(_not_baseline(HS.alert_rule_changes(_ctx())["events"]),
                      key=lambda e: e["who"])
        assert [(e["who"], e["what"]) for e in rows] == [
            ("Grafana's file provisioning (as service)",
             "Grafana re-saved 27 rules: no change to what they evaluate"),
            ("admin (in Grafana)", "Grafana re-saved 7 rules: no change to what they evaluate")]

    def test_a_device_draws_the_save_of_its_own_rule_alone(self, store):  # noqa: F811
        _resaved()
        rows = _not_baseline(HS.alert_rule_changes(_ctx(device="x3"))["events"])
        # One save of x3's rule is no burst: its own row, as before.
        assert [e["devices"] for e in rows] == [["x3"]]
        assert rows[0]["what"].startswith("Alert rule changed in Grafana: NMAS heartbeat "
                                          "missing: x3, version 2 → 3: saved with no change")


# ---------------------------------------------------------------------------- runs of rows

def _e(what="Show commands: show clock", devices=("r3",), who="operator@example.com",
       at="2026-11-13T10:00:00Z", **kw):
    row = HS._event(at, kw.pop("kind", "show_commands"), what, list(devices), who=who, **kw)
    row["devices_words"] = HS.devices_words(row["devices"])
    return row


class TestTheRuns:
    def test_alike_adjacent_rows_are_one_run_and_every_row_is_kept_in_order(self):
        rows = [_e(at=f"2026-11-13T10:{59 - i:02d}:00Z") for i in range(25)]
        (run,) = HS.runs(rows)
        assert run == rows

    def test_a_row_between_keeps_two_alike_rows_apart(self):
        a, b, c = _e(), _e(what="Show commands: show version"), _e()
        assert HS.runs([a, b, c]) == [[a], [b], [c]]

    @pytest.mark.parametrize("field,other", [
        ("devices", {"devices": ("r9",)}),
        ("who", {"who": "other@example.com"}),
        ("kind", {"kind": "privileged"}),
        ("outcome", {"outcome": "failed (nothing read)"}),
        ("marks", {"marks": ["refused"]}),
    ])
    def test_rows_differing_in_one_field_are_not_merged(self, field, other):
        a, b = _e(), _e(**other)
        assert HS.runs([a, b]) == [[a], [b]], field

    def test_a_commit_always_stands_alone(self):
        a, b = _e(kind="golden", what="Golden recorded (capture)", sha="a" * 40), \
            _e(kind="golden", what="Golden recorded (capture)", sha="b" * 40)
        assert HS.runs([a, b]) == [[a], [b]]

    def test_the_rows_of_the_runs_are_the_rows_given(self):
        rows = [_e(), _e(), _e(what="Show commands: show version"), _e(who="x@example.com"),
                _e(who="x@example.com"), _e()]
        got = HS.runs(rows)
        assert [len(r) for r in got] == [2, 1, 2, 1]
        assert [e for r in got for e in r] == rows


# ---------------------------------------------------------------------------- the page

def _show(lab, commands=("show clock",), host="r3", actor=None):  # noqa: F811
    """Show commands' Run pressed on *host* alone (the pick's name filter), as the page's
    verified person, or as *actor* (the verified identity the route reads, set for this press
    only)."""
    from modules import identity
    with pytest.MonkeyPatch.context() as mp:
        if actor:
            mp.setattr(identity, "request_actor", lambda: actor)
        r, target = _run(lab, list(commands), fingerprint=_fingerprint(lab, f"&q={host}"),
                         q=host)
    assert r.status_code == 204 and "/v2/show-commands/run/" in target, r.status_code


#: The page's rows filtered to Show commands: the lab's golden commit can fall in the same
#: second as the first runs, and is then drawn among them (rows of one second keep their
#: stores' order), which rightly ends a run there (measured 2026-11-13: 1 in 6 runs, two runs).
SHOWN = "/v2/history?since=&list=Lab&kind=show_commands"
TAB = "/v2/device/r3?tab=history&list=Lab&kind=show_commands"


def _page(lab, url=SHOWN):  # noqa: F811
    r = lab["client"].get(url)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _run_rows(html):
    """Each run drawn: ``(its id, its summary's text, the ids of the rows inside it)``."""
    out = []
    for m in re.finditer(r'<details class="hist-row tl-row tl-run" id="(run-[^"]+)"', html):
        sums = re.search(r'<summary class="hist-sum">(.*?)</summary>', html[m.end():], re.S)
        text = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", sums.group(1))).split())
        inner = html[m.end():].split('<div class="hist-detail tl-more tl-run-rows">', 1)[1]
        depth, ids = 1, []
        for t in re.finditer(r'<details\b[^>]*>|</details>', inner):
            if t.group(0) == "</details>":
                depth -= 1
                if depth == 0:
                    break
            else:
                if depth == 1 and 'class="hist-row tl-row' in t.group(0):
                    ids.append(re.search(r'id="([^"]+)"', t.group(0)).group(1))
                depth += 1
        out.append((m.group(1), text, ids))
    return out


class TestThePage:
    def test_25_show_commands_runs_are_one_row_x25_opening_to_each(self, sc):  # noqa: F811
        from modules.nsot import listref
        for _ in range(25):
            _show(sc)
        h = HS.timeline(listref.resolve("Lab"), since_days="", kinds=["show_commands"])
        shown = h["events"]
        assert len(shown) == 25
        html = _page(sc)
        ((rid, summary, ids),) = _run_rows(html)
        assert "Show commands: show clock ×25" in summary
        assert ids == [e["id"] for e in shown] and rid == f"run-{shown[-1]['id']}"
        # The first and last times, each in the viewer's zone with its UTC on the hover.
        times = re.findall(r'<time class="clock" datetime="([^"]+)"',
                           html.split(f'id="{rid}"', 1)[1].split("</summary>", 1)[0])
        assert [HS.epoch(t) for t in times] == [HS.epoch(shown[-1]["at"]),
                                                HS.epoch(shown[0]["at"])]
        # The count line counts records, not lines drawn.
        assert "Showing the newest 25" in html
        assert html.count('data-kind="show_commands"') == 26

    def test_a_different_run_between_keeps_them_apart(self, sc):  # noqa: F811
        _show(sc)
        _show(sc, commands=("show ip interface",))
        _show(sc)
        assert _run_rows(_page(sc)) == []

    def test_runs_on_another_device_or_by_another_person_are_not_merged(self, sc):  # noqa: F811
        # Newest first: other's two on r3, then the operator's on r3, on r9 and on r3.
        _show(sc)
        _show(sc, host="r9")
        _show(sc)
        _show(sc, actor="other@example.com")
        _show(sc, actor="other@example.com")
        runs = _run_rows(_page(sc))
        assert [len(ids) for _rid, _s, ids in runs] == [2], runs
        assert "Show commands: show clock ×2" in runs[0][1] and "other" in runs[0][1]

    def test_the_device_tab_draws_the_same_run(self, sc):  # noqa: F811
        for _ in range(3):
            _show(sc)
        ((_rid, summary, ids),) = _run_rows(_page(sc, TAB))
        assert "×3" in summary and len(ids) == 3

    def test_the_save_burst_is_one_row_and_a_run_beside_it_stands_alone(self, sc, store):  # noqa: F811
        _resaved(networks=("Lab",))
        _show(sc)
        html = _page(sc, "/v2/history?since=&list=Lab&kind=alert_rules&kind=show_commands")
        assert html.count("Grafana re-saved 27 rules: no change to what they evaluate") == 1
        assert html.count('data-kind="alert_rule"') == 2          # the burst and the baseline
        assert "NMAS heartbeat missing: x11" in html                # listed where it opens
        # The run just pressed is its own row: one record, folded into nothing.
        assert html.count('data-kind="show_commands"') == 1 and _run_rows(html) == []
