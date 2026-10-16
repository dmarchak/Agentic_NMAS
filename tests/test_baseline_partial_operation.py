"""C885 (the operator's walk W1, 2026-10-16): the baseline rows misread a partial operation
as a denied Save All. After s2's Mode B deploy (commit 8255d62e6f, which named one device),
"No stored baseline can be re-applied…" said "the last Save All was denied (8 device(s) not
targeted …; commit 8255d62e6f)" and "Save All alone will be refused again while it departs",
though all nine were at intent and the next Save All earned baseline/20261016T010219Z. The
earlier "last baseline was not earned (pipeline)" row likewise said "Resolve each departure"
when its only reason was "not targeted".

On r2's real capture and committed intent (`tests.test_intent_match`'s lab), the commits made
by the real `save_golden`, the deploy's reasons computed by the real `_baseline_earned` over a
nine-device inventory, and the rows drawn by the real route (`/v2/attention`):

- a deploy to one device: the row says what it was ("the last commit (a deploy to r2) did not
  cover the network, so it earned no baseline: Save All takes one"), never a denied Save All,
  never "Resolve each departure"; with no stored baseline usable, the usability row says the
  same and offers Save All alone, never "refused again";
- the controls: a Save All denied for departures keeps "Resolve each departure" and "will be
  refused again"; a deploy that also failed on a device is a denial too;
- C539 kept: the next Save All that earns one clears the row;
- one reading: History's Baseline column (`history_sources.baseline_words`) and these rows
  share `repo.not_targeted_only`.
"""

import html as _h
import re

import pytest

from modules import attention as A
from modules import history_sources as HS
from modules.nsot.repo import GoldenItem, not_targeted_only, save_golden
from tests.test_intent_match import _broken, lab  # noqa: F401 (the fixture)

#: The walk's nine, r2 among them (the lab's one device with a golden here).
NINE = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
#: The host's own trailer, as History reads it (tests/test_history_v2.py).
HOST_TRAILER = "denied: 8 device(s) not targeted: ['r1', 'r2']"


@pytest.fixture
def nine(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.restore._devices_of",
                        lambda list_name: [{"hostname": h} for h in NINE])
    # No baseline-usability answer unless a test gives one.
    monkeypatch.setattr("modules.reader_job.read_cached", lambda name: {"state": "absent"})
    monkeypatch.setattr(A, "SOURCES", (A.baseline_source,))
    return lab


def _deploy_to_r2(config, failed=()):
    """A deploy's commit as the batch makes it: its reasons from `_baseline_earned`."""
    from routes.deploy import _baseline_earned

    pending = [{"hostname": "r2", "config_text": config}]
    outcome = _baseline_earned({}, pending, list(failed), source_ref="", list_name="Lab")
    assert outcome["baseline"] is False
    out = save_golden("Lab", [GoldenItem("r2", config, "203.0.113.12")], source="pipeline",
                      actor="pipeline", allow_new=False, baseline=False,
                      baseline_reasons=outcome["baseline_reasons"])
    assert out["ok"], out
    return out


def _save_all(config):
    return save_golden("Lab", [GoldenItem("r2", config, "203.0.113.12")], actor="t",
                       source="save_all", inventory_size=1)


def _drawn(client) -> str:
    r = client.get("/v2/attention")
    assert r.status_code == 200
    return " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", r.get_data(as_text=True))).split())


def _usable_none(monkeypatch):
    value = {"usable": "", "count": 1, "baselines": [
        {"tag": "baseline/20260925T201032Z", "withdrawn": False, "stale": ["s1"]}]}
    monkeypatch.setattr("modules.reader_job.read_cached", lambda name: {
        "state": "ok", "doc": {"last_good": {"value": {"lists": {"Lab": value}},
                                             "value_at": "2026-10-16T00:57:00Z"}}})


@pytest.fixture
def client():
    import app as nmas
    return nmas.app.test_client()


class TestAPartialOperation:
    def test_the_commit_carries_the_real_reason(self, nine):
        repo, captured = nine
        _deploy_to_r2(captured)
        import subprocess
        body = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                              capture_output=True, text=True).stdout
        assert "Source: pipeline" in body and "Devices: r2" in body
        assert re.search(r"^Baseline: denied: 8 device\(s\) not targeted: \['r1', 'r3', ",
                         body, re.M), body

    def test_the_row_says_what_it_was_and_offers_save_all(self, nine, client):
        _repo, captured = nine
        out = _deploy_to_r2(captured)
        (r,) = A.baseline_source()["rows"]
        assert r["what"] == ("The last commit earned no baseline: a deploy to r2 did not "
                             "cover the network")
        assert (f"The last commit (a deploy to r2, commit {out['commit'][:10]} at "
                in r["cause"])
        assert ("did not cover the network (8 device(s) not targeted), so it earned no "
                "baseline: Save All takes one.") in r["cause"]
        assert "Resolve each departure" not in r["action"]["label"]
        assert r["action"]["label"].startswith("Save All takes one")
        words = _drawn(client)
        assert "a deploy to r2 did not cover the network" in words
        assert "Resolve each departure" not in words and "Save All was denied" not in words

    def test_with_no_baseline_usable_the_usability_row_says_the_same(self, nine, client,
                                                                     monkeypatch):
        _repo, captured = nine
        _deploy_to_r2(captured)
        _usable_none(monkeypatch)
        (r,) = A.baseline_source()["rows"]
        assert r["what"] == "No stored baseline can be re-applied"
        assert "the last Save All was denied" not in r["cause"]
        assert "a deploy to r2" in r["cause"] and "Save All takes one." in r["cause"]
        assert r["action"]["label"].startswith("Take a current baseline: Save All")
        words = _drawn(client)
        assert "refused again" not in words and "Resolve each departure" not in words
        assert "a new one cannot be earned" not in words.lower()

    def test_the_next_save_all_that_earns_one_clears_it(self, nine):
        """C539 kept: the row leaves with the decision that supersedes it."""
        _repo, captured = nine
        _deploy_to_r2(captured)
        assert len(A.baseline_source()["rows"]) == 1
        assert _save_all(captured)["baseline"].startswith("baseline/")
        assert A.baseline_source()["rows"] == []


class TestTheControls:
    def test_a_save_all_denied_for_departures_keeps_its_remedy(self, nine, client,
                                                              monkeypatch):
        _repo, captured = nine
        _save_all(_broken(captured))
        (r,) = A.baseline_source()["rows"]
        assert "r2 does not match its committed intent" in r["cause"]
        assert r["action"]["label"].startswith("Resolve each departure")
        _usable_none(monkeypatch)
        (r,) = A.baseline_source()["rows"]
        assert "the last Save All was denied" in r["cause"]
        assert "will be refused again while it departs" in r["action"]["label"]
        assert "refused again" in _drawn(client)

    def test_a_deploy_that_failed_on_a_device_is_a_denial(self, nine):
        _repo, captured = nine
        _deploy_to_r2(captured, failed=["s3"])
        (r,) = A.baseline_source()["rows"]
        assert "did not succeed" in r["cause"] and "Resolve each departure" in \
            r["action"]["label"]


class TestOneReading:
    @pytest.mark.parametrize("reasons, n", [
        (HOST_TRAILER.partition(":")[2].strip(), 8),
        ("1 device(s) did not succeed: ['s3']; 7 device(s) not targeted: ['r1']", 0),
        ("2 device(s) not targeted: ['r1', 's4']; 2 device(s) were not measured against "
         "baseline/20260920T212325Z-migrated: ['r1', 's4']", 2),
        ("r2 does not match its committed intent (+1 -1)", 0),
        ("", 0),
    ])
    def test_not_targeted_only(self, reasons, n):
        assert not_targeted_only(reasons) == n

    def test_history_reads_it_the_same_way(self):
        assert HS.baseline_words(HOST_TRAILER, [])["state"] == "not_taken"
        mixed = "denied: 1 device(s) did not succeed: ['s3']; 7 device(s) not targeted: ['r1']"
        assert HS.baseline_words(mixed, [])["state"] == "denied"
