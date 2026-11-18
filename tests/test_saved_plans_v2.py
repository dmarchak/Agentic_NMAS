"""The incident card's saved plans (Gate 1b; routes/saved_plans_v2.py,
templates/v2/_saved_plans_saves.html, board saved-plans artboard S): Save as a self-heal script
and Save as a reusable action after a verified command-plan run, Promote on a script the
problem matches, Approve on a waiting shape, each through the approval rights' chokepoint and
answered in place.

The incident's records are stood in at their readers (the page's resolve, the fix-it record,
its attempts and the problem's classification); the run is a runner-shaped record written by
the operations' own record writer, as tests/test_saved_plans.py writes it.
"""
import re

import pytest

from modules import identity
from modules import problem as P
from modules.nsot import command_policy as POL
from modules.nsot import saved_plans as S
from tests.test_saved_plans import BPDU, NET, OTHER, PERSON, store  # noqa: F401 (the fixture)

INC = "hi-abcdef12"


@pytest.fixture
def card(store, monkeypatch):  # noqa: F811
    """r2's incident on Lab, its newest attempt a recovery that passed its own verify; the
    viewer a verified person (the access proxy's assertion stood in)."""
    import app as A
    from modules.nsot import privileged, reads

    rec = {"id": reads.new_id(), "list": NET, "device": "s1", "key": "errdisable-recover",
           "kind": "command_plan", "state": "done", "outcome": "done", "actor": PERSON,
           "at": "2026-11-15T10:00:00Z", "title": "Recover s1 Gi0/2, err-disabled by bpduguard",
           "params": {"device": "s1", "interface": "GigabitEthernet0/2", "cause": "bpduguard"}}
    privileged.record(NET, rec)
    monkeypatch.setattr("modules.incident_page.resolve", lambda network, iid: {
        "found": "page", "incident": {"id": iid, "device": "s1"}})
    monkeypatch.setattr("modules.fixit.section.incident_of", lambda network, found: {
        "incident": object(), "why": ""})
    monkeypatch.setattr("modules.fixit.incident.attempts", lambda inc, *a, **kw: {
        "attempts": [{"operation": "errdisable-recover", "passed": True, "run": rec["id"]}]})
    monkeypatch.setattr(P, "classify", lambda found: BPDU)
    monkeypatch.setattr(S, "_incidents_problems", lambda network: [(INC, BPDU)])
    who = {"actor": PERSON}
    monkeypatch.setattr(identity, "identify", lambda _r=None: identity.Identity(
        actor=who["actor"], email=who["actor"], kind="person", verified=True, outcome="ok",
        peer="198.51.100.7", peer_trusted=True, header_present=True))
    A.app.config["TESTING"] = True
    return dict(store, client=A.app.test_client(), who=who)


def _html(r):
    return re.sub(r"\s+", " ", r.get_data(as_text=True))


def _get(card):
    return card["client"].get(f"/v2/saved-plans/{INC}/card?list={NET}")


def _post(card, what, **data):
    return card["client"].post(f"/v2/saved-plans/{INC}/{what}?list={NET}", data=data,
                               headers={"HX-Request": "true"})


class TestTheCard:
    def test_after_a_verified_run_it_offers_both_saves_with_the_match_and_parameters(
            self, card):
        r = _get(card)
        html = _html(r)
        assert r.status_code == 200
        assert "Recover s1 Gi0/2, err-disabled by bpduguard ran and passed its own verify" in html
        assert 'data-match="condition">condition: err_disabled (always)' in html
        assert 'name="keep_cause" value="1" checked> cause: BPDU guard' in html
        assert 'data-preview="match">1 of the 1 open incidents' in html
        assert 'data-fill="cause">cause: BPDU guard as bpduguard' in html
        # Board R5's simple card (approved 2026-11-15): the offer's Save (Automatic: saving a
        # verified fix is the approval, 6b91dc45), Customize… holding the reusable action's.
        assert "Save this fix so Mercury handles it automatically?" in html
        assert 'data-save="default"' in html and "Save as a reusable action" in html
        assert 'data-refused="action"' not in html, "rights unset: every person holds them"
        # Review 7: and the card says so, until access_rights names who holds each.
        assert ('data-rights="unset">Until Settings\' access_rights names who holds them, '
                'every verified person holds self-healing and admin rights.') in html
        card["rights"]["admin"] = [PERSON]
        assert "every verified person holds self-healing rights." in _html(_get(card))
        card["rights"]["self_healing"] = [PERSON]
        assert 'data-rights="unset"' not in _html(_get(card))
        card["rights"].clear()
        # Pressed where it is drawn (its own hx-post), the script is saved as drawn: the match
        # the ticks kept and the fills the card named.
        url = re.search(r'hx-post="([^"]*save-script[^"]*)"', html).group(1)
        r = card["client"].post(url.replace("&amp;", "&"), headers={"HX-Request": "true"},
                                data={"name": "BPDU guard recovery", "keep_cause": "1"})
        assert r.status_code == 200
        e = S.scripts(NET)["fix-bpdu-guard-recovery"]                     # 3a659d6b's key
        assert e["match"] == {"condition": "err_disabled", "cause": "BPDU guard"}
        assert e["mode"] == "auto" and e["promoted_by"] == PERSON, "Save is the approval"

    def test_no_verified_run_says_so_and_offers_nothing(self, card, monkeypatch):
        monkeypatch.setattr("modules.fixit.incident.attempts", lambda inc, *a, **kw: {
            "attempts": []})
        html = _html(_get(card))
        assert "Nothing to save yet: no command plan ran and passed its own verify" in html
        assert "Save as a self-heal script" not in html
        # And a save asked for anyway is refused, saying why, with nothing saved.
        r = _post(card, "save-script", name="BPDU guard recovery")
        assert r.status_code == 409 and "Not saved: no command plan ran" in _html(r)
        assert S.scripts(NET) == {}


class TestSaving:
    def test_saved_as_a_script_in_dry_run_then_promoted(self, card):
        """Customize's Dry run (6b91dc45: a plain Save is Automatic): saved, it is board R5's
        one line, "Saved: <name>, Dry run.", with Promote… opening the promote in place."""
        r = _post(card, "save-script", name="BPDU guard recovery", keep_cause="1", dry_run="1")
        html = _html(r)
        assert r.status_code == 200 and 'data-saved="script"' in html
        assert "BPDU guard recovery</a>, Dry run." in html, html[:600]
        e = S.scripts(NET)["fix-bpdu-guard-recovery"]
        assert e["match"] == {"condition": "err_disabled", "cause": "BPDU guard"}
        assert e["fills"]["cause"] == {"BPDU guard": "bpduguard"}
        assert "Promote BPDU guard recovery" in html
        r = _post(card, "promote", key=e["key"])
        assert r.status_code == 200 and "Promoted BPDU guard recovery" in _html(r)
        assert S.scripts(NET)[e["key"]]["mode"] == "auto"

    def test_a_person_without_the_right_is_refused_with_why(self, card):
        card["rights"].update(admin=[OTHER], self_healing=[OTHER])
        html = _html(_get(card))
        # Drawn by display name (C3715: a screen names people by display name, never an
        # identity), the refusal's words otherwise as recorded.
        assert f"{identity.display_name(PERSON)} does not hold the admin right" in html
        assert PERSON not in html and OTHER not in html
        assert re.search(r'save-action[^>]*hx-disabled-elt="this" disabled', html)
        r = _post(card, "save-action", name="Bounce interface", words="x")
        assert r.status_code == 403 and "Not saved: Refused: " in _html(r)
        assert S.actions() == {}
        r = _post(card, "save-script", name="BPDU guard recovery")
        assert r.status_code == 403 and S.scripts(NET) == {}

    def test_an_admin_saves_a_reusable_action(self, card):
        card["rights"]["admin"] = [PERSON]
        r = _post(card, "save-action", name="Bounce interface", words="Shut and no shut")
        # Board R5: the saved line "Saved: <name>, in the catalog"; a saved fix keyed fix-
        # (3a659d6b).
        assert r.status_code == 200 and 'data-saved="action"' in _html(r)
        assert "Bounce interface</a>, in the catalog" in _html(r)
        assert list(S.actions()) == ["fix-bounce-interface"]


class TestTheShapes:
    def test_a_waiting_shape_is_drawn_with_its_proposal_and_approved_by_an_admin(self, card):
        shape = "interface {interface} > description {description}"
        assert POL.propose(NET, "cisco_ios", shape, by="ai:fixit", why="a clumsy fix")["ok"]
        html = _html(_get(card))
        assert f"<code>{shape.replace('>', '&gt;')}</code> (cisco_ios), proposed by" in html
        assert "not measured yet: its first approved run measures it" in html
        card["rights"]["admin"] = [OTHER]
        r = _post(card, "approve-shape", dialect="cisco_ios", shape=shape)
        assert r.status_code == 403 and "does not hold the admin right" in _html(r)
        card["who"]["actor"] = OTHER
        r = _post(card, "approve-shape", dialect="cisco_ios", shape=shape)
        assert r.status_code == 200 and "approved; its first run measures it" in _html(r)
        assert POL.provisional(NET) == []


# ── A saved action on a device's interface (board saved-plans D) ────────────────────────────

#: A reusable action whose parameters an interface fills alone, as an admin saved it: the
#: shipped recovery's own lines and shapes, with its cause left out.
BOUNCE = {"kind": "command_plan", "key": "action-bounce-interface",
          "title": "Bounce {device} {interface_short}", "words": "Shut and no shut one port",
          "net_zero": True,
          "parameters": {"device": {"type": "device", "words": "a device"},
                         "interface": {"type": "interface", "words": "an access port",
                                       "access_port": True, "not_management": True}},
          "steps": [{"mode": "config",
                     "commands": ["interface {interface}", " shutdown", " no shutdown"]}],
          "verify": [{"name": "The port reads connected", "read": "show interfaces status",
                      "expect": "errdisable.port_connected", "poll": "errdisable-poll",
                      "within": "errdisable-connect"}],
          "reason": "Shut and no shut one port, never saved; net zero"}


@pytest.fixture
def device(card, monkeypatch):
    """r2's page on Lab with one saved action acting on one interface, its committed intent
    holding two interfaces; the runner's preview and run stood in at their seams, the job run
    at once."""
    from modules.nsot import command_plan as CP
    from modules.nsot import command_plan_run as CR

    def change(doc):
        # An action saved before C3849 on Lab: its network the one its run was on, not shared
        # (4816fadb, the operator, 2026-11-16: "a saved fix belongs to the network it was
        # saved on").
        doc["plans"][BOUNCE["key"]] = {"key": BOUNCE["key"], "kind": "action",
                                       "name": "Bounce interface", "template": BOUNCE,
                                       "from_run": {"network": NET}}
    S._update(change)
    monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, host: {
        "interfaces": [{"name": "GigabitEthernet0/2"}, {"name": "GigabitEthernet0/3"}]})
    seen = {"run": []}
    monkeypatch.setattr(CP, "preview", lambda network, key, values, **kw: {
        "ok": True, "hash": "h-bounce", "title": f"Bounce r2 {values['interface']}",
        "refusals": [], "drawn": {"program": ["interface GigabitEthernet0/2", " shutdown",
                                              " no shutdown"],
                                  "preconditions": [], "verify": [{"name": "The port reads "
                                                                           "connected"}]}})

    def run(network, key, values, **kw):
        seen["run"].append((key, values, kw))
        return {"id": kw["run_id"], "state": "done"}
    monkeypatch.setattr(CR, "run", run)
    seen["job"] = []
    monkeypatch.setattr("modules.nsot.capture_job.start", lambda lst, label, actor, work, **kw:
                        (seen["job"].append(dict(kw, payload=work("j-1"))), "j-1")[1])
    return dict(card, seen=seen)


def _dev(device, query=""):
    return device["client"].get(f"/v2/saved-plans/device/r2/actions?list={NET}{query}")


class TestTheDeviceActions:
    def test_it_is_offered_for_an_interface_and_runs_through_the_runner(self, device):
        assert list(S.interface_actions()) == [BOUNCE["key"]]
        html = _html(_dev(device))
        assert "Saved actions on an interface" in html and "Preview Bounce interface…" in html
        assert '<option value="GigabitEthernet0/3">' in html
        html = _html(_dev(device, f"&key={BOUNCE['key']}&interface=GigabitEthernet0/2"))
        assert "Run Bounce r2 GigabitEthernet0/2" in html and "Bound to h-bounce" in html
        r = device["client"].post(f"/v2/saved-plans/device/r2/run?list={NET}",
                                  headers={"HX-Request": "true"},
                                  data={"key": BOUNCE["key"], "interface": "GigabitEthernet0/2",
                                        "hash": "h-bounce"})
        assert r.status_code == 200
        (key, values, kw) = device["seen"]["run"][0]
        assert key == BOUNCE["key"] and values == {"device": "r2",
                                                   "interface": "GigabitEthernet0/2"}
        assert kw["confirmed"] == "h-bounce" and kw["person"] is True
        assert kw["actor"] == PERSON and kw["actor_verified"] == "access"
        # In progress reopens it at the device's Overview with its run (a page's job), and
        # the Overview's slot asks for that run's card.
        (job,) = device["seen"]["job"]
        assert job["page"] == (f"/v2/device/r2?tab=overview&list={NET}&run={kw['run_id']}")
        assert "device" not in job and job["payload"]["run"] == kw["run_id"]
        from flask import render_template
        import app as A
        with A.app.test_request_context(job["page"]):
            slot = render_template("v2/_saved_actions_slot.html", device={"hostname": "r2"},
                                   list_name=NET)
        assert f"run={kw['run_id']}" in slot

    def test_an_action_an_interface_does_not_fill_alone_is_not_offered(self, device):
        """The incident's recovery takes its cause too, so no interface fills it alone
        (`interface_actions`). Since da740aa1 (the operator, 2026-11-16: a fix's first run is
        a person's "on a matching incident or a chosen port") a chosen port runs it with its
        choice asked beside the port (`port_actions`): offered with its cause's select. A key
        that is neither a saved action of the network nor a built-in fix is refused, nothing
        run; the built-in recovery itself is Run… on a chosen device (fc937efe, the operator,
        2026-11-17: "same as saved fixes"), the runner bound to the hash sent."""
        def change(doc):
            doc["plans"].pop(BOUNCE["key"])
        S._update(change)
        # The recovery saved as a reusable action: its parameters are a device, an interface
        # and a cause, so no interface fills it alone.
        e = S.save_action(NET, run_id=device["run"](), name="Recover a port", words="x",
                          actor=PERSON, actor_verified="access", person=True)
        assert e["key"] in S.actions() and e["key"] not in S.interface_actions()
        html = _html(_dev(device))
        assert f'data-action="{e["key"]}"' in html and "Preview Recover a port…" in html
        assert f'name="c__{e["key"]}__cause"' in html, "its choice asked beside the port"
        r = device["client"].post(f"/v2/saved-plans/device/r2/run?list={NET}",
                                  headers={"HX-Request": "true"},
                                  data={"key": "no-such-fix", "interface": "Gi0/2", "hash": "h"})
        assert r.status_code == 409 and not device["seen"]["run"]
        assert "no saved action on one interface, nor a built-in fix" in _html(r)
        r = device["client"].post(f"/v2/saved-plans/device/r2/run?list={NET}",
                                  headers={"HX-Request": "true"},
                                  data={"key": "errdisable-recover", "interface": "Gi0/2",
                                        "hash": "h"})
        assert r.status_code == 200
        ((key, _values, kw),) = device["seen"]["run"]
        assert key == "errdisable-recover" and kw["confirmed"] == "h"

    def test_the_ai_or_an_unverified_viewer_may_not_run_it(self, device, monkeypatch):
        with identity.as_ai("assistant"):
            html = _html(_dev(device, f"&key={BOUNCE['key']}&interface=GigabitEthernet0/2"))
        assert 'data-refused="run"' in html and "ai:assistant may not approve" in html
        assert re.search(r'device/r2/run\?list=Lab"[^>]*\sdisabled[\s>]', html), \
            "Run is drawn disabled for the AI"
        monkeypatch.setattr(identity, "identify", lambda _r=None: identity.Identity())
        r = device["client"].post(f"/v2/saved-plans/device/r2/run?list={NET}",
                                  headers={"HX-Request": "true"},
                                  data={"key": BOUNCE["key"], "interface": "GigabitEthernet0/2",
                                        "hash": "h-bounce"})
        assert r.status_code in (401, 403) and not device["seen"]["run"]
