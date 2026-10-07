"""Monitoring > Coverage (P.9 (d), NSOT_GUI_BRIEF 14.3): each device by
integration, from its COMMITTED golden, and what the network's monitoring
profile would supply where it is not configured.

On test_profile_apply's lab: r2's REAL config and intent, and r6 in its real
shape (r2's with every `snmp` line removed). The network uses SNMP through
Prometheus. Each cell's state is decided by `monitoring_coverage.fleet()`;
the page draws it in words, and its form takes the ticked devices to the
batch preview.
"""

import re

import pytest

from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)

R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R6 = {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}


def _fleet(lab, settings=None, **kw):
    from modules import monitoring_coverage as M
    from modules.nsot import listref
    ref = listref.resolve("Lab")
    s = {**lab["settings"], **(settings or {})}
    return M.fleet(ref, devices=[(ref, dict(R2)), (ref, dict(R6))],
                   get=lambda k, d=None: s.get(k, d), **kw)


def _shown(cell):
    """A cell's state and words; whether it REPORTS is tests/test_coverage_reporting.py's."""
    return {"state": cell["state"], "words": cell["words"]}


def _row(c, host):
    return next(d for d in c["devices"] if d["host"] == host)


class TestTheCells:
    def test_before_a_profile_r6s_gap_says_there_is_none_and_nothing_is_offered(self, lab):
        c = _fleet(lab)
        r2, r6 = _row(c, "r2"), _row(c, "r6")
        assert _shown(r2["cells"]["snmp"]) == {"state": "ok", "words": "configured"}
        assert r6["cells"]["snmp"] == {"state": "gap_open",
                                       "words": "missing — no monitoring profile yet"}
        # Loki is not configured here: syslog is not something the network uses.
        assert r6["cells"]["syslog"]["state"] in ("ok", "unused")
        assert (c["covered"], c["total"]) == (1, 2) and r6["gaps"] == ["snmp"]
        assert not r6["selectable"] and r6["why_not"] == "the network has no monitoring profile yet"
        assert not c["profile"]["committed"]
        assert [col["connector"] for col in c["columns"] if col["key"] == "snmp"] == ["Prometheus"]

    def test_after_the_proposal_the_profile_supplies_r6s_snmp_and_r6_starts_ticked(self, lab):
        from modules.nsot import repo as R
        _commit_proposal()
        c = _fleet(lab)
        r2, r6 = _row(c, "r2"), _row(c, "r6")
        assert r6["cells"]["snmp"] == {"state": "gap", "words": "missing — the profile supplies it"}
        assert r6["supplies"] == ["snmp"] and r6["selectable"] and r6["checked"]
        # r2 lacks nothing the profile supplies: NOT offered, saying why (C295,
        # the operator, 2026-10-01: an Apply that could send nothing was offered).
        assert not r2["selectable"] and not r2["checked"] and not r2["gaps"]
        assert r2["why_not"].startswith("nothing for Apply to send: "), r2["why_not"]
        rc, out, _e = R.git(lab["repo"], "log", "-1", "--format=%h", "--", "profiles/monitoring.yml")
        assert c["profile"]["commit"] == out.strip() and "snmp" in c["profile"]["sections"]

    def test_ip_sla_missing_is_not_offered_while_the_profile_has_none(self, lab):
        """C295, the operator's case (s1, s2, s4, r6 on 2026-10-01): a device
        whose only missing piece is IP SLA was tickable, and the apply could
        send nothing. A minimal edit of r2's REAL golden: its IP SLA removed."""
        import re as _re
        from modules.prometheus_targets import read_golden
        _commit_proposal()
        _no_probe_in_intent(lab, "r2")

        def golden(ref, host):
            text = read_golden(ref, host)
            if host != "r2":
                return text
            out, skip = [], False
            for line in text.splitlines():
                if _re.match(r"^ip sla \d+", line):
                    skip = True
                    continue
                if skip and line.startswith(" "):
                    continue
                skip = False
                out.append(line)
            return "\n".join(out) + "\n"
        r2 = _row(_fleet(lab, golden=golden), "r2")
        assert r2["cells"]["ip_sla"]["state"] == "unused"
        assert not r2["selectable"] and not r2["checked"]
        assert "IP SLA isn't in the profile yet" in r2["why_not"], r2["why_not"]

    def test_an_excluded_section_is_a_decision_with_its_reason_never_a_gap(self, lab):
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        _commit_proposal()
        r6 = hostvars.read_committed(lab["repo"], "r6")
        r6["profile_exclude"] = [{"section": "snmp", "reason": "polled by the carrier's NMS"}]
        hostvars.write_committed(lab["repo"], r6)
        assert save_host_vars("Lab", ["r6"], actor="t", source="extraction")["ok"]
        cell = _row(_fleet(lab), "r6")["cells"]["snmp"]
        assert cell == {"state": "excluded", "words": "excluded — polled by the carrier's NMS"}
        assert _row(_fleet(lab), "r6")["gaps"] == []

    def test_an_unreadable_golden_is_unknown_never_not_configured(self, lab):
        def golden(ref, host):
            if host == "r6":
                raise OSError("git show failed")
            from modules import prometheus_targets as P
            return P.read_golden(ref, host)
        c = _fleet(lab, golden=golden)
        r6 = _row(c, "r6")
        assert r6["golden"] == "unreadable" and "git show failed" in r6["error"]
        assert {cell["state"] for cell in r6["cells"].values()} == {"unknown"}
        assert r6["gaps"] == [] and c["covered"] == 1

    def test_a_section_the_profile_scopes_away_is_not_a_gap(self, lab):
        """Telemetry where the profile's section is for another platform (a vIOS
        switch cannot stream): the profile's decision, drawn as such."""
        from modules.nsot import profile as _p
        _commit_proposal()
        doc = _p.read_committed(lab["repo"])
        doc["sections"]["telemetry"] = {"platforms": ["cisco_ios"], "source": "Telegraf",
                                        "data": {"subscriptions": [{"id": 101}]}}
        assert _p.commit_profile("Lab", doc, "t", "telemetry for IOS only")["ok"]
        from modules import prometheus_targets as P

        def golden(ref, host):
            text = P.read_golden(ref, host)
            return "\n".join(l for l in text.splitlines() if not l.startswith("telemetry "))
        c = _fleet(lab, settings={"telemetry_receiver": "192.0.2.5:57000"}, golden=golden)
        cell = _row(c, "r6")["cells"]["telemetry"]
        assert cell["state"] == "not_applicable"
        assert cell["words"] == "not applicable — the profile's telemetry section is for IOS"
        assert "telemetry" not in _row(c, "r6")["gaps"]


def _page(lab, monkeypatch, path="/v2/monitoring/coverage"):
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(R2), dict(R6)])
    r = lab["client"].get(path)
    return r, r.get_data(as_text=True)


class TestThePage:
    def test_before_a_profile_it_says_propose_and_offers_no_apply(self, lab, monkeypatch):
        r, html = _page(lab, monkeypatch)
        assert r.status_code == 200 and "script-src" in r.headers["Content-Security-Policy"]
        # The redraw (artboard A): the answer first, how many are fully covered.
        assert re.search(r'1 of 2 devices fully covered\s*<span class="muted">· 1 template '
                         r'missing on 1 device', html)
        assert "Lab has no monitoring profile yet" in html
        assert "/v2/monitoring/profile?propose=1" in html and "today's page" not in html
        assert "Deploy missing templates" not in html
        assert "Nothing to deploy: the network has no monitoring profile yet" in html

    def test_the_form_takes_the_ticked_devices_to_the_batch_preview(self, lab, monkeypatch):
        _commit_proposal()
        r, html = _page(lab, monkeypatch)
        assert "missing — the profile supplies it" in html
        form = re.search(r'<form method="get" action="([^"]*)" class="cov-form"[^>]*>(.*?)</form>',
                         html, re.S)
        # P.9 (d2): the v2 batch preview, carrying the list and the ticked devices.
        assert form and form.group(1) == "/v2/monitoring/apply"
        body = form.group(2)
        assert 'name="open"' not in body
        assert '<input type="hidden" name="list" value="Lab">' in body
        assert re.search(r'<input type="checkbox" name="device" value="r6" id="cov-r6" '
                         r'data-missing="1" checked', body)
        # r2 has nothing for Apply to send: no box to tick, and the reason beside it.
        assert 'value="r2"' not in body
        assert "Nothing to deploy: nothing for Apply to send" in body
        assert "Deploy missing templates…" in body
        # Every cell drawn, its words for a screen reader and on hover, never colour alone.
        assert html.count('<td class="gc" data-state=') == 2 * 8   # A's seven, C566's Mgmt sources

    def test_the_table_refreshes_on_keys_the_vocabulary_holds(self, lab, monkeypatch):
        from modules.invalidation import VOCABULARY
        r, html = _page(lab, monkeypatch, "/v2/monitoring/coverage/table")
        assert r.status_code == 200 and html.lstrip().startswith("<section")
        trig = re.search(r'hx-trigger="([^"]*)"', html).group(1)
        keys = re.findall(r"nmas:(\w+) from:body", trig)
        assert keys and set(keys) <= set(VOCABULARY) and {"goldens", "intent"} <= set(keys)

    def test_the_sidebar_monitoring_item_opens_it(self, lab, monkeypatch):
        _r, html = _page(lab, monkeypatch)
        assert re.search(r'<a class="nav-item active" href="/v2/monitoring" aria-current="page">', html)


def test_todays_opener_takes_several_device_parameters():
    """The form sends `device=r2&device=r6`; the opener read only the first."""
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "static", "js", "gen", "partials__deploy_wizard.1.js")).read()
    assert "openProfileApply(q.getAll('device').join(','), q.get('list') || '')" in src


def _no_probe_in_intent(lab, host):
    """*host* runs no probe AND has none chosen: its committed intent without IP SLA (the
    operator's s1, s2, s4 and r6 on 2026-10-01). A golden edited alone, its intent keeping the
    probe, is a probe committed and not sent: a gap the combined deploy supplies
    (tests/test_coverage_deploy.py)."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars
    hv = hostvars.read_committed(lab["repo"], host)
    hv.pop("ip_sla", None)
    hv.pop("ip_sla_schedules", None)
    hostvars.write_committed(lab["repo"], hv)
    assert save_host_vars("Lab", [host], actor="t", source="extraction")["ok"]


class TestEveryCellSaysWhy:
    """The operator, 2026-10-01: "none (a policy per device)" explained nothing.
    Every device here supports IP SLA; probes were configured by hand on r1 to
    r4 and s3, and nobody chose targets for the others."""

    def _no_ip_sla(self, ref, host):
        from modules import prometheus_targets as P
        return "\n".join(l for l in P.read_golden(ref, host).splitlines()
                         if not l.startswith("ip sla"))

    @pytest.fixture(autouse=True)
    def _r6_chose_none(self, lab):
        _no_probe_in_intent(lab, "r6")

    def test_ip_sla_with_no_policy_says_targets_are_chosen_per_device(self, lab):
        cell = _row(_fleet(lab, golden=self._no_ip_sla), "r6")["cells"]["ip_sla"]
        assert cell == {"state": "unused", "words": (
            "no probes configured — IP SLA targets are chosen per device; set a policy on the IP SLA "
            "page to add them")}

    @pytest.mark.parametrize("policy,words", [
        ("none", "no probes — the profile's IP SLA policy is to probe nothing"),
        ("gateway", "no probes yet — the profile's policy is to probe the default gateway; "
                    "review the suggested probes on the IP SLA page"),
        ("peers", "no probes yet — the profile's policy is to probe the routing peers; "
                  "review the suggested probes on the IP SLA page")])
    def test_ip_sla_says_the_profiles_policy(self, lab, policy, words):
        from modules.nsot import profile as _p
        _commit_proposal()
        doc = _p.read_committed(lab["repo"])
        doc["sections"]["ip_sla"] = {"policy": policy}
        assert _p.commit_profile("Lab", doc, "t", f"ip sla {policy}")["ok"]
        assert _row(_fleet(lab, golden=self._no_ip_sla), "r6")["cells"]["ip_sla"]["words"] == words

    def test_ip_sla_configured_by_hand_reads_configured(self, lab):
        # r2's REAL golden carries its hand-configured operations.
        cell = _row(_fleet(lab), "r2")["cells"]["ip_sla"]
        assert _shown(cell) == {"state": "ok", "words": "configured"}

    def test_vios_says_it_has_no_model_driven_telemetry_from_its_real_golden(self):
        import os
        from modules import monitoring_coverage as M
        s1 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "configs",
                               "fleet", "s1.cfg")).read()
        assert M._not_applicable_words("telemetry", {}, s1, "cisco_ios") == \
            "not applicable — vIOS doesn't support model-driven telemetry"

    def test_an_unused_integration_names_the_connector_it_lacks(self, lab):
        # Loki is not configured on this lab: syslog is not something it uses.
        def golden(ref, host):
            from modules import prometheus_targets as P
            return "\n".join(l for l in P.read_golden(ref, host).splitlines()
                             if not l.startswith("logging host"))
        cell = _row(_fleet(lab, golden=golden), "r6")["cells"]["syslog"]
        assert cell == {"state": "unused", "words": "not used — this network has no Loki connector"}
