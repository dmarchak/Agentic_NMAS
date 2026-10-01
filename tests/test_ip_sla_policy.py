"""P.9 (d4), the ADD path: IP SLA probes SUGGESTED from the monitoring
profile's policy, committed into the devices' own intent, then sent by the
batch Apply scoped to IP SLA lines (the operator, 2026-10-01: "split adding
from changing"; changing a running probe is the re-create, gated on staged
run 9).

The suggestion engine on the nine REAL fleet configs: a switch's path to a
router is placed ON THE ROUTER (one probe every 10 s cost s3 about 12% of
its CPU, C93), a path an existing probe measures from either end is not
added again, RIP's peers are named as not read, 60 s by default with the
cost stated. The routes on a lab holding r2 and s4 (both REAL, sharing
10.255.3.0/24): the policy committed as the person and bound to the profile
shown; the page draws each suggestion with where, what, why and its cost;
the commit is ONE intent commit of the ticked probes, refusing a moved plan,
an uncommitted host_vars/ and nothing ticked, and putting files back when
the commit fails; the scoped Apply then sends ONLY the IP SLA lines, and its
confirm carries the scope.
"""

import html as html_mod
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
PLAT = {h: ("cisco_ios" if h.startswith("s") else "cisco_iosxe")
        for h in ("r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4")}


def _cfg(host):
    with open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def fleet():
    from modules.nsot.parsers import get_parser
    intents = {h: get_parser(p).parse(_cfg(h)) for h, p in PLAT.items()}
    devices = {h: {"hostname": h, "platform": p} for h, p in PLAT.items()}
    return intents, devices


def _suggest(fleet, chosen, policy="peers", **section):
    from modules.nsot import ip_sla_policy as P
    intents, devices = fleet
    return P.suggest(intents, devices, {"policy": policy, **section}, list(chosen))


class TestTheSuggestions:
    def test_a_switch_path_to_a_router_is_placed_on_the_router(self, fleet):
        out = _suggest(fleet, ["s4"])
        assert [(s["on"], s["target"], s["target_device"]) for s in out["suggestions"]] == [
            ("r2", "10.255.1.24", "s4")]
        s = out["suggestions"][0]
        # r2 already runs ip sla 1, so the next free id; IOS-XE nests frequency.
        assert s["op"] == {"id": "2", "settings": [
            " icmp-echo 10.255.1.24 source-interface Loopback0", "  frequency 60"]}
        assert s["schedule"] == "2 life forever start-time now"
        assert "sparing the switch" in s["why"] and "s4 is a switch" in s["why"]

    def test_a_path_already_measured_on_its_segment_is_not_added_again(self, fleet):
        out = _suggest(fleet, ["s3"])
        assert out["suggestions"] == []
        (k,) = out["skipped"]
        assert k["device"] == "s3" and "already measured from s3 by s3's ip sla 1" in k["why"]
        assert "one probe covers it" in k["why"]

    def test_the_same_pair_is_measured_once_from_either_end(self, fleet):
        # r5 shares two sessions with r3 (IPv4 and IPv6): one probe, and the
        # second is named as the same pair.
        out = _suggest(fleet, ["r5"])
        assert [(s["on"], s["target_device"]) for s in out["suggestions"]] == [("r5", "r3")]
        assert any("its path to r3 is already measured by the suggested ip sla 1 on r5"
                   in k["why"] for k in out["skipped"])

    def test_rip_peers_are_named_as_not_read(self, fleet):
        out = _suggest(fleet, ["s1", "s2"])
        assert out["suggestions"] == []
        assert {k["device"] for k in out["skipped"]} == {"s1", "s2"}
        assert all("runs RIP" in k["why"] and "by hand" in k["why"] for k in out["skipped"])

    def test_the_gateway_policy_names_a_learned_default_as_no_target(self, fleet):
        out = _suggest(fleet, ["s4"], policy="gateway")
        assert out["suggestions"] == []
        assert "no static default route" in out["skipped"][0]["why"]

    def test_none_suggests_nothing(self, fleet):
        out = _suggest(fleet, ["s4"], policy="none")
        assert out["suggestions"] == [] and "probe nothing" in out["skipped"][0]["why"]

    def test_the_frequency_comes_from_the_policy_and_its_platform(self, fleet):
        out = _suggest(fleet, ["s4"], frequency=120, frequency_by_platform={"cisco_iosxe": 300})
        assert out["suggestions"][0]["frequency"] == 300
        assert out["suggestions"][0]["op"]["settings"][1] == "  frequency 300"

    def test_vios_writes_frequency_at_one_level(self):
        from modules.nsot import ip_sla_policy as P
        assert P.operation("cisco_ios", 3, "192.0.2.1", "Loopback0", 60)["settings"] == [
            " icmp-echo 192.0.2.1 source-interface Loopback0", " frequency 60"]

    def test_the_cost_is_the_measurement_scaled_and_unmeasured_says_so(self):
        from modules.nsot import ip_sla_policy as P
        assert P.cost_words("cisco_ios", 60).startswith("about 2.0% of its CPU for 1 probe(s) every 60 s")
        assert P.cost_words("cisco_ios", 10, 2).startswith("about 24.0%")
        assert P.cost_words("cisco_iosxe", 60).startswith("not measured on cisco_iosxe")

    def test_the_suggestions_are_deterministic(self, fleet):
        assert _suggest(fleet, ["s4", "r5"]) == _suggest(fleet, ["s4", "r5"])


class TestTheScope:
    def test_only_ip_sla_lines_are_sent_and_the_rest_is_held_back(self):
        from modules.nsot import ip_sla_policy as P
        captured = _cfg("r2")
        intended = captured.replace(
            "ip sla schedule 1 life forever start-time now",
            "ip sla schedule 1 life forever start-time now\nip sla 2\n"
            " icmp-echo 10.255.1.24 source-interface Loopback0\n  frequency 60\n"
            "ip sla schedule 2 life forever start-time now\nntp server 192.0.2.9")
        sc = P.scoped(intended, captured)
        sent = [" > ".join([c.strip() for c in r["chain"]] + [r["line"].strip()])
                for r in sc["to_send"]]
        assert sent == ["ip sla 2", "ip sla 2 > icmp-echo 10.255.1.24 source-interface Loopback0",
                        "ip sla 2 > icmp-echo 10.255.1.24 source-interface Loopback0 > frequency 60",
                        "ip sla schedule 2 life forever start-time now"]
        assert [r["line"] for r in sc["held_back"]] == ["ntp server 192.0.2.9"]
        assert "ntp server 192.0.2.9" not in sc["config"]
        assert any(r["line"].startswith("ip sla 1") for r in sc["in_place"])


# ---------------------------------------------------------------------------
# The lab: r2 and s4, REAL configs sharing 10.255.3.0/24.
# ---------------------------------------------------------------------------

@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules.nsot import approval, hostvars
    from modules.nsot import profile as _p
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    from tests.test_capture import build_capture_lab

    monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
    lab = build_capture_lab(monkeypatch, tmp_path)
    s4 = _cfg("s4")
    save_golden("Lab", [GoldenItem("s4", s4, "203.0.113.24", platform="cisco_ios")],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    hostvars.write_committed(lab["repo"], get_parser("cisco_ios").parse(s4))
    assert save_host_vars("Lab", ["s4"], actor="t", source="extraction")["ok"]
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe"},
               {"hostname": "s4", "ip": "203.0.113.24", "device_type": "cisco_ios",
                "platform": "cisco_ios"}]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(d) for d in devices])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    assert _p.commit_profile("Lab", {"version": _p.VERSION, "sections": {}}, "t", "empty")["ok"]
    lab["running"]["s4"] = s4
    return lab


def _head(lab):
    from modules.nsot.repo import git
    return git(lab["repo"], "rev-parse", "HEAD")[1]


def _policy(lab, policy="peers", frequency=60):
    from modules.nsot import ip_sla_policy as P, listref
    view = P.policy_view(listref.resolve("Lab"))
    return lab["client"].post("/v2/monitoring/ip-sla/policy", json={
        "list": "Lab", "policy": policy, "frequency": frequency, "profile_hash": view["hash"]})


def _page(lab, devices=("s4",)):
    q = "&".join(f"device={d}" for d in devices)
    r = lab["client"].get(f"/v2/monitoring/ip-sla?list=Lab&{q}")
    return r, r.get_data(as_text=True)


def _commit_body(page_html):
    m = re.search(r"data-url=\"/v2/monitoring/ip-sla/commit\" data-body='([^']*)'", page_html)
    assert m, "the commit carries its body"
    return json.loads(html_mod.unescape(m.group(1)))


def _keys(page_html):
    return re.findall(r'<input type="checkbox" name="pick" value="([^"]+)"', page_html)


class TestThePolicy:
    def test_with_no_policy_the_page_says_choose_one_and_suggests_nothing(self, lab):
        r, page = _page(lab)
        assert r.status_code == 200
        assert "The profile has no IP SLA policy yet" in page
        assert "Choose a policy above" in page and not _keys(page)
        assert "Content-Security-Policy" in r.headers

    def test_setting_it_commits_the_profile_as_the_person(self, lab):
        from modules.nsot.repo import git
        r = _policy(lab)
        assert r.status_code == 200 and r.get_json()["outcome"] == "committed", r.get_json()
        msg = git(lab["repo"], "log", "-1", "--format=%B")[1]
        assert msg.startswith("profile: IP SLA policy: peers, every 60 s")
        assert "Source: profile" in msg and "Actor: " in msg
        _r, page = _page(lab)
        assert ("probe each device's routing peers, one probe per shared network, every 60 s"
                in html_mod.unescape(page))

    def test_a_profile_that_moved_is_refused_with_nothing_committed(self, lab):
        before = _head(lab)
        r = lab["client"].post("/v2/monitoring/ip-sla/policy", json={
            "list": "Lab", "policy": "peers", "frequency": 60, "profile_hash": "stale"})
        assert r.status_code == 409 and "changed since it was shown" in r.get_json()["error"]
        assert _head(lab) == before

    @pytest.mark.parametrize("freq", [5, 4000, "often"])
    def test_a_frequency_outside_ten_to_3600_is_refused(self, lab, freq):
        before = _head(lab)
        r = _policy(lab, frequency=freq)
        assert r.status_code == 400 and "nothing was committed" in r.get_json()["error"]
        assert _head(lab) == before

    def test_an_unknown_policy_is_refused(self, lab):
        r = _policy(lab, policy="everything")
        assert r.status_code == 409 and "one of" in r.get_json()["error"]


class TestTheSuggestionsPage:
    def test_each_suggestion_says_where_what_why_and_its_cost(self, lab):
        assert _policy(lab).status_code == 200
        r, page = _page(lab)
        assert r.status_code == 200
        assert _keys(page) == ["r2:2"]
        text = html_mod.unescape(page)
        assert "<strong>ip sla 2</strong> on r2 probes <code>10.255.1.24</code> every 60 s" in text
        assert "measures r2 ↔ s4" in text
        assert "the same path is measured from r2, sparing the switch's CPU" in text
        assert "On r2: expected cost not measured on cisco_iosxe" in text
        assert "ip sla schedule 2 life forever start-time now" in text
        assert "Nothing is sent from here" in text
        assert _commit_body(page) == {"list": "Lab", "devices": ["s4"],
                                      "fingerprint": _commit_body(page)["fingerprint"]}

    def test_a_device_with_nothing_to_suggest_says_why(self, lab):
        assert _policy(lab, policy="gateway").status_code == 200
        _r, page = _page(lab)
        assert not _keys(page)
        assert "No probe to suggest for these devices" in page
        assert "no static default route" in html_mod.unescape(page)

    def test_no_device_chosen_points_to_coverage(self, lab):
        r = lab["client"].get("/v2/monitoring/ip-sla?list=Lab")
        assert "No device was chosen" in r.get_data(as_text=True)


class TestTheCommit:
    def _commit(self, lab, page, picked=None, **over):
        body = {**_commit_body(page), "picked": _keys(page) if picked is None else picked, **over}
        return lab["client"].post("/v2/monitoring/ip-sla/commit", json=body)

    def test_one_intent_commit_of_the_ticked_probes_then_the_scoped_apply(self, lab):
        from modules.nsot import hostvars
        from modules.nsot.repo import git
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        r = self._commit(lab, page)
        out = r.get_json()
        assert r.status_code == 200 and out["ok"], out
        assert out["devices"] == ["r2"]
        assert "scope=ip_sla" in out["url"] and "device=r2" in out["url"]
        files = git(lab["repo"], "show", "--name-only", "--format=", "HEAD")[1].split()
        assert files == ["host_vars/r2.yml"]
        msg = git(lab["repo"], "log", "-1", "--format=%B")[1]
        assert "Source: ip-sla" in msg and "r2 -> s4 (10.255.1.24, every 60 s)" in msg
        hv = hostvars.read_committed(lab["repo"], "r2")
        assert [o["id"] for o in hv["ip_sla"]] == ["1", "2"]
        assert hv["ip_sla_schedules"][-1] == "2 life forever start-time now"

    def test_the_scoped_apply_sends_only_the_new_probe(self, lab):
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        url = self._commit(lab, page).get_json()["url"]
        r = lab["client"].get(url)
        apply_page = r.get_data(as_text=True)
        assert r.status_code == 200, apply_page[:300]
        assert "<h1>Send the IP SLA probes</h1>" in apply_page
        prog = re.search(r'<pre class="apply-program">([^<]*)</pre>', apply_page).group(1)
        lines = html_mod.unescape(prog).splitlines()
        assert lines[0] == "ip sla 2" and "ip sla schedule 2 life forever start-time now" in lines
        assert all(l.startswith(("ip sla", " ", "exit")) for l in lines), lines
        body = json.loads(html_mod.unescape(re.search(r"data-body='([^']*)'", apply_page).group(1)))
        assert body["scope"] == "ip_sla" and body["order"] == ["r2"]
        assert '<input type="hidden" name="scope" value="ip_sla">' in apply_page

    def test_a_plan_that_moved_is_refused_with_nothing_committed(self, lab):
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        before = _head(lab)
        r = self._commit(lab, page, fingerprint="moved")
        assert r.status_code == 409 and "changed since they were shown" in r.get_json()["error"]
        assert _head(lab) == before

    def test_nothing_ticked_commits_nothing(self, lab):
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        before = _head(lab)
        r = self._commit(lab, page, picked=[])
        assert r.status_code == 409 and "no suggested probe was ticked" in r.get_json()["error"]
        assert _head(lab) == before

    def test_an_uncommitted_host_vars_change_is_refused_by_name(self, lab):
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        path = os.path.join(lab["repo"], "host_vars", "s4.yml")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("# a hand edit nobody committed\n")
        before = _head(lab)
        r = self._commit(lab, page)
        assert r.status_code == 409 and "host_vars/s4.yml" in r.get_json()["error"]
        assert _head(lab) == before

    def test_a_failed_commit_puts_every_file_back(self, lab, monkeypatch):
        from modules.nsot import hostvars
        assert _policy(lab).status_code == 200
        _r, page = _page(lab)
        committed, _state = hostvars.committed_at_head(lab["repo"], "r2")
        monkeypatch.setattr("modules.nsot.repo.save_host_vars",
                            lambda *a, **k: {"ok": False, "error": "disk full"})
        r = self._commit(lab, page)
        err = r.get_json()["error"]
        assert r.status_code == 409 and "disk full" in err and "put back" in err
        with open(os.path.join(lab["repo"], "host_vars", "r2.yml"), encoding="utf-8") as fh:
            assert fh.read() == committed


class TestTheScopeIsCarried:
    def test_an_unknown_scope_is_refused_never_read_as_the_profile(self, lab):
        r = lab["client"].get("/v2/monitoring/apply?list=Lab&device=r2&scope=<b>x</b>")
        assert r.status_code == 400
        assert "unknown scope" in r.get_data(as_text=True) and "<b>" not in r.get_data(as_text=True)
        r = lab["client"].post("/v2/monitoring/apply/confirm", json={
            "list": "Lab", "scope": "everything", "order": ["r2"],
            "confirmations": {"r2": "x"}, "command_hashes": {"r2": "y"}})
        assert r.status_code == 400 and "unknown scope" in r.get_json()["error"]

    def test_the_confirm_hands_its_scope_to_the_job(self, lab, monkeypatch):
        seen = {}
        monkeypatch.setattr("modules.deploy_job.start",
                            lambda *a, **k: seen.update(k) or "job1")
        r = lab["client"].post("/v2/monitoring/apply/confirm", json={
            "list": "Lab", "scope": "ip_sla", "order": ["r2"],
            "confirmations": {"r2": "x"}, "command_hashes": {"r2": "y"}})
        assert r.status_code == 202 and seen["scope"] == "ip_sla"


class TestCoverageLinksHere:
    def test_a_device_with_no_probe_is_linked_to_the_ip_sla_page(self, lab, monkeypatch):
        from modules.nsot import listref
        assert _policy(lab).status_code == 200
        # Coverage reads the inventory itself (test_coverage_page's way in).
        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [
            {"hostname": "r2", "ip": "203.0.113.12", "platform": "cisco_iosxe"},
            {"hostname": "s4", "ip": "203.0.113.24", "platform": "cisco_ios"}])
        r = lab["client"].get("/v2/monitoring/coverage/table")
        page = html_mod.unescape(r.get_data(as_text=True))
        assert "1 device(s) run no probe (s4)" in page
        assert "/v2/monitoring/ip-sla?list=Lab&device=s4" in page
        assert "review the suggested probes on the IP SLA page" in page


class TestTheShippedClient:
    def _call(self, expr):
        import dukpy
        with open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8") as fh:
            js = fh.read()
        return dukpy.evaljs("var window = {};\n" + js + "\n" + expr)

    def test_the_body_carries_the_ticked_keys_and_the_policy_fields(self):
        base = json.dumps({"list": "Lab", "devices": ["s4"], "fingerprint": "f"})
        got = json.loads(self._call(
            f"window.NMAS_APPLY.ipslaBody({json.dumps(base)}, '', '', ['r2:2'])"))
        assert got == {"list": "Lab", "devices": ["s4"], "fingerprint": "f", "picked": ["r2:2"]}
        got = json.loads(self._call(
            "window.NMAS_APPLY.ipslaBody('{\"list\": \"Lab\"}', 'peers', '60', null)"))
        assert got == {"list": "Lab", "policy": "peers", "frequency": "60"}

    def test_nothing_ticked_is_sent_as_an_empty_list_not_omitted(self):
        got = json.loads(self._call("window.NMAS_APPLY.ipslaBody('{}', '', '', [])"))
        assert got == {"picked": []}

    def test_a_commit_goes_to_the_scoped_apply_and_a_policy_redraws(self):
        assert self._call("window.NMAS_APPLY.ipslaOutcome(200, {ok: true, url: '/v2/x'})") == {
            "go": "/v2/x", "reload": False, "error": ""}
        assert self._call("window.NMAS_APPLY.ipslaOutcome(200, {ok: true})") == {
            "go": "", "reload": True, "error": ""}

    def test_a_refusal_is_said_in_the_servers_words(self):
        assert self._call("window.NMAS_APPLY.ipslaOutcome(409, {ok: false, error: 'moved'})") == {
            "go": "", "reload": False, "error": "moved"}
        assert self._call("window.NMAS_APPLY.ipslaOutcome(500, null)")["error"] == \
            "refused (HTTP 500)"
