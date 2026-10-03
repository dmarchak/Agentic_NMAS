"""Every per-device record is read into the device's History tab, and every operation says
which source reads it (C359; the operator, 2026-10-03: persist's first real run on v2 was
correct and readable NOW, on its result, and not LATER, in History).

- The declaration: every gated route that can change a device or its record (confirm,
  approve, configure; `route_gates.GATES`) is in `operation_stages.HISTORY`, EXACTLY: it names
  the `history_sources.SOURCES` that read its record, or says `n/a:` why no device's record
  is involved, or `MISSING:` why nothing keeps one (counted, only shrinking). Every source is
  named by some operation or says what writes it. History draws every source in the registry.
- The behaviour, through the real routes on test_device_v2's lab (r3): a record planted in
  each source's own store, through its own writer where one exists, is one line in r3's
  History, with who and its full record; a source that raises is said, never a shorter
  timeline.
- End to end: a persist confirmed on the v2 card, its REAL recorder in place, is a line in
  r2's History ("Persisted", by the person, never a rotation), which it was not before.
"""

import json
import os
import re
import time

import pytest

from modules import history_sources as HS
from modules import operation_stages as S
from modules import route_gates as G
from modules.nsot import onboard as _onboard
from tests.test_device_v2 import _get, _text, lab  # noqa: F401 (the fixture)

#: The real recorder, taken before test_persist_screen's lab replaces it with a spy.
REAL_RECORD_NATIVE_PERSIST = _onboard._record_native_persist
KINDS = ("confirm", "approve", "configure")


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    """The rotation record, the break-glass log and the hold records live in DATA_DIR,
    which the run shares across tests: each test here plants its own."""
    data = tmp_path / "own-data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))


def _now(offset=0):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


class TestTheDeclaration:
    def test_every_route_that_can_change_a_device_is_declared_exactly(self):
        population = {ep for ep, g in G.GATES.items() if g.kind in KINDS}
        assert len(population) >= 70, len(population)
        assert set(S.HISTORY) == population, (sorted(population - set(S.HISTORY)),
                                              sorted(set(S.HISTORY) - population))

    def test_each_names_sources_history_draws_or_says_why_not(self):
        bad = []
        for ep, value in S.HISTORY.items():
            if isinstance(value, tuple):
                bad += [f"{ep}: {s!r} is no History source" for s in value if s not in HS.SOURCES]
                if not value:
                    bad.append(f"{ep}: names no source")
            elif not (value.startswith(("n/a:", "MISSING:"))
                      and len(value.split(":", 1)[1].split()) >= 3):
                bad.append(f"{ep}: {value!r} is neither sources nor a reason")
        assert bad == []

    def test_the_gaps_are_counted_and_only_shrink(self):
        missing = [ep for ep, v in S.HISTORY.items() if isinstance(v, str) and v.startswith("MISSING:")]
        assert len(missing) == S.HISTORY_MISSING_CEILING, missing

    def test_every_source_is_named_by_an_operation_or_says_what_writes_it(self):
        named = {s for v in S.HISTORY.values() if isinstance(v, tuple) for s in v}
        unclaimed = set(HS.SOURCES) - named - set(S.WRITTEN_ELSEWHERE)
        assert unclaimed == set(), unclaimed
        assert set(S.WRITTEN_ELSEWHERE) <= set(HS.SOURCES)

    def test_history_draws_every_source_in_the_registry(self, lab, monkeypatch):  # noqa: F811
        asked = []
        fake = {name: (lambda n: lambda ctx: asked.append(n) or
                       {"events": [], "errors": [], "cut": []})(name) for name in HS.SOURCES}
        monkeypatch.setattr(HS, "SOURCES", fake)
        _get(lab, "/v2/device/r3/history")
        assert asked == list(fake), "History asks every source, in the registry's order"

    def test_a_source_that_raises_is_said(self, lab, monkeypatch):  # noqa: F811
        def boom(ctx):
            raise ValueError("planted")
        monkeypatch.setitem(HS.SOURCES, "rotation", boom)
        text = _text(_get(lab, "/v2/device/r3/history")[1])
        assert "the rotation record could not be read (ValueError: planted)" in text


def _history(lab):  # noqa: F811
    return _get(lab, "/v2/device/r3/history")[1]


class TestEachSourceReachesTheTab:
    def test_a_persist_and_a_rotation(self, lab):  # noqa: F811
        from modules.nsot import credential_rotation as cr
        REAL_RECORD_NATIVE_PERSIST("r3", {"ok": True, "detail": "read back"},
                                   "operator@example.com", via="device page")
        cr.record_outcome("rotate", {"device": "r3", "actor": "alex@example.com",
                                     "state": cr.REVERTED, "via": "device page",
                                     "steps": [{"name": "push", "ok": True},
                                               {"name": cr.VERIFY, "ok": False,
                                                "error": "the fresh login was refused"}]})
        html = _history(lab)
        assert "Persisted: the startup config carries the running credential" in html
        assert "Rotation: reverted" in html and "stopped at verify" in html
        assert re.search(r'badge-danger[^>]*>[^<]*rotation', html), "a failed rotation is danger"
        assert "the fresh login was refused" in html, "the full record opens under the line"

    def test_a_retry_an_onboarding_run_and_an_intent_commits_person(self, lab):  # noqa: F811
        from modules.nsot import hostvars
        path = os.path.join(lab["repo"], hostvars.RETRY_LOG_REL)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump([{"device": "r3", "at": _now(), "actor": "alex@example.com",
                        "reason": "the neighbour was down for maintenance", "note": "OSPF lost"}], fh)
        with open(_onboard.runs_path(lab["repo"]), "a") as fh:
            fh.write(json.dumps({"device": "r3", "at": _now(), "actor": "alex@example.com",
                                 "kind": "verify", "ok": True, "promoted": True,
                                 "golden_commit": "abc123", "steps": ["rotate", "persist"]}) + "\n")
        html = _history(lab)
        assert "Retry authorised after a rollback" in html
        assert "the neighbour was down for maintenance" in html
        assert "Onboarding verify: done" in html

    def test_a_window_an_acknowledgement_and_a_breakglass_export(self, lab):  # noqa: F811
        from modules import acknowledgements, config, restarts
        assert restarts.record_planned(["r3"], time.time(), time.time() + 600,
                                       "alex@example.com", "IOS-XE upgrade", "test",
                                       list_name="Lab")["ok"]
        acknowledgements.record("authorisations:Lab:r3:shutdown", _now(), why="planned work",
                                by="alex@example.com", verified="person",
                                kind="repeated_authorisation", what="shutdown authorised 3 times")
        with open(os.path.join(config.DATA_DIR, "breakglass_exports.jsonl"), "a") as fh:
            fh.write(json.dumps({"at": time.time(), "list": "Lab", "actor": "alex@example.com",
                                 "via": "browser", "devices": {"r3": "d1"},
                                 "key_fingerprint": "fp"}) + "\n")
        html = _history(lab)
        assert "Planned-restart window declared" in html and "IOS-XE upgrade" in html
        assert "Acknowledged: shutdown authorised 3 times" in html
        assert "Break-glass record exported (1 device)" in html

    def test_an_interrupted_hold_a_freshness_authorisation_and_an_approval(self, lab,  # noqa: F811
                                                                            monkeypatch):
        from modules import config
        from modules.nsot import freshness, listref
        # Freshness resolves its file from LISTS_DIR (never creating a list); the lab's list
        # folder is <tmp>/lab, so LISTS_DIR is <tmp>.
        monkeypatch.setattr(config, "LISTS_DIR", os.path.dirname(listref.resolve("Lab").data_dir))
        folder = os.path.join(config.DATA_DIR, "device_ops", "lab")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "interrupted.jsonl"), "a") as fh:
            fh.write(json.dumps({"record": {"device": "r3", "list": "Lab", "operation": "deploy",
                                            "actor": "alex@example.com", "started": time.time(),
                                            "pid": 4242, "progress": {"step": "push"}},
                                 "found_at": time.time()}) + "\n")
        freshness.authorise("Lab", "r3", "fp123", actor="alex@example.com",
                            reason="Oxidized is a day behind")
        qpath = os.path.join(listref.resolve("Lab").data_dir, "approval_queue.json")
        with open(qpath, "w") as fh:
            json.dump([{"id": "q1", "device_hostname": "r3", "action_type": "revert_to_golden",
                        "status": "approved", "created_at": "2026-10-03 01:00:00",
                        "resolved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "resolved_by": "alex@example.com", "context": "drift answered"}], fh)
        html = _history(lab)
        assert "A deploy was cut off: its process ended" in html
        assert "Freshness gate authorised" in html and "Oxidized is a day behind" in html
        assert "Revert to golden: approved" in html

    def test_a_save_that_measured_the_device_and_changed_no_golden(self, lab):  # noqa: F811
        from modules.nsot import repo as R
        rc, _o, err = R.git(lab["repo"], "commit", "--allow-empty", "-q", "-m",
                            "golden: measured\n\nSource: save_all\nActor: alex@example.com\n"
                            "Devices-Measured: r3, r9\nIntent-Match: yes (2 of 2)")
        assert rc == 0, err
        assert "Measured, golden unchanged (save_all)" in _history(lab)


class TestPersistEndToEnd:
    def test_a_persist_confirmed_on_the_card_is_in_history(self, tmp_path, monkeypatch):
        """The operator's r2, in test_persist_screen's lab (its fixture's body, called here
        because its name is this module's other lab's): the card's confirm, the real recorder
        put back where that lab put a spy."""
        from tests.test_persist_screen import lab as persist_lab
        built = persist_lab.__wrapped__(tmp_path, monkeypatch)
        monkeypatch.setattr("modules.nsot.onboard._record_native_persist",
                            REAL_RECORD_NATIVE_PERSIST)
        c = built["client"]
        html = c.get("/v2/device/r2/persist").get_data(as_text=True)
        vals = json.loads(re.search(r"hx-vals='([^']*)'", html[html.index("op-confirm"):]).group(1))
        out = c.post("/v2/device/r2/persist/confirm", data=vals).get_data(as_text=True)
        assert "Persisted" in out
        hist = c.get("/v2/device/r2/history").get_data(as_text=True)
        assert "Persisted: the startup config carries the running credential" in hist
        assert "test-person@example.invalid" in hist and "via device page" in hist
        lines = re.findall(r'<summary class="hist-sum">(.*?)</summary>', hist, re.S)
        assert lines and not [l for l in lines if "rotat" in l.lower()], (
            "a save is never drawn as a rotation (C362)")
