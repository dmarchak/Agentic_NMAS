"""The toolbar assistant as a senior network engineer working through Mercury (the operator,
2026-11-28: "I should be able to execute tasks by telling the assistant. Everything it does
though is run through code, similar to the self healing. If Mercury doesn't have a tool for it,
it should say so. When prompted to make a change it should present a plan for approval before
making any changes"; modules/ai/assistant.py, prompt v6 and schema v4; modules/plan_engine.py's
plan ``change``; routes/plans_v2.py).

- **A change is a plan:** the plan ``change`` holds 1 to 10 steps, each one of the operations
  a change admits (`plan_engine.CHANGE_ADMITTED`) with exactly its step kind's parameters, held
  by the one check of a plan's steps an incident's fix is held by; each step previewed by its
  own step kind, the plan approved once by its hash and run by the plan engine's run.
- **Presented for approval in the conversation:** an answer proposing a plan loads the plan's
  preview card in place at once (a GET: a preview writes nothing and makes no AI call), its own
  card id, Approve bound to its hash; nothing runs before that press.
- **No tool:** what no operation or read does is said ("Mercury has no tool for this: …") and
  recorded once as an operation Mercury lacks, for the question, masked.
- **Reads of a device named:** a device of the network the question names may be read, each
  read still judged by the read loop's check; a name the network does not hold is refused.
- **The NEVERs held by code:** a step outside the admitted set, or a parameter outside its
  step kind's schema, is refused (no command text reaches a device); no settings route and no
  run, start or approve is reachable from an answer; no step or answer field takes a secret;
  an answer saying a change was made is refused.

The gateway is real, the provider a fake (tests/test_ai_assistant_stage2.py's `lab`); the plan
engine runs on tests/test_committed_before_p1.py's `host` (r2 and s1 in Lab, committed).
"""
import json
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from modules import plan_engine as E
from modules.ai import assistant
from tests.ai_person import PERSON, pressed_by
from tests.test_ai_assistant import world  # noqa: F401 (the fixture)
from tests.test_ai_assistant_stage2 import (  # noqa: F401 (`lab`, the fixture)
    ask, lab, post, reads_on, show, words)
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

REASON = "the link is described at both ends"
#: The plan a change is, and the operations its steps may be: the operator's decision of
#: 2026-11-28 as the build took it, written here by hand (the expectation's own path, never
#: read from the code it checks).
CHANGE = "change"
ADMITTED = ("intent-edit", "intent-deploy", "intent-description", "dhcp-reservation",
            "ztp-create")
#: A change of two steps, an interface's description at each end of a link (the host's own
#: interfaces: s1's Gi0/1, r2's GigabitEthernet1).
STEPS = [{"operation": "intent-description",
          "params": {"device": "s1", "interface": "Gi0/1", "description": "s1 to r2"}},
         {"operation": "intent-description",
          "params": {"device": "r2", "interface": "GigabitEthernet1",
                     "description": "r2 to s1"}}]


def _asked(plan="change", steps=STEPS, params=()):
    """A v4 answer's plan, as the model gives it: every value text, each {name, value}."""
    return {"plan": plan, "params": [{"name": k, "value": v} for k, v in params],
            "steps": [{"operation": s["operation"],
                       "params": [{"name": k, "value": v} for k, v in s["params"].items()]}
                      for s in steps]}


def _V4():
    """The assistant's v4 answer schema, as the registry holds it."""
    from modules.ai import schemas
    model = schemas.REGISTRY.get(("assistant", 4))
    assert model is not None, "the assistant's answer schema v4 is registered"
    return model


def _v4(**over):
    return _V4()(**dict(words("Mercury can describe both ends."), **{"no_tool": None, **over}))


def _steps_check(steps) -> str:
    """The change plan's own check of its steps (its one parameter's refusal)."""
    assert CHANGE in E.PLANS, "the plan engine has the plan change"
    (param,) = E.PLANS[CHANGE].params
    assert param.name == "steps", param
    return param.refusal(steps)


def _offered() -> dict:
    """What the assistant is told of each plan, by its key."""
    return {p["plan"]: p for p in assistant.context()["plans"]}


# ── a change is a plan of Mercury's operations ──────────────────────────────────────────────

class TestAChangeIsAPlan:
    def test_each_step_is_previewed_by_its_own_kind_and_the_plan_runs_once_approved(
            self, host):  # noqa: F811
        """The change's preview is each step's own (the intent description's), bound in one
        hash; approved by that hash, the plan engine's run commits each step in order."""
        from tests.test_intent_patch import _git
        got = E.preview("Lab", CHANGE, {"steps": STEPS})
        assert got["ok"], got["refused"]
        assert [(s["kind"], s["params"]["device"]) for s in got["steps"]] == [
            ("intent-description", "s1"), ("intent-description", "r2")]
        assert got["title"] == "Change s1, r2: 2 steps" and len(got["hash"]) == 16
        before = _git(host["repo"], "rev-parse", "HEAD").strip()
        rec = E.run("Lab", CHANGE, {"steps": STEPS}, got["hash"], actor=PERSON,
                    actor_verified="access", person=True, reason=REASON)
        assert rec["outcome"] == "done", rec.get("why")
        log = _git(host["repo"], "log", "--format=%s", f"{before}..HEAD").splitlines()
        assert len(log) == 2, log
        assert "r2 to s1" in _git(host["repo"], "show", "HEAD:host_vars/r2.yml")

    def test_unapproved_or_moved_it_runs_nothing(self, host):  # noqa: F811
        from tests.test_intent_patch import _git
        before = _git(host["repo"], "rev-parse", "HEAD").strip()
        rec = E.run("Lab", CHANGE, {"steps": STEPS}, "0" * 16, actor=PERSON,
                    actor_verified="access", person=True, reason=REASON)
        assert rec["outcome"] == "refused" and "the plan is not the one approved" in rec["why"]
        assert _git(host["repo"], "rev-parse", "HEAD").strip() == before

    def test_the_assistant_s_steps_are_held_to_the_plan_engine_s_schema(self):
        plan, why = assistant.plan_of(_v4(plan=_asked()))
        assert why == "" and plan == {"plan": "change", "params": {"steps": STEPS},
                                      "title": "Change s1, r2: 2 steps"}, (plan, why)
        offered = _offered()
        assert CHANGE in offered, sorted(offered)
        assert [o["operation"] for o in offered[CHANGE]["operations"]] == list(ADMITTED)
        assert not [p for o in offered[CHANGE]["operations"] for p in o["params"]
                    if p["name"] in ("incident", "proposal")], "a change has no incident"


class TestTheNevers:
    @pytest.mark.parametrize("operation", ["port-recover", "describe-link", "show",
                                           "reload", "incident-fix"])
    def test_a_step_outside_the_admitted_set_is_refused_never_echoed(self, operation):
        """NEVER: a change's step is one of `CHANGE_ADMITTED`; a catalog operation (an
        incident's), a plan, a command or anything else is refused before any preview."""
        steps = [{"operation": operation, "params": {}}]
        got = E.preview("Lab", CHANGE, {"steps": steps})
        assert (got["ok"], got["code"], got["steps"]) == (False, "wrong_shape", []), got
        # The plan's refusal names its rule and never what was given; the steps' own check
        # names the step and the set it compared against (tests/test_plan_intent_deploy.py's
        # convention for an incident's fix).
        said = _steps_check(steps)
        assert said == ("a list whose step 1 names an operation that is not one a change "
                        "admits (intent-edit, intent-deploy, intent-description, "
                        "dhcp-reservation and ztp-create)"), said
        plan, why = assistant.plan_of(_v4(plan=_asked(steps=steps)))
        assert plan is None and why.startswith("its plan is refused: change's parameter "
                                               "steps is 1 to 10 steps"), why
        assert operation not in got["refused"] and operation not in why

    @pytest.mark.parametrize("step, named", [
        ({"operation": "intent-deploy", "params": {"device": "r2", "commands": "reload"}},
         "commands"),
        ({"operation": "intent-edit", "params": {"device": "r2", "changes": "[]",
                                                 "config": "no ip routing"}}, "config"),
        # The deploy step's own schema names incident and proposal (an incident's fix gives
        # them); a change takes neither, so naming one is refused like any stray parameter.
        ({"operation": "intent-deploy", "params": {"device": "r2", "incident": "hi-0123abcd"}},
         "incident"),
        ({"operation": "intent-edit", "params": {"device": "r2", "changes": "[]",
                                                 "proposal": "p1"}}, "proposal"),
    ])
    def test_a_parameter_not_in_its_step_kind_s_schema_is_refused(self, step, named):
        """NEVER: no command text reaches a device: a parameter the step kind does not name is
        refused whatever it holds (an incident's own parameters too), and nothing is previewed."""
        got = E.preview("Lab", CHANGE, {"steps": [step]})
        assert (got["ok"], got["code"], got["steps"]) == (False, "wrong_shape", []), got
        said = _steps_check([step])
        assert "the plan engine refuses" in said and f"'{named}' was also given" in said, said
        assert "a parameter the schema does not name is refused" in said
        plan, why = assistant.plan_of(_v4(plan=_asked(steps=[step])))
        assert plan is None and why.startswith("its plan is refused"), why
        for text in (got["refused"], said, why):
            assert "reload" not in text and "no ip routing" not in text, text

    def test_no_step_of_a_change_and_no_answer_field_takes_a_secret(self):
        """NEVER: no parameter a change's steps take, and no field of the v4 answer, is one a
        secret goes in (tests/test_ai_never.py's scan), and no step's by-hand route is one the
        AI may never propose (`plan_engine.ai_step_refusal`)."""
        from tests.test_ai_never import SECRETISH, secret_fields

        assert secret_fields({"assistant.v4": _V4()}) == []
        offered = _offered()
        assert CHANGE in offered, sorted(offered)
        names = [(o["operation"], p["name"]) for o in offered[CHANGE]["operations"]
                 for p in o["params"]]
        assert len(names) >= 12, names
        assert [n for n in names if re.search(SECRETISH, n[1], re.I)] == []
        assert {k: E.ai_step_refusal(k) for k in ADMITTED} == {
            k: "" for k in ADMITTED}

    @pytest.mark.parametrize("said", [
        "I have deployed the change to r2.", "The change has been applied on r2.",
        "I’ve now committed s1's description.", "Your change is now made."])
    def test_an_answer_saying_a_change_was_made_is_refused(self, said):
        """NEVER: the assistant makes no change, so its words never say one was made (Mercury's
        check, before anything is drawn); words of a plan to come, and a fact History holds of
        a change Mercury made before, pass."""
        why = assistant.check(_v4(answer=said, cites=["x"]), [{"link": "x"}])
        assert why.startswith("its words say a change was made"), why
        for fine in ("Approve the plan and Mercury applies both steps.",
                     "History shows Mercury deployed r2's intent on Tuesday (read:1).",
                     "Once approved, the change is applied step by step."):
            assert assistant.check(_v4(answer=fine, cites=["x"]), [{"link": "x"}]) == "", fine


    @pytest.mark.parametrize("said", [
        "Run `show ip ospf neighbor` on r2.",
        "On the device:\n```\nconfigure terminal\ninterface Gi2\n shutdown\n```",
        "Type `reload` at the console.",
        "r2# show running-config | section line vty",
        "Router(config)# no ip route 0.0.0.0 0.0.0.0"])
    def test_an_answer_naming_a_device_command_is_refused(self, said):
        """NEVER (C4334; CLAUDE.md, No terminal steps): an answer, or what it says Mercury has
        no tool for, never names a device command: held by Mercury's check, not the prompt
        alone. Mercury's own words for its screens and controls pass."""
        why = assistant.check(_v4(answer=said, cites=["x"]), [{"link": "x"}])
        assert why.startswith("its words name a device command"), why
        lacking = _V4().model_fields["no_tool"].annotation.__args__[0](
            wanted="a reload of r2", why=said)
        why = assistant.check(_v4(answer="Mercury has no tool for this.", cites=["x"],
                                  no_tool=lacking), [{"link": "x"}])
        assert why.startswith("its words name a device command"), why
        for fine in ("Open **Show commands**, choose r2 and the OSPF neighbours read.",
                     "Use **Change it in words…** on r2's Intent tab, then preview it.",
                     "Mercury has no operation that reloads a whole site at once.",
                     "The `description` field of GigabitEthernet2 holds the old text."):
            assert assistant.check(_v4(answer=fine, cites=["x"]), [{"link": "x"}]) == "", fine


#: r2's GigabitEthernet2 description as committed on the host's lab, and a change of it
#: (tests/test_plan_intent_deploy.py's).
GI2_DESC = "s4 Gi1/0 - VLAN 100 CORE"
RENAME = {"path": "interfaces.GigabitEthernet2.description", "before": GI2_DESC,
          "after": GI2_DESC + " (plan)"}


class TestTheDeployInAChange:
    def _cut_is(self, monkeypatch, lost):
        """THE deploy's plan as it is, its reach to other devices once the program runs said
        to be *lost* (`expected_effects.reach_lost`)."""
        real = E._deploy_entry

        def entry(*a, **k):
            got = dict(real(*a, **k))
            got["expected_effects"] = dict(got.get("expected_effects") or {},
                                           reach_lost=lost)
            return got
        monkeypatch.setattr(E, "_deploy_entry", entry)

    def test_a_deploy_whose_cut_is_not_known_is_refused_naming_why(
            self, host, monkeypatch):  # noqa: F811
        """A change's deploy is held as an incident's fix's is: whether it cuts Mercury's path
        to a device must be known, and a deploy where it is not is refused, naming what was
        compared and both sides (the cut's state, the one needed, and why it is not known)."""
        steps = [{"operation": "intent-edit", "params": {"device": "r2", "changes": [RENAME]}},
                 {"operation": "intent-deploy", "params": {"device": "r2"}}]
        self._cut_is(monkeypatch, {"state": "known", "cut": [], "why": "measured"})
        assert E.preview("Lab", CHANGE, {"steps": steps})["ok"], "the premise: it previews"
        self._cut_is(monkeypatch, {"state": "unknown", "cut": [],
                                   "why": "this host's addresses could not be read (x)"})
        got = E.preview("Lab", CHANGE, {"steps": steps})
        assert not got["ok"] and got["hash"] == "", got
        assert ("whether the deploy cuts Mercury's path to a device is unknown (needed: known): "
                "this host's addresses could not be read (x)") in got["refused"], got["refused"]

    def test_a_description_then_a_deploy_of_one_device_is_refused_naming_intent_edit(
            self, host):  # noqa: F811
        """A deploy's program is computed from the intent an earlier step would commit only
        when that step hands it on (intent-edit does); intent-description does not, so a
        change that sets a description and then deploys the same device is refused, naming
        intent-edit as the way, before anything is previewed."""
        steps = [{"operation": "intent-description", "params": {
                     "device": "r2", "interface": "GigabitEthernet2", "description": "x"}},
                 {"operation": "intent-deploy", "params": {"device": "r2"}}]
        got = E.preview("Lab", CHANGE, {"steps": steps})
        assert (got["ok"], got["steps"]) == (False, []), got
        assert got["refused"] == (
            "step 2 deploys r2 after step 1 changes its intent by Set an interface's "
            "description in a device's intent, whose change a later step of the same plan "
            "does not see: name that change as an intent-edit step, whose intent the deploy "
            "is computed from"), got["refused"]


# ── presented for approval in the conversation ──────────────────────────────────────────────

def _urls(html: str) -> list:
    """Each request the drawn HTML (unescaped once) can make: ``(attribute, method, path,
    query, triggers)``."""
    out = []
    for m in re.finditer(r"<[a-z][^>]*>", html):
        tag = m.group(0)
        trigger = re.search(r'hx-trigger="([^"]*)"', tag)
        for attr, url in re.findall(r'\b(href|hx-get|hx-post|action)="([^"]*)"', tag):
            u = urlsplit(url)
            if u.scheme or not u.path.startswith("/"):
                continue
            method = "POST" if attr == "hx-post" or (attr == "action" and "post" in tag.lower()) \
                else "GET"
            out.append((attr, method, u.path, parse_qs(u.query),
                        trigger.group(1) if trigger else ""))
    return out


def _endpoint(app, path, method):
    return app.url_map.bind("localhost").match(path, method=method)[0]


def test_a_proposed_change_loads_its_preview_card_in_place_and_nothing_runs(lab, monkeypatch):
    """The answer proposing a change draws its preview card at once (one GET that loads itself,
    the plan engine's preview, the card's id the answer's); the card's one POST is Approve,
    bound to the plan's hash; no settings route is reachable from either, and no plan ran."""
    import app as APP
    from modules.nsot import privileged

    lab["state"]["answer"] = dict(words("Here is the plan: it describes both ends of the link; "
                                        "approve it on its card."),
                                  plan=_asked(), no_tool=None)
    r, html = post(lab, "Describe the link between s1 Gi0/1 and r2 GigabitEthernet1")
    assert r.status_code == 200, html[:400]
    got = _urls(html)
    loads = [(m, _endpoint(APP.app, p, m), q) for _a, m, p, q, t in got if t == "load"]
    assert [(m, e) for m, e, _q in loads] == [("GET", "plans_v2.preview")], got
    query = loads[0][2]
    # C4329: asked by its answer's id, the plan read from the person's own conversation; its
    # parameters never travel in the address.
    assert "params" not in query and "plan" not in query, query
    assert query["answer"][0].startswith("ai-"), query
    card = query["card"][0]
    assert card.startswith("plan-card-ai-") and f'id="{card}"' in html
    assert "Preview the plan…" not in html, "nothing to press before the preview"
    # The card it loads, the plan engine's preview planted (its steps' own previews are the
    # plan engine's tests' above): Approve, its one POST, bound to the hash, on its own card.
    planted = [{"n": n, "kind": "intent-description", "words": "Set a description",
                "params": s["params"], "ok": True, "hash": "ab" * 8, "refused": "",
                "drawn": {"title": f"{s['params']['device']}", "change": "description set"}}
               for n, s in enumerate(STEPS, 1)]
    previewed = []

    def preview(network, plan, params, *a, **k):
        previewed.append((network, plan, params))
        return {"ok": True, "plan": "change", "title": "Change s1, r2: 2 steps",
                "words": "the steps", "params": {"steps": STEPS}, "steps": planted,
                "hash": "cd" * 8, "refused": "", "code": ""}
    monkeypatch.setattr(E, "preview", preview)
    before = privileged.runs("Lab")
    c = lab["client"].get("/v2/plans/preview", query_string={k: v[0] for k, v in query.items()},
                          headers={"HX-Request": "true"})
    card_html = unescape(c.get_data(as_text=True))
    assert c.status_code == 200 and f'id="{card}"' in card_html, card_html[:400]
    assert previewed and previewed[0][1] == "change", previewed
    assert previewed[0][2] == {"steps": STEPS}, "the plan the conversation keeps"
    posts = [(_endpoint(APP.app, p, m), t) for _a, m, p, q, t in _urls(card_html)
             if m == "POST"]
    assert posts == [("plans_v2.approve", "")], posts
    assert f'hx-target="#{card}"' in card_html and '"hash": "' + "cd" * 8 in card_html
    assert f'<input type="hidden" name="card" value="{card}">' in card_html
    every = [_endpoint(APP.app, p, m) for _a, m, p, q, t in got + _urls(card_html)]
    assert [e for e in every if e.startswith("settings")] == [], every
    assert privileged.runs("Lab") == before, "previewing ran nothing"


def test_two_cards_in_one_conversation_each_approve_their_own():
    """Each card's id is the one its request names when it has a card's shape, else the
    page's own: a conversation's cards never share an Approve target."""
    from routes import plans_v2
    named = "plan-card-ai-0123456789abcdef"
    assert plans_v2.card("Default", {"card": named}).get("card") == named
    for bad in ("", "x", 'plan-card-a"><script>', "plan-card-" + "a" * 81):
        assert plans_v2.card("Default", {"card": bad}).get("card") == "plan-card", bad


# ── Mercury has no tool for this ─────────────────────────────────────────────────────────────

def test_no_tool_is_said_and_recorded_once_for_review_masked(lab):
    """What no operation or read of Mercury's does: drawn as "Mercury has no tool for this:
    <wanted>." with the why, recorded once as an operation Mercury lacks, for the question (its
    call), masked; no command and no manual gap."""
    from modules.ai import missing
    lab["state"]["answer"] = dict(words("Mercury has no tool for this.", cites=[],
                                        covered=False),
                                  no_tool={"wanted": "Upgrade r2's IOS XE image",
                                           "why": "no operation of Mercury's installs "
                                                  "software; a line pasted as username ops "
                                                  "secret 0 Pl4nted-Value-7"})
    r, html = post(lab, "Upgrade r2 to the newest IOS XE")
    assert r.status_code == 200, html[:400]
    said = re.search(r"<div class=\"asst-handoff\" data-no-tool[^>]*><p class=\"small\">"
                     r"<strong>(.*?)</strong>(.*?)</p>", html, re.S)
    assert said and said.group(1) == "Mercury has no tool for this: Upgrade r2's IOS XE image.", \
        html[-1500:]
    assert "no operation of Mercury's installs software" in said.group(2)
    assert "Pl4nted-Value-7" not in html
    rows = missing.rows()["rows"]
    assert len(rows) == 1, rows
    (row,) = rows
    assert (row["kind"], row["feature"], row["about"]["kind"], row["network"]) == (
        "operation", "assistant", "question", "Lab"), row
    assert row["about"]["id"].startswith("ai-") and row["what"] == "Upgrade r2's IOS XE image"
    assert "Pl4nted-Value-7" not in json.dumps(row)
    assert "The manual doesn't cover this" not in html


# ── the reads: a device the question names ─────────────────────────────────────────────────

class TestTheDevicesNamed:
    def test_a_device_of_the_network_named_on_another_s_page_is_read(self, lab, monkeypatch):
        asked = reads_on(monkeypatch)
        lab["queue"].extend([words("Reading r6 first.", covered=False, reads=[show("r6")]),
                             words("r6 runs IOS XE 17.09.01a.", cites=["read:1"])])
        got = ask(lab, "What version is r6 running?")
        assert asked == [("Lab", ["r2", "r6"])], "the page's device, then the one named"
        (run,) = lab["ran"]
        assert run["hosts"] == ["r6"] and run["commands"] == ["show version"]
        assert got["state"] == "answered" and got["reads"][0]["verdict"] == "run", got

    def test_with_no_device_in_view_the_one_named_is_read(self, lab, monkeypatch):
        asked = reads_on(monkeypatch)
        lab["queue"].extend([words("Reading r2 first.", covered=False, reads=[show("r2")]),
                             words("r2 runs IOS XE 17.09.01a.", cites=["read:1"])])
        ask(lab, "What version is R2 running?", where="/v2/devices")
        assert asked == [("Lab", ["r2"])], "named in any case, read as the inventory spells it"
        assert [r["hosts"] for r in lab["ran"]] == [["r2"]]

    def test_a_name_the_network_does_not_hold_is_never_read(self, lab, monkeypatch):
        """Of two devices named, the one the network holds is read and the other, no device
        of the network, is refused by the read loop's check and never reaches a device."""
        asked = reads_on(monkeypatch)
        lab["queue"].extend([words("Reading both first.", covered=False,
                                   reads=[show("r6"), show("r9")]),
                             words("r6 runs IOS XE 17.09.01a.", cites=["read:1"])])
        got = ask(lab, "Compare r6's and r9's versions")
        assert asked == [("Lab", ["r2", "r6"])], "r9 is no device of Lab"
        assert [r["hosts"] for r in lab["ran"]] == [["r6"]], lab["ran"]
        assert [(r["device"], r["verdict"]) for r in got["reads"]] == [
            ("r6", "run"), ("r9", "refused")], got["reads"]


# ── the scan: nothing an answer reaches runs, starts or approves ───────────────────────────

def test_the_assistant_reaches_no_run_start_or_approve():
    """NEVER, by the AI NEVERs' graph (tests/test_ai_never.py): from every unit of the
    assistant and its chat job's work, nothing reachable is the plan engine's run or start, a
    job's start, an approve or confirm view (plans_v2.approve among them) or a settings write.
    Its floor: the reach holds the plan engine's check of a plan, the gateway and the no-tool
    record (the job's one new write); its planted case: a unit beside the assistant's that
    starts the plan it was handed is found, its path named."""
    import app as APP
    from tests import test_ai_never as N

    files = dict(N.product_files())
    files["modules/ai/assistant_planted.py"] = (
        "from modules import plan_engine\n\n"
        "def act(plan):\n    plan_engine.start('Default', plan['plan'], plan['params'], 'h',\n"
        "                      actor='ai', actor_verified='none', person=False, reason='')\n")
    units = N.graph(files)
    never = (N.job_starters(units) | N.gated_views(APP.app) | set(N.SETTINGS)
             | {"modules.plan_engine.run", "modules.plan_engine.start",
                "routes.plans_v2.approve"})
    assert "routes.plans_v2.approve" in N.gated_views(APP.app)
    planted = N.findings(N.reach(units, ["modules.ai.assistant_planted.act"]), never)
    assert any(f.endswith("modules.plan_engine.start") for f in planted), planted
    start = [u for u in units if u.startswith("modules.ai.assistant.")] + [
        "modules.ai.assistant_turns.work", "modules.ai.assistant_turns.drawn_of"]
    seen = N.reach(units, start)
    for floor in ("modules.plan_engine.checked", "modules.ai.gateway.ask",
                  "modules.ai.missing.record"):
        assert floor in seen, floor
    assert N.findings(seen, never) == []


class TestALongChange:
    """C4329: a change of more than a few steps could not be previewed: plans_v2 refused
    parameters past 2,000 characters, and two description steps took about 250. The bound is the
    plan engine's own largest change, and the chat asks a card by its answer's id."""

    def test_the_bound_takes_the_largest_change_the_step_kinds_allow(self):
        from routes import plans_v2
        assert plans_v2.PARAMS_CHARS == E.MOST_STEPS * E.MOST_CHANGES * 512
        steps = [{"operation": "intent-description",
                  "params": {"device": f"edge{n}", "interface": "GigabitEthernet1",
                             "description": "uplink to the core, " + "x" * 200}}
                 for n in range(E.MOST_STEPS)]
        text = json.dumps({"steps": steps})
        assert len(text) > 2000, "the premise: past the old bound"
        got, why = plans_v2._params(text)
        assert why == "" and got == {"steps": steps}

    def test_a_card_asked_by_an_answer_not_the_persons_is_refused_naming_why(self, monkeypatch):
        from modules.ai import assistant_threads
        from routes import plans_v2
        rows = [{"got": {"call_id": "ai-0123456789abcdef", "plan": {
            "plan": "change", "list": "Lab", "params": {"steps": STEPS}}}}]
        monkeypatch.setattr(assistant_threads, "read", lambda actor: {"rows": rows})
        found, why = plans_v2._answered_plan("ai-0123456789abcdef", "Lab")
        assert why == "" and found["plan"] == "change"
        assert json.loads(found["params"]) == {"steps": STEPS}
        none, why = plans_v2._answered_plan("ai-ffffffffffffffff", "Lab")
        assert none is None and "no answer of yours" in why
        other, why = plans_v2._answered_plan("ai-0123456789abcdef", "Branch")
        assert other is None and why == "that answer's plan is for Lab, not Branch"
        c = plans_v2.card("Lab", {"answer": "ai-ffffffffffffffff", "card": "plan-card-x"})
        assert c["preview"]["ok"] is False and "no answer of yours" in c["preview"]["refused"]


@pytest.fixture(autouse=True)
def as_person():
    with pressed_by(PERSON):
        yield
