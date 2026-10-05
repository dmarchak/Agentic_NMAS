"""The device page's Deploy, with Mode B, on v2 (7.3; the device-actions canvas, boards 5 and 6;
the last of the four device actions).

On test_profile_apply's lab (r2's REAL capture and intent), edited so the deploy has all three
things the board draws: r2's golden lacks `lldp run` and carries `load-interval 30` on
GigabitEthernet2, and its intent adds `shutdown` on GigabitEthernet3. So the program sends
`lldp run` and a dangerous `shutdown`, and `load-interval 30` is left on the device, offered for
removal. The plan is `routes.deploy.plan_devices`, the one `/deploy/plan` uses; the apply is
`apply_batch` as a job (`deploy_job`), the one the batch apply uses, its device path spied:

- the card (from "Plan a deploy…", or the page without script): the exact program, the
  dangerous line waiting on its reason (not confirmable), the residue with its box, what will
  not happen, the operands, the checks, no confirm until every reason is given;
- a reason typed plans again and offers the confirm bound to that program's hash; a residue
  line ticked plans its removal (Mode B) and waits on its own reason, then carries both, by id
  and with each reason, into the hash and the apply;
- the confirm starts the deploy as a job (kind "deploy", never "monitoring profile apply"),
  as the verified person; the card draws the pipeline's stages while it runs and listens for
  the job and each step; the result is the receipt's, in place;
- a program that moved is refused with nothing sent; a failed verify that rolled back draws
  "Rolled back" and its two ways out, each opening what it names;
- a confirm naming no list, an unknown list or no hash is refused.
"""

import html as html_mod
import json
import os
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def deploy(lab, monkeypatch):  # noqa: F811
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    real = lab["captured"]
    assert "\nlldp run\n" in real and "\ninterface GigabitEthernet2\n" in real
    golden = real.replace("\nlldp run\n", "\n").replace(
        "\ninterface GigabitEthernet2\n", "\ninterface GigabitEthernet2\n load-interval 30\n")
    out = save_golden("Lab", [GoldenItem("r2", golden, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    intent = real.replace("\ninterface GigabitEthernet3\n", "\ninterface GigabitEthernet3\n shutdown\n")
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(intent))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    return lab


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _residue_id(card, text="load-interval 30"):
    m = re.search(r'name="rm" value="([^"]+)" id="rm-[^"]+"[^>]*>\s*<label[^>]*><code>[^<]*'
                  + re.escape(text), card)
    assert m, "the residue line has its box"
    return m.group(1)


def _spy(monkeypatch, outcome="deployed", rollback=None, sent_hash=None):
    import routes.deploy as rd
    reached = []

    def spy(entry, list_name, rows, authorise, **kw):
        reached.append({"device": entry["artifact"].device, "authorise": authorise,
                        "scope": kw.get("scope", "")})
        return {"device": entry["artifact"].device, "outcome": outcome,
                "commands": ["lldp run"], "stage": "verify" if rollback else "",
                **({"program_hash": sent_hash[0]} if sent_hash else {}),
                "verify": {"ok": not rollback, "checked_protocols": ["ospf"],
                           "pre": {"ospf": 6}, "post": {"ospf": 5 if rollback else 6}},
                "reason": "OSPF 5 of 6 after the settle window" if rollback else "",
                **({"rolled_back": True, "rollback_outcome": rollback} if rollback else {})}
    monkeypatch.setattr(rd, "_deploy_one", spy)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    return reached


def _reasons(dz="the link is being retired"):
    return f"&dz::0={dz}"


class TestTheCard:
    def test_the_program_the_dangerous_line_the_residue_and_no_confirm_yet(self, deploy):
        r, card = _get(deploy, "/v2/device/r2/deploy")
        assert r.status_code == 200
        assert "Deploy committed intent to r2" in card and 'id="device-op"' in card
        assert "lldp run" in card and "shutdown" in card
        assert 'name="dz::0"' in card, "the dangerous line waits on its reason"
        assert "load-interval 30" in card and 'name="rm"' in card
        assert "What will not happen" in card and "Operands" in card and "Checks" in card
        assert "op-confirm" not in card, "no confirm until every reason is given"
        assert "waits on your stated reason" in card
        assert "default-src" in r.headers.get("Content-Security-Policy", "")

    def test_a_reason_plans_again_and_offers_the_confirm_bound_to_that_program(self, deploy):
        _r, card = _get(deploy, "/v2/device/r2/deploy?back=overview" + _reasons())
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["capture_hash"] and vals["command_hash"]
        assert json.loads(vals["authorise"]) == [{"line": "shutdown",
                                                   "reason": "the link is being retired"}]
        assert json.loads(vals["remove"]) == []
        assert 'data-op="deploy"' in card[card.index("op-confirm") - 200:]

    def test_a_ticked_line_is_removed_with_its_own_reason_in_the_hash(self, deploy):
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        _r, ticked = _get(deploy, f"/v2/device/r2/deploy?rm={rid}" + _reasons())
        assert "will be removed" in ticked and f'name="why::{rid}"' in ticked
        assert "op-confirm" not in ticked, "a ticked line waits on its own reason"
        _r, both = _get(deploy, f"/v2/device/r2/deploy?rm={rid}&why::{rid}=left+over+from+the+old+design"
                        + _reasons())
        assert "no load-interval 30" in both, "the removal is in the program"
        vals, before = _vals(both), _vals(plain)
        assert json.loads(vals["remove"]) == [rid]
        assert vals["command_hash"] != before["command_hash"]
        assert {"reason": "left over from the old design"} .items() <= next(
            a for a in json.loads(vals["authorise"]) if "load-interval" in a["line"]).items()

    def test_a_freed_card_keeps_what_its_person_entered(self, deploy):
        """C473 (2026-10-05): a card refused because another operation held the device redraws
        when the hold ends, and it drew the card from its start, empty: the ticked removal and
        every typed reason gone. Its redraw now sends the card's form, and `when_free` plans
        from it, the same program and hash as the card had."""
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        q = f"rm={rid}&why::{rid}=left+over+from+the+old+design" + _reasons()
        _r, direct = _get(deploy, f"/v2/device/r2/deploy?{q}")
        _r, freed = _get(deploy, f"/v2/device/r2/when-free?op=deploy&back=overview&{q}")
        assert "no load-interval 30" in freed, "the ticked removal survived"
        assert _vals(freed)["command_hash"] == _vals(direct)["command_hash"]

    def test_every_held_card_with_fields_sends_its_form_when_freed(self):
        """The shape: each held card whose form a person fills (deploy, restore, retry) includes
        that form in its `when_free` redraw. Retire and revert carry theirs in the URL."""
        for name in ("_deploy.html", "_restore.html", "_retry.html"):
            text = open(os.path.join(ROOT, "templates", "v2", name), encoding="utf-8").read()
            held = [line for line in text.splitlines() if "device_v2.when_free" in line]
            assert held and all('hx-include="find .op-form"' in line for line in held), name

    def test_the_header_opens_the_card_and_the_page_draws_it_without_script(self, deploy):
        _r, page = _get(deploy, "/v2/device/r2")
        head = page[page.index('data-op="deploy"') - 40:page.index("Plan a deploy")]
        assert 'hx-get="/v2/device/r2/deploy' in head
        _r, page = _get(deploy, "/v2/device/r2?op=deploy")
        assert "Deploy committed intent to r2" in page


class TestTheConfirm:
    def _confirm(self, lab, vals, **change):
        return lab["client"].post("/v2/device/r2/deploy/confirm", data=dict(vals, **change))

    def test_it_runs_as_a_job_as_the_person_and_draws_the_result(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        sent = []
        reached = _spy(monkeypatch, sent_hash=sent)
        _r, plain = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        rid = _residue_id(plain)
        _r, card = _get(deploy, f"/v2/device/r2/deploy?rm={rid}"
                        "&why::{rid}=left+over+from+the+old+design".replace("{rid}", rid)
                        + _reasons())
        # The device path sends exactly the program confirmed (the pipeline's own hash).
        sent.append(_vals(card)["command_hash"])
        r = self._confirm(deploy, _vals(card))
        assert r.status_code == 200
        waiting = r.get_data(as_text=True)
        assert "Deploying to r2" in waiting and "data-stepper" in waiting
        assert "nmas:deploy_job from:body, nmas:device_progress from:body" in waiting
        job = re.search(r"/deploy/job/([0-9a-f]+)", waiting).group(1)
        assert capture_job.get(job)["kind"] == "deploy", "never 'monitoring profile apply'"
        assert capture_job.wait(job, 20)
        assert [x["device"] for x in reached] == ["r2"] and reached[0]["scope"] == ""
        lines = {a["line"]: a["reason"] for a in reached[0]["authorise"]["r2"]}
        assert lines.get("shutdown") == "the link is being retired"
        assert any("load-interval" in k and v == "left over from the old design" for k, v in lines.items())
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "Deploy to r2" in out and "op-ok" in out and "Open in History" in out
        assert "hx-trigger" not in out, "a finished deploy listens for nothing"

    def test_a_program_that_moved_is_refused_with_nothing_sent(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        reached = _spy(monkeypatch)
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card), command_hash="0" * 16)
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        assert reached == [], "nothing was sent"
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "refused" in out and "op-ok" not in out

    def test_a_failed_verify_rolled_back_offers_its_two_ways_out(self, deploy, monkeypatch):
        from modules.nsot import capture_job
        _spy(monkeypatch, outcome="failed",
             rollback={"state": "restored",
                       "detail": "the rollback undid what landed and read r2 back as it was"})
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card))
        job = re.search(r"/deploy/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        _r, out = _get(deploy, f"/v2/device/r2/deploy/job/{job}")
        assert "Rolled back" in out and "read r2 back as it was" in out
        assert 'data-next-acts="revert"' in out and 'data-next-acts="retry"' in out
        # The two ways out open their cards here (board 11), in place of this one.
        assert 'hx-get="/v2/device/r2/revert?back=' in out and 'hx-get="/v2/device/r2/retry?back=' in out
        assert "op=revert" in out and "op=retry" in out

    @pytest.mark.parametrize("change, words", [
        ({"list": ""}, "names no list"),
        ({"list": "Nowhere"}, "names no list"),
        ({"command_hash": ""}, "no program to be bound to"),
    ])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, deploy, monkeypatch, change,
                                                           words):
        reached = _spy(monkeypatch)
        _r, card = _get(deploy, "/v2/device/r2/deploy?" + _reasons()[1:])
        r = self._confirm(deploy, _vals(card), **change)
        assert r.status_code in (400, 404) and words in r.get_data(as_text=True)
        assert reached == []


@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


CARD = "document.getElementById('device-op')"
#: htmx binds a swapped-in control while it settles: click only once nothing settles.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_plan_give_the_reason_confirm_and_the_result_arrives_in_place(
            self, deploy, live_browser, monkeypatch):
        """The path a person takes: "Plan a deploy…", the dangerous line's reason typed (the
        card plans again and offers the confirm), the confirm, the stepper, the result by
        the job's announcement, the page never reloaded."""
        browser, srv, b = live_browser
        sent = []
        reached = _spy(monkeypatch, sent_hash=sent)
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            # "Plan a deploy…" is the Actions menu's first row (2026-10-05), no separate button.
            b.click('.page-actions button[aria-haspopup="menu"]')
            b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                       "return m && m.offsetParent !== null", 10)
            b.click('.page-actions a[data-op="deploy"]')
            b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=\"dz::0\"]') "
                       f"&& {SETTLED}", 15)
            b.js("var i = document.querySelector('input[name=\"dz::0\"]');"
                 "i.value = 'the link is being retired';"
                 "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            vals = b.js("return document.querySelector('#device-op .op-confirm')"
                        ".getAttribute('hx-vals')")
            sent.append(json.loads(vals)["command_hash"])
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}",
                       30)
            assert "Deploy to r2" in b.js(f"return {CARD}.textContent")
            assert b.js("return window.__notReloaded") == 1
            assert [x["device"] for x in reached] == ["r2"]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
