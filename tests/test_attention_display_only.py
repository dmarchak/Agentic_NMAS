"""Display only (C3166; the operator's addition 1, 2026-11-12): "Cached values are for drawing
pages. The heal pipeline (detect, decide, guards, apply, verify, can't-fix), deploys and their
before/after reads always read live."

Needs attention's background store (modules/attention_store.py) holds values for drawing
pages. Held, they can be up to a cadence old; a decision made on one would be made on a page's
stale copy. Two holds, each shown able to fail:

1. **Through the real code, counted.** The store holds a value for the network, planted with a
   row a decision would act on if it read it, and its read counter (`attention_store.reads()`,
   every read of a held value) is taken before and after each path runs through its real code:
   heal's detect pass (`heal.detect.run`), the decision (`heal.decide.decide_one`: a would-heal
   and a can't-fix), the act (`heal.act.act_one`: the stops again at apply, the plan, the apply
   as the policy, verify and the record), and a deploy's plan and apply with its before and
   after reads (the cores every v2 deploy runs, tests/deploy_core.py). None of them reads it.
2. **By parsing.** No module of those paths names the store at all (an import or an
   attribute), so a path no test here runs cannot read it either.
"""

import ast
import os

import pytest

from modules import attention as A
from modules import attention_store as S
from tests import deploy_core
from tests.source_index import tracked
from tests.test_deploy_plan_apply_seam import _plan
from tests.test_deploy_plan_apply_seam import client  # the fixture, named by each test below
from tests.test_heal_act import act
from tests.test_heal_decide import GOLDEN, ROUTE4, one
from tests.test_heal_decide import lab  # the fixture, named by each test below
from tests.test_heal_detect import Device, change
from tests.test_heal_policy import T0
from tests.test_heal_triggers import _Lazy
from tests.test_heal_triggers import world  # the fixture, named by each test below
from tests.test_sdn_connections import networks  # the fixture `lab` builds on

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = _Lazy("detect")

#: The paths that must read live, by file: the heal pipeline (every module of modules/heal/),
#: and a deploy's (the nine-stage pipeline, THE plan and apply, the batch job, the deploy's own
#: module, a restore, verify's scope).
LIVE_PATHS = (tracked("modules/heal", suffix=".py", recursive=False)
              + [os.path.join(ROOT, *p.split("/")) for p in (
                  "modules/pipeline.py", "routes/deploy.py", "modules/deploy_job.py",
                  "modules/nsot/deploy.py", "modules/nsot/restore.py",
                  "modules/nsot/verify_scope.py")])
STORE = "attention_store"


@pytest.fixture
def held(monkeypatch):
    """A held value for Default with a row on it (a planted drift row naming edge-b), and the
    store's read counter before the path runs."""
    def drift_source():
        return A.source_result("drift", "Drift", read_at=T0, took_ms=0, checked="planted", rows=[
            A.row(source="drift", kind="drifted", key="lab:drifted:edge-b", level="warning",
                  what="edge-b departs from its golden (a held value, never a live one)",
                  cause="planted by the display-only test", devices=["edge-b"],
                  action={"label": "Capture what the device holds as its golden, or deploy"})])
    monkeypatch.setattr(A, "SOURCES", (drift_source,))
    S.refresh("Default", publish=False)
    assert S._nets["Default"].value["rows"], "the planted value is held"
    return S.reads()


@pytest.fixture
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


class TestThroughTheRealCode:
    def test_the_counter_counts_a_read(self, held):
        """The control: a page's read of the held value is counted."""
        S.read("Default")
        S.badge("Default")
        assert S.reads() == held + 2

    def test_heals_detect_pass_reads_nothing_held(self, world, held):
        change()
        got = D.run("Default", now=T0 + 5, check=Device("drifted"), clock=lambda: T0 + 5)
        assert got["reads"] == 1, "the detect pass read the device live"
        assert S.reads() == held

    def test_the_decision_reads_nothing_held(self, lab, held):
        assert one(GOLDEN + ROUTE4)["outcome"] == "would_heal"
        assert S.reads() == held

    def test_a_cant_fix_reads_nothing_held(self, lab, held):
        cant = one(GOLDEN + "username audit privilege 15 secret 9 $9$abc\n")
        assert cant["outcome"] == "cant_fix", cant["words"]
        assert S.reads() == held

    def test_the_act_its_guards_apply_and_verify_read_nothing_held(self, lab, held,
                                                                   no_host_addresses):
        got, _src, _d = act(GOLDEN + ROUTE4)
        assert got["outcome"] == "healed", got["words"]
        assert {"stops", "apply", "symptom", "record"} <= {s["step"] for s in got["steps"]}
        assert S.reads() == held

    def test_a_deploys_plan_and_apply_read_nothing_held(self, client, held):
        device = _plan(client)
        result = deploy_core.post_apply(json={"confirmations": {"r6": device["capture_hash"]},
                                              "command_hashes": {"r6": device["command_hash"]}})
        assert "r6" in result.get_json().get("deployed", [])
        assert S.reads() == held


def _names_the_store(source: str) -> list:
    """Each line of *source* that imports the store or names it as an attribute."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").endswith(STORE) or any(a.name == STORE for a in node.names):
                out.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(a.name.endswith(STORE) for a in node.names):
                out.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == STORE:
            out.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id == STORE:
            out.append(node.lineno)
    return sorted(set(out))


class TestByParsing:
    def test_the_population(self):
        """Measured 2026-11-12: 36 modules under modules/heal/ and six of the deploy's."""
        assert len(LIVE_PATHS) >= 40
        assert all(os.path.exists(p) for p in LIVE_PATHS), \
            [p for p in LIVE_PATHS if not os.path.exists(p)]

    def test_the_scan_finds_a_planted_read(self):
        assert _names_the_store("from modules import attention_store\n") == [1]
        assert _names_the_store("import modules.attention_store as s\n") == [1]
        assert _names_the_store("x = 1\nimport modules\nmodules.attention_store.read()\n") == [3]
        assert _names_the_store("from modules import attention\nattention.needs_attention()\n") \
            == [], "a live computation is not the store"

    def test_no_live_path_names_the_store(self):
        found = {os.path.relpath(p, ROOT): lines for p in LIVE_PATHS
                 if (lines := _names_the_store(open(p, encoding="utf-8").read()))}
        assert not found, ("a path that must read live names Needs attention's held values "
                           f"(C3166, display only): {found}")
