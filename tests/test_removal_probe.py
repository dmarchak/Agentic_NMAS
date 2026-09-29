"""`scripts/nmas-removal-probe`: the instrument that decides which removal
shapes Mode B may send (the operator: ask the platform, because this is
where being wrong destroys configuration). Its device run is the operator's;
what is tested here is what it would do and how it reads what it sees.
"""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys

from modules.nsot import removal as RM

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-removal-probe")
R2 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg"),
          encoding="utf-8").read()


def _probe():
    loader = importlib.machinery.SourceFileLoader("nmas_removal_probe", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


P = _probe()


class TestEveryShapeIsProbed:
    def test_the_exemplars_and_the_shapes_are_one_set(self):
        """Both directions: a shape with no exemplar could never be measured,
        so never removed; an exemplar with no shape measures nothing Mode B
        uses."""
        assert set(P.EXEMPLARS) == {s.key for s in RM.SHAPES}
        assert len(P.EXEMPLARS) >= 11, "a floor: 11 less logging-buffered, plus the list-form ACL"

    def test_each_exemplar_is_an_instance_of_its_shape(self):
        for key in P.EXEMPLARS:
            for ex in P.plan_for(key):
                unit = ex["unit"]
                kind = next(s.kind for s in RM.SHAPES if s.key == key)
                shape = RM.shape_for(unit["chain"], unit["line"], kind)
                assert shape is not None and shape.key == key, (key, unit)

    def test_the_scratch_touches_no_management_path_and_no_account(self):
        for key in P.EXEMPLARS:
            for ex in P.plan_for(key):
                text = " ".join(ex["setup"] + ex["program"] + ex["teardown"])
                assert "username" not in text and "line vty" not in text, key
                assert "10.255." not in text, "documentation addresses only (RFC 5737)"

    def test_the_numbered_acl_program_is_the_one_suspected_of_deleting_the_list(self):
        (ex,) = P.plan_for("global.numbered-acl-entry")
        assert ex["program"] == ["no access-list 97 permit 192.0.2.1"]
        assert len(ex["setup"]) == 2, "a second entry, so the probe can SEE it go"


class TestTheClassifier:
    UNIT = {"chain": ["interface Loopback199"], "line": " load-interval 30"}
    WITH = R2 + "interface Loopback199\n load-interval 30\n description keep\n"

    def test_exactly_the_line_gone_is_exact(self):
        after = R2 + "interface Loopback199\n description keep\n"
        assert P.classify(self.WITH, after, self.UNIT)["result"] == "exact"

    def test_more_gone_is_broader_and_names_it(self):
        out = P.classify(self.WITH, R2, self.UNIT)
        assert out["result"] == "broader" and "description keep" in out["detail"]

    def test_something_new_is_different(self):
        after = R2 + "interface Loopback199\n description keep\nno logging buffered\n"
        out = P.classify(self.WITH, after, self.UNIT)
        assert out["result"] == "different" and "no logging buffered" in out["detail"]

    def test_the_line_still_there_is_incomplete(self):
        assert P.classify(self.WITH, self.WITH, self.UNIT)["result"] == "incomplete"

    def test_a_device_error_is_refused(self):
        out = P.classify(self.WITH, self.WITH, self.UNIT, "% Invalid input detected")
        assert out["result"] == "refused"

    def test_a_numbered_named_acl_entry_is_found_as_printed(self):
        config = R2 + "ip access-list extended NMASPROBE\n 10 permit ip host 192.0.2.1 any\n"
        unit = {"chain": ["ip access-list extended NMASPROBE"],
                "line": " permit ip host 192.0.2.1 any", "match_in_readback": True}
        assert P._locate(unit, config)["line"] == " 10 permit ip host 192.0.2.1 any"


class TestTheScriptItself:
    def test_the_dry_run_connects_to_nothing_and_prints_every_shape(self):
        out = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True,
                             timeout=60, cwd=ROOT)
        assert out.returncode == 0, out.stderr
        assert out.stdout.startswith("DRY RUN: nothing connects")
        for key in P.EXEMPLARS:
            assert key in out.stdout

    def test_apply_needs_an_accountable_person(self):
        out = subprocess.run([sys.executable, SCRIPT, "--apply", "--list", "Lab",
                              "--device", "r2"], capture_output=True, text=True,
                             timeout=60, cwd=ROOT)
        assert out.returncode == 1 and "--actor" in out.stdout

    def test_it_never_saves(self):
        src = open(SCRIPT, encoding="utf-8").read()
        body = src[src.index("def main"):]
        assert "save_config" not in body and "write memory" not in body


class TestALiveProcessIsNotAScratch:
    """The operator (2026-09-28): IOS allows one `router bgp`, so the BGP
    shape either adds a neighbour to the device's LIVE process or cannot be
    measured, and each must be stated rather than discovered."""

    (EX,) = P.plan_for("bgp.neighbor-remote-as", "router bgp 65001")

    def test_it_runs_in_the_devices_own_process_and_only_when_asked(self):
        assert self.EX["setup"][0] == "router bgp 65001" and self.EX["live"]
        why = P.skip_reason(self.EX, "router bgp 65001", allow_live_bgp=False)
        assert "LIVE BGP process (router bgp 65001)" in why and "--allow-live-bgp" in why
        assert P.skip_reason(self.EX, "router bgp 65001", allow_live_bgp=True) == ""

    def test_no_bgp_is_not_measured_never_refused(self):
        why = P.skip_reason(self.EX, "", allow_live_bgp=True)
        assert why.startswith("not measured: this device runs no BGP")

    def test_the_dry_run_names_the_live_process_not_a_made_up_as(self):
        out = subprocess.run([sys.executable, SCRIPT, "--shape", "bgp.neighbor-remote-as"],
                             capture_output=True, text=True, timeout=60, cwd=ROOT)
        assert "LIVE: runs only with --allow-live-bgp" in out.stdout
        assert "its LIVE process" in out.stdout and "65000" not in out.stdout

    def test_what_the_run_could_not_ask_never_enters_the_platform_record(self):
        rows = {"a": {"result": "exact", "detail": "", "device": "r3", "at": "t"},
                "b": {"result": "unmeasured", "detail": "not measured: x", "device": "r3", "at": "t"},
                "c": {"result": "failed", "detail": "the scratch did not land", "device": "r3",
                      "at": "t"},
                "d": {"result": "broader", "detail": "also removed: y", "device": "r3", "at": "t"}}
        rec = P.report(rows, "cisco_iosxe")
        assert set(rec["by_dialect"]["cisco_iosxe"]) == {"a", "d"}
        assert set(rec["full"]) == {"a", "b", "c", "d"}

    def test_exact_only_if_every_example_was(self):
        assert P.fold([{"result": "exact"}, {"result": "unmeasured"}]) == "unmeasured"
        assert P.fold([{"result": "exact"}, {"result": "broader"}]) == "broader"
        assert P.fold([{"result": "exact"}, {"result": "exact"}]) == "exact"



class TestTheFirstRealRun:
    """s4, 2026-09-29: removing `logging buffered 16001` left
    `no logging buffered`, and the repair could not undo it."""

    S4 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s4.cfg"),
              encoding="utf-8").read()
    UNIT = {"chain": [], "line": "logging buffered 16001"}

    def test_a_no_form_left_behind_is_overrides_default_not_different(self):
        out = P.classify(self.S4 + "logging buffered 16001\n",
                         self.S4 + "no logging buffered\n", self.UNIT)
        assert out == {"result": "overrides_default", "detail": "appeared: no logging buffered"}

    def test_an_unrelated_line_appearing_is_still_different(self):
        out = P.classify(self.S4 + "logging buffered 16001\n",
                         self.S4 + "no ip domain lookup\n", self.UNIT)
        assert out["result"] == "different"

    def test_the_repair_sees_the_line_the_residue_calculation_now_sees_too(self):
        """s4 carries `no logging console`, and the setting key reduced both it
        and `no logging buffered` to `logging` (C193): the residue calculation
        offered NOTHING, which is what the first run's repair acted on. Fixed
        2026-09-29: the leftover is residue, offered, and refused by the
        measured gate with its reason, never invisible. The repair's plain
        difference still agrees."""
        now = self.S4 + "no logging buffered\n"
        offered = RM.candidates(self.S4, now)
        assert [c["line"] for c in offered] == ["no logging buffered"], offered
        (unit,) = RM.removable(self.S4, now, mgmt_ip="10.255.1.14", dialect="cisco_ios")
        assert "no measured shape covers this line" in unit["why_not"]
        assert P.extras(self.S4, now) == [{"chain": [], "line": "no logging buffered"}]

    def test_logging_buffered_is_retired_from_the_probe(self):
        assert "global.logging-buffered" not in P.EXEMPLARS

    def test_the_run_repairs_with_the_plain_difference(self):
        """The seam: `extras` is right only if the run calls it."""
        src = open(SCRIPT, encoding="utf-8").read()
        body = src[src.index("def main"):]
        assert "extra = extras(before, now)" in body
        assert "candidates(" not in body


class TestWhatTheDeviceDisplays:
    """r3 (IOS-XE), 2026-09-29: both ACL shapes came back "did not land". The
    named one because `plan_for` dropped the example's read-back matching (a
    seam: the locator's test set the flag by hand); the numbered one because
    IOS-XE shows `access-list 97 permit X` as `ip access-list standard 97` /
    ` 10 permit X`, a form nothing looked for."""

    R3 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r3.cfg"),
              encoding="utf-8").read()
    XE = R3 + ("ip access-list extended NMASPROBE\n 10 permit ip host 192.0.2.1 any\n"
               " 20 permit ip host 192.0.2.2 any\nip access-list standard 97\n"
               " 10 permit 192.0.2.1\n 20 permit 192.0.2.2\n")

    def test_the_example_reaches_the_locator_with_its_matching_intact(self):
        """The seam, through `plan_for`, the path the run takes."""
        (ex,) = P.plan_for("named-acl.entry")
        assert P._locate(ex["unit"], self.XE) == {
            "chain": ["ip access-list extended NMASPROBE"],
            "line": " 10 permit ip host 192.0.2.1 any"}

    def test_a_numbered_entry_typed_at_the_top_is_found_in_list_form(self):
        (ex,) = P.plan_for("global.numbered-acl-entry")
        found = P._locate(ex["unit"], self.XE)
        assert found == {"chain": ["ip access-list standard 97"], "line": " 10 permit 192.0.2.1"}
        assert P.located_key(found, self.XE) == "numbered-acl.list-entry", \
            "filed under the shape Mode B would classify the displayed line as"
        assert RM.negation_program([found]) == ["ip access-list standard 97",
                                                " no 10 permit 192.0.2.1", "exit"]

    def test_a_list_form_entry_shown_at_the_top_is_found_too(self):
        """The reverse, IOS's display: typed in list form, shown as a top line."""
        (ex,) = P.plan_for("numbered-acl.list-entry")
        shown = R2_WITH = R2 + "access-list 96 permit 192.0.2.1\naccess-list 96 permit 192.0.2.2\n"
        found = P._locate(ex["unit"], shown)
        assert found == {"chain": [], "line": "access-list 96 permit 192.0.2.1"}
        assert P.located_key(found, R2_WITH) == "global.numbered-acl-entry"

    def test_not_there_in_any_form_is_none_and_the_evidence_is_kept(self):
        (ex,) = P.plan_for("named-acl.entry")
        assert P._locate(ex["unit"], self.R3) is None
        added = P.setup_added(self.R3, self.XE)
        assert "ip access-list extended NMASPROBE >  10 permit ip host 192.0.2.1 any" in added

    def test_a_result_is_filed_under_the_shape_it_was_shown_as(self):
        results = {}
        P.file_results(results, "global.numbered-acl-entry", [
            {"result": "exact", "detail": "", "shown_as": "numbered-acl.list-entry",
             "sent_as": "global.numbered-acl-entry"}], device="r3", at="t", dialect="x")
        assert set(results) == {"numbered-acl.list-entry"}
        P.file_results(results, "global.logging-host", [
            {"result": "exact", "detail": "", "shown_as": "(no shape)"}], device="r3", at="t",
            dialect="x")
        assert results["global.logging-host"]["result"] == "unmeasured"

    def test_every_example_records_what_its_restore_sent(self):
        """C194: a clean end says whether the repair was needed."""
        src = open(SCRIPT, encoding="utf-8").read()
        body = src[src.index("def main"):]
        for field in ('"teardown_error"', 'restore["extras_sent"]', 'restore["readded"]',
                      'rows[-1]["restore"] = restore'):
            assert field in body, field


class TestTheHeaderSeparatesTwoBehaviours:
    def test_numbered_and_named_lists_are_different_shapes(self):
        assert RM.shape_for(["ip access-list standard 97"], " 10 permit 192.0.2.1",
                            "leaf").key == "numbered-acl.list-entry"
        assert RM.shape_for(["ip access-list standard NAT-PRIVATE"],
                            " 10 permit 10.0.0.0 0.255.255.255", "leaf").key == "named-acl.entry"
        assert RM.shape_for(["ip access-list extended NMASPROBE"],
                            " 10 permit ip host 192.0.2.1 any", "leaf").key == "named-acl.entry"
