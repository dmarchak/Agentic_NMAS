"""The device page's Rotate on v2 (7.3; the device-actions mockup signed off 2026-10-02, its
"Rotate, a check failing" artboard).

On test_persist_screen's lab (r2 in the Lab inventory) with test_rotate_screen's fakes of
`credential_rotation`'s device-facing calls (`plan`, `rotate`, `persist`), through the real
routes, job registry and templates:

- the Actions menu draws Rotate as its card's request; without script the page draws the
  starting card;
- the card asks for its own preview (a POST on load: the plan reads the device's account line
  live), and draws what will not happen, what is sent with the password masked and the steps
  after it, the operands, the checks naming the verified person, and the confirm bound to the
  plan's fingerprint, busy on itself;
- a failing preflight check refuses with no confirm; a held device fails its check BY NAME,
  says it reads again when that operation finishes, and listens for the hold's release
  (`device_holds`); `when-free` answers 204 while held and the card again once free;
- the confirm starts the rotation as a job through the same confirm as `/rotate/apply`, the
  device held across rotate and persist; the card waits for `rotation`, then draws the result
  with its one next step (export the break-glass record); a persist that stopped is partial,
  named; a plan whose fingerprint moved is refused with nothing sent and no job;
- a write naming no list, an unknown list, or no plan is refused;
- releasing a hold announces `device_holds` from the app's process, and a process with no
  emitter releases quietly.
"""

import json
import re

import pytest

from modules.nsot import capture_job
from modules.nsot import credential_rotation as cr
from modules.nsot import rotate_op as RO
from tests.test_persist_screen import lab  # noqa: F401 (the inventory)
from tests.test_rotate_screen import NEW, _plan


@pytest.fixture
def rot(lab, monkeypatch):  # noqa: F811
    state = {"plan": _plan(), "rotate_state": cr.ROTATED_PENDING_PERSIST,
             "persist_state": cr.ROTATED_PERSISTED, "calls": []}
    monkeypatch.setattr(RO, "plan", lambda l, h: dict(state["plan"], list_name=l))

    def rotate(list_name, hostname, **kw):
        from modules.nsot import device_ops
        state["calls"].append(("rotate", device_ops.holder(list_name, hostname) is not None,
                               kw.get("confirmed_fingerprint"), kw.get("via")))
        return {"device": hostname, "state": state["rotate_state"], "steps": [
            {"name": "push", "ok": True},
            {"name": cr.VERIFY, "ok": True, "detail": "fresh login with the new credential"}],
            "new_hash": "9 $9$s$h", "mgmt_ip": "192.0.2.12", "username": "admin",
            "commit": {"ok": True, "commit": "abc1234def56"}}

    def persist(result, **kw):
        from modules.nsot import device_ops
        state["calls"].append(("persist", device_ops.holder(kw["list_name"],
                                                            kw["hostname"]) is not None))
        ok = state["persist_state"] == cr.ROTATED_PERSISTED
        return {**result, "state": state["persist_state"], "persistence": [
            {"name": "device_startup_config", "ok": ok,
             "error": "" if ok else "the startup config does not carry it"}]}

    monkeypatch.setattr(cr, "rotate", rotate)
    monkeypatch.setattr(cr, "persist", persist)
    monkeypatch.setattr(cr, "platform_of", lambda l, h: "cisco_iosxe")
    monkeypatch.setattr(RO, "_inventory_password", lambda l, h: NEW)
    return dict(lab, rot=state)


def _preview(rot, back="history"):
    c = rot["client"]
    start = c.get(f"/v2/device/r2/rotate?back={back}").get_data(as_text=True)
    assert 'hx-trigger="load"' in start and 'hx-post="/v2/device/r2/rotate/preview"' in start
    assert "Reading r2's account line now" in start
    r = c.post("/v2/device/r2/rotate/preview", data={"list": "Lab", "back": back})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_data(as_text=True)


def _confirm(rot, html, **over):
    vals = json.loads(re.search(r"hx-vals='([^']*)'", html[html.index("op-confirm"):]).group(1))
    return rot["client"].post("/v2/device/r2/rotate/confirm", data={**vals, **over})


def _finish(rot, rotating_html):
    job = re.search(r"/rotate/job/([0-9a-f]+)", rotating_html).group(1)
    assert capture_job.wait(job, 30)
    return rot["client"].get(f"/v2/device/r2/rotate/job/{job}?back=history").get_data(as_text=True)


class TestTheMenu:
    def test_rotate_runs_here(self, rot):
        html = rot["client"].get("/v2/device/r2").get_data(as_text=True)
        menu = html[html.index('role="menu"'):html.index('class="tabs"')]
        row = menu[menu.index('data-op="rotate"') - 200:menu.index('data-op="rotate"') + 1500]
        assert 'hx-get="/v2/device/r2/rotate?back=overview"' in row
        assert "Capture, Rotate and Persist run here" in menu
        page = rot["client"].get("/v2/device/r2?op=rotate").get_data(as_text=True)
        assert 'hx-post="/v2/device/r2/rotate/preview"' in page[page.index('id="tab-body"'):]


class TestThePreview:
    def test_it_draws_every_part(self, rot):
        html = _preview(rot)
        assert "Rotate r2's credential" in html
        not_doing = html[html.index("What will not happen"):html.index("What is sent")]
        assert "The template is not changed" in not_doing and "DEAD credential" in not_doing
        sent = html[html.index("What is sent"):html.index("Operands")]
        assert "&lt;generated&gt;" in sent and "The new password is never shown" in sent
        assert "verify: a FRESH login" in sent and "persist: save on the device" in sent
        ops = html[html.index("Operands"):html.index("Checks")]
        assert "admin (privilege 15)" in ops and "32 characters" in ops and "fp-abc123" in ops
        checks = html[html.index("Checks"):html.index("op-ft")]
        assert "You are a verified person: test-person@example.invalid" in checks
        assert "badge-danger" not in checks
        foot = html[html.index("op-ft"):]
        assert "accepts ONLY the new password" in foot and "Bound to plan fp-abc123" in foot
        assert '"fingerprint": "fp-abc123"' in foot and '"list": "Lab"' in foot
        assert 'class="op-busy">Reading r2 again and starting the rotation' in foot
        assert "when-free" not in html, "a card not refused for a hold listens for nothing"
        assert rot["rot"]["calls"] == [], "a preview rotates nothing"

    def test_a_failing_preflight_refuses_with_no_confirm(self, rot):
        rot["rot"]["plan"] = _plan(ok=False)
        html = _preview(rot)
        assert "badge-danger" in html and "TCP connection to device failed" in html
        assert "op-confirm" not in html and "Not available:" in html

    def test_a_held_device_fails_by_name_and_reads_again_when_freed(self, rot):
        from modules.nsot import device_ops
        device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
        try:
            html = _preview(rot)
            assert "alex@example.invalid" in html and "op-confirm" not in html
            assert "This preview reads again when that operation finishes" in html
            assert 'hx-get="/v2/device/r2/when-free?op=rotate&amp;back=history"' in html
            assert 'hx-trigger="nmas:device_holds from:body"' in html
            still = rot["client"].get("/v2/device/r2/when-free?op=rotate&back=history")
            assert still.status_code == 204 and still.get_data() == b""
        finally:
            device_ops.release("Lab", "r2")
        free = rot["client"].get("/v2/device/r2/when-free?op=rotate&back=history")
        assert free.status_code == 200
        assert 'hx-post="/v2/device/r2/rotate/preview"' in free.get_data(as_text=True)


class TestTheConfirm:
    def test_it_runs_as_a_job_holding_the_device_and_draws_the_result(self, rot):
        r = _confirm(rot, _preview(rot))
        assert r.status_code == 200
        waiting = r.get_data(as_text=True)
        assert "Rotating r2's credential" in waiting
        assert 'hx-trigger="nmas:rotation from:body"' in waiting
        out = _finish(rot, waiting)
        assert rot["rot"]["calls"] == [("rotate", True, "fp-abc123", "device page"),
                                       ("persist", True)]
        assert "op-card op-ok" in out and "rotated and persisted" in out
        assert "fresh login with the new credential" in out
        assert "Export the break-glass record again" in out
        assert 'data-op="breakglass-export"' in out
        assert "abc1234def56"[:12] in out[out.index("Recorded"):]
        assert 'hx-get="/v2/device/r2/history"' in out, "Close puts back the tab it replaced"

    def test_a_persist_that_stopped_is_partial_and_named(self, rot):
        rot["rot"]["persist_state"] = cr.ROTATED_UNVERIFIED
        out = _finish(rot, _confirm(rot, _preview(rot)).get_data(as_text=True))
        assert "op-card op-danger" in out
        assert "Persistence stopped at device_startup_config" in out
        assert "nmas-persist-credential r2 --list Lab" in out

    def test_a_moved_fingerprint_is_refused_with_nothing_sent(self, rot):
        html = _preview(rot)
        rot["rot"]["plan"] = _plan(fingerprint="fp-moved")
        r = _confirm(rot, html)
        out = r.get_data(as_text=True)
        assert r.status_code == 409 and "op-card op-warn" in out
        assert "fp-abc123 -&gt; fp-moved" in out and "Preview it again" in out
        assert rot["rot"]["calls"] == []

    @pytest.mark.parametrize("body,words", [
        ({"fingerprint": "x"}, "names no list"),
        ({"list": "Elsewhere", "fingerprint": "x"}, "names no list"),
        ({"list": "Lab"}, "no plan to be bound to"),
    ])
    def test_a_write_naming_no_list_or_no_plan_is_refused(self, rot, body, words):
        r = rot["client"].post("/v2/device/r2/rotate/confirm", data=body)
        assert r.status_code == 400 and words in r.get_data(as_text=True)
        assert rot["rot"]["calls"] == []

    def test_an_unknown_job_says_so(self, rot):
        out = rot["client"].get("/v2/device/r2/rotate/job/0123abcd").get_data(as_text=True)
        assert "This server has no record of that rotation" in out


class TestTheHoldsRelease:
    def test_a_release_is_announced_from_the_apps_process(self, monkeypatch):
        from modules import invalidation
        from modules.nsot import device_ops
        sent = []
        monkeypatch.setattr(invalidation, "_emitter", lambda ev, msg: sent.append(msg))
        device_ops.acquire("Lab", "r7", "deploy", "a@example.invalid")
        device_ops.acquire("Lab", "r7", "deploy", "a@example.invalid")   # re-entrant
        device_ops.release("Lab", "r7")
        assert sent == [], "still held by the outer hold: nothing to say yet"
        device_ops.release("Lab", "r7")
        assert [m["keys"] for m in sent] == [["device_holds"]]
        assert sent[0]["by"] == "device-ops"

    def test_a_process_with_no_emitter_releases_quietly(self, monkeypatch):
        from modules import invalidation
        from modules.nsot import device_ops
        monkeypatch.setattr(invalidation, "_emitter", None)
        device_ops.acquire("Lab", "r7", "deploy", "a@example.invalid")
        device_ops.release("Lab", "r7")
        assert device_ops.holder("Lab", "r7") is None


# ------------------------------------------------ clicking what ships, where Firefox runs

@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


@pytest.fixture
def served(rot, live_browser):
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, "rot": rot}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


CARD = "document.getElementById('device-op')"
#: htmx binds a swapped-in control while it settles: click only once nothing settles
#: (tests/test_device_capture_v2.py measured it).
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def _open(self, served):
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/device/r2"))
        b.wait_for("return !!window.Alpine && window.NMAS && "
                   "NMAS.live().state === 'connected' && " + SETTLED, 15)
        b.js("window.__notReloaded = 1; return 1")
        b.click('button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('.page-actions [role=menu]'); "
                   "return m && m.offsetParent", 5)
        b.click('a[role="menuitem"][data-op="rotate"]')
        return b

    def test_the_rotation_runs_and_its_result_arrives_by_announcement(self, served):
        b = self._open(served)
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        b.click("#device-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}", 20)
        assert "rotated and persisted" in b.js(f"return {CARD}.textContent")
        assert b.js("return window.__notReloaded") == 1
        assert [c[0] for c in served["rot"]["rot"]["calls"]] == ["rotate", "persist"]

    def test_a_held_card_reads_again_when_the_hold_is_released(self, served):
        """The signed mockup's promise, end to end: refused while a deploy holds r2, the card
        reads again on its own when the hold ends, and offers the confirm."""
        from modules.nsot import device_ops
        device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
        try:
            b = self._open(served)
            b.wait_for(f"return {CARD} && {CARD}.textContent.indexOf('alex@example.invalid')"
                       f" >= 0 && {SETTLED}", 15)
            assert not b.js(f"return !!{CARD}.querySelector('.op-confirm')")
        finally:
            device_ops.release("Lab", "r2")
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        assert b.js("return window.__notReloaded") == 1
