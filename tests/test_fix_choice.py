"""The fix choice on the incident's card (Stage 5 step 7; the operator, 2026-11-27; rows C4301 to
C4304; board docs/boards/fix-choice.html): Fixes for this problem, one list of every saved fix
the incident's problem matches, in place of a row of buttons.

THE WORLD: the s1 walk's open incident (tests/fixtures/heal_records/open_bpdu.json,
hi-ebc220c86c8f: s1 Gi1/0 err-disabled by BPDU guard, standing on a can't-fix decision whose
words say no configuration fix can cure it) in Lab's heal stores, written by the test into its
own data folder (tests/test_saved_plans.py's `store`); and the walk's two saved fixes, made by
Mercury's own writers as the walk had them: BPDU guard recovery (access ports), saved from a
verified run and so Automatic, matching the port role ``access``; and BPDU guard recovery (any
port), written as a New fix with no port role, so Manual only. Each is offered by the real
`saved_plans.fix_offers`, previewed by the runner's own preview (`command_plan.preview`) on
Mercury's model of s1 (tests/test_command_plan.py's `Model`: s1's committed intent and golden,
real captures); the incident's page is drawn by its own route through the test client. No
device, no AI call.

Each test holds one purpose:
- the card draws one list, one row per matching fix, each with its mode, its record and one
  small Run bound to the hash its preview drew, none a primary button; Hand over… after it;
- the Automatic fix self-healing would run is Recommended, with why; with none Automatic, none;
- a row's expand says what it sends, checks and verifies;
- the status line names how many fixes match, and the Next line points at the list, never at a
  cause no configuration can cure (C4301, C4303);
- while a fix runs, no row, Run or Hand over… is drawn: the run's stepper; the Timeline follows
  the run's steps; no banner of the press is drawn beside it (C4302);
- after a failed run the list comes back with the failure above it (C4302);
- Make this fix automatic? is offered for a Manual fix whose match names the port's role, said
  with what it would then do, and promotes through the one path, answering on the card; never
  for one matching any port, which the store refuses too, naming why (C4304);
- after a saved fix's run, nothing offers to save it (C4304, C4299);
- the "Not scored yet" line is under the card's Details, not in the story (step 7).
"""
import json
import os
import re
from html import unescape

import pytest

from modules import identity
from modules.nsot import command_plan as CP
from modules.nsot import saved_plans as S
from tests.test_saved_plans import FILLS, MATCH, PERSON, WHO, store  # noqa: F401 (the fixture)

NET = "Lab"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCESS = "BPDU guard recovery (access ports)"
ANY = "BPDU guard recovery (any port)"
#: The walk's any-port fix's match: the condition and the cause, no port role.
ANY_MATCH = {"condition": "err_disabled", "cause": "BPDU guard"}


def fixture(name: str) -> dict:
    """One of the s1 walk's captured records (tests/fixtures/heal_records/README.md)."""
    with open(os.path.join(ROOT, "tests", "fixtures", "heal_records", f"{name}.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def walk(store, monkeypatch):  # noqa: F811
    """The walk's open incident in Lab's stores, its two saved fixes, s1's model behind the
    runner's preview, the viewer a verified person, and the app's test client."""
    import app as A
    from modules.fixit import section as FS
    from modules.heal import decisions as HD
    from modules.heal import incidents as HI
    from modules.heal import steplog as SL
    from tests.test_command_plan import Model
    from tests.test_fix_manual_controls import with_pair_check

    opened = fixture("open_bpdu")
    for path, rows in ((HD.path(NET), opened["decisions"]), (SL._path(NET), opened["steps"])):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows)
    os.makedirs(os.path.dirname(HI.path(NET)), exist_ok=True)
    with open(HI.path(NET), "w", encoding="utf-8") as fh:
        json.dump({"version": HI.VERSION, "incidents": opened["incidents"]}, fh)
    real = CP.preview
    monkeypatch.setattr(CP, "preview", lambda network, key, values, **kw: real(
        network, key, values, **dict(kw, sources=kw.get("sources") or Model(network=NET))))
    monkeypatch.setattr(FS, "_identity", lambda net, dev: "nb:1")
    access = S.save_script(NET, run_id=store["run"](), name=ACCESS, match=dict(MATCH),
                           fills=FILLS, **WHO)
    template = with_pair_check(S.read()["plans"][access["key"]]["template"])
    anyport = S.new_fix(NET, name=ANY, words="", match=dict(ANY_MATCH), fills=FILLS,
                        template=template, **WHO)
    who = {"actor": PERSON}
    monkeypatch.setattr(identity, "identify", lambda _r=None: identity.Identity(
        actor=who["actor"], email=who["actor"], kind="person", verified=True, outcome="ok",
        peer="198.51.100.7", peer_trusted=True, header_present=True))
    A.app.config["TESTING"] = True
    return dict(store, client=A.app.test_client(), iid=opened["page"], access=access["key"],
                anyport=anyport["key"], opened=opened)


def page(w) -> str:
    r = w["client"].get(f"/v2/incident/{w['iid']}?list={NET}")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def card_of(html: str) -> str:
    """The incident's card, up to its Details."""
    start = html.index('id="inc-bluf"')
    return html[start:html.index('id="inc-details"', start)]


def rows_of(html: str) -> dict:
    """Each row of Fixes for this problem, by its fix's key."""
    return {m.group(1): m.group(0) for m in re.finditer(
        r'<li class="fix-row" data-fix="([^"]+)".*?</li>', html, re.S)}


def offers_of(w) -> list:
    """The fixes the incident offers now (`saved_plans.fix_offers` on its page's own read)."""
    from modules import incident_page
    return S.fix_offers(NET, incident_page.resolve(NET, w["iid"]))


def row_of(w, key: str) -> str:
    """*key*'s row on the incident's card as its page draws it now."""
    card = card_of(page(w))
    rows = rows_of(card)
    assert key in rows, f"no row for {key} in Fixes for this problem: {text(card)[:400]}"
    return rows[key]


class TestTheList:
    def test_one_row_per_matching_fix_each_run_bound_to_its_preview(self, walk):
        html = page(walk)
        card = card_of(html)
        assert "Fixes for this problem" in text(card), text(card)[:600]
        rows = rows_of(card)
        assert set(rows) == {walk["access"], walk["anyport"]}, list(rows)
        offers = {o["key"]: o for o in offers_of(walk)}
        from modules import fix_page
        stored = S.fixes(NET)
        assert sorted(offers) == sorted(rows), "one row per offer, none more"
        assert (stored[walk["access"]]["how"], stored[walk["anyport"]]["how"]) == (
            "automatic", "manual"), "the walk's two: Automatic and Manual only"
        for key, row in rows.items():
            run = unescape(re.search(r'hx-post="([^"]*/fixit/script[^"]*)"', row).group(1))
            bound = dict(p.split("=", 1) for p in run.split("?", 1)[1].split("&"))
            # Each Run is bound to the hash the runner's preview draws for it now.
            assert (bound["key"], bound["hash"]) == (key, offers[key]["hash"]), run
            assert "btn-primary" not in row, "every row's Run drawn alike"
            mode = re.search(r'class="fix-row-mode"[^>]*><span class="badge[^"]*"[^>]*>([^<]+)<',
                             row).group(1)
            assert mode == fix_page.HOW[stored[key]["how"]][0], (key, mode)
        assert "Automatic" in text(rows[walk["access"]])
        assert "Manual only" in text(rows[walk["anyport"]])
        assert "Fix with saved script" not in card and "What this fix does" not in card
        # Hand over… after the list, separate.
        assert card.index("Fixes for this problem") < card.index("Hand over…")

    def test_the_automatic_fix_self_healing_runs_is_recommended_and_none_without(self, walk):
        rows = {k: row_of(walk, k) for k in (walk["access"], walk["anyport"])}
        assert "data-recommended" in rows[walk["access"]], rows[walk["access"]][:400]
        assert "Recommended" in text(rows[walk["access"]])
        assert "self-healing runs this one on this problem when it is in Auto" in \
            text(rows[walk["access"]])
        assert "data-recommended" not in rows[walk["anyport"]]
        assert "Recommended" not in text(rows[walk["anyport"]])
        # The rule: the first Automatic fix in the order self-healing fires them.
        picked = [k for k, r in rows.items() if "data-recommended" in r]
        assert picked == [o["key"] for o in offers_of(walk) if o["mode"] == "auto"][:1]
        # With no fix Automatic, none is recommended.
        S._update(lambda doc: doc["plans"][walk["access"]].update(mode=S.MANUAL))
        rows = rows_of(card_of(page(walk)))
        assert len(rows) == 2 and not any("Recommended" in text(r) for r in rows.values()), \
            [text(r)[:200] for r in rows.values()]
        assert [o for o in offers_of(walk) if o["mode"] == "auto"] == []

    def test_a_row_expands_to_what_it_sends_checks_and_verifies(self, walk):
        row = row_of(walk, walk["anyport"])
        does = re.search(r'<details class="fix-row-does"[^>]*><summary>(.*?)</summary>(.*?)'
                         r'</details>', row, re.S)
        assert does, row[:600]
        assert text(does.group(1)) == ("Recover an err-disabled interface on s1 Gi1/0, a fix "
                                       "for any port")
        sent = re.search(r"<pre[^>]*><code>(.*?)</code></pre>", does.group(2), re.S).group(1)
        assert unescape(sent).split("\n") == [
            "interface GigabitEthernet1/0", " shutdown", " no shutdown"], sent
        # What it sends is the runner's preview's program for this incident, line for line.
        program = next(o["program"] for o in offers_of(walk) if o["key"] == walk["anyport"])
        assert unescape(sent).split("\n") == program, (sent, program)
        assert S.templates()[walk["anyport"]].net_zero, "a net-zero plan: its last verify said"
        body = text(does.group(2))
        assert "Checks first: The port is err-disabled by the cause now" in body, body
        assert "Then verifies: The port reads connected" in body, body
        assert "It matches a switch port err-disabled by BPDU guard." in body, body


class TestTheWords:
    def test_the_status_counts_the_fixes_and_next_points_at_the_list(self, walk):
        """C4303 and C4301: the status line names how many fixes match, and the story's Next
        line points at the list, never at the can't-fix decision's "no configuration fix on
        s1 can cure this (… a cable, an optic or a far end)"."""
        html = page(walk)
        status = re.search(r'data-bluf="status" data-status[^>]*>(.*?)</div>', html, re.S)
        assert text(status.group(1)) == (
            "2 saved fixes can fix this: choose one under Fixes for this problem"), status
        nxt = re.search(r'<dd class="inc-sum-next">(.*?)</dd>', html, re.S).group(1)
        assert text(nxt) == ("It needs a person: choose one of the 2 saved fixes under Fixes "
                             "for this problem."), nxt
        assert "can cure this" not in text(nxt) and "far end" not in text(nxt)
        # The count is the offers', and the decision still says what the Next line no longer
        # repeats.
        assert int(text(status.group(1)).split()[0]) == len(offers_of(walk))
        decided = walk["opened"]["decisions"][-1]["outcome_words"]
        assert "can cure this" in decided and text(nxt) not in decided

    def test_the_not_scored_line_is_under_the_cards_details(self, walk):
        html = page(walk)
        details = html[html.index('id="inc-details"'):html.index("</section>",
                                                                 html.index('id="inc-details"'))]
        story = html[html.index("data-story"):]
        assert "Not scored yet, so no number is drawn" in text(details), text(details)[:300]
        assert "Not scored yet" not in text(story[:story.index("</dl>") + 400])
        assert html.count("Not scored yet") == 1
        # Its words are the page's model's needs, each drawn.
        from modules import incident_page
        needs = incident_page.page(NET, walk["iid"], attention={})["story"]["needs"]
        assert set(needs) >= {"confidence", "severity", "risk"}
        line = re.search(r'<p class="inc-needs-line[^>]*>(.*?)</p>', details, re.S).group(1)
        assert text(line) == (
            f"Not scored yet, so no number is drawn: confidence (needs: {needs['confidence']}), "
            f"severity (needs: {needs['severity']}) and risk (needs: {needs['risk']})."), line


#: A minute and a quarter after the walk's incident opened (22:05:46Z): 22:10:00Z.
AFTER = 1795817400.0


def ran(key: str, outcome: str = "done", at: float = AFTER) -> str:
    """A run of *key* on s1 at *at*, as the runner records it (`command_plan_run.run`'s record,
    written by the operations' own record writer): its id."""
    import time

    from modules.nsot import command_plan_run as CR
    from modules.nsot import privileged, reads
    rec = {"id": reads.new_id(at), "list": NET, "device": "s1", "key": key,
           "kind": "command_plan", "state": CR.RECORD_STATE.get(outcome, "failed"),
           "outcome": outcome, "actor": PERSON, "actor_verified": "access",
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at)), "started_at": at,
           "finished_at": at + 30, "why": CR.OUTCOME_WORDS.get(outcome, outcome),
           "params": {"device": "s1", "interface": "GigabitEthernet1/0",
                      "cause": "bpduguard"}}
    privileged.record(NET, rec)
    return rec["id"]


class TestWhileAFixRuns:
    def _running(self, walk, key):
        """A press of *key*'s Run as `fixit_v2.fix_with_script` starts it (a job of the saved
        fix's kind, its page the incident's naming the fix), its steps attached as the runner
        attaches them, held at its send until released."""
        import threading

        from modules import op_progress
        from modules.nsot import capture_job
        from modules.nsot import command_plan_run as CR

        steps, go, attached = [], threading.Event(), threading.Event()

        def work(_job):
            op_progress.attach(CR.STEPS, steps, labels=dict(CR.STEP_LABELS, hold="Hold s1"))
            steps.extend([{"step": "approve", "result": "ok"}, {"step": "hold", "result": "ok"},
                          {"step": "read_before", "result": "ok"}])
            attached.set()
            go.wait(60)
            return {"state": "done", "words": ""}
        job = capture_job.start(NET, f"{ANY} on {walk['iid']}", PERSON, work,
                                kind=S.JOB_KIND,
                                page=f"/v2/incident/{walk['iid']}?list={NET}&fix={key}")
        assert attached.wait(60)
        return job, go

    def test_only_its_stepper_is_drawn_and_the_timeline_follows_it(self, walk):
        from modules.nsot import capture_job

        job, go = self._running(walk, walk["anyport"])
        try:
            html = page(walk)
        finally:
            go.set()
            assert capture_job.wait(job, 60)
        card = card_of(html)
        assert 'class="fix-row"' not in card and "/fixit/script" not in card, \
            text(card)[:600]
        assert 'data-modal-open="fixit-hand-' not in card, "no Hand over… while it runs"
        status = re.search(r'data-bluf="status" data-status[^>]*>(.*?)</div>', card, re.S)
        assert "inc-stepper" in status.group(1), status.group(1)[:400]
        assert re.search(r'aria-current="step"[^>]*data-step="preconditions"',
                         status.group(1)), status.group(1)[:600]
        # The Timeline moves with the run: Applying now, saying the stepper's current step.
        current = re.search(r'aria-current="step"[^>]*>(.*?)(?:<time|</span>)',
                            status.group(1), re.S).group(1)
        life = re.search(r'<li class="inc-life-node inc-life-now" data-stage="([^"]+)"'
                         r'.*?</li>', html, re.S)
        assert life and life.group(1) == "Applying", life and life.group(0)
        words = re.search(r'class="inc-life-words">(.*?)</span>', life.group(0)).group(1)
        assert words == text(current) and words, (words, current)
        assert "Applying (now)" in text(html), "the Timeline's line names it"
        # Its page redraws on each step while it runs.
        live = re.search(r'<div id="incident-live"[^>]*>', html).group(0)
        assert "nmas:device_progress from:body" in live, live

    def test_its_press_draws_no_banner_beside_the_stepper(self, walk, monkeypatch):
        """C4302: "The 'Running …' banner states the current step and disappears when the run
        ends": the press answers with the card itself, its stepper the answer, and its job's
        page names the fix that runs."""
        from modules.nsot import capture_job
        jobs = []
        monkeypatch.setattr(capture_job, "start", lambda network, label, actor, work, **kw:
                            jobs.append(kw) or "job-1")
        html = card_of(page(walk))
        run = re.search(r'hx-post="([^"]*/fixit/script[^"]*key=%s[^"]*)"'
                        % re.escape(walk["anyport"]), html).group(1)
        r = walk["client"].post(unescape(run), headers={"HX-Request": "true"},
                                data={"drawn_spent": "0", "drawn_cap": "1"})
        out = r.get_data(as_text=True)
        assert r.status_code == 200, text(out)[:600]
        answer = re.search(r'<div class="bluf-answer"[^>]*>(.*?)</div>\s*(<p|<div)', out,
                           re.S).group(1)
        assert text(answer) == "", text(answer)
        assert "held, checked, sent" not in out
        assert [j["page"] for j in jobs] == [
            f"/v2/incident/{walk['iid']}?list={NET}&fix={walk['anyport']}"], jobs

    def test_after_a_failed_run_the_list_returns_with_the_failure_above_it(self, walk):
        from modules.nsot import privileged
        rid = ran(walk["anyport"], outcome="rolled_back")
        # Its words are the run record's own.
        card = card_of(page(walk))
        said = re.search(r'data-fix-failed>.*?did not fix it:</strong> ([^<]+)', card, re.S)
        assert said, f"no failure stated above the list: {text(card)[:400]}"
        assert said.group(1).strip() == privileged.get(NET, rid)["why"], said.group(1)
        assert privileged.get(NET, rid)["state"] == "failed", "the runner's own failed state"
        card = card_of(page(walk))
        assert set(rows_of(card)) == {walk["access"], walk["anyport"]}
        failed = re.search(r'data-fix-failed>(.*?)</div></div>', card, re.S)
        assert failed, text(card)[:600]
        assert text(failed.group(1)).startswith(
            f"{ANY} did not fix it: did not verify, and was rolled back"), text(failed.group(1))
        assert card.index("data-fix-failed") < card.index('class="fix-row"')
        assert 'data-modal-open="fixit-hand-' in card, "Hand over… back too"


class TestMakeThisFixAutomatic:
    def test_a_manual_fix_matching_a_port_role_offers_it_and_it_promotes_on_the_card(
            self, walk):
        from tests.test_fix_manual_controls import LATER, with_pair_check
        template = with_pair_check(S.read()["plans"][walk["access"]]["template"])
        e = S.new_fix(NET, name="BPDU guard recovery (access, by hand)", words="",
                      match=dict(MATCH), fills=FILLS, template=template, **WHO)
        row = row_of(walk, e["key"])
        auto = re.search(r'<details class="simple-menu menu-wrap fix-auto".*?</details>', row,
                         re.S)
        assert auto and "Make this fix automatic?" in text(auto.group(0)), text(row)[:600]
        said = text(auto.group(0))
        assert ("Then it runs by itself, with no one pressing Run, on every incident it "
                "matches (a switch port err-disabled by BPDU guard, on an access port) while "
                "Lab's self-healing is in Auto.") in said, said
        assert "Not yet: version 1 has no verified run yet" in said, said
        assert "Make it automatic" not in said.replace("Make this fix automatic?", "")
        # Once its version has a verified run, its press promotes through the one path and
        # answers on the card.
        from tests.test_fix_manual_controls import run_at
        run_at(LATER, e["key"])
        row = row_of(walk, e["key"])
        url = re.search(r'hx-post="([^"]*/saved-plans/[^"]*/promote[^"]*)"', row).group(1)
        assert "view=fixit" in unescape(url), url
        r = walk["client"].post(unescape(url), headers={"HX-Request": "true"},
                                data={"drawn_spent": "0", "drawn_cap": "1"})
        out = r.get_data(as_text=True)
        assert r.status_code == 200, text(out)[:600]
        assert 'id="inc-fixit"' in out
        assert ("Made automatic: BPDU guard recovery (access, by hand) now runs by itself on "
                "every incident it matches, while self-healing is in Auto") in text(out)
        assert S.read()["plans"][e["key"]]["mode"] == "auto"

    def test_never_for_a_fix_matching_any_port_and_the_store_refuses_it(self, walk):
        from modules import fix_page
        from tests.test_fix_manual_controls import LATER, run_at
        run_at(LATER, walk["anyport"])
        row = row_of(walk, walk["anyport"])
        assert "Make this fix automatic?" not in text(row), text(row)
        assert not fix_page.automatic_form(NET, walk["anyport"], WHO)["offer"], \
            "nor Set Automatic… on its page"
        with pytest.raises(S.Refused) as got:
            S.promote(walk["anyport"], network=NET, **WHO)
        assert f"{ANY} matches any port (its match names no port role), so it stays Manual: " \
               "an uplink's err-disable is never re-enabled automatically" in str(got.value)
        runs_on = S.promote_line(NET, walk["anyport"], walk["iid"])["runs_on"]
        r = walk["client"].post(f"/v2/saved-plans/{walk['iid']}/promote?list={NET}",
                                headers={"HX-Request": "true"},
                                data={"key": walk["anyport"], "runs_on": runs_on,
                                      "view": "fixit"})
        out = text(r.get_data(as_text=True))
        assert r.status_code == 409, out[:600]
        assert f"Not made automatic: {ANY} matches any port" in out, out[:600]
        assert S.read()["plans"][walk["anyport"]]["mode"] == S.MANUAL


class TestAfterASavedFixRan:
    def test_nothing_offers_to_save_it(self, walk):
        """C4304 (and C4299's words): the newest passed attempt is a saved fix's run, so the
        incident's save card offers nothing, and says on its hover why: it is saved already."""
        ran(walk["anyport"])
        r = walk["client"].get(f"/v2/saved-plans/{walk['iid']}/card?list={NET}")
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "Save this fix so Mercury handles it automatically?" not in html, text(html)
        assert 'data-offer="saved"' in html, html[:400]
        assert (f'title="Nothing to save: the fix that ran, {ANY}, is a saved fix already."'
                in unescape(html)), html[:600]
        assert "no command plan ran" not in html
        # The name it says is the saved fix's, and a Save asked for anyway saves nothing.
        named = re.search(r"the fix that ran, (.*?), is a saved fix already",
                          unescape(html)).group(1)
        assert named == S.fixes(NET)[walk["anyport"]]["name"]
        before = sorted(S.fixes(NET))
        r = walk["client"].post(f"/v2/saved-plans/{walk['iid']}/save-script?list={NET}",
                                headers={"HX-Request": "true"}, data={"name": "again"})
        assert r.status_code == 409 and sorted(S.fixes(NET)) == before
        assert "is a saved fix already" in text(r.get_data(as_text=True))

    def test_the_fixed_card_names_it_and_offers_make_it_automatic_by_its_rule(self, walk):
        """C4304: closed by a Manual fix whose match names the port's role, the Fixed card
        names it and offers Make this fix automatic? beside How it was fixed, and nothing
        offers to save it."""
        from modules.heal import incidents as HI
        from tests.test_fix_manual_controls import with_pair_check
        template = with_pair_check(S.read()["plans"][walk["access"]]["template"])
        e = S.new_fix(NET, name="BPDU guard recovery (access, by hand)", words="",
                      match=dict(MATCH), fills=FILLS, template=template, **WHO)
        rid = ran(e["key"])
        S.close_fixed(NET, walk["iid"], {"id": rid, "device": "s1",
                                         "interface": "GigabitEthernet1/0"},
                      S.fixes(NET)[e["key"]], PERSON)
        closed = next(i for i in HI.read(NET)["incidents"] if i["id"] == walk["iid"])
        assert closed["state"] == "closed" and closed["fixed"]["script"] == e["key"], closed
        html = page(walk)
        how = re.search(r'data-how>(.*?)</p>(.*?)(?:<details class="simple-details"|$)', html,
                        re.S)
        assert how and "BPDU guard recovery (access, by hand)" in text(how.group(1)), \
            text(html)[:600]
        auto = re.search(r'<details class="simple-menu menu-wrap fix-auto"[^>]*data-auto="'
                         r'([^"]+)"', how.group(2))
        assert auto and auto.group(1) == closed["fixed"]["script"], text(how.group(2))[:400]
        assert "Save this fix" not in html
        assert S.read()["plans"][e["key"]]["mode"] == S.MANUAL, "drawing it changed nothing"


# ── The independent review of the fix choice (2026-11-27; C4306) ─────────────────────────────

HX = {"HX-Request": "true"}


def card_html(w) -> str:
    """The incident's saved-plans card as its page asks for it."""
    r = w["client"].get(f"/v2/saved-plans/{w['iid']}/card?list={NET}", headers=HX)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def field(html: str, name: str) -> str:
    m = re.search(r'name="%s" value="([0-9a-f]*)"' % name, html)
    return m.group(1) if m else ""


class TestNeverAutomaticForAnyPort:
    """HIGH 1 and 2: a Save of a match on any port is saved Manual only, said before the press,
    by either save path; and an Automatic any-port entry already stored runs nothing by itself."""

    def _verified(self, walk, monkeypatch):
        """The built-in recovery ran and verified on the incident (a catalog plan, so Save is
        offered), and no retry starts unseen."""
        from modules.heal import retry
        started = []
        monkeypatch.setattr(retry, "run_soon", lambda *a, **kw: started.append(kw))
        ran("errdisable-recover")
        return started

    def test_a_save_unticking_the_port_role_saves_manual_said_before_the_press(
            self, walk, monkeypatch):
        started = self._verified(walk, monkeypatch)
        base = f"/v2/saved-plans/{walk['iid']}"
        drawn = field(card_html(walk), "drawn")
        line = walk["client"].get(f"{base}/runs-on?list={NET}&keep_cause=1",
                                  headers=HX).get_data(as_text=True)
        assert "data-manual" in line and ("Saved Manual only: a fix for any port is never "
                                          "automatic") in text(line), text(line)
        assert "Mercury will handle this automatically" not in text(line)
        r = walk["client"].post(f"{base}/save-script?list={NET}", headers=HX, data={
            "name": "Recovery, unticked", "keep_cause": "1", "drawn": drawn,
            "runs_on": field(line, "runs_on")})
        out = text(r.get_data(as_text=True))
        assert r.status_code == 200, out[:600]
        e = S.read()["plans"]["fix-recovery-unticked"]
        assert "port_role" not in e["match"] and e["mode"] == S.MANUAL, e["mode"]
        assert "Saved Manual only: Recovery, unticked matches any port" in out, out[:600]
        assert started == [], "nothing retried by itself"

    def test_a_save_of_a_run_already_saved_never_raises_it_to_automatic(self, walk,
                                                                          monkeypatch):
        started = self._verified(walk, monkeypatch)
        base = f"/v2/saved-plans/{walk['iid']}"
        drawn = field(card_html(walk), "drawn")
        r = walk["client"].post(f"{base}/save-action?list={NET}", headers=HX, data={
            "name": "Recover by hand", "words": "x", "drawn": drawn})
        assert r.status_code == 200, text(r.get_data(as_text=True))[:600]
        assert S.read()["plans"]["fix-recover-by-hand"].get("mode") is None
        line = walk["client"].get(f"{base}/runs-on?list={NET}&keep_cause=1",
                                  headers=HX).get_data(as_text=True)
        r = walk["client"].post(f"{base}/save-script?list={NET}", headers=HX, data={
            "name": "Recover by hand", "keep_cause": "1", "drawn": drawn,
            "runs_on": field(line, "runs_on")})
        assert r.status_code == 200, text(r.get_data(as_text=True))[:600]
        e = S.read()["plans"]["fix-recover-by-hand"]
        assert e["match"] == ANY_MATCH and e["mode"] == S.MANUAL, (e["match"], e["mode"])
        assert "promoted_by" not in e and started == []

    def test_an_automatic_any_port_entry_is_refused_at_fire_time_and_sends_nothing(
            self, walk, monkeypatch):
        from modules.nsot import command_plan_run as CR

        def planted(doc):
            e = doc["plans"][walk["anyport"]]
            e.update(mode="auto", promoted_by=PERSON, promoted_at=e["saved_at"],
                     digest=CP.parse(e["template"]).digest)
        # Planted past every writer, as a store from before the rule holds it (since C4311 a
        # write through the store converts it, and a read shows it Manual only).
        raw(planted)
        assert stored_raw()[walk["anyport"]]["mode"] == "auto", "floor: planted Auto"
        monkeypatch.setattr("modules.connection.with_temp_connection",
                            lambda *a, **kw: pytest.fail("a session was opened"))
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **kw: pytest.fail("a session was opened"))
        rec = CR.run(NET, walk["anyport"], {"device": "s1", "interface": "Gi1/0",
                                            "cause": "bpduguard"},
                     actor=PERSON, actor_verified="", person=False, confirmed="0" * 16,
                     incident=walk["iid"], reason="a planted fire",
                     authority={"script": walk["anyport"]})
        assert rec["outcome"] == "refused" and not rec.get("program"), rec
        assert (f"its automatic run is refused: {ANY} matches any port (its match names no "
                "port role)") in rec["why"], rec["why"]
        assert "Nothing was sent" in rec["why"]


class TestTheReviewsOtherFindings:
    def test_a_built_in_plans_close_never_reads_as_a_saved_fix(self, walk):
        """MEDIUM 3: a built-in plan pressed through Run… closes with its own key; the save
        card still offers to save it, never "is a saved fix already"."""
        rid = ran("errdisable-recover")
        S.close_fixed(NET, walk["iid"], {"id": rid, "device": "s1",
                                         "interface": "GigabitEthernet1/0"},
                      {"key": "errdisable-recover",
                       "name": "Recover an err-disabled interface"}, PERSON)
        html = card_html(walk)
        assert "is a saved fix already" not in html, text(html)[:400]
        assert "Save this fix so Mercury handles it automatically?" in html, text(html)[:400]
        assert S.offer(NET, walk["iid"], **WHO)["state"] == "ready"

    def test_a_running_fix_no_row_offers_is_named_by_its_own_name(self, walk):
        """MEDIUM 4: the run's key is not among the offers (a built-in pressed on its page):
        the card names it by its own words, never another offer's name."""
        from modules import incident_page
        from modules.nsot import capture_job
        job, go = TestWhileAFixRuns()._running(walk, "errdisable-recover")
        try:
            fixit = incident_page.page(NET, walk["iid"], attention={})["fixit"]
        finally:
            go.set()
            assert capture_job.wait(job, 60)
        assert fixit["working"] == "Running Recover an err-disabled interface", fixit["working"]
        assert ACCESS not in fixit["working"] and ANY not in fixit["working"]

    def test_make_it_automatic_is_disabled_for_a_viewer_without_the_right(self, walk):
        """LOW 5: drawn disabled, the refusal its title, as other rights-gated controls."""
        from modules import display_names
        from tests.test_fix_manual_controls import LATER, run_at, with_pair_check
        from tests.test_saved_plans import OTHER
        template = with_pair_check(S.read()["plans"][walk["access"]]["template"])
        e = S.new_fix(NET, name="BPDU guard recovery (access, by hand)", words="",
                      match=dict(MATCH), fills=FILLS, template=template, **WHO)
        run_at(LATER, e["key"])
        walk["rights"].update(self_healing=[OTHER])
        row = row_of(walk, e["key"])
        button = re.search(r'<button[^>]*/promote[^>]*>', row)
        assert button, text(row)[:600]
        assert re.search(r"\sdisabled[\s>]", button.group(0)), button.group(0)
        title = unescape(re.search(r'title="([^"]*)"', button.group(0)).group(1))
        assert title == display_names.people(identity.right_refusal("self_healing", **WHO)), \
            title
        assert S.read()["plans"][e["key"]]["mode"] == S.MANUAL


# ── The operator's ruling, 2026-11-28 (OPERATOR.md#automatic-port-roles; C4311, C4312) ──────

#: Each port role a match may name, and whether its fix may be Automatic (an allowlist).
ROLES = [("access", True), ("trunk", False), ("routed", False), ("", False),
         ("uplink-ish", False)]


def matched(role: str) -> dict:
    m = {"condition": "err_disabled", "cause": "BPDU guard"}
    return dict(m, port_role=role) if role else m


def raw(change) -> dict:
    """The saved plans' store as stored on disk, changed by *change* past every writer (as a
    store written before the rule holds it), and read afresh after."""
    with open(S._path(), encoding="utf-8") as fh:
        doc = json.load(fh)
    change(doc)
    with open(S._path(), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    S._READ.clear()
    return doc


def stored_raw() -> dict:
    with open(S._path(), encoding="utf-8") as fh:
        return json.load(fh)["plans"]


class TestTheAccessAllowlist:
    @pytest.mark.parametrize("role,allowed", ROLES)
    def test_a_save_is_automatic_only_for_access_ports_and_says_so(self, store, role,
                                                                   allowed):  # noqa: F811
        e = S.save_script(NET, run_id=store["run"](), name=f"Recovery {role or 'any'}",
                          match=matched(role), fills=FILLS, **WHO)
        assert e["mode"] == ("auto" if allowed else S.MANUAL), e["mode"]
        line = S.runs_on(NET, matched(role), "")
        assert line["manual"] is (not allowed), line
        if not allowed:
            scope = f"{role} ports" if role else "any port"
            assert line["words"].startswith(
                f"Saved Manual only: a fix for {scope} is never automatic"), line["words"]

    @pytest.mark.parametrize("role,allowed", ROLES)
    def test_promote_refuses_every_role_but_access(self, store, role, allowed):  # noqa: F811
        e = S.save_script(NET, run_id=store["run"](), name=f"Recovery {role or 'any'}",
                          match=matched(role), fills=FILLS, dry_run=True, **WHO)
        if allowed:
            assert S.promote(e["key"], network=NET, **WHO)["mode"] == "auto"
            return
        with pytest.raises(S.Refused) as got:
            S.promote(e["key"], network=NET, **WHO)
        named = (f"{role} ports" if role else "any port (its match names no port role)")
        assert f"matches {named}, so it stays Manual" in str(got.value), str(got.value)
        assert "only a fix for access ports may be automatic" in str(got.value)
        assert S.read()["plans"][e["key"]]["mode"] == "dry_run"

    def test_a_fix_the_rule_marked_once_runs_automatically_after_it_is_promoted(
            self, store):  # noqa: F811
        """The third review's finding 1: the rule's mark (`manual_by_rule`) answers the match it
        was made for; a fix whose match now names access ports, promoted, carries no stale mark,
        so its automatic run is not refused for a rule it no longer breaks."""
        e = S.save_script(NET, run_id=store["run"](), name="Recovery, corrected to access",
                          match=matched("access"), fills=FILLS, dry_run=True, **WHO)

        def marked(doc):
            doc["plans"][e["key"]]["manual_by_rule"] = "matches any port, so it stays Manual"
        raw(marked)
        assert S.promote(e["key"], network=NET, **WHO)["mode"] == "auto"
        stored = stored_raw()[e["key"]]
        assert "manual_by_rule" not in stored, stored.get("manual_by_rule")
        why = S.authority_refusal(e["key"], {"script": e["key"]}, NET)
        assert "matches any port" not in why, why

    @pytest.mark.parametrize("role,allowed", ROLES)
    def test_a_stored_automatic_fix_runs_only_for_access_ports(self, store, monkeypatch,
                                                                 role, allowed):  # noqa: F811
        from modules.nsot import command_plan_run as CR
        e = S.save_script(NET, run_id=store["run"](), name=f"Recovery {role or 'any'}",
                          match=matched(role), fills=FILLS, dry_run=True, **WHO)

        def planted(doc):
            got = doc["plans"][e["key"]]
            got.update(mode="auto", promoted_by=PERSON, promoted_at=got["saved_at"],
                       digest=CP.parse(got["template"]).digest)
        raw(planted)
        why = S.authority_refusal(e["key"], {"script": e["key"]}, NET)
        if allowed:
            assert why == "", why
            return
        assert why.startswith("its automatic run is refused: ") and "stays Manual" in why, why
        monkeypatch.setattr("modules.connection.with_temp_connection",
                            lambda *a, **kw: pytest.fail("a session was opened"))
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda *a, **kw: pytest.fail("a session was opened"))
        rec = CR.run(NET, e["key"], {"device": "s1", "interface": "Gi0/2",
                                     "cause": "bpduguard"}, actor=PERSON, actor_verified="",
                     person=False, confirmed="0" * 16, reason="a planted fire",
                     authority={"script": e["key"]})
        assert rec["outcome"] == "refused" and why in rec["why"], rec["why"]


class TestAStoredAutomaticFixTheRuleRefuses:
    """C4311: a fix stored Automatic that the rule refuses reads Manual only everywhere at once,
    and the store's next write converts it, recorded as Mercury's under the ruling; an
    Automatic access-port fix is untouched."""

    def _planted(self, walk):
        from tests.test_fix_manual_controls import with_pair_check
        template = with_pair_check(S.read()["plans"][walk["access"]]["template"])
        trunk = S.new_fix(NET, name="BPDU guard recovery (trunk ports)", words="",
                          match=matched("trunk"), fills=FILLS, template=template, **WHO)

        def planted(doc):
            for key in (walk["anyport"], trunk["key"]):
                e = doc["plans"][key]
                e.update(mode="auto", promoted_by=PERSON, promoted_at="2026-11-27T21:00:00Z",
                         digest=CP.parse(e["template"]).digest)
        raw(planted)
        return trunk["key"]

    def test_it_reads_and_is_drawn_manual_never_recommended_nor_batched(self, walk):
        from modules import fix_page, incident_page
        trunk = self._planted(walk)
        assert stored_raw()[walk["anyport"]]["mode"] == "auto", "floor: stored Automatic"
        every = S.fixes(NET)
        assert (every[walk["anyport"]]["how"], every[trunk]["how"],
                every[walk["access"]]["how"]) == ("manual", "manual", "automatic")
        found = incident_page.resolve(NET, walk["iid"])
        assert S.script_for(NET, found)[0]["key"] == walk["access"], "the batch's pick"
        row = row_of(walk, walk["anyport"])
        assert "Manual only" in text(row) and "data-recommended" not in row, text(row)
        assert "Make this fix automatic?" not in text(row)
        listed = {r["key"]: r for r in fix_page.listing(NET)["rows"]}
        assert listed[trunk]["how"] == "manual", listed[trunk]["how"]
        r = walk["client"].get(f"/v2/fixes/{trunk}?list={NET}")
        page_text = text(r.get_data(as_text=True))
        assert r.status_code == 200 and "Manual only" in page_text, page_text[:400]
        assert "made Manual only under the operator's ruling of 2026-11-28" in page_text

    def test_the_next_write_converts_it_with_a_record_and_leaves_access_alone(self, walk):
        trunk = self._planted(walk)
        before = stored_raw()[walk["access"]]
        S._update(lambda doc: None)
        after = stored_raw()
        for key in (walk["anyport"], trunk):
            e = after[key]
            assert e["mode"] == S.MANUAL and "stays Manual" in e["manual_by_rule"], key
            ch = e["changes"][-1]
            assert (ch["action"], ch["by"]) == ("made_manual", S.RULED_BY), ch
            # The third review's finding 3: the ruling's sentence alone, never cut mid-sentence
            # (the role it refused is the entry's own `manual_by_rule`).
            assert ch["words"] == S.RULED_WHY and ch["at"], ch
        assert after[walk["access"]] == before, "an Automatic access-port fix is untouched"
        assert after[walk["access"]]["mode"] == "auto"
