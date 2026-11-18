"""The Lab 10 demo replayed offline (2026-11-17): each injected fault run end to end through
Mercury's real code against recorded device answers, its outcome checked against the close the
host recorded for it.

**What the demo injected.** Every take on 2026-11-17 (00:26, 02:36, 03:16, 03:26, 04:51, 17:53
the class demo "take G", and 22:28 UTC) injected seven faults, one problem per device, as
lab10-live-demo-plan's "The faults" lists them: an interface description removed on r2
(GigabitEthernet3), r3 and r4 (GigabitEthernet4) and r6 (GigabitEthernet3), each closed
"healed: healed and verified; the incident named no symptom beyond the configuration" by
Mercury's built-in restore; BPDU guard err-disable on s1 and s2 (Gi1/0), each closed "fixed:
saved script BPDU guard recovery (access ports)'s run <id> verified"; and port security on s5
(Gi0/3), closed "fixed: the plan's run <id> verified on s5 ... (attempt 1, errdisable-recover)"
by the AI's plan a person approved. The host's incidents store, read masked on 2026-11-18,
holds all 49 closes (`RECORDED` below names each take's incident per device).

**What each replay runs and what it stands in for:**

- **r2, r3, r4: the restore** through the real decision (`decide.decide_one`) and the real act
  (`act.act_one`: its stops, its plan's program computed by `routes.deploy._program`, its
  after-verify verdict, its record and the incident's close), on each router's sanitized golden
  (tests/fixtures/configs/fleet/, the same descriptions the demo plan names) read back with the
  one description removed. The decision's sources are tests/test_heal_decide.py's `Fake` and the
  apply is tests/test_heal_act.py's `FakeAct` (the pipeline's stages are
  tests/test_heal_act.py `TestThroughTheRealApply`'s, on s1). The demo's restores ran as G6's
  switch-on batch; the batch path is not replayed here, only the decision and act each restore
  went through.
- **s1: the saved script** "BPDU guard recovery (access ports)", saved from a verified run of the
  built-in errdisable-recover plan, fired on s1's standing incident classified from s1's own
  captured lines (tests/fixtures/errdisable/), through `saved_plans.fire_matching`, the real
  runner (`command_plan_run.run`) on tests/test_command_plan.py's fake switch, and its close
  (`saved_plans.close_fixed`, `decide.end_standing`). The script's match is G7 walk item 3's
  (condition err-disabled, cause BPDU guard, port role access); its fills are the shipped map.
- **s5: the AI's recorded answer** (tests/fixtures/incident_story/, take G's troubleshooting
  record), replayed with no provider call: its step's parameter hash recomputed by today's
  code is the one recorded, and the step is held by the plan engine's schema and the built-in
  plan's parameters. Its run and close need inputs no fixture holds (see the notes).

**Not replayed** (their inputs are not offline): r6 (no golden of r6 is a fixture), s2 (no
capture of s2's lines in Loki, nor its intent or `show interfaces status`), s5's run and close
(s5's golden, intent and err-disabled row), r7's telemetry plan of 01:31 UTC (its
troubleshooting record and the plan run's reads). No device, no network, no AI.
"""
import os
import re

import pytest

from tests import test_command_plan as CPT
from tests import test_errdisable as T
from tests.test_command_plan import lab as plan_lab  # noqa: F401 (the fake switch's lab)
from tests.test_deploy_contract import _config
from tests.test_heal_act import _ReadOnce
from tests.test_heal_decide import Fake, settle
from tests.test_heal_decide import lab as heal_lab  # noqa: F401 (heal to intent's lab)
from tests.test_heal_policy import T0, auto, confirm
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture heal_lab builds on)

A, DC, DS, I, K = (_Lazy("act"), _Lazy("decide"), _Lazy("decisions"), _Lazy("incidents"),
                   _Lazy("kinds"))

#: The takes of 2026-11-17 (UTC), as the host's incidents store names them.
TAKES = ("00:26", "02:36", "03:16", "03:26", "04:51", "17:53", "22:28")
#: Each take's incident per device (the host's store, read masked 2026-11-18).
RECORDED = {
    "r2": ("hi-9ae3c74dd331", "hi-c3c424e3b2a6", "hi-3f7d1cb2dc3a", "hi-44a32b871bb3",
           "hi-0d3bf029e286", "hi-4471f30fbc6c", "hi-292a664056c3"),
    "r3": ("hi-150ec6edf2a8", "hi-438b179ddc70", "hi-977e71ad809c", "hi-85ef3bc594ea",
           "hi-a6a1fc9c37bd", "hi-425a61c9ce63", "hi-8a02867fc425"),
    "r4": ("hi-646613bb65d6", "hi-eaeceb43a5b2", "hi-a54e66f9b07f", "hi-a7e13e5a474a",
           "hi-b710f8a68633", "hi-bb61a64d9fba", "hi-221f4dc5d0b7"),
    "r6": ("hi-c67b96bd03c7", "hi-ea331f085a55", "hi-7dcec557de35", "hi-823a820cb61b",
           "hi-d121f76d5c31", "hi-e95eac2bc6d3", "hi-9c60545b6ecf"),
    "s1": ("hi-0ebe9edce98a", "hi-1e09808dba6b", "hi-33ac3842f090", "hi-6a25bba1193a",
           "hi-9989e5e4c6b8", "hi-3617b7059465", "hi-1bab6170b8e9"),
    "s2": ("hi-39d04abd304d", "hi-9524376e0360", "hi-4dfa37d67c05", "hi-7c0e6df9e080",
           "hi-5aabafb07f50", "hi-282737477976", "hi-2be58eb23448"),
    "s5": ("hi-63cb96fe16bc", "hi-993d7893861a", "hi-8ad38f815c18", "hi-a7d550d8d924",
           "hi-2764f896b3e0", "hi-ed64c53852c5", "hi-f615a34db632"),
}
#: The close every take recorded for a restored router, word for word before its decision id.
RESTORED = ("healed: healed and verified; the incident named no symptom beyond the "
            "configuration (decision ")


def test_every_take_closed_seven_faults_and_r7_in_none():
    """The record the replays are checked against: seven devices in each of the seven takes,
    r7 in none of them (the operator's request named "five faults (r6, r7, s5)")."""
    assert sorted(RECORDED) == ["r2", "r3", "r4", "r6", "s1", "s2", "s5"]
    assert all(len(ids) == len(TAKES) for ids in RECORDED.values())
    assert len({i for ids in RECORDED.values() for i in ids}) == 49
    assert "r7" not in RECORDED


# ── r2, r3, r4: a removed description restored by Mercury's built-in restore ──────────────

#: The demo's config faults (lab10-live-demo-plan, "The faults"): the interface whose
#: description was removed, and that description as each router's golden holds it.
DESCRIPTIONS = {
    "r2": ("GigabitEthernet3", "P2P to s2 Gi0/2 - RIPng"),
    "r3": ("GigabitEthernet4", "P2P to r4 Gi4 - OSPFv3 core interlink"),
    "r4": ("GigabitEthernet4", "P2P to r3 Gi4 - OSPFv3 core interlink"),
}


class _Verified(_ReadOnce):
    """tests/test_heal_act.py's act sources with the real symptom read, its apply's result
    carrying what the pipeline's verify stage gives a device that verified (``verify`` ok:
    every take recorded "verified"); the check after verify is the act's own."""

    def apply(self, device, **kw):
        check = kw["after_verify"]
        return super().apply(device, **dict(kw, after_verify=lambda dev, r, ctx: check(
            dev, dict(r, verify={"ok": True}), ctx)))


def _without_description(golden: str, iface: str, words: str) -> str:
    """*golden* as the device read back after `no description` on *iface*: the one line gone."""
    line = f"interface {iface}\n description {words}\n"
    assert golden.count(line) == 1, f"{iface}'s description is not in the golden as named"
    return golden.replace(line, f"interface {iface}\n", 1)


@pytest.mark.parametrize("device", sorted(DESCRIPTIONS))
def test_a_removed_description_is_restored_and_closes_healed(heal_lab, device):  # noqa: F811
    """Every take (00:26 to 22:28 UTC, `RECORDED`): r2's, r3's and r4's incident from the
    CONFIG_I of `no description` closed "healed: healed and verified; the incident named no
    symptom beyond the configuration (decision hd-...)" by Mercury's built-in restore
    (`missing_line`, Default's Auto kinds). Replayed: the decision heals, its program is the one
    description line under its interface, the act heals and verifies, and the incident closes
    with the recorded words."""
    iface, words = DESCRIPTIONS[device]
    golden = _config(device)
    running = _without_description(golden, iface, words)
    auto("Default", now=T0 - 60, kinds=("missing_line",))
    inc = settle(running, golden=golden, device=device)
    made = DC.decide_one("Default", inc, now=T0,
                         sources=Fake(running, golden=golden, intended=golden))
    d = DS.record("Default", made, T0)
    assert d["outcome"] == "heal", d["words"]
    assert d["program"] == [f"interface {iface}", f" description {words}", "exit"], \
        d["program"]
    got = A.act_one("Default", d["id"], now=T0 + 5,
                    sources=_Verified(running, {}, golden=golden, intended=golden,
                                      post=K._stored(golden)))
    assert got["outcome"] == "healed", (got["words"], got["steps"])
    (closed,) = [i for i in I.read("Default")["incidents"] if i["device"] == device]
    assert closed["state"] == "closed"
    assert closed["closed_why"] == f"{RESTORED}{d['id']})", closed["closed_why"]


# ── s1: BPDU guard err-disable fixed by the saved script, no AI ────────────────────────────

SCRIPT = "BPDU guard recovery (access ports)"
#: Every take's s1 close, as recorded: "nothing: fixed: saved script <name>'s run <last 8 of its
#: id> verified on s1 at HH:MM UTC (decision hd-...)".
SCRIPT_CLOSED = re.compile(r"nothing: fixed: saved script " + re.escape(SCRIPT)
                           + r"'s run (?P<run>[0-9a-f]{8}) verified on s1 at \d\d:\d\d UTC "
                             r"\(decision hd-[0-9a-f]{12}\)")


class _S1(Fake):
    """The heal decision's sources for s1: its committed golden at intent, read at its golden
    (the demo's faults stayed off the switches' configurations: one problem per device)."""

    def __init__(self):
        golden = T.s1_golden()
        super().__init__(golden, golden=golden, intended=golden)

    def device(self, device):
        return {"hostname": device, "ip": "192.0.2.11", "platform": "cisco_ios"}

    def platform(self, device, dev):
        return "cisco_ios"


@pytest.fixture
def s1_world(plan_lab, heal_lab, monkeypatch):  # noqa: F811
    """s1's fake switch (tests/test_command_plan.py's, from s1's captures and golden) behind
    every session; Mercury's model for s1 wherever the plan's preview and the runner build
    their own sources (a saved script's automatic run passes none); the saved plans' store
    left empty after."""
    from modules import plan_engine as PE
    from modules.nsot import command_plan as CP
    from modules.nsot import command_plan_run as CR
    from modules.nsot import saved_plans as S

    real = CR.Sources

    def moved(s):
        plan_lab["t"] += float(s)

    def runner_sources(network, *, clock=None, sleep=None, model=None, **kw):
        return real(network, clock=clock or (lambda: plan_lab["t"]), sleep=sleep or moved,
                    model=model or CPT.Model(), **kw)
    monkeypatch.setattr(CP, "Sources", CPT.Model)
    monkeypatch.setattr(CR, "Sources", runner_sources)
    S._CACHE.update(mtime=None, templates={})
    S._READ.clear()
    yield plan_lab
    if os.path.exists(S._path()):
        os.remove(S._path())
    S._CACHE.update(mtime=None, templates={})
    S._READ.clear()
    PE.refresh_saved_kinds()


def test_s1s_bpdu_guard_err_disable_is_fixed_by_the_saved_script(s1_world):
    """Every take (00:26 to 22:28 UTC, `RECORDED["s1"]`; take G's hi-3617b7059465 closed at
    17:59:06): s1 Gi1/0 err-disabled by BPDU guard closed "nothing: fixed: saved script BPDU
    guard recovery (access ports)'s run <id> verified on s1 at HH:MM UTC (decision hd-...)",
    with no AI. Replayed: the rehearsal's verified run of the built-in plan saved as that
    script (saving is the approval: Auto, promoted by the saver); the switch err-disabled again
    (the take's injection, s1's captured lines); the incident opened from its alerts,
    classified from s1's own lines and confirmation read, settled and decided (the heal's
    decision: no configuration fix, can't fix); the decision's pass fires the script, the real
    runner recovers the port on the fake switch, verifies it, and the incident closes with the
    recorded words, its run named."""
    from modules import problem as P
    from modules.heal import decide, detect
    from modules.heal import errdisable as E
    from modules.heal import incidents
    from modules.nsot import command_plan as CP
    from modules.nsot import saved_plans as S

    lab = s1_world
    confirm("Default", now=T.AT + 300, heal_mode="auto", heal_kinds_auto=["missing_line"])
    # The rehearsal: a person's verified run of the built-in recovery, saved as the script.
    rehearsed = CPT.go(lab)
    assert (rehearsed["outcome"], rehearsed["state"]) == ("done", "done"), rehearsed["why"]
    rehearsal_problem = P.Problem(**E.problem_fields("s1", T.classified()))
    e = S.save_script(
        T.NET, run_id=rehearsed["id"], name=SCRIPT,
        match={"condition": rehearsal_problem.condition,
               **{k: str(getattr(rehearsal_problem, k)) for k in S.OPTIONAL_MATCH
                  if getattr(rehearsal_problem, k, "")}},
        fills=S.default_fills(CP.template_of(CPT.KEY), rehearsal_problem,
                              rehearsed["params"]),
        actor=T.ACTOR, actor_verified="access", person=True)
    assert e["mode"] == "auto", e
    # The take: the switch err-disabled again, its alerts open the incident.
    lab["sw"] = CPT.Switch()
    iid = T.opened("Critical syslog received")["incident"]
    T.opened("Interface down", "GigabitEthernet1/0", at=T.AT + 20)
    got = E.reclassify_step(T.NET, sources=T.Src(), now=T.AT + 600)
    assert got["classified"] == [iid], got
    # Settled as the detect pass settles a port event: on its classification's device read.
    (inc,) = [i for i in incidents.read(T.NET)["incidents"] if i["id"] == iid]
    out = {"reads": 0, "waiting": [], "cleared": [], "ready": []}
    detect._settle_port(T.NET, inc, out, 0, T.AT + 610, "the replay")
    assert [r["how"] for r in out["ready"]] == ["confirmed"], out
    ran = decide.run(T.NET, now=T.AT + 620, sources=_S1())
    assert [d["outcome"] for d in ran["decided"]] == ["cant_fix"], ran
    assert [(s["key"], s["mode"], s["ok"]) for s in ran["scripts"]] == [
        (e["key"], "auto", True)], ran["scripts"]
    sw = lab["sw"]
    assert sw.batches == [[f"interface {CPT.PORT}", " shutdown", " no shutdown"]]
    assert sw.state == "connected"
    (inc,) = [i for i in incidents.read(T.NET)["incidents"] if i["id"] == iid]
    assert inc["state"] == "closed", inc
    m = SCRIPT_CLOSED.fullmatch(inc["closed_why"])
    assert m, inc["closed_why"]
    assert m["run"] == ran["scripts"][0]["run"][-8:]


# ── s5: the AI's recorded plan, replayed with no provider call ─────────────────────────────

def _take_g_record() -> dict:
    """Take G's troubleshooting record of s5's port-security incident (hi-ed64c53852c5, 17:53
    to 18:02 UTC), as tests/fixtures/incident_story/ keeps it."""
    import json
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                           "incident_story", "hi-ed64c53852c5.fixit.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def test_s5s_recorded_ai_plan_is_the_one_todays_code_holds_and_hashes():
    """Take G (hi-ed64c53852c5, `RECORDED["s5"]`, closed 18:02:14 UTC "fixed: the plan's run
    cbfbab23 verified on s5 at 18:02 UTC (attempt 1, errdisable-recover)"): the AI proposed
    errdisable-recover for GigabitEthernet0/3, cause psecure-violation (call
    ai-32c642bea0ba4e30), a person approved it by plan hash 37340172ebf0a9ce and it verified.
    Replayed from the record with no provider call: today's code reads the same one-step plan
    from the answer, hashes its parameters to the hash recorded (a82b640d99e0383b, what an
    attempt is compared by), holds it to the plan engine's schema and the built-in plan's
    parameters, and lets the AI propose it. Its run and its close need s5's inputs (the notes)."""
    from types import SimpleNamespace

    from modules import plan_engine as PE
    from modules.fixit import incident as F
    from modules.fixit import plan as FP
    from modules.nsot import command_plan as CP

    rec = _take_g_record()
    (line,) = [ln for ln in rec["lines"] if ln.get("source") == "ai"]
    (approved,) = [ln for ln in rec["lines"] if ln.get("choice") == "approve"]
    assert (line["proposal"], approved["decides"]) == ("p1", "p1")
    steps = FP.steps_of(line, rec["device"]["name"])
    assert [s["operation"] for s in steps] == ["errdisable-recover"]
    (kept,) = line["steps"]
    assert F.params_hash(kept["operation"], kept["params"]) == kept["params_hash"] \
        == line["params_hash"] == "a82b640d99e0383b"
    held = CP.checked(CP.template_of(kept["operation"]), dict(kept["params"], device="s5"))
    assert held["interface"] == "GigabitEthernet0/3" and held["cause"] == "psecure-violation"
    incident = SimpleNamespace(id=rec["incident"], device=rec["device"]["name"],
                               network=rec["network"])
    _p, _held, engine = PE.checked(PE.INCIDENT_FIX, FP.plan_params(incident, line))
    assert [s["kind"] for s in engine] == ["errdisable-recover"]
    assert PE.ai_step_refusal("errdisable-recover") == ""
