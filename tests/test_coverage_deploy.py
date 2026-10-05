"""Coverage's combined deploy (artboard A2, signed off 2026-10-02; Coverage's third step).

One program per device: every template it is missing, the monitoring profile's lines AND the
IP SLA probes committed to its intent, sent only where the device lacks them; nothing else in
its intent. A configured template whose data is not arriving is never part of it, and is named
with where its cause is looked for.

On test_profile_apply's lab: r2's REAL golden and intent, and r6 in its real shape (r2's with
every `snmp` line and both discovery flags removed). Here r6's golden also loses its IP SLA
operation, which its committed intent keeps: a probe committed and not yet sent. r2's SNMP is
made to fail with the real reader capture's one edit (tests/test_coverage_reporting.py).
"""

import html as html_mod
import json
import re

import pytest

from tests.test_coverage_grid import _box, _cell, _table, r2_snmp_down  # noqa: F401
from tests.test_coverage_reporting import read  # noqa: F401 (the fixture)
from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)


def _strip_ip_sla(text: str) -> str:
    """The config without its IP SLA operations and schedules (each `ip sla N` stanza)."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^ip sla \d+\s*$", line):
            inside = True
            continue
        if inside and line.startswith(" "):
            continue
        inside = False
        if line.startswith("ip sla schedule "):
            continue
        out.append(line)
    return "\n".join(out) + "\n"


@pytest.fixture
def r6_probe_unsent(lab):
    """r6's golden without its IP SLA operation; its committed intent keeps it."""
    from modules.nsot import hostvars
    from modules.nsot.repo import GoldenItem, save_golden
    assert re.search(r"^ip sla 1$", lab["r6"], re.M), "the fixture's r6 runs ip sla 1 (r2's)"
    text = _strip_ip_sla(lab["r6"])
    assert "ip sla" not in text
    save_golden("Lab", [GoldenItem("r6", text, "203.0.113.16", platform="cisco_iosxe")],
                source="onboarding", actor="t", baseline=False)
    assert [o["id"] for o in hostvars.read_committed(lab["repo"], "r6")["ip_sla"]] == ["1"]
    _commit_proposal()
    return text


def _plan(lab, scope, devices=("r6",)):
    body = lab["client"].post("/deploy/plan", json={"devices": list(devices), "scope": scope,
                                                    "list_name": "Lab"}).get_json()
    return body


def _sent(d):
    return [c.strip() for c in d["commands"] if c.strip() != "exit"]


class TestOneProgram:
    def test_the_profiles_lines_and_the_committed_probe_in_one_program(self, lab, r6_probe_unsent):
        body = _plan(lab, "templates")
        (d,) = body["devices"]
        assert not d.get("refused"), d.get("refused")
        sent = _sent(d)
        assert any(c.startswith("snmp-server") for c in sent), sent
        assert "lldp run" in sent
        assert "ip sla 1" in sent and any(c.startswith("ip sla schedule 1 ") for c in sent), sent
        # Nothing but the templates: SNMP, the discovery flags, IP SLA.
        assert all(c.startswith(("snmp", "ip sla", "icmp-echo", "frequency", "threshold",
                                 "timeout", "tag", "lldp run", "cdp run"))
                   for c in sent), sent
        assert set(d["profile_scope"]["by_section"]) >= {"snmp", "ip_sla"}

    def test_the_profile_alone_still_holds_the_probe_back(self, lab, r6_probe_unsent):
        """The control by an independent path: the profile's own scope, unchanged, does not
        send the probe; the combined one does."""
        (d,) = _plan(lab, "profile")["devices"]
        assert "ip sla 1" not in _sent(d)
        assert "ip sla 1" in [r["line"].strip() for r in d["profile_scope"]["held_back"]]

    def test_the_devices_other_intent_is_held_back(self, lab, r6_probe_unsent):
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        r6 = hostvars.read_committed(lab["repo"], "r6")
        r6["ntp_servers"] = list(r6.get("ntp_servers") or []) + ["192.0.2.99"]
        hostvars.write_committed(lab["repo"], r6)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        (d,) = _plan(lab, "templates")["devices"]
        assert not any("192.0.2.99" in c for c in d["commands"])
        assert "ntp server 192.0.2.99" in [r["line"].strip() for r in d["profile_scope"]["held_back"]]

    def test_the_apply_holds_the_confirmed_scope(self, lab, r6_probe_unsent, monkeypatch):
        """The seam: the combined plan's hash is accepted by an apply in the same scope and
        refused by the profile's, whose program differs by the probe, with nothing sent."""
        import routes.deploy as rd
        (d,) = _plan(lab, "templates")["devices"]
        conf = {"confirmations": {"r6": d["capture_hash"]},
                "command_hashes": {"r6": d["command_hash"]}, "list_name": "Lab"}
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            reached.append(kw.get("scope", ""))
            return {"device": entry["artifact"].device, "outcome": "deployed"}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", lambda *a, **k: {})
        lab["client"].post("/deploy/apply", json=dict(conf, scope="profile"))
        assert reached == [], "the profile's program is not the one confirmed"
        lab["client"].post("/deploy/apply", json=dict(conf, scope="templates"))
        assert reached == ["templates"]


class TestOneChangeRolledBackAsOne:
    """A2: the first device that fails stops the rest, and every sent line is read back, a
    line not read back rolling the program back as one (C10: the batch otherwise stops only
    after 2 verify failures that raised)."""

    def _conf(self, lab):
        (d,) = _plan(lab, "templates")["devices"]
        return {"confirmations": {"r6": d["capture_hash"]},
                "command_hashes": {"r6": d["command_hash"]}, "list_name": "Lab"}

    def test_the_apply_stops_at_the_first_failure_one_device_at_a_time(self, lab, monkeypatch,
                                                                      r6_probe_unsent):
        import routes.deploy as rd
        seen = []

        def run_batch(plan, one, breaker=None, sequential=False, list_name=""):
            seen.append((breaker.limit, breaker.any_failure, sequential, list_name))
            return {"results": [], "by_outcome": {}, "deployed": [], "breaker_tripped": False,
                    "breaker_reason": "", "total": 0, "workers": 1}
        monkeypatch.setattr("modules.nsot.deploy.run_batch", run_batch)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", lambda *a, **k: {})
        lab["client"].post("/deploy/apply", json=dict(self._conf(lab), scope="templates"))
        assert seen == [(1, True, True, "Lab")], "the batch carries its list (P.8)"
        (p,) = _plan(lab, "profile")["devices"]
        lab["client"].post("/deploy/apply", json={
            "confirmations": {"r6": p["capture_hash"]}, "command_hashes": {"r6": p["command_hash"]},
            "list_name": "Lab", "scope": "profile"})
        assert seen[-1][1] is False and seen[-1][2] is False, "every other scope as before"
        assert seen[-1][3] == "Lab"

    def test_the_device_path_reads_every_line_back(self, lab, monkeypatch, r6_probe_unsent):
        import routes.deploy as rd
        caught = []

        class Runner:
            def __init__(self, ctx):
                caught.append(ctx)

            def run(self):
                raise RuntimeError("stopped here: the test reads the context only")
        monkeypatch.setattr("modules.pipeline.PipelineRunner", Runner)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        monkeypatch.setattr(rd, "_write_receipts", lambda *a, **k: {})
        lab["client"].post("/deploy/apply", json=dict(self._conf(lab), scope="templates"))
        assert caught and caught[-1].read_back_all is True


class TestCoverageOffersIt:
    def test_a_probe_committed_and_not_sent_is_missing_and_supplied(self, lab, monkeypatch,
                                                                     r6_probe_unsent):
        html = _table(lab, monkeypatch)
        cell = _cell(html, "r6", "IP SLA")
        assert 'data-state="gap"' in cell
        assert "missing — 1 probe committed to its intent, not yet sent" in html_mod.unescape(cell)
        # SNMP and IP SLA: LLDP reads unknown in Coverage (IOS-XE's default is not measured).
        assert 'data-missing="2"' in _box(html, "r6")

    def test_the_form_asks_for_the_combined_deploy(self, lab, monkeypatch, r6_probe_unsent):
        html = _table(lab, monkeypatch)
        form = re.search(r'<form method="get" action="/v2/monitoring/apply"[^>]*>(.*?)</form>',
                         html, re.S)
        assert form and '<input type="hidden" name="scope" value="templates">' in form.group(1)


def _page(lab, monkeypatch, report, devices=("r6", "r2")):
    from modules.nsot import listref
    from tests.test_coverage_page import R2, R6
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(R2), dict(R6)])
    monkeypatch.setattr("time.time", lambda: report["read_at"])
    monkeypatch.setattr("modules.device_page._cached", lambda name: (report, "", ""))
    q = "&".join(f"device={d}" for d in devices)
    r = lab["client"].get(f"/v2/monitoring/apply?list=Lab&scope=templates&{q}")
    return r, r.get_data(as_text=True)


class TestThePage:
    def test_drawn_as_the_board(self, lab, monkeypatch, r6_probe_unsent, r2_snmp_down):
        r, page = _page(lab, monkeypatch, r2_snmp_down)
        assert r.status_code == 200, page[:400]
        assert "Content-Security-Policy" in r.headers
        text = html_mod.unescape(page)
        # r6 sends; r2 has everything, its SNMP not reporting.
        assert "<h1>Deploy missing templates to 1 device " in text
        card = re.search(r'<section class="card cdep-device" id="apply-r6">(.*?)</section>',
                         text, re.S)
        assert card, "r6's card"
        assert "1. r6</strong>" in card.group(1)
        assert "· one program: SNMP, LLDP, IP SLA</span>" in card.group(1)
        prog = re.search(r'<pre class="apply-program">(.*?)</pre>', card.group(1), re.S).group(1)
        assert "ip sla 1" in prog.splitlines() and any(l.startswith("snmp-server")
                                                        for l in prog.splitlines())
        assert ">Leave out</button>" in card.group(1)
        assert ">Earlier</button>" not in card.group(1) and ">Later</button>" not in card.group(1)
        assert "Checks:" in card.group(1)
        # What verify does here, from the rule that decides it (`verify_note`, read_back_all).
        assert ("and every line sent is read back, a line that did not land rolling this "
                "device's program back as one") in card.group(1)
        # r2: nothing to send, its SNMP not reporting named with where to diagnose it.
        idle = re.search(r'<li id="apply-r2">(.*?)</li>', text, re.S).group(1)
        assert "SNMP is not reporting" in idle
        assert 'href="/v2/device/r2?tab=monitoring">diagnose it on r2</a>' in idle
        # The bound statement, Back and the one confirm in the board's words.
        assert "Bound to these programs: if a device or a template changes before you confirm" in text
        assert '<a class="btn" href="/v2/monitoring/coverage">Back</a>' in text
        assert ">Deploy to 1 device, in this order</button>" in text
        body = json.loads(html_mod.unescape(re.search(r"data-body='([^']*)'", page).group(1)))
        assert body["scope"] == "templates" and body["order"] == ["r6"]

    def test_a_not_reporting_template_on_a_device_that_sends_is_named_on_its_card(
            self, lab, monkeypatch, r6_probe_unsent, read):
        """r6 sends its missing templates; its configured telemetry (r2's, in r6's real
        shape), its stream stopped, is named on its card and never part of the program. (Its
        syslog cannot be judged without a heartbeat: unproven, never not reporting.)"""
        from tests.test_coverage_reporting import _capture
        cap = _capture()
        # r6's telemetry stopped arriving 40 minutes before the capture (the one edit).
        stopped = 0
        for r in cap["telemetry"]["data"]["result"]:
            if r["metric"].get("source") == "r6":
                if "values" in r:
                    r["values"] = [v for v in r["values"] if v[0] <= cap["captured_at"] - 2400]
                else:
                    r["value"][1] = str(cap["captured_at"] - 2400)
                stopped += 1
        assert stopped, "the capture holds r6's telemetry"
        value, _p, _l = read(cap)
        _r, page = _page(lab, monkeypatch, value, devices=("r6",))
        text = html_mod.unescape(page)
        card = re.search(r'<section class="card cdep-device" id="apply-r6">(.*?)</section>',
                         text, re.S).group(1)
        assert "Telemetry is not reporting" in card
        assert "not part of this deploy, it is configured" in card
        assert 'href="/v2/device/r6?tab=' in card and ">Diagnose it on r6</a>" in card
        prog = re.search(r'<pre class="apply-program">(.*?)</pre>', card, re.S).group(1)
        assert not any(l.startswith("telemetry") for l in prog.splitlines())

    def test_moving_a_device_plans_again_in_the_new_order(self, lab, monkeypatch, r6_probe_unsent,
                                                          r2_snmp_down):
        r, page = _page(lab, monkeypatch, r2_snmp_down)
        r = lab["client"].get("/v2/monitoring/apply/preview?list=Lab&scope=templates&device=r6"
                              "&device=r2&drop=r6")
        part = r.get_data(as_text=True)
        assert r.status_code == 200 and 'id="apply-r6"' not in part
        assert "Nothing to deploy" in html_mod.unescape(part) or 'id="apply-r2"' in part


class TestTheConfirm:
    def test_the_confirm_hands_the_combined_scope_to_the_job(self, lab, monkeypatch):
        seen = {}
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
        monkeypatch.setattr("modules.deploy_job.start", lambda *a, **k: seen.update(k) or "job1")
        r = lab["client"].post("/v2/monitoring/apply/confirm", json={
            "list": "Lab", "scope": "templates", "order": ["r6"],
            "confirmations": {"r6": "x"}, "command_hashes": {"r6": "y"}})
        assert r.status_code == 202 and seen["scope"] == "templates"

    def test_a_device_sent_whose_verify_did_not_pass_is_never_drawn_done(
            self, lab, monkeypatch, r6_probe_unsent, r2_snmp_down):
        """C394: sent, and verify did not pass without raising (here, intent unmet): the
        heading reads partly done and the device's own step says so, never the done green.
        The result is built by the real code from the device's result (receipts.rows_for,
        operation_result); only the device step is a spy."""
        import routes.deploy as rd
        from modules.nsot import capture_job

        def spy(entry, list_name, rows, authorise, **kw):
            return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"],
                    "verify": {"ok": False, "issues": [], "unreadable": [],
                               "intent_unmet": ["ospf: declared by intent and not up"]}}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, page = _page(lab, monkeypatch, r2_snmp_down)
        body = json.loads(html_mod.unescape(re.search(r"data-body='([^']*)'", page).group(1)))
        out = lab["client"].post("/v2/monitoring/apply/confirm", json=body).get_json()
        assert capture_job.wait(out["job"], 20)
        frag = lab["client"].get(out["url"]).get_data(as_text=True)
        step = re.search(r'<li class="step step-([a-z_]+)">\s*<span class="step-mark"></span>'
                         r'<span class="step-words">r6</span>\s*<span class="step-note">([^<]*)<',
                         frag)
        assert step, frag[:600]
        assert step.group(1) == "partial", step.group(0)
        assert "and its verify did not pass" in step.group(2)
        assert "Partly done" in frag

    def test_the_job_names_what_it_is(self):
        from modules import deploy_job
        assert deploy_job.KINDS["templates"] == "monitoring templates deploy"


def test_a_real_browser_deploys_from_coverage_s_own_button(lab, monkeypatch, r6_probe_unsent,
                                                           r2_snmp_down):
    """The whole way, clicked (C385: every opener is clicked where it sits): Coverage's
    "Deploy missing templates…" opens the combined deploy for the ticked device, and its
    confirm runs the batch in this scope, the device step a spy (no device is contacted)."""
    import time

    import routes.deploy as rd
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules.nsot import listref
    from tests.test_coverage_page import R2, R6
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(R2), dict(R6)])
    monkeypatch.setattr("modules.device_page._cached", lambda name: (r2_snmp_down, "", ""))
    reached = []

    def spy(entry, list_name, rows, authorise, **kw):
        reached.append((entry["artifact"].device, kw.get("scope", "")))
        return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"]}
    monkeypatch.setattr(rd, "_deploy_one", spy)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/monitoring/coverage"))
            b.wait_for("return window.Alpine && document.querySelector('#cov-r6')", 15)
            b.wait_for("var bar=document.querySelector('#cov-bar'); return bar && !bar.hidden")
            b.js("Array.prototype.filter.call(document.querySelectorAll('#cov-bar button'), "
                 "function (x) { return /Deploy missing templates/.test(x.textContent); })[0]"
                 ".click();")
            b.wait_for("return /^Deploy missing templates to 1 device/.test("
                       "(document.querySelector('h1') || {}).textContent || '')", 15)
            assert b.js("return document.querySelector('#apply-r6 .cdep-hd').textContent"
                        ".replace(/\\s+/g, ' ')").strip().startswith("1. r6 · one program: SNMP, LLDP, IP SLA")
            b.wait_for("var c=document.querySelector('#apply-confirm');"
                       "return window.Alpine && c && !c.disabled")
            b.click("#apply-confirm")
            text = ""
            for _ in range(40):
                text = b.wait_for("var j=document.querySelector('#apply-job');"
                                  "return j && j.textContent")
                if "device(s) deployed" in text:
                    break
                b.js("var x=document.querySelector('#apply-job button'); if (x) x.click(); return 1")
                time.sleep(0.25)
            assert "1 of 1 device(s) deployed" in text, text
            assert reached == [("r6", "templates")]
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
