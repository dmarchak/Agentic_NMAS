"""The device page's Restore from a moment, on v2 (7.3; the device-actions canvas, boards 9 and
10, signed off 2026-10-03).

On test_profile_apply's lab (r2's REAL capture and intent), given a history to choose from:
- the lab's first golden of r2, committed BEFORE its intent (a moment that predates onboarding);
- a moment WITH intent: r2's golden carrying `shutdown` on GigabitEthernet3 and another
  description on GigabitEthernet2, its intent parsed from it (tagged `golden/r2/...`);
- today's golden: r2 without `lldp run`, that shutdown and that description, with
  `load-interval 30` on GigabitEthernet2.
So re-applying the middle moment sends `lldp run`, the description and a dangerous `shutdown`,
and leaves `load-interval 30` (merge-only). The plan is `routes.golden.restore_plan`, the one
`/golden/restore/preview` uses; the apply is `run_targets` as a job (`deploy_job.start_restore`),
the one `/golden/restore/apply` uses, its device path spied:

- the chooser lists every moment, newest first, each with its credential state;
- the preview: the program, the dangerous line waiting on its stated reason, what is left on the
  device, the operands and checks; a reason plans again and offers the confirm bound to it;
- a moment that predates onboarding asks: leave it, or un-onboard it too;
- the confirm CARRIES its list (C396) and starts the restore as a job as the person; the result
  is the receipt's, in place; a moved program is refused with nothing sent; a confirm naming no
  list or no moment is refused.
"""

import html as html_mod
import json
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)


def _with(text, after, line):
    assert f"\n{after}\n" in text, after
    return text.replace(f"\n{after}\n", f"\n{after}\n{line}\n", 1)


@pytest.fixture
def history(lab, monkeypatch):  # noqa: F811
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, git, save_golden, save_host_vars
    real = lab["captured"]
    # Every interface already has a description, so the moment CHANGES Gi2's (a replace).
    assert " description s4 Gi1/0 - VLAN 100 CORE\n" in real
    middle = _with(real, "interface GigabitEthernet3", " shutdown").replace(
        " description s4 Gi1/0 - VLAN 100 CORE\n",
        " description s4 Gi1/0 - VLAN 100 CORE (restore test)\n", 1)
    hostvars.write_committed(lab["repo"], get_parser("cisco_iosxe").parse(middle))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    # Each moment at its own time: tags made in one second would sort in no reliable order.
    import time
    base = int(time.time())
    monkeypatch.setenv("GIT_COMMITTER_DATE", f"{base + 60} +0000")
    out = save_golden("Lab", [GoldenItem("r2", middle, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    # The tag ON that commit (two tags made in one second sort in no reliable order).
    tags = git(lab["repo"], "tag", "--points-at", out["commit"], "--list", "golden/r2/*")[1].split()
    assert len(tags) == 1, tags
    today = _with(real.replace("\nlldp run\n", "\n"), "interface GigabitEthernet2",
                  " load-interval 30")
    monkeypatch.setenv("GIT_COMMITTER_DATE", f"{base + 120} +0000")
    assert save_golden("Lab", [GoldenItem("r2", today, "203.0.113.12", platform="cisco_iosxe")],
                       source="capture", actor="t", baseline=False).get("commit")
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    # The restore asks the inventory whether a device is stale (`build_targets`), and the
    # inventory modules hold their own name for the list's folder: the lab's, as config's.
    from modules import config
    for mod in ("modules.inventory", "modules.inventory.source_config"):
        monkeypatch.setattr(mod + ".get_list_data_dir", config.get_list_data_dir)
    lab["middle"] = tags[-1]
    return lab


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _spy(monkeypatch, outcome="deployed"):
    import routes.deploy as rd
    reached = []

    def spy(entry, list_name, rows, authorise, source_ref="", **kw):
        reached.append({"device": entry["artifact"].device, "list": list_name,
                        "authorise": authorise, "ref": source_ref})
        return {"device": entry["artifact"].device, "outcome": outcome, "commands": ["lldp run"],
                "verify": {"ok": True, "checked_protocols": ["ospf"], "pre": {"ospf": 6},
                           "post": {"ospf": 6}}}
    monkeypatch.setattr(rd, "_deploy_one", spy)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    return reached


def _reason(i=0, why="the port is unused since the circuit was cancelled"):
    return f"&dz::{i}={why}"


class TestTheChooser:
    def test_every_moment_newest_first_with_its_credential_state(self, history):
        r, card = _get(history, "/v2/device/r2/restore")
        assert r.status_code == 200 and "Restore r2 from a moment" in card
        refs = re.findall(r'name="chosen" value="([^"]+)"', card)
        assert refs[0] == "HEAD" and history["middle"] in refs
        assert "credentials current" in card
        assert "Withdrawn baselines are not offered" in card
        # The newest EARLIER moment is ticked: the golden now sends nothing by construction.
        assert f">Preview {history['middle']}<" in card, "the button names the moment ticked"
        assert "sends nothing by construction" in card
        assert "The same golden as now: re-applying it sends nothing." in card, "today's own tag"
        assert "default-src" in r.headers.get("Content-Security-Policy", "")

    def test_ticking_a_moment_names_it_on_the_button(self, history):
        _r, card = _get(history, f"/v2/device/r2/restore?chosen={history['middle']}")
        assert f">Preview {history['middle']}<" in card

    def test_the_menu_row_runs_here_and_without_script_opens_the_page_with_it(self, history):
        _r, page = _get(history, "/v2/device/r2")
        menu = page[page.index('role="menu"'):page.index('class="tabs"')]
        row = menu[menu.index('data-op="restore"') - 50:menu.index('data-op="restore"') + 600]
        assert 'hx-get="/v2/device/r2/restore?back=overview"' in row
        assert "open on today" not in menu.split("Restore")[0][-200:]
        _r, page = _get(history, "/v2/device/r2?op=restore")
        body = page[page.index('id="tab-body"'):]
        assert 'id="device-op"' in body and "Restore r2 from a moment" in body


class TestThePreview:
    def test_the_program_the_reason_it_waits_on_and_what_stays(self, history):
        r, card = _get(history, f"/v2/device/r2/restore/preview?chosen={history['middle']}")
        assert r.status_code == 200, card[:400]
        assert f"Re-apply {history['middle']} to r2" in card
        assert "lldp run" in card and "VLAN 100 CORE (restore test)" in card
        assert "shutdown" in card and 'name="dz::0"' in card, "the dangerous line waits"
        assert "load-interval 30" in card and "will NOT be removed" in card
        assert "Operands" in card and "Checks" in card
        assert "op-confirm" not in card, "no confirm until the reason is given"

    def test_a_reason_plans_again_and_offers_the_confirm_bound_to_it(self, history):
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={history['middle']}"
                        + _reason())
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["moment"] == history["middle"]
        assert vals["capture_hash"] and vals["command_hash"]
        assert json.loads(vals["authorise"]) == [{
            "line": "shutdown", "reason": "the port is unused since the circuit was cancelled"}]
        assert 'data-op="restore"' in card[card.index("op-confirm") - 200:]

    def test_a_moment_before_onboarding_asks_leave_it_or_un_onboard_it(self, history):
        from modules.nsot.repo import git
        first = git(history["repo"], "tag", "--list", "golden/r2/*",
                    "--sort=creatordate")[1].split()[0]
        assert first != history["middle"]
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={first}")
        assert "had no committed intent at" in card
        assert 'name="un_onboard" value="0"' in card and 'name="un_onboard" value="1"' in card
        assert "Leave r2 as it is" in card and "op-confirm" not in card
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={first}&un_onboard=1")
        assert "Re-apply" in card and 'name="un_onboard" value="1"' in card


class TestTheConfirm:
    def _confirm(self, lab, vals, **change):
        return lab["client"].post("/v2/device/r2/restore/confirm", data=dict(vals, **change))

    def test_it_runs_as_a_job_in_its_list_as_the_person_and_draws_the_result(self, history,
                                                                            monkeypatch):
        from modules.nsot import capture_job
        reached = _spy(monkeypatch)
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={history['middle']}"
                        + _reason())
        # C396: the list is the card's, whatever is active.
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Elsewhere")
        r = self._confirm(history, _vals(card))
        waiting = r.get_data(as_text=True)
        assert r.status_code == 200 and f"Re-applying {history['middle']} to r2" in waiting
        assert "nmas:deploy_job from:body, nmas:device_progress from:body" in waiting
        job = re.search(r"/restore/job/([0-9a-f]+)", waiting).group(1)
        assert capture_job.get(job)["kind"] == "restore"
        assert capture_job.wait(job, 20)
        assert [(x["device"], x["list"], x["ref"]) for x in reached] == [
            ("r2", "Lab", history["middle"])]
        lines = {a["line"]: a["reason"] for a in reached[0]["authorise"]["r2"]}
        assert lines == {"shutdown": "the port is unused since the circuit was cancelled"}
        _r, out = _get(history, f"/v2/device/r2/restore/job/{job}?moment={history['middle']}")
        assert f"Re-apply {history['middle']} to r2" in out and "Open in History" in out
        assert "hx-trigger" not in out, "a finished restore listens for nothing"

    def test_a_program_that_moved_is_refused_with_nothing_sent(self, history, monkeypatch):
        from modules.nsot import capture_job
        reached = _spy(monkeypatch)
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={history['middle']}"
                        + _reason())
        r = self._confirm(history, _vals(card), command_hash="0" * 16)
        job = re.search(r"/restore/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 20)
        assert reached == [], "nothing was sent"
        _r, out = _get(history, f"/v2/device/r2/restore/job/{job}")
        assert "refused" in out and "op-ok" not in out

    @pytest.mark.parametrize("change, words", [
        ({"list": ""}, "names no list"),
        ({"list": "Nowhere"}, "names no list"),
        ({"moment": ""}, "no moment or program to be bound to"),
        ({"command_hash": ""}, "no moment or program to be bound to"),
    ])
    def test_a_confirm_without_its_list_moment_or_hash_is_refused(self, history, monkeypatch,
                                                                  change, words):
        reached = _spy(monkeypatch)
        _r, card = _get(history, f"/v2/device/r2/restore/preview?moment={history['middle']}"
                        + _reason())
        r = self._confirm(history, _vals(card), **change)
        assert r.status_code in (400, 404) and words in r.get_data(as_text=True)
        assert reached == []


CARD = "document.getElementById('device-op')"
#: htmx binds a swapped-in control while it settles: click only once nothing settles.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


def test_a_real_browser_restores_from_the_menu_to_the_result(history, monkeypatch):
    """The path a person takes (C385: every opener clicked where it sits): Actions, "Restore
    from…", the moment's Preview, the dangerous line's reason typed (the card plans again and
    offers the confirm), the confirm, the result in place by the job's announcement, the page
    never reloaded."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    reached = _spy(monkeypatch)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click('.page-actions button[aria-haspopup="menu"]')
            b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                       "return m && m.offsetParent !== null", 10)
            b.click('.page-actions a[data-op="restore"]')
            b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=chosen]') && {SETTLED}",
                       15)
            b.js("Array.prototype.filter.call(document.querySelectorAll('#device-op button'), "
                 "function (x) { return /^Preview /.test(x.textContent.trim()); })[0].click();")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=\"dz::0\"]') "
                       f"&& {SETTLED}", 15)
            b.js("var i = document.querySelector('input[name=\"dz::0\"]');"
                 "i.value = 'the port is unused since the circuit was cancelled';"
                 "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && /Open in History/.test({CARD}.textContent) && {SETTLED}",
                       30)
            assert f"Re-apply {history['middle']} to r2" in b.js(f"return {CARD}.textContent")
            assert b.js("return window.__notReloaded") == 1
            assert [(x["device"], x["ref"]) for x in reached] == [("r2", history["middle"])]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
