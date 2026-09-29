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
        assert len(P.EXEMPLARS) >= 11

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
