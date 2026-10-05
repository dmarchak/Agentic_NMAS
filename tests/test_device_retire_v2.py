"""The device page's Retire, on v2 (7.3; the device-actions canvas, board 12, signed off
2026-10-03 with the change asked: what is GENERATED is dropped at its next regeneration and
the result says so; what SURVIVES is named with how it is removed), and a retired device's
address showing its retired record (C185, the flagged choice agreed).

On test_retire_screen's world (r4 and r5 in the list 'Lab': a real repository, CSV, manifest
and credential store; NetBox holding r5 as device 9, created by hand). The plan is
`retire.plan`, the apply `retire.apply` with the export log as the break-glass basis, the
ones `/retire/*` use:

- the menu row runs here, and the menu says every action does;
- the card: the reason, the steps in order (the row last), the generated (the heartbeat rule;
  the scrape targets where a target directory is set) with when each drops, what survives
  with how each is removed (NetBox, Oxidized's row, a hand-built panel), what it leaves
  unchanged, the checks; with no export holding r5's credential it is refused and points at
  Credentials; a preview writes nothing; an empty reason offers no confirm;
- the confirm carries its list and retires as the person; the result says what was done, what
  was dropped (the targets read back) and what is still to remove; the device's address then
  shows its retired record; a plan that moved does nothing; no list or no hash refused;
- `targets_after` reads the files back (dropped, still, not managed); `retired_record` matches
  the trailer exactly;
- in a real browser, from the menu to the result, then the address showing the record.
"""

import html as html_mod
import json
import os
import re

import pytest

from tests.conftest import TEST_PERSON
from tests.test_retire_screen import REASON, _export, _state, screen  # noqa: F401
from tests.test_retire import world  # noqa: F401


@pytest.fixture
def page(screen, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return screen


@pytest.fixture
def exported(page):
    _export(page)
    return page


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _part(card, title):
    start = card.index(f"<h3>{title}</h3>")
    nxt = card.find('<div class="op-part">', start)
    return card[start:nxt if nxt > 0 else len(card)]


def _card(lab, reason=REASON):
    from urllib.parse import quote
    return _get(lab, f"/v2/device/r5/retire?reason={quote(reason)}")


def _targets(monkeypatch, tmp_path, devices):
    """A target directory, and a generation naming *devices* (what the keeper would write)."""
    from modules import prometheus_targets as PT
    d = tmp_path / "targets"
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(PT, "target_dir", lambda: str(d))
    monkeypatch.setattr(PT, "_record_path", lambda: str(tmp_path / "targets-record.json"))
    groups = [{"targets": [ip], "labels": {"device": h}} for h, ip in devices]
    monkeypatch.setattr(PT, "generate", lambda: {
        "files": {"nmas-snmp-all.json": groups}, "devices": len(groups), "inventory": 2,
        "notes": [], "excluded": {}})
    return d


class TestTheMenu:
    def test_the_row_runs_here_and_every_action_does(self, page):
        _r, body = _get(page, "/v2/device/r5")
        menu = body[body.index('role="menu"'):body.index('class="tabs"')]
        assert 'hx-get="/v2/device/r5/retire?back=overview&amp;list=Lab"' in menu
        assert "manage_device" not in menu and "/manage/" not in menu
        assert "Every action runs here." in menu
        _r, body = _get(page, "/v2/device/r5?op=retire")
        assert "Retire r5 from management" in body[body.index('id="tab-body"'):]


class TestTheCard:
    def test_steps_generated_survives_and_a_preview_writes_nothing(self, exported, monkeypatch,
                                                                    tmp_path):
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14"), ("r5", "192.0.2.15")])
        before = _state(exported)
        r, card = _card(exported)
        assert r.status_code == 200 and "default-src" in r.headers.get(
            "Content-Security-Policy", "")
        steps = re.findall(r"<li>(.*?)</li>", _part(card, "What retire changes, in order"))
        assert steps[-1].startswith("delete the CSV row"), "the row goes last"
        assert any("one commit: remove host_vars/r5.yml, golden/r5.cfg" in s for s in steps)
        gen = _part(card, "Generated, so dropped")
        assert "Prometheus&#39;s scrape targets" in gen and "drops it at its next run" in gen
        assert "Its Grafana heartbeat rule" in gen
        survives = _part(card, "What survives")
        assert "The NetBox device 9" in survives and "delete it in NetBox" in survives
        assert "remove r5 where Oxidized is configured" in survives
        assert "removed in Grafana" in survives
        assert "Its credential survives ONLY in the break-glass record" in survives
        unchanged = _part(card, "Not changed")
        assert "running configuration is not changed" in unchanged
        assert "NetBox device 9 is KEPT" not in unchanged, "said once, under What survives"
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["reason"] == REASON and vals["hash"]
        assert _state(exported) == before, "a preview writes nothing"

    def test_without_an_export_it_is_refused_and_points_at_credentials(self, page):
        _r, card = _card(page)
        assert "op-confirm" not in card
        assert "Refused until the break-glass record holds r5" in card
        assert 'href="/v2/credentials?list=Lab&amp;open=export"' in card

    def test_an_empty_reason_offers_no_confirm(self, exported):
        _r, card = _card(exported, reason="")
        assert "op-confirm" not in card and "a reason is given" in card


class TestTheConfirm:
    def test_it_retires_as_the_person_and_the_address_shows_the_record(self, exported,
                                                                       monkeypatch, tmp_path):
        d = _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
        _r, card = _card(exported)
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "r5 is retired" in out and "op-ok" in out, out[:600]
        dropped = _part(out, "Dropped")
        assert "Prometheus&#39;s targets were regenerated without r5 (read back at" in dropped
        assert "heartbeat rule" in dropped
        assert "where Oxidized is configured" in _part(out, "Still to remove")
        assert "this address shows its retired record" in out and "Back to Devices" in out
        assert json.loads((d / "nmas-snmp-all.json").read_text())[0]["labels"]["device"] == "r4"
        msg = exported["R"].git(exported["repo"], "log", "-1", "--format=%B")[1]
        assert "Retired-Device: r5" in msg and f"Actor: {TEST_PERSON}" in msg
        r, page_html = _get(exported, "/v2/device/r5")
        assert r.status_code == 200 and "Its record" in page_html
        assert f"Retired by {TEST_PERSON}" in page_html and REASON in page_html
        head = exported["R"].git(exported["repo"], "rev-parse", "HEAD")[1]
        assert head[:12] in page_html
        assert "/v2/history?device=r5" in page_html.replace("&amp;", "&")

    def test_a_plan_that_moved_does_nothing(self, exported):
        _r, card = _card(exported)
        vals = dict(_vals(card), hash="0" * 16)
        before = _state(exported)
        out = exported["client"].post("/v2/device/r5/retire/confirm",
                                      data=vals).get_data(as_text=True)
        assert "op-ok" not in out and "the plan changed since you confirmed it" in out
        assert _state(exported) == before

    @pytest.mark.parametrize("drop, said", [("list", "names no list"),
                                            ("hash", "carried no plan")])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, exported, drop, said):
        _r, card = _card(exported)
        vals = dict(_vals(card))
        vals.pop(drop)
        before = _state(exported)
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=vals)
        assert r.status_code == 400 and said in r.get_data(as_text=True)
        assert _state(exported) == before


def test_a_free_device_draws_the_card_again(exported):
    _r, out = _get(exported, "/v2/device/r5/when-free?op=retire&back=history")
    assert "Retire r5 from management" in out and 'id="device-op"' in out


class TestTheReadBack:
    def test_targets_after_says_dropped_still_or_not_managed(self, monkeypatch, tmp_path):
        from modules import prometheus_targets as PT
        from modules.nsot import retire as RT
        monkeypatch.setattr(PT, "target_dir", lambda: "")
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "not_managed"
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "dropped"
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14"), ("r5", "192.0.2.15")])
        got = RT.targets_after("r5", "192.0.2.15")
        assert got["state"] == "still" and "nmas-snmp-all.json" in got["statement"]
        monkeypatch.setattr(PT, "generate", lambda: (_ for _ in ()).throw(OSError("disk")))
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "failed"

    def test_retired_record_matches_the_trailer_exactly(self, world):  # noqa: F811
        from modules.nsot import retire as RT
        R, repo = world["R"], world["repo"]
        with open(os.path.join(repo, "note.txt"), "w") as fh:
            fh.write("x\n")
        R.git(repo, "add", "note.txt")
        R.git(repo, "commit", "-q", "-m", "retire: r55\n\nRetired-Device: r55\nActor: a@b\n"
                                          "Reason: gone")
        assert RT.retired_record(repo, "r5") is None, "r55's retirement is not r5's"
        rec = RT.retired_record(repo, "r55")
        assert rec["reason"] == "gone" and rec["actor"] == "a@b"


#: The card, and htmx at rest (a swapped-in control binds while it settles).
CARD = "document.querySelector('#device-op')"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "nmas-oxidized-cred")
#: router.db before: r4's and r5's rows, and a device no list manages.
ROUTER_DB = ["192.0.2.14:ios:admin:Pw1", "192.0.2.15:ios:admin:Pw2", "192.0.2.99:ios:admin:Pw3"]


@pytest.fixture
def oxidized(monkeypatch, tmp_path):
    """Oxidized configured, its router.db a temp file, and THE helper script run on it: only
    `sudo` and the install check are stood in for (C398)."""
    import subprocess
    import sys
    from modules.nsot import credential_rotation as CR

    db = tmp_path / "router.db"
    db.write_text("\n".join(ROUTER_DB) + "\n", encoding="utf-8")
    calls = []

    def run(flags, stdin, router_db=""):
        calls.append(list(flags))
        p = subprocess.run([sys.executable, HELPER, "--file", str(db), *flags],
                           input=stdin, capture_output=True, text=True)
        return json.loads(p.stdout or "{}")
    monkeypatch.setattr(CR, "oxidized_managed", lambda: True)
    monkeypatch.setattr(CR, "_run_helper", run)
    rows = lambda: [l for l in db.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E731
    return {"db": db, "rows": rows, "calls": calls}


class TestTheOxidizedRow:
    """C398 (the operator, 2026-10-04): retire removes the device's router.db row through the
    root helper's REMOVE mode, read back, before the CSV row; a retired record still holding one
    offers "Finish this retirement"."""

    def test_the_plan_has_the_step_before_the_row_and_says_nothing_survives(self, exported,
                                                                          oxidized):
        from modules.nsot import retire as RT
        p = RT.plan("Lab", "r5", REASON)
        keys = [s["key"] for s in p["steps"]]
        assert keys.index("oxidized") == keys.index("row") - 1, keys
        step = next(s for s in p["steps"] if s["key"] == "oxidized")
        assert not step["done"] and "192.0.2.15" in step["what"]
        assert not [w for w in p["survives"] if "Oxidized" in w["what"]]

    def test_the_confirm_removes_exactly_that_row_and_reads_it_back(self, exported, oxidized):
        _r, card = _card(exported)
        out = exported["client"].post("/v2/device/r5/retire/confirm",
                                      data=_vals(card)).get_data(as_text=True)
        assert "r5 is retired" in out, out[:400]
        assert oxidized["rows"]() == [ROUTER_DB[0], ROUTER_DB[2]], "only r5's row left"
        assert "Removed its row from Oxidized's router.db, read back" in html_mod.unescape(out)
        assert "Oxidized no longer polls it" in out
        assert ["--ip", "192.0.2.15", "--remove"] in oxidized["calls"]
        assert not any("--ip" in c and "--remove" not in c for c in oxidized["calls"]), \
            "no credential act"

    def test_a_refused_removal_stops_before_the_csv_row(self, exported, oxidized, monkeypatch):
        from modules.nsot import credential_rotation as CR
        real = CR._run_helper
        monkeypatch.setattr(CR, "_run_helper", lambda flags, stdin, router_db="": (
            {"ok": False, "error": "the helper refused"} if "--remove" in flags
            else real(flags, stdin, router_db)))
        _r, card = _card(exported)
        out = exported["client"].post("/v2/device/r5/retire/confirm",
                                      data=_vals(card)).get_data(as_text=True)
        assert "Stopped at oxidized" in out and "the helper refused" in out
        from modules.device import load_saved_devices
        assert any(d["hostname"] == "r5" for d in load_saved_devices(exported["csv"])), \
            "the CSV row stays: a retirement run again finishes it"

    def test_a_removal_said_done_and_not_read_back_gone_stops(self, exported, oxidized,
                                                              monkeypatch):
        """The read-back decides, never the helper's word: a removal that answers done while
        the row stays stops the retirement before the CSV row, saying what holds."""
        from modules.nsot import credential_rotation as CR
        real = CR._run_helper
        monkeypatch.setattr(CR, "_run_helper", lambda flags, stdin, router_db="": (
            {"ok": True, "removed": 1} if "--remove" in flags
            else real(flags, stdin, router_db)))
        _r, card = _card(exported)
        out = html_mod.unescape(exported["client"].post(
            "/v2/device/r5/retire/confirm", data=_vals(card)).get_data(as_text=True))
        assert "router.db still holds 192.0.2.15" in out and "r5 is retired" not in out
        assert len(oxidized["rows"]()) == 3

    def test_a_retired_record_holding_its_row_offers_to_finish(self, exported, oxidized,
                                                               monkeypatch):
        from modules.nsot import credential_rotation as CR
        # Retired where Oxidized was not the tool's (as the host's r5 was): its row stays.
        monkeypatch.setattr(CR, "oxidized_managed", lambda: False)
        _r, card = _card(exported)
        assert "r5 is retired" in exported["client"].post(
            "/v2/device/r5/retire/confirm", data=_vals(card)).get_data(as_text=True)
        monkeypatch.setattr(CR, "oxidized_managed", lambda: True)
        _r, page = _get(exported, "/v2/device/r5")
        assert "Still to remove:" in page and "Finish this retirement" in page
        assert "192.0.2.15" in page
        r = exported["client"].post("/v2/device/r5/retire/finish", data={"list": "Lab"})
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "Finished:" in out and "read back" in out
        assert oxidized["rows"]() == [ROUTER_DB[0], ROUTER_DB[2]]
        _r, page = _get(exported, "/v2/device/r5")
        assert "Finish this retirement" not in page, "nothing left to finish"

    def test_finishing_says_the_helper_pruned_its_older_backups(self, exported, oxidized,
                                                                monkeypatch):
        """C430 (the operator, 2026-10-04: r5's Finish was the helper's first write since C415,
        and its result could not say whether it pruned): the result carries the pruning."""
        from modules.nsot import credential_rotation as CR
        monkeypatch.setattr(CR, "oxidized_managed", lambda: False)
        _r, card = _card(exported)
        exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        monkeypatch.setattr(CR, "oxidized_managed", lambda: True)
        for stamp in ("20260901-000000", "20260902-000000", "20260903-000000",
                      "20260904-000000"):
            (oxidized["db"].parent / f"router.db.nmas-bak-{stamp}").write_text("x\n")
        out = html_mod.unescape(exported["client"].post(
            "/v2/device/r5/retire/finish", data={"list": "Lab"}).get_data(as_text=True))
        assert ("The helper kept its backup of router.db from before this write and removed 2 "
                "older backups.") in out, out[:600]
        kept = sorted(p.name for p in oxidized["db"].parent.iterdir()
                      if p.name.startswith("router.db.nmas-bak-"))
        assert len(kept) == 3

    def _orphans(self, monkeypatch):
        from modules import host_helpers
        from modules.nsot import credential_rotation as CR
        monkeypatch.setattr(CR, "helper_status", lambda: {"ok": True, "state": "ok"})
        return host_helpers.oxidized_orphans_row()

    def test_job_health_names_a_retired_device_router_db_still_holds(self, exported, oxidized,
                                                                     monkeypatch):
        """C398's last part: the helper's address list against the managed devices, through
        the real helper and the real retire commit; then Finish clears it."""
        from modules import attention
        from modules.nsot import credential_rotation as CR
        monkeypatch.setattr(CR, "oxidized_managed", lambda: False)
        _r, card = _card(exported)
        exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        monkeypatch.setattr(CR, "oxidized_managed", lambda: True)

        got = self._orphans(monkeypatch)
        assert got["state"] == "orphaned" and got["devices"] == ["r5"]
        assert "r5 (192.0.2.15, retired from Lab)" in got["headline"]
        assert "1 of devices it retired, 1 it never managed (not the tool's to remove)" \
            in got["detail"]
        assert ["--addresses"] in oxidized["calls"]
        from modules import host_helpers
        assert got in host_helpers.helper_rows(), "job health's helper rows carry it"
        (row,) = attention.job_health_source(health=lambda: {"jobs": [got]})["rows"]
        assert row["level"] == "warning" and row["devices"] == ["r5"]
        assert row["action"]["label"].startswith("Open each retired device and press Finish")

        exported["client"].post("/v2/device/r5/retire/finish", data={"list": "Lab"})
        after = self._orphans(monkeypatch)
        assert after["state"] == "ok" and "0 of devices it retired" in after["detail"]

    def test_an_address_the_tool_never_managed_is_no_row(self, exported, oxidized, monkeypatch):
        got = self._orphans(monkeypatch)
        assert got["state"] == "ok"
        assert "1 it never managed (not the tool's to remove)" in got["detail"]

    def test_no_oxidized_is_no_row_and_an_unreadable_list_is_said(self, exported, oxidized,
                                                                  monkeypatch):
        from modules import host_helpers
        from modules.nsot import credential_rotation as CR
        monkeypatch.setattr(CR, "oxidized_managed", lambda: False)
        assert host_helpers.oxidized_orphans_row() == {}
        monkeypatch.setattr(CR, "oxidized_managed", lambda: True)
        got = host_helpers.oxidized_orphans_row(addresses={"ok": False, "error": "sudo refused"})
        assert got["state"] == "unknown" and "sudo refused" in got["detail"]

    def test_a_helper_that_is_not_this_releases_is_its_own_row_not_this_one(self, exported,
                                                                           oxidized,
                                                                           monkeypatch):
        from modules import host_helpers
        from modules.nsot import credential_rotation as CR
        monkeypatch.setattr(CR, "helper_status", lambda: {"ok": False, "state": "drifted"})
        assert host_helpers.oxidized_orphans_row() == {}

    def test_finishing_needs_its_list_and_a_retire_commit(self, exported, oxidized):
        before = oxidized["rows"]()
        r = exported["client"].post("/v2/device/r5/retire/finish", data={})
        assert r.status_code == 400 and "names no list" in r.get_data(as_text=True)
        r = exported["client"].post("/v2/device/r5/retire/finish", data={"list": "Lab"})
        assert r.status_code == 404 and "no retire commit" in r.get_data(as_text=True)
        assert oxidized["rows"]() == before


def test_a_real_browser_retires_from_the_menu_then_the_address_shows_the_record(exported):
    """The path a person takes (C385: every opener clicked where it sits): Actions, Retire…,
    the reason typed (the card plans again and offers the confirm), the confirm, the result in
    place (the page never reloaded), then the device's address, which shows its record."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/device/r5"))
            b.wait_for("return !!window.Alpine && window.NMAS && "
                       "NMAS.live().state === 'connected' && " + SETTLED, 15)
            b.js("window.__notReloaded = 1; return 1")
            b.click('.page-actions button[aria-haspopup="menu"]')
            b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                       "return m && m.offsetParent !== null", 10)
            b.click('.page-actions a[data-op="retire"]')
            b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=reason]') "
                       f"&& {SETTLED}", 15)
            b.js("var i = document.querySelector('#device-op input[name=reason]');"
                 f"i.value = {json.dumps(REASON)};"
                 "i.dispatchEvent(new Event('change', {bubbles: true})); return 1")
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            b.click("#device-op .op-confirm")
            b.wait_for(f"return {CARD} && /r5 is retired/.test({CARD}.textContent) && {SETTLED}",
                       20)
            assert b.js("return window.__notReloaded") == 1
            b.go(srv.url("/v2/device/r5"))
            b.wait_for("return /Its record/.test(document.body.textContent)", 15)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
