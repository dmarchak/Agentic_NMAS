"""A past alert's evidence pack (the operator's order of 2026-10-26, items 3 and 4): Build
evidence on Monitoring › Alerts › History rebuilds a pack from the alert history as of the
alert's time, every section marked captured at the time, rebuilt afterwards or cannot be
rebuilt (`evidence_pack.PROVENANCE`), kept frozen; the marks ride in what Explain sends; a
second Explain reads the same pack.

On tests/test_evidence_pack.py's lab (r1 by IPv6, r2 by IPv4, r3; Loki and Prometheus from their
captures) and tests/test_ai_explain.py's world (hosted AI allowed, a planted answer). The past
alerts are the captured state history of 21 Oct (tests/fixtures/grafana/alert_history/
annotations_firing.json): r2's heartbeat rule fired on no data at 01:4x and resolved, and its
device is r2 by the rule's label.
"""
import json
import os
import subprocess
import time
from html import unescape

import pytest

from modules.ai import triggers
from tests.ai_person import pressed_by
from modules import alert_history as H
from modules import evidence_pack as EP
from modules.ai import explain
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_alert_history import _backfill, load
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import V4, _alerts, _build, _section, pack_lab  # noqa: F401

RULE = "NMAS heartbeat missing: r2"


@pytest.fixture
def history(pack_lab, monkeypatch):  # noqa: F811
    """The lab with the history in its folder, the 21 Oct slice backfilled, and nothing held
    by the alerts reader now."""
    monkeypatch.setattr(H, "_path", lambda: str(pack_lab["tmp"] / "alert_history.jsonl"))
    monkeypatch.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
    monkeypatch.setattr(H, "_firing_now", lambda: set())
    assert _backfill(load("annotations_firing"))["added"] == 93
    return pack_lab


def _episode(rule=RULE):
    """r2's heartbeat episode, edited only to read as firing: the captured rule fired on no
    data (`Alerting (NoData)`, the reader's no-data kind), so its first state is set to the
    condition's kind to stand for a firing alert; its times and labels are the capture's."""
    e = next(e for e in H.episodes(H.read()["rows"]) if e["rule"] == rule)
    return dict(e, fired_at=e["started_at"], outcome="fired")


def _marks(pack):
    return {s["name"]: s["provenance"] for s in pack["sections"]}


# ---------------------------------------------------------------------------- the marks

class TestEachSectionIsMarked:
    def test_a_pack_built_as_its_alert_fired_is_captured_throughout(self, pack_lab):
        pack = _build(_alerts(V4))
        # Schema 5 (C1849 to C1851) and 6 (C1896) keep schema 4's marks, on their new sections
        # too.
        assert pack["provenance"] == "captured" and pack["schema"] == 6
        assert set(_marks(pack).values()) == {"captured"} and "concurrent" in _marks(pack)
        assert "observer" in _marks(pack)
        assert all(s["provenance_words"].startswith("captured at the time")
                   for s in pack["sections"])

    def test_a_past_alerts_pack_says_what_was_captured_rebuilt_or_missing(self, history):
        e = _episode()
        pack = EP.build_for_episode(e, actor="operator@example.com")
        assert pack["provenance"] == "rebuilt" and pack["episode"] == e["id"]
        assert pack["built_at"] == e["fired_at"] and pack["device"] == "r2"
        assert _marks(pack) == {"alert": "captured", "concurrent": "rebuilt",
                                "device": "rebuilt", "history": "rebuilt",
                                "intent": "rebuilt", "neighbours": "missing",
                                "observed": "missing", "endpoints": "missing",
                                "health": "rebuilt", "observer": "rebuilt", "logs": "rebuilt"}
        for name in ("neighbours", "observed", "endpoints"):
            s = _section(pack, name)
            assert s["state"] == "absent" and s["pieces"] == []
            assert "cannot be rebuilt" in s["why"] and "as_of" not in s
            assert s["provenance_words"] == f"cannot be rebuilt: {EP.NOT_REBUILT[name]}"
        assert "operator@example.com" in pack["trigger"]
        # C1851 (the operator's Walk 2, 2026-10-27): the health figures are read for the
        # devices within two hops in the network model as it is now, said so, where they were
        # read for the alert's device alone ("0 of 0 devices"); tests/test_evidence_pack_ids.py
        # holds the two-hop reach on a fleet with intent.
        health = _section(pack, "health")
        assert "the network model as it is now" in health["devices_from"]
        assert "may differ from then" in health["provenance_words"]
        assert EP.intact(pack)

    def test_the_window_is_the_onset_to_the_alerts_time(self, history):
        e = _episode()
        pack = EP.build_for_episode(e, actor="operator@example.com")
        win = _section(pack, "health")["window"]
        assert win["to"] == e["fired_at"]
        # A heartbeat rule's onset is its start less the rule's window (750 s here).
        assert pack["onset"] == H.iso(H.epoch(e["started_at"]) - 750)

    def test_history_leaves_out_what_was_recorded_after_the_alerts_time(self, history):
        pack = EP.build_for_episode(_episode(), actor="operator@example.com")
        hist = _section(pack, "history")
        assert all(p["at"] <= pack["built_at"] for p in hist["pieces"])

    def test_the_intent_check_is_at_the_commit_current_then(self, pack_lab):
        """Two commits a second apart: the check as of between them reads the first."""
        from modules.nsot import listref
        from modules.nsot.repo import GoldenItem, save_golden

        repo = pack_lab["repo"]
        first = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                               text=True, check=True).stdout.strip()
        between = time.time() + 0.5
        time.sleep(1.6)
        body = open(os.path.join(repo, "golden", "r3.cfg"), encoding="utf-8").read()
        assert save_golden("Lab", [GoldenItem("r3", body + "\n! later\n", "192.0.2.13",
                                              platform="cisco_iosxe")],
                           source="capture", actor="operator@example.com",
                           baseline=False)["ok"]
        head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
        assert head != first
        sec = EP.intent_section_at(listref.resolve("Lab"), {"hostname": "r3",
                                                           "platform": "cisco_iosxe"}, between)
        assert sec.get("as_of_commit") == first[:12] and sec["state"] == "ok", (sec["state"], sec["why"])
        assert f"committed at {first[:12]}" in sec["source"]
        now = EP.intent_section_at(listref.resolve("Lab"), {"hostname": "r3",
                                                           "platform": "cisco_iosxe"},
                                   time.time() + 5)
        assert now["as_of_commit"] == head[:12]
        assert subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True,
                              text=True, check=True).stdout == "", "the repository only read"

    def test_before_the_repository_held_a_commit_the_check_says_so(self, pack_lab):
        from modules.nsot import listref
        sec = EP.intent_section_at(listref.resolve("Lab"), {"hostname": "r3"}, 1_000_000_000)
        assert sec["state"] == "absent" and "holds no commit as of 2001-09-09" in sec["why"]


# ---------------------------------------------------------------------------- Explain

class TestExplainReadsTheMarkedFrozenPack:
    @pytest.fixture
    def rebuilt(self, world, monkeypatch):  # noqa: F811
        monkeypatch.setattr(H, "_path", lambda: str(world.lab["tmp"] / "alert_history.jsonl"))
        monkeypatch.setattr(H, "_networks", lambda: {"grafana-alerts": ["Lab"]})
        monkeypatch.setattr(H, "_firing_now", lambda: set())
        _backfill(load("annotations_firing"))
        pack = EP.build_for_episode(_episode(), actor="operator@example.com")
        assert EP.record(pack)["ok"]
        # The rationale names no device it does not cite (C1897): r2's alert is cited.
        world.answer = _answer(pack, rationale="r2's heartbeat stopped.", hypotheses=[{
            "claim": "The heartbeat stopped.", "evidence_refs": ["alert"],
            "confirm_with": "show logging | include HEARTBEAT"}])
        return pack

    def _sent_pack(self, world, i=0):
        import re
        content = world.sent[i]["body"]["messages"][0]["content"]
        return json.loads(re.search(r'<data name="pack">(.*?)</data>', content, re.S).group(1))

    def test_each_sections_mark_is_in_what_explain_sends(self, world, rebuilt):
        with pressed_by("operator@example.com"):
            got = explain.explain(rebuilt["id"], actor="operator@example.com",
                                  trigger=triggers.person("operator@example.com"), send=world.send,
                                  today="2026-10-26")
        assert got["ok"] is True, got
        sent = {s["name"]: s for s in self._sent_pack(world)}
        assert sent["neighbours"]["provenance"] == "missing"
        assert sent["logs"]["provenance"] == "rebuilt"
        assert sent["alert"]["provenance"] == "captured"
        assert sent["health"]["provenance"] == "rebuilt", "kept by the health trim"
        assert all(s["provenance_words"] for s in sent.values())

    def test_explaining_again_sends_the_same_pack_and_builds_nothing(self, world, rebuilt):
        before = EP.read()["rows"]
        for _ in range(2):
            with pressed_by("operator@example.com"):
                explain.explain(rebuilt["id"], actor="operator@example.com",
                                trigger=triggers.person("operator@example.com"), send=world.send,
                                today="2026-10-26")
        assert self._sent_pack(world, 0) == self._sent_pack(world, 1)
        assert EP.read()["rows"] == before

    def test_the_prompt_text_and_version_are_explains_own(self, world, rebuilt):
        from modules.ai import prompts
        with pressed_by("operator@example.com"):
            explain.explain(rebuilt["id"], actor="operator@example.com",
                            trigger=triggers.person("operator@example.com"), send=world.send,
                            today="2026-10-26")
        system = world.sent[0]["body"]["system"]
        assert system[0]["text"] == prompts.load(*explain.PROMPT)["text"]
        assert "provenance" not in system[0]["text"]


# ---------------------------------------------------------------------------- the routes

class TestTheHistoryTab:
    def test_history_lists_past_alerts_grouped_with_build_evidence(self, history):
        c = history["client"]
        r = c.get("/v2/monitoring/alerts/history?range=all")
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "Content-Security-Policy" in r.headers
        assert "fired and resolved" in html and "Build evidence" in html
        assert 'aria-current="page">History' in html
        assert "NMAS heartbeat missing" in html and "Transitions as Grafana timed them" in html
        part = c.get("/v2/monitoring/alerts/history/list?range=all&show=all&device=r2")
        assert "r2" in unescape(part.get_data(as_text=True))

    def test_build_evidence_builds_once_and_draws_the_marked_pack(self, history):
        c = history["client"]
        e = _episode()
        r = c.post(f"/v2/monitoring/alerts/history/{e['id']}/evidence",
                   headers={"HX-Request": "true"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200, html
        assert r.headers.get("X-NMAS-Invalidates")
        assert "rebuilt afterwards" in html and "cannot be rebuilt" in html
        assert 'data-op="alert-evidence"' in html, "Explain is drawn on the built pack"
        packs = EP.read()["rows"]
        assert len(packs) == 1 and packs[0]["episode"] == e["id"]
        again = c.post(f"/v2/monitoring/alerts/history/{e['id']}/evidence",
                       headers={"HX-Request": "true"})
        assert again.status_code == 200 and EP.read()["rows"] == packs, "frozen: never rebuilt"
        listed = unescape(c.get("/v2/monitoring/alerts/history?range=all&show=all")
                          .get_data(as_text=True))
        assert packs[0]["id"] in listed

    def test_an_alert_the_history_does_not_hold_is_refused_saying_so(self, history):
        c = history["client"]
        r = c.post("/v2/monitoring/alerts/history/0123456789abcdef0123/evidence",
                   headers={"HX-Request": "true"})
        assert r.status_code == 404 and "is in the alert history" in unescape(
            r.get_data(as_text=True))
        assert EP.read()["state"] == "absent"
        bad = c.post("/v2/monitoring/alerts/history/not-an-id/evidence",
                     headers={"HX-Request": "true"})
        assert bad.status_code == 404 and EP.read()["state"] == "absent"

    def test_an_unreadable_history_is_said_never_a_quiet_list(self, history, monkeypatch):
        monkeypatch.setattr(H, "read", lambda: {"state": "unreadable", "rows": [],
                                                "error": "PermissionError: denied"})
        html = unescape(history["client"].get("/v2/monitoring/alerts/history")
                        .get_data(as_text=True))
        assert "The alert history cannot be read." in html and "PermissionError" in html
        assert "No alert fired" not in html
