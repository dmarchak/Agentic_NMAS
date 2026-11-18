"""The plan engine's intent change and its deploy (the operator, 2026-11-15: "Lasting changes:
the AI proposes an intent patch (YAML), and the existing intent -> Jinja -> deploy path does
the rest. No new device-writing code"; C3646, C3756; modules/plan_engine.py, the section
"Intent changes and their deploys").

- **``intent-edit``**: any field intent models, by bulk intent's compare-and-set steps, held to
  the schema, to what is committed and to the editor's whole check; previewed as the masked
  intent diff; committed through the editor's one write path as the approving person.
- **``intent-deploy``**: THE deploy's planner (`routes.deploy.plan_devices`) from the CANDIDATE
  intent an earlier step would commit, its hash binding the program; at run time computed again
  from what is committed and refused, naming what moved; then THE apply as a person's Deploy.
- **An incident's fix** admits both beside the catalog's operations, each held to the
  incident's own device and the heal guards.

On the host's real committed documents (tests/test_committed_before_p1.py's `host`: r2 and s1
in the network Lab, their goldens the masked captures). THE apply is stood in at its one seam
(`routes.deploy.apply_batch`, which sends to a device): the stand-in records what it was asked
to send and reads what is committed when it is asked, so the order and the binding are
measured, never assumed.
"""
import pytest

from modules import plan_engine as E
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

PERSON = "person@example.invalid"
REASON = "the port carries the new core link"
INCIDENT = "hi-abcdef12"
GI2 = "interfaces.GigabitEthernet2"
DESC = "s4 Gi1/0 - VLAN 100 CORE"
#: IPv6 beside IPv4 (documentation prefixes): r2's Gi2 holds 2001:DB8:3::12/64 and an IPv4
#: address; the patch moves its IPv4 address and adds a second IPv6 one.
V4 = {"path": f"{GI2}.ipv4", "before": "10.255.3.12 255.255.255.0",
      "after": "192.0.2.40 255.255.255.0"}
V6 = {"path": f"{GI2}.ipv6", "before": ["2001:DB8:3::12/64"],
      "after": ["2001:DB8:3::12/64", "2001:DB8:40::12/64"]}
RENAME = {"path": f"{GI2}.description", "before": DESC, "after": DESC + " (plan)"}


def _head(host):  # noqa: F811
    from tests.test_intent_patch import _git
    return _git(host["repo"], "rev-parse", "HEAD").strip()


def _git(host, *args):  # noqa: F811
    from tests.test_intent_patch import _git as g
    return g(host["repo"], *args)


def _Incident():
    """r2's incident as the fix-it record takes it (`fixit.incident.Incident`), detected an
    hour ago."""
    import time

    from modules.fixit import incident as F
    return F.Incident(network="Lab", id=INCIDENT, device_id="uid:r2-test", device="r2",
                      detected=time.time() - 3600)


@pytest.fixture
def scoped(host, monkeypatch):  # noqa: F811
    """An incident of r2 with a page (the fix-it record's lookup stood in), r2 Mercury's to
    change and no planned work holding it, unless a test says otherwise (`seams`); and THE
    apply's stand-in, recording each call with what is committed when it is made."""
    from modules.nsot import hostvars

    seams = {"management": "", "g3": None, "calls": [], "result": {"outcome": "deployed",
                                                                   "verify": {"ok": True}}}
    monkeypatch.setattr("modules.fixit.plan._incident_for", lambda network, i: (
        (_Incident(), "") if (network, i) == ("Lab", INCIDENT)
        else (None, f"{i} is no incident of {network} that has a page")))
    monkeypatch.setattr("modules.inventory.management.refusal_for",
                        lambda network, device, what="": seams["management"])
    monkeypatch.setattr("modules.heal.guards.g3_planned",
                        lambda network, device, now, **kw: seams["g3"])

    def apply_batch(network, confirmations, command_hashes, **kw):
        committed, _s = hostvars.committed_at_head(host["repo"], "r2")
        seams["calls"].append({"network": network, "confirmations": confirmations,
                               "command_hashes": command_hashes, "kw": kw,
                               "committed": committed, "head": _head(host)})
        return {"results": [dict(seams["result"], device=d) for d in confirmations]}
    monkeypatch.setattr("routes.deploy.apply_batch", apply_batch)
    return dict(host, seams=seams)


def fix(*steps):
    return {"incident": INCIDENT, "proposal": "p1",
            "steps": [{"operation": op, "params": p} for op, p in steps]}


def edit(*changes, device="r2"):
    return ("intent-edit", {"device": device, "changes": list(changes)})


def deploy(device="r2", **more):
    return ("intent-deploy", dict({"device": device}, **more))


def approve(params, h=None, **over):
    kw = dict(actor=PERSON, actor_verified="access", person=True, reason=REASON)
    kw.update(over)
    p = E.preview("Lab", E.INCIDENT_FIX, params)
    assert p["ok"], p["refused"]
    return E.run("Lab", E.INCIDENT_FIX, params, p["hash"] if h is None else h, **kw)


# ── The intent change: any field intent models, held to its schema ──────────────────────────

class TestTheIntentChange:
    def test_its_preview_is_the_masked_intent_diff_and_writes_nothing(self, scoped):
        before = _head(scoped)
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(RENAME)))
        assert got["ok"], got["refused"]
        (s,) = got["steps"]
        assert s["kind"] == "intent-edit" and s["hash"]
        assert f"-  description: {DESC}\n+  description: {DESC} (plan)" in s["drawn"]["diff"]
        assert f"+    description {DESC} (plan)" in s["drawn"]["render"]
        assert "deploys nothing by itself" in s["drawn"]["not_done"][0]
        assert "candidate" not in s, "the patched text is a later step's, never drawn"
        assert _head(scoped) == before

    def test_a_yaml_patch_is_the_same_patch(self, scoped):
        """The assistant's parameters are text: the patch's YAML is held as the list it says."""
        text = (f"- path: {GI2}.description\n  before: {DESC}\n  after: {DESC} (plan)\n")
        a = E.preview("Lab", E.INCIDENT_FIX, fix(edit(RENAME)))
        b = E.preview("Lab", E.INCIDENT_FIX, fix(("intent-edit", {"device": "r2",
                                                                  "changes": text})))
        assert b["ok"], b["refused"]
        assert a["steps"][0]["hash"] == b["steps"][0]["hash"]

    @pytest.mark.parametrize("change, words", [
        ({"path": f"{GI2}.description", "before": "another description", "after": "x y"},
         f"{GI2}.description: the patch expects \"another description\", and r2's committed "
         f"intent"),
        ({"path": f"{GI2}.descripton", "before": {"__absent__": True}, "after": "x y"},
         f"names a path the intent schema does not model: {GI2}.descripton"),
        ({"path": "interfaces.GigabitEthernet9.shutdown", "before": {"__absent__": True},
          "after": True}, "cannot be placed at interfaces.GigabitEthernet9.shutdown"),
        ({"path": f"{GI2}.description", "before": DESC, "after": DESC},
         "r2's committed intent already holds the patch"),
    ])
    def test_a_patch_the_schema_or_intent_refuses_is_refused_naming_both(self, scoped, change,
                                                                          words):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(change)))
        assert not got["ok"] and words in got["refused"], got["refused"]
        assert got["hash"] == ""

    def test_a_document_the_editors_check_refuses_is_refused_by_it(self, scoped):
        """The patched document through the editor's whole check (`intent_edit.validate`):
        shut and brought up at once undo each other (C1429)."""
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(
            {"path": f"{GI2}.shutdown", "before": False, "after": True},
            {"path": f"{GI2}.no_shutdown", "before": False, "after": True})))
        assert not got["ok"] and "refused by the editor's check" in got["refused"], got

    def test_a_value_that_reads_as_a_secret_is_refused(self, scoped):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(
            {"path": f"{GI2}.description", "before": DESC,
             "after": "username admin secret 9 $9$abcdefghijklmnop"})))
        assert not got["ok"] and "reads as a secret" in got["refused"], got["refused"]

    def test_approved_it_commits_as_the_person_and_reads_it_back(self, scoped):
        from modules import identity
        before = _head(scoped)
        person = identity.Identity(actor=PERSON, email=PERSON, kind="person", verified=True,
                                   outcome="ok", peer_trusted=True, verification="access")
        with identity.carried(person):
            rec = approve(fix(edit(RENAME)))
        assert rec["outcome"] == "done", rec["why"]
        log = _git(scoped, "log", "--format=%B", f"{before}..HEAD")
        assert log.startswith(f"host_vars: r2 {REASON}") and f"Actor: {PERSON}" in log
        assert "Actor-Verified: access" in log and "Source: plan" in log
        assert f"description: {DESC} (plan)" in _git(scoped, "show", "HEAD:host_vars/r2.yml")
        assert scoped["seams"]["calls"] == [], "a change of intent alone deploys nothing"

    def test_a_removal_from_intent_is_marked_what_the_device_keeps(self, scoped):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(
            {"path": f"{GI2}.description", "before": DESC, "after": ""})))
        assert got["ok"], got["refused"]
        (s,) = got["steps"]
        assert s["drawn"]["device_keeps"] == [f"description {DESC}"], s["drawn"]
        assert any("a merge-only deploy leaves on r2" in w and "Mode B" in w
                   for w in s["drawn"]["not_done"])


# ── The deploy, bound by its hash (C3646) ───────────────────────────────────────────────────

class TestTheDeployBoundByItsHash:
    def test_its_program_is_planned_from_the_candidate_intent(self, scoped):
        """IPv4 beside IPv6: the deploy step after the change sends both new addresses, from
        intent not yet committed; alone, it plans committed intent; nothing is written."""
        before = _head(scoped)
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(V4, V6), deploy()))
        assert got["ok"], got["refused"]
        program = got["steps"][1]["drawn"]["program"]
        assert " ip address 192.0.2.40 255.255.255.0" in program, program
        assert " ipv6 address 2001:DB8:40::12/64" in program, program
        alone = E.preview("Lab", E.INCIDENT_FIX, fix(deploy()))
        assert alone["ok"], alone["refused"]
        assert alone["steps"][0]["drawn"]["program"] == [
            "ip ssh source-interface Loopback0", "ip tftp source-interface Loopback0"]
        assert alone["steps"][0]["hash"] != got["steps"][1]["hash"]
        assert _head(scoped) == before

    def test_its_hash_is_the_deploys_own_program_unmasked(self, scoped):
        from modules.nsot.deploy import command_fingerprint
        from routes.deploy import plan_devices
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(V4, V6), deploy()))
        rec = approve(fix(edit(V4, V6), deploy()))
        assert rec["outcome"] == "done", rec["why"]
        entry = plan_devices("Lab", ["r2"])[0]
        assert got["steps"][1]["resolved"]["program"] == command_fingerprint(
            entry["commands"], [], [], [])
        assert got["steps"][1]["resolved"]["capture"] == entry["capture_hash"]

    def test_approved_the_intent_is_committed_before_the_deploy_sends_it(self, scoped):
        from routes.deploy import plan_devices
        before = _head(scoped)
        rec = approve(fix(edit(V4, V6), deploy()))
        assert rec["outcome"] == "done", rec["why"]
        assert [s["state"] for s in rec["plan_steps"]] == ["done", "done"]
        (call,) = scoped["seams"]["calls"]
        assert call["head"] != before and "2001:DB8:40::12/64" in call["committed"]
        entry = plan_devices("Lab", ["r2"])[0]
        assert call["command_hashes"] == {"r2": entry["command_hash"]}
        assert call["confirmations"] == {"r2": entry["capture_hash"]}
        assert call["kw"]["actor"] == PERSON and call["kw"]["actor_kind"] == "person"
        assert call["kw"]["stop_at_first"] is True and not call["kw"].get("remove")

    def test_a_program_that_moved_after_the_commit_is_refused_naming_it(self, scoped,
                                                                        monkeypatch):
        """Another person's commit lands between the plan's intent commit and its deploy: the
        program computed again from what is committed is not the one approved, so the deploy
        step stops, naming the program and both hashes, and nothing is sent."""
        from modules.nsot import intent_edit
        real = intent_edit.commit

        def commit(network, device, text, *a, **kw):
            got = real(network, device, text, *a, **kw)
            opened = intent_edit.open_doc(network, device)
            assert real(network, device, opened["yaml"].replace(
                "description: P2P to s2 Gi0/2 - RIPng", "description: moved by someone"),
                "another person's edit", opened["base"], "someone")["ok"]
            return got
        monkeypatch.setattr(intent_edit, "commit", commit)
        rec = approve(fix(edit(RENAME), deploy()))
        assert rec["outcome"] == "stopped", rec
        assert [s["state"] for s in rec["plan_steps"]] == ["done", "refused"]
        words = rec["plan_steps"][1]["words_said"]
        approved = rec["plan_steps"][1]["resolved"]["program"]
        assert f"its program: approved {approved}, now " in words, words
        assert "its capture" not in words, "the capture did not move"
        assert scoped["seams"]["calls"] == [], "nothing was sent"

    def test_a_deploy_that_did_not_verify_stops_the_plan(self, scoped):
        scoped["seams"]["result"] = {"outcome": "deployed", "verify": {"ok": False}}
        rec = approve(fix(edit(RENAME), deploy()))
        assert rec["outcome"] == "stopped" and "r2 did not deploy and verify" in rec["why"]

    def test_a_removal_reaches_the_device_only_by_its_id_with_the_persons_reason(self,
                                                                                 scoped):
        """Mode B: the cleared description stays on the device unless the deploy step names
        its line's removal by id; named, the removal is in the program and its hash, and its
        reason is the approving person's."""
        from modules.nsot import authorisation
        clear = {"path": f"{GI2}.description", "before": DESC, "after": ""}
        kept = E.preview("Lab", E.INCIDENT_FIX, fix(edit(clear), deploy()))
        assert kept["ok"], kept["refused"]
        assert f"description {DESC}" not in " ".join(kept["steps"][1]["drawn"]["program"])
        cand = E._intent_edit_preview("Lab", {"device": "r2", "changes": [clear]})
        offered = [r for r in E._deploy_entry("Lab", "r2", [], cand["candidate"])["removable"]
                   if r["line"].strip() == f"description {DESC}" and not r["why_not"]]
        assert len(offered) == 1, offered
        rid = offered[0]["id"]
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(clear), deploy(remove=[rid])))
        assert got["ok"], got["refused"]
        assert f" no description {DESC}" in got["steps"][1]["drawn"]["program"] or any(
            "no description" in c for c in got["steps"][1]["drawn"]["program"])
        assert got["steps"][1]["hash"] != kept["steps"][1]["hash"]
        rec = approve(fix(edit(clear), deploy(remove=[rid])))
        assert rec["outcome"] == "done", rec["why"]
        (call,) = scoped["seams"]["calls"]
        assert call["kw"]["remove"] == {"r2": [rid]}
        auth = call["kw"]["authorise"]["r2"]
        assert auth and all(a["reason"] == REASON for a in auth), auth
        assert not authorisation.problems(
            [c for c in got["steps"][1]["drawn"]["program"]], auth,
            [a["line"] for a in auth]), "every line needing a reason has the person's"

    def test_a_removal_the_deploy_does_not_offer_is_refused(self, scoped):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(RENAME), deploy(remove=["0123456789ab"])))
        assert not got["ok"] and "the deploy's plan refuses it" in got["refused"], got

    def test_a_deploy_that_sends_nothing_is_refused(self, scoped, monkeypatch):
        monkeypatch.setattr("routes.deploy.plan_devices", lambda network, hosts, **kw: [
            {"device": hosts[0], "deployable": True, "commands": [], "to_add": [],
             "capture_hash": "c0ffee", "removals": {"ids": [], "keys": []}}])
        got = E.preview("Lab", E.INCIDENT_FIX, fix(deploy()))
        assert not got["ok"] and "the deploy of r2 sends nothing" in got["refused"], got


# ── An incident's fix: held to its own device and the heal guards ───────────────────────────

class TestTheIncidentsFix:
    def test_it_admits_intent_steps_beside_the_catalogs(self):
        p, held, steps = E.checked(E.INCIDENT_FIX, fix(edit(RENAME), deploy()))
        assert [s["kind"] for s in steps] == ["intent-edit", "intent-deploy"]
        assert steps[1]["params"] == {"device": "r2", "remove": "", "incident": INCIDENT,
                                      "proposal": "p1"}

    @pytest.mark.parametrize("step, words", [
        (("intent-edit", {"device": "r2"}), "no changes was given"),
        (("intent-deploy", {"device": "r2", "incident": INCIDENT}),
         "'incident' was also given"),
        (("intent-deploy", {"device": "r2", "remove": ["not-an-id"]}),
         "parameter remove is"),
        (("intent-edit", {"device": "r2", "changes": [{"path": "x"}]}),
         "parameter changes is"),
    ])
    def test_a_step_off_its_schema_is_refused(self, step, words):
        """Refused before anything is read; the plan's refusal never echoes what was given,
        and the steps' own check names the parameter."""
        with pytest.raises(E.Refused) as exc:
            E.checked(E.INCIDENT_FIX, fix(step))
        assert exc.value.code == "wrong_shape", exc.value.code
        said = E._fix_steps_refusal(fix(step)["steps"])
        assert "the plan engine refuses" in said and words in said, said

    def test_a_step_on_another_device_is_refused_naming_both(self, scoped):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(deploy(device="s1")))
        assert not got["ok"] and ("the step names the device s1, and hi-abcdef12 is r2's"
                                  in got["refused"]), got["refused"]
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(
            {"path": "interfaces.Gi0/1.description", "before": "x", "after": "y"},
            device="s1")))
        assert not got["ok"] and "the step names the device s1" in got["refused"]

    def test_a_guard_holding_the_device_refuses_each_step(self, scoped):
        scoped["seams"]["g3"] = {"guard": 3, "name": "planned work", "words": "a window"}
        for steps in (fix(edit(RENAME)), fix(deploy())):
            got = E.preview("Lab", E.INCIDENT_FIX, steps)
            assert not got["ok"] and "guard 3 (planned work) holds r2: a window" in \
                got["refused"], got["refused"]
        scoped["seams"]["g3"] = None
        scoped["seams"]["management"] = "r2 is observed only (mercury.management). Nothing " \
                                        "was sent."
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(RENAME)))
        # The whole refusal (C3976: its reason first, the step's own words after it, so a card
        # keeping its first 400 characters names the reason): the device's "Nothing was sent"
        # is not carried into a preview's refusal.
        assert not got["ok"] and got["refused"] == (
            "step 1 is refused by its own preview: r2 is observed only (mercury.management). "
            f"(step 1: {E.STEP_KINDS['intent-edit'].words})"), got["refused"]

    def test_an_incident_without_a_page_is_refused(self, scoped):
        params = dict(fix(edit(RENAME)), incident="hi-0000000000")
        got = E.preview("Lab", E.INCIDENT_FIX, params)
        assert not got["ok"] and "is no incident of Lab that has a page" in got["refused"]

    def test_two_changes_to_one_device_in_one_plan_are_refused(self, scoped):
        got = E.preview("Lab", E.INCIDENT_FIX, fix(edit(RENAME), edit(V4)))
        assert not got["ok"] and "one intent change per device" in got["refused"]
