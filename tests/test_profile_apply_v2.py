"""P.9 step (d2): Monitoring > Coverage's batch Apply in v2: the preview, the
rollout order, the confirm and the result, drawn server-side under the strict
policy (today's renderer emits inline handlers, which the policy refuses).

On test_profile_apply's lab with the proposal committed: r2's REAL config and
intent (it holds the profile's lines) and r6 in its real shape (r2's with
every `snmp` line removed, so the profile supplies its SNMP). The plan is
`routes.deploy.plan_devices`, the one `/deploy/plan` uses with scope
`profile`; the apply is `apply_batch`, the one `/deploy/apply` uses, run as a
job in the ROLLOUT ORDER the preview shows and sets.
"""

import html as html_mod
import json
import os
import re
import threading
import time

import pytest

from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def idle(lab, monkeypatch):
    """r2 as the lab holds it: every line the profile supplies already on it,
    so it has NOTHING to send (C295)."""
    _commit_proposal()
    # The lab's list is not in the registry, and a read naming an unknown
    # list is refused (C51): the test names it as known.
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return lab


@pytest.fixture
def ready(idle):
    """Two devices that each receive a program: r6 (its SNMP and LLDP) and r2,
    whose golden is a minimal edit of its REAL one with `lldp run` removed, so
    the profile supplies it that one line. Before C295 these tests ran r2 with
    nothing to send, which is the very batch the operator found useless."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    text = idle["captured"]
    assert "\nlldp run\n" in text
    edited = text.replace("\nlldp run\n", "\n")
    out = save_golden("Lab", [GoldenItem("r2", edited, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    # Its intent from the same edit (as r6's lab shape is built), so the line is
    # the PROFILE's to supply: a line r2's own intent held would be its own.
    hostvars.write_committed(idle["repo"], get_parser("cisco_iosxe").parse(edited))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    return idle


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _page(lab, devices=("r6", "r2"), extra=""):
    q = "&".join(f"device={d}" for d in devices)
    return _get(lab, f"/v2/monitoring/apply?list=Lab&{q}{extra}")


def _body(page_html):
    m = re.search(r"data-body='([^']*)'", page_html)
    assert m, "the confirm carries its body"
    return json.loads(html_mod.unescape(m.group(1)))


def _order(page_html):
    return re.findall(r'<li class="rollout-item">\s*<span class="grow"><a href="#apply-([^"]+)"', page_html)


class TestNothingToSend:
    """C295 (the operator, 2026-10-01): a device that already holds every line
    the profile supplies reads "nothing to send", leaves the rollout order and
    the confirm, and a batch where every device has nothing has no confirm."""

    def test_a_device_with_nothing_to_send_leaves_the_order_and_the_confirm(self, idle):
        _r, page = _page(idle)                         # r6 receives; r2, as the lab holds it, does not
        assert _order(page) == ["r6"]
        body = _body(page)
        assert body["order"] == ["r6"] and "r2" not in body["confirmations"]
        nothing = re.search(r'<ul class="apply-not" id="apply-nothing">(.*?)</ul>', page, re.S)
        assert nothing and "<strong>r2</strong>" in nothing.group(1)
        assert "nothing to send" in nothing.group(1)
        assert 'aria-label="Move r2' not in page and 'aria-label="Leave r2 out' not in page
        assert "Apply to 1 device(s) in this order" in page

    def test_every_device_with_nothing_to_send_offers_no_confirm(self, idle):
        _r, page = _page(idle, devices=("r2",))
        assert 'id="apply-confirm"' not in page and "data-body=''" in page
        assert "Nothing to apply: every device chosen already has every line the profile supplies." in page
        assert "Rollout order" not in page


class TestThePreview:
    def test_the_programs_and_hashes_are_the_scoped_plans(self, ready):
        r, page = _page(ready)
        assert r.status_code == 200
        assert _order(page) == ["r6", "r2"]
        plan = ready["client"].post("/deploy/plan", json={
            "devices": ["r6", "r2"], "scope": "profile", "list_name": "Lab"}).get_json()
        want = {d["device"]: d for d in plan["devices"]}
        body = _body(page)
        assert body["list"] == "Lab" and body["order"] == ["r6", "r2"]
        for name in ("r6", "r2"):
            assert body["confirmations"][name] == want[name]["capture_hash"]
            assert body["command_hashes"][name] == want[name]["command_hash"]
        # r6's program is the profile's lines, drawn MASKED on the way out.
        r6 = want["r6"]["commands"]
        assert r6 and any(c.startswith("snmp-server") for c in r6)
        assert "&lt;redacted:" in page and "1. r6" in page

    def test_every_gate_and_operand_has_words(self, ready):
        """C296 (the operator, 2026-10-01: ten empty bullets per device). Every
        gate drawn names its check and says its state in words, and every
        operand names itself and carries a value, on every device's preview."""
        _r, page = _page(ready)
        lists = re.findall(r'<ul class="apply-gates">(.*?)</ul>', page, re.S)
        assert len(lists) == 2
        states = "passes|FAILS|does not apply|checked again at apply|not reached"
        for block in lists:
            items = re.findall(r"<li[^>]*>(.*?)</li>", block, re.S)
            assert len(items) >= 8
            for li in items:
                m = re.match(r"<strong>([^<]+)</strong> (" + states + r")\b", li.strip())
                assert m and m.group(1).strip(), li
        for block in re.findall(r'<dl class="apply-operands">(.*?)</dl>', page, re.S):
            pairs = re.findall(r"<dt>(.*?)</dt><dd><code>(.*?)</code></dd>", block, re.S)
            assert len(pairs) >= 6
            assert all(n.strip() and v.strip() for n, v in pairs), pairs

    def test_no_stored_secret_value_leaves_in_the_page(self, ready):
        from tests.test_profile_apply import _secret_values
        _r, page = _page(ready)
        for v in _secret_values(ready):
            assert v not in page

    def test_the_rollout_order_is_set_on_the_page(self, ready):
        _r, page = _page(ready, extra="&move=down:r6")
        assert _order(page) == ["r2", "r6"] and _body(page)["order"] == ["r2", "r6"]
        _r, page = _page(ready, extra="&move=up:r2")
        assert _order(page) == ["r2", "r6"]
        _r, page = _page(ready, extra="&drop=r2")
        assert _order(page) == ["r6"] and _body(page)["order"] == ["r6"]

    def test_the_rollout_order_says_why_it_matters(self, ready):
        _r, page = _page(ready)
        assert "One device at a time, in this order." in page
        assert "the first devices are the ones a bad change would reach" in page

    def test_no_device_chosen_says_where_to_choose(self, ready):
        _r, page = _get(ready, "/v2/monitoring/apply?list=Lab")
        assert "No device was chosen" in page and "data-body" not in page

    def test_the_fragment_replans_under_the_strict_policy(self, ready):
        from modules import csp
        for url in ("/v2/monitoring/apply?list=Lab&device=r6",
                    "/v2/monitoring/apply/preview?list=Lab&device=r6"):
            r, html = _get(ready, url)
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY, url
            assert not re.search(r"\sstyle=|\son[a-z]+=|<script(?![^>]*\ssrc=)", html), url
        r, frag = _get(ready, "/v2/monitoring/apply/preview?list=Lab&device=r6")
        assert frag.lstrip().startswith('<section class="card apply" id="apply-preview">')
        assert 'hx-trigger="change"' in frag

    def test_a_device_that_cannot_receive_it_says_why_and_is_not_confirmed(self, ready, monkeypatch):
        from modules.nsot import device_ops
        monkeypatch.setattr(device_ops, "busy_text",
                            lambda ln, host: "held by a deploy since 01:00" if host == "r6" else "")
        _r, page = _page(ready)
        assert "held by a deploy since 01:00" in page
        assert _body(page)["order"] == ["r2"]


def _confirm(lab, body):
    return lab["client"].post("/v2/monitoring/apply/confirm", json=body)


class TestTheConfirm:
    def _spy(self, monkeypatch, gate=None):
        import routes.deploy as rd
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            name = entry["artifact"].device
            reached.append((name, kw.get("scope", "")))
            if gate is not None and name == "r2":
                gate.wait(10)
            return {"device": name, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        return reached

    def test_the_batch_runs_as_a_job_in_the_rollout_order(self, ready, monkeypatch):
        from modules.nsot import capture_job
        reached = self._spy(monkeypatch)
        # The order the PAGE set, and not alphabetical (a sorted run would pass
        # an alphabetical one: the control that sorts it found that).
        _r, page = _page(ready, devices=("r2", "r6"), extra="&move=down:r2")
        assert _body(page)["order"] == ["r6", "r2"]
        r = _confirm(ready, _body(page))
        assert r.status_code == 202, r.get_json()
        out = r.get_json()
        assert capture_job.wait(out["job"], 20)
        assert reached == [("r6", "profile"), ("r2", "profile")]
        rr, frag = _get(ready, out["url"])
        assert rr.status_code == 200
        assert "2 of 2 device(s) deployed" in frag and "every device in the batch appears here" in frag
        assert "hx-trigger" not in frag, "a finished batch listens for nothing"

    def test_the_golden_commit_names_the_person_who_confirmed(self, ready, monkeypatch):
        """The review's finding, 2026-10-01: the job thread has no request, so
        `request_actor()` there reads `unauthenticated`, and the batch's golden
        commit named nobody while the receipts named the person. The actor
        the confirm verified is carried into the commit."""
        import routes.deploy as rd
        from modules import identity
        from modules.nsot import capture_job
        self._spy(monkeypatch)
        committed = []
        monkeypatch.setattr(rd, "_commit_batch_golden",
                            lambda ln, report, **kw: committed.append(kw.get("actor")) or {})
        seen = []
        real = identity.request_actor
        monkeypatch.setattr(identity, "request_actor", lambda: seen.append(real()) or seen[-1])
        _r, page = _page(ready, devices=("r6",))
        out = _confirm(ready, _body(page)).get_json()
        assert capture_job.wait(out["job"], 20)
        person = seen[0]
        assert person and person != "unauthenticated", seen
        assert committed == [person], (committed, person)

    def test_while_it_runs_each_device_reads_where_the_batch_is(self, ready, monkeypatch):
        from modules.nsot import capture_job
        gate = threading.Event()
        self._spy(monkeypatch, gate)
        _r, page = _page(ready)                      # r6 first, then r2
        out = _confirm(ready, _body(page)).get_json()
        try:
            for _ in range(200):
                _rr, frag = _get(ready, out["url"])
                if "being applied" in frag:
                    break
                threading.Event().wait(0.02)
            assert 'hx-trigger="nmas:deploy_job from:body"' in frag
            r6 = frag.index(">r6<")
            r2 = frag.index(">r2<")
            assert r6 < r2
            # r6 finished; its record is committed only when the batch ends (R5's receipts)
            assert "step-done" in frag and "done; its record is committed when the batch ends (" in frag
            assert "step-current" in frag and "being applied" in frag     # r2 running
            assert "Check now" in frag
        finally:
            gate.set()
            capture_job.wait(out["job"], 20)

    def test_a_program_that_moved_is_refused_alone_with_nothing_sent(self, ready, monkeypatch):
        from modules.nsot import capture_job
        reached = self._spy(monkeypatch)
        _r, page = _page(ready)
        body = _body(page)
        body["command_hashes"]["r6"] = "0" * 16
        out = _confirm(ready, body).get_json()
        assert capture_job.wait(out["job"], 20)
        assert reached == [("r2", "profile")]
        _rr, frag = _get(ready, out["url"])
        assert "the exact command list changed since you confirmed" in frag
        # Its progress row reads refused, never "not reached" (the breaker's
        # words): the review's finding, 2026-10-01.
        from modules import deploy_job
        steps = {s["device"]: s for s in deploy_job.state(out["job"])["steps"]}
        assert steps["r6"]["state"] == "done" and steps["r6"]["outcome"] == "refused", steps["r6"]

    def test_the_confirm_refuses_what_carries_nothing(self, ready):
        r = _confirm(ready, {"order": ["r6"], "confirmations": {"r6": "x"},
                             "command_hashes": {"r6": "y"}})
        assert r.status_code == 400 and "No known list" in r.get_json()["error"]
        r = _confirm(ready, {"list": "Nowhere", "order": ["r6"], "confirmations": {"r6": "x"},
                             "command_hashes": {"r6": "y"}})
        assert r.status_code == 400
        r = _confirm(ready, {"list": "Lab", "order": ["r6"], "confirmations": {"r6": "x"}})
        assert r.status_code == 400 and "Nothing confirmed" in r.get_json()["error"]

    def test_an_unknown_job_says_so(self, ready):
        r, frag = _get(ready, "/v2/monitoring/apply/job/nope")
        assert r.status_code == 404 and "no record of that batch" in frag

    def test_the_confirm_is_gated_and_invalidates_through_its_announcer(self):
        from modules import invalidation, route_gates
        assert route_gates.GATES["v2.profile_apply_confirm"].kind == "confirm"
        assert isinstance(invalidation.DECLARED["v2.profile_apply_confirm"],
                          invalidation.Nothing)
        assert "deploy_job" in invalidation.ANNOUNCERS["deploy-job"]


class TestTheShippedClient:
    def _js(self):
        return open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8").read()

    def _outcome(self, status, body):
        import dukpy
        return dukpy.evaljs("var window = {};\n" + self._js()
                            + f"\nwindow.NMAS_APPLY.confirmOutcome({status}, {json.dumps(body)})")

    def test_a_started_job_is_followed(self):
        assert self._outcome(202, {"ok": True, "url": "/v2/monitoring/apply/job/a"}) == {
            "started": True, "url": "/v2/monitoring/apply/job/a", "error": ""}

    def test_a_refusal_is_said_in_the_servers_words(self):
        got = self._outcome(400, {"ok": False, "error": "Nothing confirmed: x"})
        assert got["started"] is False and got["error"] == "Nothing was sent: Nothing confirmed: x"
        assert self._outcome(500, None)["error"] == "Nothing was sent: refused (HTTP 500)"

    def test_the_component_reads_its_attributes_from_its_root(self):
        src = self._js()
        assert "this.$el" not in src and "self.$el" not in src
        for attr in ("data-url", "data-body", "data-label"):
            assert f"$root.getAttribute('{attr}')" in src

    def test_the_frame_loads_it(self, ready):
        _r, page = _page(ready)
        assert re.search(r'<script defer src="/static/js/nmas_apply\.js[^"]*"></script>', page)
        assert 'x-data="applyConfirm"' in page


class TestASupersededLine:
    """r6 holding ANOTHER community beside the one the profile supplies: the
    old line is offered for removal (Mode B; `snmp-server community` is
    measured exact on both platforms), never removed unless ticked, and a
    ticked one needs its stated reason before the device can be confirmed."""

    @pytest.fixture
    def old(self, ready):
        from modules.nsot.repo import GoldenItem, save_golden
        cfg = ready["r6"].replace("\nend", "\nsnmp-server community OLDCOMMUNITY RO\nend")
        assert cfg != ready["r6"]
        save_golden("Lab", [GoldenItem("r6", cfg, "203.0.113.16", platform="cisco_iosxe")],
                    source="capture", actor="t", baseline=False)
        return ready

    def _id(self, page):
        m = re.search(r'name="rm::r6" value="([0-9a-f]+)"', page)
        assert m, "the superseded line is offered with its box"
        return m.group(1)

    def test_it_is_offered_and_never_removed_unticked(self, old):
        _r, page = _page(old, devices=("r6",))
        self._id(page)
        assert "OLDCOMMUNITY" not in page and "snmp-server community &lt;redacted:" in page
        assert "<strong>will be removed</strong>" not in page and not _body(page).get("remove")

    def test_ticked_it_waits_on_a_reason_then_carries_it(self, old):
        _r, page = _page(old, devices=("r6",))
        rid = self._id(page)
        _r, ticked = _page(old, devices=("r6",), extra=f"&rm::r6={rid}")
        assert "will be removed" in ticked and f'name="why::r6::{rid}"' in ticked
        assert "data-body=''" in ticked, "no reason yet: r6 cannot be confirmed"
        _r, why = _page(old, devices=("r6",),
                        extra=f"&rm::r6={rid}&why::r6::{rid}=the+old+collector+is+retired")
        body = _body(why)
        assert body["remove"] == {"r6": [rid]}
        (auth,) = body["authorise"]["r6"]
        assert auth["reason"] == "the old collector is retired" and "OLDCOMMUNITY" not in auth["line"]
        assert body["command_hashes"]["r6"] != _body(page)["command_hashes"]["r6"]

    def test_the_confirmed_removal_reaches_the_device_path(self, old, monkeypatch):
        import routes.deploy as rd
        from modules.nsot import capture_job
        seen = []

        def spy(entry, list_name, rows, authorise, **kw):
            seen.append((kw.get("remove"), authorise))
            return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, page = _page(old, devices=("r6",))
        rid = self._id(page)
        _r, why = _page(old, devices=("r6",),
                        extra=f"&rm::r6={rid}&why::r6::{rid}=the+old+collector+is+retired")
        out = _confirm(old, _body(why)).get_json()
        assert capture_job.wait(out["job"], 20)
        (remove, authorise), = seen
        assert remove == {"r6": [rid]} and authorise["r6"][0]["reason"] == "the old collector is retired"


# ------------------------------------------------ clicking what ships
#
# C243's lesson (the Update button's first real run was disabled by its own
# wiring): the page is loaded in a REAL browser and its shipped controls
# clicked, where Firefox runs. Skipped, saying why, where it cannot start.

@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the client's pure logic and the "
                    "$root rule above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


class TestClickingTheShippedPage:
    def test_reorder_then_confirm_runs_the_batch_in_the_order_set(self, ready, monkeypatch,
                                                                   live_browser):
        import routes.deploy as rd
        browser, srv, b = live_browser
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            reached.append(entry["artifact"].device)
            return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        try:
            b.go(srv.url("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))
            b.wait_for("var c=document.querySelector('#apply-confirm');"
                       "return window.Alpine && c && !c.disabled")
            assert b.js("return document.querySelector('#apply-confirm').textContent.trim()") == \
                "Apply to 2 device(s) in this order"
            # "Later" on r6, the first row: the server plans the batch again.
            b.click('button[aria-label="Move r6 later"]')
            b.wait_for("var a=document.querySelectorAll('#rollout li a');"
                       "return a.length === 2 && a[0].textContent === 'r2'")
            b.wait_for("var c=document.querySelector('#apply-confirm');"
                       "return window.Alpine && c && !c.disabled")
            b.click("#apply-confirm")
            text = ""
            for _ in range(40):
                text = b.wait_for("var j=document.querySelector('#apply-job');"
                                  "return j && j.textContent")
                if "device(s) deployed" in text:
                    break
                b.js("var x=document.querySelector('#apply-job button');"
                     "if (x) x.click(); return 1")
                time.sleep(0.25)
            assert "2 of 2 device(s) deployed" in text, text
            assert reached == ["r2", "r6"]
            assert b.js("return document.querySelector('#apply-confirm').disabled") is True
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


# ------------------------------------------------ the device page (P.9 d3)

R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R6 = {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}


class TestMonitoredBy:
    """The device page's Monitoring tab opens with what the device is
    monitored by: Coverage's own cells (`monitoring_coverage.fleet`) for this
    device alone, and "Apply monitoring profile…" when the profile supplies
    something it lacks, opening the same preview for it alone."""

    @pytest.fixture
    def page(self, ready, monkeypatch):
        from modules import device_page
        from modules.nsot import listref
        rows = {"r2": R2, "r6": R6}
        monkeypatch.setattr(device_page, "find_device",
                            lambda name: (listref.resolve("Lab"), dict(rows[name])))
        return lambda name: _get(ready, f"/v2/device/{name}/monitored-by")

    def test_r6_lacks_snmp_and_is_offered_the_profile(self, page):
        r, html = page("r6")
        assert r.status_code == 200
        assert "<strong>SNMP</strong><span class=\"muted\"> through Prometheus</span>: missing — the profile supplies it" in html
        assert 'href="/v2/monitoring/apply?list=Lab&amp;device=r6">Apply monitoring profile…</a>' in html

    def test_r2_lacks_nothing_and_says_so(self, page):
        _r, html = page("r2")
        assert "r2 is configured for everything the network uses." in html
        assert "Apply monitoring profile" not in html

    def test_the_link_opens_the_same_preview_for_that_device(self, ready, page):
        _r, html = page("r6")
        href = html_mod.unescape(re.search(r'href="(/v2/monitoring/apply\?[^"]+)"', html).group(1))
        _r, preview = _get(ready, href)
        assert _order(preview) == ["r6"] and _body(preview)["order"] == ["r6"]

    def test_a_failed_read_is_said_never_an_empty_section(self, page, monkeypatch):
        from modules import monitoring_coverage

        def boom(*a, **k):
            raise OSError("git show failed")
        monkeypatch.setattr(monitoring_coverage, "fleet", boom)
        _r, html = page("r6")
        assert "could not be read (OSError: git show failed)" in html
        assert "not the same as it being monitored by nothing" in html

    def test_it_redraws_on_keys_v2_relays_under_the_strict_policy(self, page):
        from modules import csp, invalidation
        r, html = page("r6")
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        keys = re.findall(r"nmas:(\w+) from:body",
                          re.search(r'hx-trigger="([^"]*)"', html).group(1))
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        assert keys == ["goldens", "job_health"]
        for k in keys:
            assert k in invalidation.VOCABULARY and f"NMAS.subscribe('{k}'" in src

    def test_the_monitoring_tab_opens_with_it(self, ready, monkeypatch):
        from tests.test_device_v2 import _get as _dget  # noqa: F401 (same client shape)
        src = open(os.path.join(ROOT, "templates", "v2", "_monitoring.html"), encoding="utf-8").read()
        head = src[:src.index('<div class="toolbar">')]
        assert 'include "v2/_monitored_by.html"' in head


class TestNeedsAttentionOpensIt:
    def test_a_not_monitored_rows_action_opens_the_v2_preview(self):
        """The design (MONITORING_PROFILE.md 5): the row's action becomes this
        apply once it exists. Drawn on the v2 landing from the row the real
        `action_for` builds."""
        from flask import render_template

        import app as A
        from types import SimpleNamespace

        from modules import monitoring_coverage

        # `action_for` reads the ref's name alone; resolving a list would create it.
        action = monitoring_coverage.action_for(
            SimpleNamespace(name="Lab"), "r6", ["snmp"], {"applies": ["snmp"], "profile": True})
        assert action["open"] == "profile_apply"
        row = {"level": "warning", "what": "r6 is not monitored by SNMP", "cause": "c",
               "devices": ["r6"], "since": None, "operands": [], "action": action, "source": "s",
               "key": "k", "triage": None}
        with A.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={
                "ok": True, "rows": [row], "sources": [], "headline": "1", "counts": {},
                "badge": {"n": 1, "level": "warning"}})     # needs_attention()'s own count
        assert 'href="/v2/monitoring/apply?device=r6&amp;list=Lab">Preview the apply…</a>' in html
        assert "today&#39;s page" not in html.split("r6 is not monitored")[1].split("</article>")[0]
