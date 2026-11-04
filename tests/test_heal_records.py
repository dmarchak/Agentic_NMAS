"""Heal to intent's records (board H, part H6; docs/HEAL_TO_INTENT.md sections 4, 8, 9 and 11),
no network, no device, no NetBox: fakes only.

- **The step log** (`modules/heal/steplog.py`): a records store kept per network, every string
  masked at write and again on History's way out; absent and unreadable different; a write
  creates no network; each decision's steps in `decide.STEPS`' order, ending where the
  decision did; the act's program and hash written BEFORE anything is sent, and a heal whose
  row cannot be written refused with nothing sent; the act's every step and its records.
- **History** (`history_sources.heal`): one row per incident, its outcome and mode marked,
  opening to every step; ``Actor-Verified: policy`` counted under its own words, never as not
  verified, and kept out of "Show only these".
- **The trailers made true:** a heal's golden commit reads ``Source: heal_to_intent`` and
  ``Actor-Verified: policy``, with a ``Heal-Decision:`` trailer; a deploy's still ``pipeline``.
- **The change record** (`modules/heal/change_record.py`): board CR's sections in order, every
  one Mercury's, deterministic, masked, its rollback re-adding a removed line (IPv4 and IPv6),
  and no AI call.
- **The NetBox journal entry** (`modules/heal/journal.py`): through `_nb_post`, refused with the
  switch off or no authority, written under the policy's declared authority and recorded as
  created with it, never a configuration value; not written, and said, when writes are off,
  the device has no NetBox id, or nothing was sent.
- **An interrupted heal** (`modules/heal/interrupted.py`): a heal whose job ended before it
  recorded its outcome is found by its mark, recorded ``interrupted``, its incident closed,
  the network halted when its program may have been sent, and raised in Needs attention until
  a later decision clears it; a running heal and a finished one are never touched; the find is
  a read.
"""
import json
import os
import subprocess

import pytest

from tests.test_heal_act import FakeAct, SETTER, act, decided
from tests.test_heal_decide import GOLDEN, ROUTE4, ROUTE6, Fake, settle
from tests.test_heal_decide import lab  # the fixture, named by each test below
from tests.test_heal_policy import T0, auto
from tests.test_sdn_connections import networks  # the fixture `lab` builds on
from tests.test_heal_triggers import _Lazy

A, DC, DS, I, SL, INT, CR, J = (_Lazy("act"), _Lazy("decide"), _Lazy("decisions"),
                                _Lazy("incidents"), _Lazy("steplog"), _Lazy("interrupted"),
                                _Lazy("change_record"), _Lazy("journal"))
SECRET = "snmp-server community S3cretRO RO"


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


def _rows(network="Default"):
    got = SL.read(network)
    assert got["state"] in ("ok", "absent"), got
    return got["rows"]


# ── The step log store ──────────────────────────────────────────────────────────────────────

class TestTheStore:
    def test_every_string_is_masked_at_write_and_kept_owner_only(self, lab):
        SL.append("Default", {"row": "decision", "decision": "hd-000000000001",
                              "device": "edge-b", "program": [SECRET, ROUTE4.strip(),
                                                              ROUTE6.strip()],
                              "steps": [{"step": "read", "result": "ok",
                                         "words": f"read: {SECRET}"}]}, T0)
        (row,) = _rows()
        text = json.dumps(row)
        assert "S3cretRO" not in text, "a secret's value never reaches the store"
        assert row["program"][1:] == [ROUTE4.strip(), ROUTE6.strip()], "IPv4 and IPv6 kept"
        assert row["at"] and row["id"].startswith("hs-") and row["network"] == "Default"
        assert oct(os.stat(SL._path("Default")).st_mode & 0o777) == "0o600"

    def test_absent_and_unreadable_are_different_answers(self, lab):
        assert SL.read("Default")["state"] == "absent"
        assert SL.incidents("Default")["state"] == "absent"
        os.makedirs(os.path.dirname(SL._path("Default")), exist_ok=True)
        with open(SL._path("Default"), "w", encoding="utf-8") as fh:
            fh.write("{torn\n")
        assert SL.read("Default")["state"] == "unreadable"
        assert SL.incidents("Default")["state"] == "unreadable"
        with pytest.raises(RuntimeError, match="cannot be read"):
            SL.incident("Default", "hi-1")

    def test_a_write_creates_no_network_and_names_its_rows(self, lab):
        from modules.config import list_data_path

        with pytest.raises(SL.Refused, match="is no network"):
            SL.append("Nowhere", {"row": "decision"})
        assert not os.path.exists(list_data_path("Nowhere"))
        with pytest.raises(SL.Refused, match="one of"):
            SL.append("Default", {"row": "anything"})

    def test_it_is_a_records_store_kept_per_network(self):
        from modules import records_db
        from modules import records_migrate as RM

        assert "heal_steps" in records_db.STORES and records_db.STORE_WORDS["heal_steps"]
        st = RM.store_of("heal_steps")
        assert st.per_network and st.path_for("default").endswith("heal_steps.jsonl")


# ── The decision's steps ────────────────────────────────────────────────────────────────────

class TestTheDecisionsSteps:
    def test_a_dry_run_decision_s_steps_in_order_with_its_program(self, lab):
        settle(GOLDEN + ROUTE4, claim=False)
        got = DC.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))
        (decided_,) = got["decided"]
        (e,) = SL.incidents("Default")["entries"]
        assert [s["step"] for s in e["steps"]] == [n for n, _w in DC.STEPS], e["steps"]
        assert e["steps"][-2]["result"] == "would_heal" == e["outcome"]
        assert e["decisions"] == [decided_["decision"]] and e["mode"] == "dry_run"
        d = DS.find("Default", decided_["decision"])
        assert e["program"] == d["program"] and e["program_hash"] == d["program_hash"]
        assert "steps" not in d and "phase" not in d, "the decision's own store keeps none"

    def test_a_guard_ends_the_steps_where_it_applied(self, lab):
        DS.halt("Default", guard=14, name="a rolled-back heal", words="planted", operands={},
                now=T0 - 5)
        auto("Default", now=T0 - 60)
        settle(GOLDEN + ROUTE4, claim=False)
        DC.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))
        (e,) = SL.incidents("Default")["entries"]
        assert [s["step"] for s in e["steps"]] == ["claim", "stops", "record"], e["steps"]
        assert e["steps"][1]["result"] == "halted"

    def test_a_step_log_that_cannot_be_written_does_not_stop_the_decision(self, lab,
                                                                          monkeypatch):
        def broken(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr("modules.heal.steplog.append", broken)
        settle(GOLDEN + ROUTE4, claim=False)
        got = DC.run("Default", now=T0, sources=Fake(GOLDEN + ROUTE4))
        assert got["decided"] and not got["failed"], got


# ── The act's rows ──────────────────────────────────────────────────────────────────────────

class _Watching(FakeAct):
    """The act's sources, noting what the step log held when the apply was called."""

    def apply(self, device, **kw):
        self.at_apply = [r.get("row") for r in _rows()]
        self.started = next((r for r in _rows() if r.get("row") == "started"), None)
        return super().apply(device, **kw)


class TestTheActsRows:
    @pytest.mark.parametrize("route", [ROUTE4, ROUTE6])
    def test_the_program_is_written_before_anything_is_sent(self, lab, route):
        d = decided(GOLDEN + route)
        src = _Watching(GOLDEN + route)
        got = A.act_one("Default", d["id"], now=T0 + 5, sources=src)
        assert got["outcome"] == "healed", got["words"]
        assert src.started is not None, "the started row precedes the apply"
        assert src.started["program_hash"] == d["program_hash"]
        assert src.started["program"] == d["program"]
        assert src.started["steps"][-1]["step"] == "apply"

    def test_the_act_row_keeps_every_step_and_its_records(self, lab):
        got, _src, d = act(GOLDEN + ROUTE4)
        (row,) = [r for r in _rows() if r.get("row") == "act"]
        assert [s["step"] for s in row["steps"]] == [s["step"] for s in got["steps"]]
        assert row["outcome"] == "healed" and row["decision"] == d["id"]
        rec = row["records"]
        assert rec["golden"] == "c" * 40
        assert d["id"] in rec["receipt"] and rec["recheck"].startswith("ok")
        assert rec["change_record"]["state"] == "made"
        assert rec["journal"]["state"] == "not_written" and "writes are off" in \
            rec["journal"]["words"]
        (e,) = SL.incidents("Default")["entries"]
        assert e["state"] == "done" and e["outcome"] == "healed"

    def test_a_step_log_that_cannot_be_written_refuses_with_nothing_sent(self, lab,
                                                                         monkeypatch):
        d = decided(GOLDEN + ROUTE4)

        def broken(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr("modules.heal.steplog.append", broken)
        src = FakeAct(GOLDEN + ROUTE4)
        got = A.act_one("Default", d["id"], now=T0 + 5, sources=src)
        assert src.apply_kw is None, "nothing reached the apply"
        assert got["outcome"] == "refused" and "step log" in got["words"]
        assert got["records"]["step_log"].startswith("not written")

    def test_a_heal_refused_before_its_program_has_no_change_record(self, lab):
        d = decided(GOLDEN + ROUTE4)
        got = A.act_one("Default", d["id"], now=T0 + 5,
                        sources=FakeAct(GOLDEN + ROUTE4, read_error="timed out"))
        assert got["outcome"] == "refused"
        assert got["records"]["change_record"]["state"] == "none"


# ── The trailers ────────────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("reader_stores_in_tmp")
class TestTheTrailers:
    def _commit(self, monkeypatch, tmp_path, **kw):
        import routes.deploy as RD

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
        seen = {}
        monkeypatch.setattr(RD, "_baseline_earned", lambda *a, **k: {
            "baseline": False, "baseline_reasons": ["a test"], "standing": {}})
        monkeypatch.setattr("modules.nsot.repo.save_golden",
                            lambda ln, items, **k: seen.update(k) or {"ok": False,
                                                                      "error": "spied"})
        report = {"batch_id": "b1", "results": [
            {"device": "s1", "outcome": "deployed", "program_hash": "p" * 16,
             "heal": {"decision": "hd-0123456789ab"},
             "golden_pending": [{"hostname": "s1", "config_text": "hostname s1\n",
                                 "mgmt_ip": "192.0.2.21", "netbox_id": None,
                                 "device_uid": "s1"}]}]}
        RD._commit_batch_golden("Lab", report, actor=SETTER, **kw)
        return seen

    def test_a_heal_s_commit_names_its_workflow_and_its_decision(self, monkeypatch, tmp_path):
        import routes.deploy as RD

        seen = self._commit(monkeypatch, tmp_path, source=RD.HEAL_SOURCE)
        assert seen["source"] == "heal_to_intent"
        assert "Heal-Decision: s1=hd-0123456789ab" in seen["extra_trailers"]

    def test_a_deploy_s_commit_is_still_the_pipeline_s(self, monkeypatch, tmp_path):
        seen = self._commit(monkeypatch, tmp_path)
        assert seen["source"] == "pipeline"
        assert not [t for t in seen["extra_trailers"] if t.startswith("Heal-Decision")]

    def test_the_commit_reads_source_heal_to_intent_and_actor_verified_policy(
            self, tmp_path, monkeypatch):
        from modules import identity, route_gates
        from modules.nsot import repo as R

        monkeypatch.setattr(route_gates, "_installed", True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(tmp_path / name))
        (tmp_path / "t").mkdir()
        assert R.save_golden("t", [R.GoldenItem("r1", "hostname r1\n", "192.0.2.1",
                                                platform="cisco_ios")],
                             source="capture", actor=SETTER, allow_new=True)["ok"]
        with identity.carried_policy(SETTER, "fp-1"):
            out = R.save_golden("t", [R.GoldenItem("r1", "hostname r1\nlogging host "
                                                   "2001:db8::50\n", "192.0.2.1",
                                                   platform="cisco_ios")],
                                source="heal_to_intent", actor=SETTER)
        assert out.get("ok"), out
        msg = subprocess.run(["git", "-C", str(tmp_path / "t" / "config_repo"), "log", "-1",
                              "--format=%B"], capture_output=True, text=True,
                             check=True).stdout
        assert "Source: heal_to_intent" in msg and "Actor-Verified: policy" in msg, msg
        assert f"Actor: {SETTER}" in msg

    def test_the_golden_history_says_who_made_it(self):
        from modules.device_list import SOURCE_WORDS

        assert SOURCE_WORDS["heal_to_intent"] == "self-healing"


# ── History ─────────────────────────────────────────────────────────────────────────────────

class TestHistory:
    def test_policy_is_its_own_identity_never_not_verified(self):
        from modules import history_sources as HS

        events = [{"verified": v, "sha": str(i)} for i, v in
                  enumerate(("access", "policy", "policy", "none", "host-shell"))]
        got = HS.identity(events)
        assert (got["verified"], got["policy"], got["unverified"]) == (1, 2, 2)
        assert ("by the policy a verified person confirmed", 2) in got["others"]
        assert ("not verified", 1) in got["others"]

    def test_who_changed_it_says_policy_as_history_does(self):
        """The evidence an explanation reads (`modules.ai.who`) says a policy's commit as
        History counts it, never "not verified"."""
        from modules import history_sources as HS
        from modules.ai import who

        words = dict(HS.IDENTITY_KINDS)["policy"]
        assert who.HOW["policy"] == words and who.HOW.get("policy") != "not verified"

    def test_show_only_these_keeps_policy_commits_out(self, monkeypatch):
        from modules import history_sources as HS

        rows = [{"at": "2026-11-03T10:00:0%dZ" % i, "kind": "golden", "what": v, "devices": [],
                 "verified": v, "sha": str(i) * 40} for i, v in
                enumerate(("access", "policy", "none"))]
        events, _people, _counts = HS._kept({"golden": {"events": rows, "errors": [],
                                                         "cut": []}},
                                            {"device": "", "members": None, "since": None,
                                             "until": None}, "", "", None, True, "", None,
                                            None)
        assert [e["verified"] for e in events] == ["none"]

    def _ctx(self, device="", until=None):
        import types

        return {"ref": types.SimpleNamespace(name="Default"), "device": device, "limit": 50,
                "since": None, "until": until, "members": None, "inventory": set()}

    def test_one_row_per_incident_opening_to_every_step(self, lab):
        from modules import history_sources as HS

        got, _src, d = act(GOLDEN + ROUTE6)
        (e,) = HS.heal(self._ctx())["events"]
        assert e["kind"] == "heal" and e["devices"] == ["edge-b"]
        assert e["outcome"] == "healed" and "healed" in e["marks"] and "AUTO" in e["marks"]
        assert e["sha"] == "c" * 40, "the golden commit is linked by its sha"
        record = dict(e["record"])
        assert record["Incident"] == d["incident"] and d["id"] in record["Decisions"]
        assert record["Program lines (masked)"] == ROUTE6.strip().join(("no ", ""))
        assert [v.split(":", 1)[0] for k, v in e["record"] if k[0].isdigit()] == \
            [s["result"] for s in got["steps"]], "every step of the act, in order"

    def test_a_device_s_history_draws_its_own_rows_and_the_window_holds(self, lab):
        from modules import history_sources as HS

        act(GOLDEN + ROUTE4)
        assert HS.heal(self._ctx(device="edge-b"))["events"]
        assert HS.heal(self._ctx(device="core-a"))["events"] == []
        assert HS.heal(self._ctx(until=T0 - 86400 * 365 * 10))["events"] == []

    def test_a_row_written_unmasked_is_masked_on_the_way_out(self, lab):
        from modules import history_sources as HS

        os.makedirs(os.path.dirname(SL._path("Default")), exist_ok=True)
        with open(SL._path("Default"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"row": "decision", "incident": "hi-1", "device": "edge-b",
                                 "decision": "hd-1", "outcome": "would_heal", "at":
                                 "2026-11-03T10:00:00Z", "epoch": T0, "words": SECRET,
                                 "program": [SECRET], "program_hash": "h",
                                 "steps": [{"step": "read", "result": "ok",
                                            "words": SECRET}]}) + "\n")
        (e,) = HS.heal(self._ctx())["events"]
        assert "S3cretRO" not in json.dumps(e), "masked again on the way out"

    def test_an_unreadable_step_log_is_said_never_empty(self, lab):
        from modules import history_sources as HS

        os.makedirs(os.path.dirname(SL._path("Default")), exist_ok=True)
        with open(SL._path("Default"), "w", encoding="utf-8") as fh:
            fh.write("{torn\n")
        got = HS.heal(self._ctx())
        assert got["errors"] and "could not be read" in got["errors"][0]

    def test_it_is_a_declared_source_and_kind(self):
        from modules import history_sources as HS
        from modules import operation_stages as S

        assert HS.SOURCES["heal"] is HS.heal and HS.SOURCE_KINDS["heal"] == ("heal",)
        assert HS.KIND_FILTERS["heal"] == ("heal",) and "heal" in S.WRITTEN_ELSEWHERE


# ── The change record ───────────────────────────────────────────────────────────────────────

class TestTheChangeRecord:
    def _build(self, route, monkeypatch=None, **kw):
        from modules.heal import decide, kinds

        read = GOLDEN + route
        c = kinds.classify(GOLDEN, read, GOLDEN, platform="cisco_iosxe", mgmt_ip="192.0.2.6")
        prog = decide.program(GOLDEN, read, c["units"], c["removal_ids"], mgmt_ip="192.0.2.6",
                              platform="cisco_iosxe")
        decision = {"id": "hd-1", "incident": "hi-1", "kind": c["kind"],
                    "units": [kinds.masked_unit(u) for u in c["units"]],
                    "person": {"words": "the line names the account alice"}}
        result = {"outcome": "healed", "words": "healed and verified", "steps": [
            {"step": "intent", "result": "ok", "words": "each healed unit at intent"},
            {"step": "golden", "result": "ok", "words": "read again: at its golden"}]}
        policy = {"fingerprint": "fp-1", "by": SETTER, "reason": "Lab 10's AUTO"}
        return CR.build("Default", decision, result, host="edge-b", platform="cisco_iosxe",
                        prog=prog, read=kinds._stored(read), entry={}, authorise=[
                            {"line": prog["keys"][0], "reason": "the policy's words"}],
                        policy=policy, golden_before="c0ffee", golden_commit="c" * 40,
                        until="2026-11-04T00:00:00Z", at="2026-11-03T10:00:00Z", **kw), prog

    @pytest.mark.parametrize("route", [ROUTE4, ROUTE6])
    def test_board_cr_s_sections_in_order_its_rollback_re_adding_the_line(self, route):
        got, prog = self._build(route)
        text = got["markdown"]
        assert got["state"] == "made"
        at = [text.index(f"## {s}") for s in CR.SECTIONS]
        assert at == sorted(at), "every section, in board CR's order"
        assert prog["commands"][0] in text, "the program as sent"
        rollback = text.split("## Rollback plan", 1)[1]
        assert route.strip() in rollback, "the rollback re-adds the removed line"
        assert "fp-1" in text and SETTER in text and "2026-11-04T00:00:00Z" in text
        assert "no AI call" in text

    def test_it_is_deterministic_and_never_asks_a_model(self, monkeypatch):
        def no(*a, **k):
            raise AssertionError("the change record asked a model")

        monkeypatch.setattr("modules.ai.gateway.ask", no)
        first, _ = self._build(ROUTE4)
        again, _ = self._build(ROUTE4)
        assert first["markdown"] == again["markdown"]

    def test_a_secret_never_reaches_it(self):
        from modules.heal import change_record

        got = change_record.build("Default", {"id": "hd-1", "units": []},
                                  {"outcome": "healed", "steps": []}, host="edge-b",
                                  platform="cisco_iosxe",
                                  prog={"commands": [SECRET], "hash": "h" * 16, "ids": []},
                                  read=GOLDEN, entry={}, authorise=[], policy={})
        assert got["state"] == "made" and "S3cretRO" not in got["markdown"]

    def test_no_program_no_record(self):
        got = CR.build("Default", {}, {}, host="edge-b", platform="", prog=None, read="",
                       entry={}, authorise=[], policy={})
        assert got["state"] == "none" and "no change record" in got["words"]


# ── The NetBox journal entry ────────────────────────────────────────────────────────────────

class _NetBox:
    """A NetBox session that records each POST and answers with an id."""

    def __init__(self):
        self.posts = []

    def post(self, url, json=None, timeout=None):
        import types

        self.posts.append((url, json))
        return types.SimpleNamespace(ok=True, status_code=201, json=lambda: {**json, "id": 77})


DECISION = {"id": "hd-0123456789ab", "incident": "hi-1", "kind": "added_line",
            "program": [SECRET], "program_hash": "p" * 16,
            "policy": {"fingerprint": "fp-1", "by": SETTER, "reason": "Lab 10's AUTO"}}


@pytest.fixture
def nb_store(tmp_path, monkeypatch):
    from modules import netbox_guard

    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(tmp_path / "created.json"))
    monkeypatch.setattr("modules.netbox_guard.list_writer.__enter__", lambda s: s)
    monkeypatch.setattr("modules.netbox_guard.list_writer.__exit__", lambda s, *e: False)
    return netbox_guard


class TestTheJournal:
    def _write(self, outcome="healed", nb_id=41, session=None):
        nb = session or _NetBox()
        got = J.write("Default", "edge-b", {}, DECISION, outcome, nb_id=nb_id,
                      ready=lambda: (True, "", nb, "http://nb.invalid"))
        return got, nb

    def test_writes_off_is_not_written_and_asks_nothing(self, monkeypatch, nb_store):
        monkeypatch.setattr(nb_store, "writes_allowed", lambda: False)
        got, nb = self._write()
        assert got["state"] == "not_written" and "writes are off" in got["words"]
        assert nb.posts == []

    def test_no_netbox_id_is_not_written(self, monkeypatch, nb_store):
        monkeypatch.setattr(nb_store, "writes_allowed", lambda: True)
        monkeypatch.setattr("modules.heal.journal.netbox_id", lambda *a: None)
        got = J.write("Default", "edge-b", {}, DECISION, "healed",
                      ready=lambda: pytest.fail("NetBox was asked"))
        assert got["state"] == "not_written" and "no NetBox record" in got["words"]

    def test_nothing_sent_is_not_written(self, monkeypatch, nb_store):
        monkeypatch.setattr(nb_store, "writes_allowed", lambda: True)
        got, nb = self._write(outcome="refused")
        assert got["state"] == "not_written" and nb.posts == []

    @pytest.mark.parametrize("outcome, kind", [("healed", "success"),
                                               ("symptom_remains", "warning"),
                                               ("rolled_back", "danger")])
    def test_written_under_the_policy_s_authority_and_recorded(self, monkeypatch, nb_store,
                                                               outcome, kind):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: True if key == "netbox_allow_writes"
                            else default)
        # The `nmas-managed` tag's id, as `_managed_tag_id` caches it for this NetBox.
        monkeypatch.setattr("modules.netbox_client._managed_tag_ids",
                            {"http://nb.invalid": 9})
        got, nb = self._write(outcome=outcome)
        assert got["state"] == "written" and got["id"] == 77, got
        # What the NetBox census reconciles the entry against (H6): the device and the heal.
        assert (got["device_id"], got["heal"]) == (41, DECISION["id"]), got
        ((url, payload),) = nb.posts
        assert J.heal_id(payload["comments"]) == DECISION["id"], payload["comments"]
        assert url == "http://nb.invalid/api/extras/journal-entries/"
        assert (payload["assigned_object_type"], payload["assigned_object_id"],
                payload["kind"]) == ("dcim.device", 41, kind)
        assert "S3cretRO" not in payload["comments"] and "snmp-server" not in \
            payload["comments"], "never a configuration value"
        # C2437: tagged `nmas-managed` like every object Mercury creates (the lab NetBox
        # 4.6.9's OPTIONS answer a writable `tags` on journal entries, read 2026-11-04).
        assert payload.get("tags") == [9], payload
        (row,) = nb_store.get_created("Default", "extras/journal-entries")[
            "extras/journal-entries"]
        assert row["id"] == 77 and row["actor"] == SETTER
        assert row["authority"] == f"heal policy fp-1 confirmed by {SETTER}"

    def test_an_entry_that_cannot_be_tagged_is_not_posted(self, monkeypatch, nb_store):
        """Fail closed, as every create (C59): an untagged entry is never sent, and the heal's
        result says the write failed."""
        monkeypatch.setattr(nb_store, "writes_allowed", lambda: True)
        monkeypatch.setattr("modules.netbox_client._managed_tag_ids", {})

        def no_tag(*a, **k):
            raise RuntimeError("NetBox returned HTTP 500")
        monkeypatch.setattr("modules.netbox_client._ensure_tag", no_tag)
        got, nb = self._write()
        assert got["state"] == "failed" and "untagged" in got["words"], got
        assert nb.posts == []

    def test_the_chokepoint_refuses_without_an_authority(self, monkeypatch, nb_store):
        from modules import netbox_client, netbox_guard

        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        nb = _NetBox()
        with pytest.raises(netbox_guard.NetBoxWriteUnauthorised):
            netbox_client.add_journal_entry(nb, "http://nb.invalid", 41, "success", "words")
        with pytest.raises(ValueError, match="kind"):
            netbox_client.add_journal_entry(nb, "http://nb.invalid", 41, "loud", "words")
        assert nb.posts == []

    def test_its_netbox_id_comes_from_the_inventory_or_the_manifest(self, monkeypatch):
        assert J.netbox_id("Default", "edge-b", {"_netbox_id": "41"}) == 41
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("nb:52", {}))
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("R", (), {"repo_dir": "/nonexistent"})())
        assert J.netbox_id("Default", "edge-b", {}) == 52
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:edge-b", {}))
        assert J.netbox_id("Default", "edge-b", {}) is None


# ── An interrupted heal ─────────────────────────────────────────────────────────────────────

def _taken(running=GOLDEN + ROUTE4):
    d = decided(running)
    return DS.take("Default", d["id"], by="test", now=T0 + 1)


def _left(d, pid=999999):
    """The mark a process that ended left: its record, no lock held."""
    p = INT.path("Default", d["id"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"decision": d["id"], "device": d["device"], "pid": pid,
                   "started_at": "2026-11-03T10:00:00Z"}, fh)


class TestInterrupted:
    def test_a_running_heal_is_never_found(self, lab):
        d = _taken()
        m = INT.Mark("Default", d["id"], d["device"]).acquire()
        try:
            assert INT.find("Default")["found"] == []
            assert INT.reap("Default", now=T0 + 9)["reaped"] == []
        finally:
            m.release()
        assert not os.path.exists(INT.path("Default", d["id"])), "a clean end leaves nothing"

    def test_a_process_that_ended_mid_apply_is_recorded_and_halts(self, lab):
        d = _taken()
        SL.record_started("Default", d, [{"step": "apply", "result": "running",
                                          "words": "applying"}], d["program"],
                          d["program_hash"], by="test", now=T0 + 2)
        _left(d)
        (found,) = INT.find("Default")["found"]
        assert found["mark"] == "left"
        out = INT.reap("Default", now=T0 + 9)
        (r,) = out["reaped"]
        assert r["halted"] and "ended while it ran" in r["words"]
        assert "may have been sent" in r["words"] and "apply" in r["words"]
        assert DS.find("Default", d["id"])["applied"]["outcome"] == "interrupted"
        assert DS.halted("Default")["guard"] == 14
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed", "the device may take a new incident"
        (e,) = SL.incidents("Default")["entries"]
        assert e["state"] == "interrupted" and e["outcome"] == "interrupted"
        assert INT.reap("Default", now=T0 + 10)["reaped"] == [], "recorded once"

    def test_a_job_that_raised_before_its_apply_is_recorded_and_does_not_halt(self, lab):
        d = _taken()
        SL.record_raised("Default", d, "RuntimeError: the session pool is closed")
        (r,) = INT.reap("Default", now=T0 + 9)["reaped"]
        assert not r["halted"] and "RuntimeError: the session pool is closed" in r["words"]
        assert "nothing was sent" in r["words"]
        assert DS.halted("Default") == {}

    def test_a_finished_heal_is_never_found(self, lab):
        got, _src, d = act(GOLDEN + ROUTE4)
        assert got["outcome"] == "healed"
        assert INT.find("Default")["found"] == []

    def test_a_heal_that_finishes_while_its_mark_is_probed_is_never_counted(self, lab,
                                                                           monkeypatch):
        """The mark is probed BEFORE the decisions are read again: a heal writes its outcome
        before it releases its mark, so one that ends between the reads is seen finished."""
        d = _taken()
        real = INT.mark_state

        def finishing(network, decision_id):
            DS.applied(network, decision_id, "healed", by="the job", words="healed",
                       now=T0 + 3)
            return real(network, decision_id)

        monkeypatch.setattr("modules.heal.interrupted.mark_state", finishing)
        assert INT.find("Default")["found"] == []
        assert DS.find("Default", d["id"])["applied"]["outcome"] == "healed"

    def test_the_find_is_a_read(self, lab):
        d = _taken()
        _left(d)
        folder = os.path.dirname(SL._path("Default"))

        def listing():
            return sorted((os.path.join(r, f), os.path.getsize(os.path.join(r, f)))
                          for r, _d, fs in os.walk(folder) for f in fs)

        before = listing()
        assert INT.find("Default")["found"]
        assert listing() == before

    def test_a_job_that_raises_is_found_by_the_next_pass(self, lab, monkeypatch):
        from modules.nsot import capture_job

        monkeypatch.setattr(capture_job, "_announce", lambda job_id, ok: None)
        decided(GOLDEN + ROUTE4)

        def boom(n, d, sources=None):
            raise RuntimeError("the job died")

        monkeypatch.setattr("modules.heal.act.apply_decision", boom)
        (started,) = A.run("Default", now=T0 + 1)["started"]
        assert capture_job.wait(started["job"], 10)
        assert capture_job.get(started["job"])["state"] == "failed"
        assert INT.mark_state("Default", started["decision"])[0] == "none", "released"
        again = A.run("Default", now=T0 + 2)
        assert again["interrupted"] == [started["decision"]]
        assert "the job died" in DS.find("Default", started["decision"])["applied"]["words"]

    def test_act_one_holds_and_releases_the_mark(self, lab):
        d = decided(GOLDEN + ROUTE4)
        m = INT.Mark("Default", d["id"], d["device"]).acquire()
        try:
            got = A.act_one("Default", d["id"], now=T0 + 5, sources=FakeAct(GOLDEN + ROUTE4))
            assert got["outcome"] == "" and "running in another job" in got["words"]
            assert DS.find("Default", d["id"]).get("taken") is None, "nothing was taken"
        finally:
            m.release()
        got = A.act_one("Default", d["id"], now=T0 + 6, sources=FakeAct(GOLDEN + ROUTE4))
        assert got["outcome"] == "healed"
        assert INT.mark_state("Default", d["id"])[0] == "none"


class TestTheNeedsAttentionRow:
    def rows(self, monkeypatch):
        from modules import attention

        monkeypatch.setattr(attention, "_page_network", lambda: "Default")
        return [r for r in attention.heal_source(now=T0 + 20)["rows"]
                if r["kind"] == "interrupted"]

    def test_an_interrupted_heal_is_a_row_with_an_action_until_it_clears(self, lab,
                                                                         monkeypatch):
        from modules.attention import ACKNOWLEDGED_HERE, CLEARS

        d = _taken()
        SL.record_started("Default", d, [], d["program"], d["program_hash"], by="test",
                          now=T0 + 2)
        _left(d)
        (found,) = self.rows(monkeypatch)
        assert "the heal runner records it" in found["cause"], "found, not yet recorded"
        INT.reap("Default", now=T0 + 9)
        (r,) = self.rows(monkeypatch)
        assert r["level"] == "danger" and r["event"] == d["id"] and r["acknowledge"]
        assert r["devices"] == ["edge-b"] and "edge-b" in r["action"]["href"]
        assert "acknowledge" in r["action"]["label"] and "halted" in r["cause"]
        assert ("heal", "interrupted") in ACKNOWLEDGED_HERE
        assert "acknowledge" in CLEARS[("heal", "interrupted")][0]
        DS.record("Default", {"outcome": "nothing", "device": "edge-b"}, T0 + 15)
        assert self.rows(monkeypatch) == [], "a later decision finds it with nothing to heal"
