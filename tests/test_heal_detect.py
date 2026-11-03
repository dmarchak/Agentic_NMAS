"""Heal to intent's grace period, topology hold and detect pass, and the seam H3 takes
(`modules/heal/grace.py`, `modules/heal/hold.py`, `modules/heal/detect.py`, `incidents.ready`
and `incidents.claim`; board H, part H2, docs/HEAL_TO_INTENT.md sections 4 and 6, N1, N3 and
N12), no network, no device, a fake clock.

- **The grace period (N1):** two reads at least the grace apart, the same departure, no outside
  change between; 120 s on a network marked lab, 900 s otherwise. An outside change, or a
  departure that moved, restarts it from the first read after; a clean or uncheckable read
  settles at once; an error neither passes nor fails, and three in a row settle as unreadable.
- **N12:** a person's change is healed after the grace period, the person named.
- **The topology hold (N3):** a Mercury change on the device or an intent neighbour (IPv4 and
  IPv6 peers), a rotation, an onboarding, a retirement or a link-set change holds it for 60
  minutes on a lab network and 4 hours otherwise; a record that cannot be read holds.
- **The detect pass:** reads only when a read is due, under the network's lock, at most
  `READS_PER_PASS`; off closes what is watching and reads nothing; each attached device read
  once; a settled incident is ready, and the decision claims it once.
- **The departure** a read carries is a hash of the masked differing lines; the real
  `check_device` returns it.
"""
import pytest

from tests.test_heal_policy import T0, confirm, iso, mark
from tests.test_sdn_connections import networks  # the fixture, named by each test below
from tests.test_heal_triggers import _Lazy, cause, world  # the fixtures and one helper

G, H, D, I, P = (_Lazy("grace"), _Lazy("hold"), _Lazy("detect"), _Lazy("incidents"),
                 _Lazy("policy"))


def rd(epoch, state="drifted", departure="d1", lines=1, error=""):
    return {"epoch": epoch, "state": state, "departure": departure, "changed_lines": lines,
            "error": error}


# ── The grace period, pure ──────────────────────────────────────────────────────────────────

class TestGrace:
    def test_no_read_yet_is_due_now(self):
        got = G.judge([], [], 120, T0)
        assert (got["state"], got["due_at"]) == ("need_read", T0)

    def test_one_drifted_read_waits_the_grace_out(self):
        got = G.judge([rd(T0)], [], 120, T0 + 10)
        assert (got["state"], got["due_at"]) == ("waiting", T0 + 120)

    def test_two_reads_the_grace_apart_with_the_same_departure_persist(self):
        got = G.judge([rd(T0), rd(T0 + 120)], [], 120, T0 + 120)
        assert got["state"] == "persisted" and (got["first"], got["second"]) == (0, 1)
        assert "two reads 120 s apart (at least 120 s), the same departure (d1)" in got["words"]

    def test_two_reads_closer_than_the_grace_wait_on(self):
        got = G.judge([rd(T0), rd(T0 + 119)], [], 120, T0 + 119)
        assert (got["state"], got["due_at"]) == ("waiting", T0 + 120)

    def test_a_departure_that_moved_restarts_it_from_that_read(self):
        got = G.judge([rd(T0), rd(T0 + 200, departure="d2")], [], 120, T0 + 200)
        assert (got["state"], got["first"], got["due_at"]) == ("waiting", 1, T0 + 320)
        assert "a different departure (d1 then d2)" in got["words"]

    def test_an_outside_change_between_the_reads_restarts_it(self):
        got = G.judge([rd(T0), rd(T0 + 200)], [T0 + 100], 120, T0 + 200)
        assert (got["state"], got["first"], got["due_at"]) == ("waiting", 1, T0 + 320)

    def test_an_outside_change_after_every_read_needs_a_read_now(self):
        got = G.judge([rd(T0)], [T0 + 50], 120, T0 + 60)
        assert (got["state"], got["due_at"]) == ("need_read", T0 + 60)

    def test_errors_between_two_reads_say_nothing_of_the_device(self):
        got = G.judge([rd(T0), rd(T0 + 60, "error", error="timed out"), rd(T0 + 130)], [], 120,
                      T0 + 130)
        assert (got["state"], got["first"], got["second"]) == ("persisted", 0, 2)

    def test_a_clean_read_settles_at_once(self):
        assert G.judge([rd(T0, "clean", "")], [], 900, T0)["state"] == "at_golden"

    def test_an_uncheckable_device_settles_at_once_naming_why(self):
        got = G.judge([rd(T0, "skipped", "", error="no golden config saved")], [], 900, T0)
        assert got["state"] == "not_checkable" and "no golden config saved" in got["words"]

    def test_an_error_is_read_again_and_three_settle_as_unreadable(self):
        one = G.judge([rd(T0, "error", error="timed out")], [], 120, T0)
        assert (one["state"], one["due_at"]) == ("need_read", T0 + G.RETRY_SECONDS)
        three = G.judge([rd(T0 + i * 60, "error", error=f"e{i}") for i in range(3)], [], 120,
                        T0 + 120)
        assert three["state"] == "unreadable" and "e0; e1; e2" in three["words"]

    def test_without_fingerprints_the_counts_are_compared_and_said(self):
        got = G.judge([rd(T0, departure=""), rd(T0 + 900, departure="")], [], 900, T0 + 900)
        assert got["state"] == "persisted" and "count of differing lines" in got["words"]


# ── The topology hold (N3) ──────────────────────────────────────────────────────────────────

def topo(**kw):
    base = {"neighbours": lambda n, d: ["peer-a"], "receipts": lambda n, d: [],
            "rotations": lambda n: {}, "onboarding": lambda n: [],
            "retirements": lambda n: {}, "link_set": lambda n: {}}
    base.update(kw)
    return base


class TestTopologyHold:
    def test_nothing_recent_holds_nothing(self):
        got = H.topology("Default", "core-b", T0, hold_minutes=60, **topo())
        assert got["held"] is False and "1 intent neighbour(s)" in got["words"]

    def test_a_receipt_on_an_intent_neighbour_holds_for_the_window(self):
        rec = {"peer-a": [{"id": "x1", "action": "deploy", "at": iso(T0 - 59 * 60)}]}
        got = H.topology("Default", "core-b", T0, hold_minutes=60,
                         **topo(receipts=lambda n, d: rec.get(d, [])))
        assert got["held"] and got["until"] == iso(T0 + 60)
        assert "Mercury's deploy of peer-a (receipt x1)" in got["words"]
        past = H.topology("Default", "core-b", T0 + 120, hold_minutes=60,
                          **topo(receipts=lambda n, d: rec.get(d, [])))
        assert past["held"] is False

    @pytest.mark.parametrize("source,value,what", [
        ("rotations", lambda n: {"core-b": (T0 - 60, iso(T0 - 60))}, "a credential rotation"),
        ("onboarding", lambda n: [{"at": iso(T0 - 60), "kind": "verify", "device": "new-1"}],
         "an onboarding (verify) of new-1"),
        ("retirements", lambda n: {"old-1": {"name": "old-1", "epoch": T0 - 60}},
         "the retirement of old-1"),
        ("link_set", lambda n: {"changed_epoch": T0 - 60}, "observed link set changed")])
    def test_each_kind_of_recent_change_holds(self, source, value, what):
        got = H.topology("Default", "core-b", T0, hold_minutes=60, **topo(**{source: value}))
        assert got["held"] and what in got["words"], got["words"]

    def test_a_record_that_cannot_be_read_holds(self):
        def torn(n, d):
            raise RuntimeError("torn")

        got = H.topology("Default", "core-b", T0, hold_minutes=60, **topo(receipts=torn))
        assert got["held"] and "cannot be read" in got["words"] and "torn" in got["words"]

    def test_the_minutes_are_60_on_a_lab_network_and_240_otherwise(self, networks):
        confirm("Default", heal_mode="dry_run")
        assert H.minutes("Default", T0)["minutes"] == 240
        mark("Default")
        got = H.minutes("Default", T0)
        assert (got["minutes"], got["source"]) == (60, "lab default")
        held = H.topology("Default", "core-b", T0, **topo(
            receipts=lambda n, d: [{"id": "x", "action": "deploy", "at": iso(T0 - 61 * 60)}]))
        assert held["held"] is False and held["minutes"] == 60

    def test_intent_neighbours_are_ipv4_and_ipv6_peers(self, world, monkeypatch):
        """BGP over IPv4 and IPv6, and OSPFv3, each in intent's own shape."""
        from modules import neighbours as N

        intents = {
            "core-b": {"interfaces": [{"name": "Gi1", "ipv4": "192.0.2.1 255.255.255.252"},
                                      {"name": "Gi2", "ospfv3": {"process": 1, "area": 0},
                                       "ipv6": ["2001:db8:1::1/64"]},
                                      {"name": "Gi3", "ipv6": ["2001:db8:2::1/64"]}],
                       "routing": {"bgp": {"asn": 65001, "neighbors": [
                           "neighbor 2001:db8:2::2 remote-as 65002",
                           "neighbor 192.0.2.2 remote-as 65004"]}}},
            "peer-v3": {"interfaces": [{"name": "Gi1", "ospfv3": {"process": 1, "area": 0},
                                        "ipv6": ["2001:db8:1::2/64"]}]},
            "peer-6": {"interfaces": [{"name": "Gi1", "ipv6": ["2001:db8:2::2/64"]}]},
            "peer-4": {"interfaces": [{"name": "Gi1", "ipv4": "192.0.2.2 255.255.255.252"}]},
            "apart": {"interfaces": [{"name": "Gi1", "ipv4": "192.0.2.9 255.255.255.252"}]}}
        monkeypatch.setattr(N, "committed_intents", lambda repo: (intents, ""))
        assert H._neighbours("Default", "core-b") == ["peer-4", "peer-6", "peer-v3"]


# ── The detect pass ─────────────────────────────────────────────────────────────────────────

class Device:
    """A fake `check_device`: each call returns the next of *answers*, read at the clock."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, network, device, by):
        self.calls.append(device)
        state = self.answers.pop(0) if self.answers else "drifted"
        if isinstance(state, Exception):
            raise state
        return {"ok": state in ("drifted", "clean"), "state": state, "hostname": device,
                "changed_lines": 1 if state == "drifted" else None, "departure":
                "d1" if state == "drifted" else "", "error": "", "skipped": False}


def change(device="core-b", ts=T0):
    cause(device, ts)


class TestDetect:
    def test_off_closes_what_is_watching_and_reads_nothing(self, world):
        change()
        P.turn_off("Default", actor="op@example.com")
        dev = Device()
        got = D.run("Default", now=T0 + 10, check=dev)
        assert got["mode"] == "off" and dev.calls == [] and len(got["closed"]) == 1
        assert "nothing new starts" in I.read("Default")["incidents"][0]["closed_why"]

    def test_production_waits_900_s_and_the_person_is_named(self, world):
        change()
        dev = Device("drifted", "drifted")
        first = D.run("Default", now=T0 + 5, check=dev, clock=lambda: T0 + 5)
        assert first["reads"] == 1 and first["waiting"][0]["due_at"] == T0 + 905
        early = D.run("Default", now=T0 + 600, check=dev, clock=lambda: T0 + 600)
        assert early["reads"] == 0, "no read before it is due"
        due = D.run("Default", now=T0 + 905, check=dev, clock=lambda: T0 + 905)
        assert due["ready"] and due["ready"][0]["how"] == "persisted"
        (inc,) = I.ready("Default")
        assert inc["settled"]["operands"]["grace_seconds"] == 900
        assert inc["triggers"][0]["person"].get("user") == "alice", "N12: the person named"

    def test_a_lab_network_waits_120_s(self, world):
        mark("Default")
        change()
        dev = Device("drifted", "drifted")
        D.run("Default", now=T0 + 5, check=dev, clock=lambda: T0 + 5)
        got = D.run("Default", now=T0 + 125, check=dev, clock=lambda: T0 + 125)
        assert got["ready"][0]["how"] == "persisted", got
        assert I.ready("Default")[0]["settled"]["operands"]["grace_seconds"] == 120

    def test_an_outside_change_between_the_reads_restarts_the_grace(self, world):
        mark("Default")
        change()
        dev = Device("drifted", "drifted", "drifted")
        D.run("Default", now=T0 + 5, check=dev, clock=lambda: T0 + 5)
        change(ts=T0 + 60)
        got = D.run("Default", now=T0 + 125, check=dev, clock=lambda: T0 + 125)
        assert got["ready"] == [] and got["waiting"][0]["due_at"] == T0 + 245, got

    def test_a_clean_read_is_ready_at_once_for_the_decision(self, world):
        change()
        got = D.run("Default", now=T0 + 5, check=Device("clean"), clock=lambda: T0 + 5)
        assert got["ready"][0]["how"] == "at_golden"

    def test_a_drift_run_in_progress_is_not_a_read(self, world):
        from modules.drift_check import DriftRunning

        change()
        got = D.run("Default", now=T0 + 5, check=Device(DriftRunning({"trigger": "scheduled"})))
        assert got["reads"] == 1 and I.read("Default")["incidents"][0]["reads"] == []

    def test_each_attached_device_is_read_once(self, world):
        from tests.test_heal_triggers import symptom

        change()
        symptom("leaf-c", T0 + 1)
        dev = Device("drifted", "clean", "drifted")
        D.run("Default", now=T0 + 5, check=dev)
        D.run("Default", now=T0 + 30, check=dev)
        assert dev.calls == ["core-b", "leaf-c"]
        (inc,) = [i for i in I.read("Default")["incidents"] if i["state"] == "watching"]
        assert [r["state"] for r in inc["attached"][0]["reads"]] == ["clean"]

    def test_a_pass_reads_at_most_its_bound_and_names_the_rest(self, world, monkeypatch):
        names = [f"dev-{i:02d}" for i in range(D.READS_PER_PASS + 2)]
        monkeypatch.setattr("modules.attention._device_networks",
                            lambda: {n: ["Default"] for n in names})
        for i, n in enumerate(names):
            change(n, T0 + i)
        got = D.run("Default", now=T0 + 60, check=Device())
        assert got["reads"] == D.READS_PER_PASS and len(got["deferred"]) == 2

    def test_a_pass_in_progress_refuses_a_second_by_name(self, world):
        change()
        with I.HealLock("Default", actor="Mercury", trigger="a pass elsewhere"):
            got = D.run("Default", now=T0 + 5, check=Device())
        assert got["ran"] is False and "a pass elsewhere" in got["busy"]


class TestTheSeam:
    def ready_one(self):
        change()
        D.run("Default", now=T0 + 5, check=Device("clean"))
        (inc,) = I.ready("Default")
        return inc

    def test_the_decision_claims_a_ready_incident_once(self, world):
        inc = self.ready_one()
        got = I.claim("Default", inc["id"], by="the decision", now=T0 + 6)
        assert got["state"] == "claimed" and I.ready("Default") == []
        with pytest.raises(I.Refused):
            I.claim("Default", inc["id"], by="the decision", now=T0 + 7)

    def test_an_outside_change_after_it_settled_sends_it_back(self, world):
        inc = self.ready_one()
        change(ts=T0 + 30)
        (back,) = I.read("Default")["incidents"]
        assert back["id"] == inc["id"] and back["state"] == "watching"
        assert back["settled"] is None and back["unsettled"]
        with pytest.raises(I.Refused):
            I.claim("Default", inc["id"], by="the decision")

    def test_an_unreadable_store_is_never_no_incident(self, world):
        from modules.filestore import StoreUnreadable

        self.ready_one()
        with open(I.path("Default"), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        with pytest.raises(StoreUnreadable):
            I.ready("Default")

    def test_nothing_in_the_detect_pass_sends_to_a_device(self):
        """H2 changes no device: the pass's only device call is the drift read."""
        import ast
        import inspect

        from modules.heal import detect, grace, incidents, triggers

        sent = {"send_config_set", "send_command", "apply_batch", "run_device_command",
                "PipelineRunner", "open_ssh", "ConnectHandler"}
        for mod in (detect, grace, incidents, triggers):
            names = {n.attr if isinstance(n, ast.Attribute) else n.id
                     for n in ast.walk(ast.parse(inspect.getsource(mod)))
                     if isinstance(n, (ast.Attribute, ast.Name))}
            assert not names & sent, (mod.__name__, names & sent)


# ── The departure a read carries ────────────────────────────────────────────────────────────

class TestDeparture:
    def test_the_same_lines_the_same_departure_the_headers_aside(self):
        from modules.drift_check import departure

        a = ["--- golden", "+++ running", "@@ -1 +1 @@", "+ip route 0.0.0.0 0.0.0.0 Null0"]
        b = ["--- other", "+++ names", "@@ -9 +9 @@", "+ip route 0.0.0.0 0.0.0.0 Null0"]
        assert departure(a) == departure(b) != "" and departure(["--- a", "+++ b"]) == ""

    def test_a_secret_is_masked_before_it_is_hashed(self):
        from modules.drift_check import departure

        one = ["+snmp-server community s3cretOne RO"]
        two = ["+snmp-server community s3cretTwo RO"]
        assert departure(one) == departure(two), "the value is masked, never what is hashed"

    def test_the_real_check_device_returns_it(self, monkeypatch, tmp_path):
        from modules import drift_check as DC
        from modules.config import get_current_list_name
        from tests import payload_providers as PP

        PP._drift_run(monkeypatch, tmp_path)
        got = DC.check_device(get_current_list_name(), "r2", by="heal to intent")
        assert got["state"] == "drifted" and len(got["departure"]) == 16 and got["read_at"]
        clean = DC.check_device(get_current_list_name(), "r1", by="heal to intent")
        assert (clean["state"], clean["departure"]) == ("clean", "")
        read = D.read_device(get_current_list_name(), "r2", by="heal to intent")
        assert (read["state"], read["departure"]) == ("drifted", got["departure"])
        skipped = D.read_device(get_current_list_name(), "r3", by="heal to intent")
        assert skipped["state"] == "skipped" and "no golden" in skipped["error"]
