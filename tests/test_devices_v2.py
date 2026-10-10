"""The v2 Devices list (NSOT_GUI_BRIEF 3.3; step 4), from `modules/device_list`.

On test_profile_apply's lab (r2's REAL config and intent; r6 in its real
shape), with real golden commits whose `Intent-Match:` trailers `save_golden`
computes. The list costs a FIXED number of reads whatever its size (the
brief's scale rule): one bounded `git log` over `golden/`, one over the commits
carrying `Intent-Match:`, and one `git ls-tree` over `host_vars/`, never a read
per device. A device's intent state is its state at its last MEASUREMENT (a Save
All that found it unchanged included), and says which and when.
"""

import os
import re

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R6 = {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}


@pytest.fixture
def inv(lab, monkeypatch):
    rows = [dict(R2), dict(R6)]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(r) for r in rows])
    lab["rows"] = rows
    return lab


def _ref():
    from modules.nsot import listref
    return listref.resolve("Lab")


def _capture(host, text):
    """A real capture commit: `save_golden` computes its Intent-Match trailer
    against the intent committed NOW."""
    from modules.nsot.repo import GoldenItem, save_golden
    ip = {"r2": R2["ip"], "r6": R6["ip"]}[host]
    out = save_golden("Lab", [GoldenItem(host, text, ip, platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out


class TestTheTrailerIsRead:
    def test_each_shape_save_golden_writes(self):
        from modules.device_list import _intent_of
        assert _intent_of("r2", "yes (9 of 9)")["state"] == "at_intent"
        assert _intent_of("r2", "no: r2 (+1 -1)") == {"state": "departs", "words": "departs (+1 -1)"}
        assert _intent_of("r6", "no: r2 (+1 -1); r6 (-1)")["words"] == "departs (-1)"
        assert _intent_of("r6", "no: r2 (+1 -1)")["state"] == "at_intent"     # not named: matched
        assert _intent_of("r2", "no: r2 (unknown (no committed intent))")["state"] == "unknown"
        # A short word in the row; the reason, whole, on its hover (the operator, 2026-10-02).
        got = _intent_of("r2", "no: r2 (unknown (no committed intent: nothing says what "
                               "this device should be))")
        assert got["words"] == "unknown"
        assert got["why"] == "no committed intent: nothing says what this device should be"
        assert _intent_of("r2", "")["state"] == "unrecorded"
        # A name that is a prefix of another is not that other.
        assert _intent_of("r1", "no: r10 (+1)")["state"] == "at_intent"


class TestTheListing:
    def test_a_departing_capture_reads_departs_as_of_its_last_capture(self, inv):
        from modules.device_list import listing
        _capture("r6", inv["r6"].replace("\nend", "\nlogging buffered 8192\nend"))
        # r2: an intent edit (an NTP server) and a capture that carries it, so
        # its newest golden commit records it AT intent (its first golden
        # predates the intent).
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        hv = hostvars.read_committed(inv["repo"], "r2")
        hv["ntp_servers"] = list(hv.get("ntp_servers") or []) + ["192.0.2.123"]
        hostvars.write_committed(inv["repo"], hv)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        _capture("r2", inv["captured"].replace("\nend", "\nntp server 192.0.2.123\nend"))
        d = listing(_ref())
        rows = {r["name"]: r for r in d["rows"]}
        assert rows["r6"]["intent"]["state"] == "departs"
        # The device holds a line its intent lacks: "-1" in the trailer's words.
        assert rows["r6"]["intent"]["words"] == "departs (-1)"
        assert rows["r6"]["measured"]["words"] == "a capture, golden changed"
        assert rows["r2"]["intent"] == {"state": "at_intent", "words": "at intent"}
        assert rows["r6"]["measured"]["iso"] and rows["r6"]["platform"] == "cisco_iosxe"
        assert d["total"] == 2 and d["counts"]["departs"] == 1 and d["counts"]["at_intent"] == 1

    def test_no_intent_and_no_golden_are_their_own_states(self, inv):
        from modules.device_list import listing
        inv["rows"].append({"hostname": "r9", "ip": "192.0.2.9", "platform": "cisco_ios"})
        rows = {r["name"]: r for r in listing(_ref())["rows"]}
        assert rows["r9"]["intent"]["state"] == "no_intent" and rows["r9"]["measured"] is None

    def test_the_reads_are_fixed_whatever_the_size(self, inv, monkeypatch):
        """The scale rule: three git reads for two devices and for sixty."""
        from modules import device_list
        from modules.nsot import repo as R
        real, calls = R.git, []

        def counting(*a, **k):
            calls.append(a[1] if len(a) > 1 else "")
            return real(*a, **k)
        monkeypatch.setattr(R, "git", counting)
        device_list.listing(_ref())
        two = list(calls)
        calls.clear()
        inv["rows"] += [{"hostname": f"x{i}", "ip": f"192.0.2.{i}", "platform": "cisco_ios"}
                        for i in range(60)]
        device_list.listing(_ref())
        assert two == calls == ["log", "log", "ls-tree"], (two, calls)

    def test_an_unreadable_history_is_unknown_never_no_golden(self, inv, monkeypatch):
        from modules import device_list
        from modules.nsot import repo as R
        real = R.git
        monkeypatch.setattr(R, "git", lambda *a, **k: (128, "", "fatal: bad object")
                            if len(a) > 1 and a[1] == "log" else real(*a, **k))
        d = device_list.listing(_ref())
        assert "the golden history could not be read (fatal: bad object)" in d["error"]
        assert {r["intent"]["state"] for r in d["rows"]} == {"unknown"}

    def test_pending_onboardings_are_rows(self, inv, monkeypatch):
        from modules import device_list
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [{
            "name": "r7", "mgmt_ip": "", "reserved_address": "203.0.113.17", "state": "in_flight"}])
        rows = {r["name"]: r for r in device_list.listing(_ref())["rows"]}
        assert rows["r7"]["pending"] and rows["r7"]["status"]["words"] == "Pending onboarding"
        assert rows["r7"]["address"] == "awaiting DHCP (203.0.113.17)"

    def test_search_and_filters(self, inv):
        from modules.device_list import listing
        _capture("r6", inv["r6"].replace("\nend", "\nlogging buffered 8192\nend"))
        assert [r["name"] for r in listing(_ref(), q="R6")["rows"]] == ["r6"]
        assert [r["name"] for r in listing(_ref(), q="203.0.113.12")["rows"]] == ["r2"]
        assert [r["name"] for r in listing(_ref(), state="departs")["rows"]] == ["r6"]
        assert listing(_ref(), platform="cisco_ios")["rows"] == []


def _save_all(lab, texts):
    """A real Save All over the given captures, the whole two-device inventory."""
    from modules.nsot.repo import GoldenItem, save_golden
    ip = {"r2": R2["ip"], "r6": R6["ip"]}
    return save_golden("Lab", [GoldenItem(h, t, ip[h], platform="cisco_iosxe")
                               for h, t in texts.items()],
                       source="save_all", actor="t", inventory_size=2)


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


class TestTheLastMeasurement:
    """The operator, 2026-10-02: the list read only golden commits, so a Save All
    that found a device UNCHANGED (the best evidence there is) did not count, its
    intent state was its last CHANGE's and its age that change's. A measurement
    is any save that read the device; expected values come from git directly."""

    def _base(self, inv):
        r6 = inv["r6"].replace("\nend", "\nlogging buffered 8192\nend")
        _capture("r6", r6)
        assert "r2.cfg" in _git(inv["repo"], "ls-tree", "--name-only", "HEAD", "golden/")
        return {"r2": inv["captured"], "r6": r6}

    def test_a_save_all_that_changed_nothing_is_the_last_measurement(self, inv):
        from modules.device_list import listing
        texts = self._base(inv)
        golden_sha = _git(inv["repo"], "log", "-1", "--format=%h", "--", "golden/r6.cfg").strip()
        out = _save_all(inv, texts)
        assert out["decision_only"] and out["changed"] == [], out
        decision = out["commit"][:7]
        rows = {r["name"]: r for r in listing(_ref())["rows"]}
        for host in ("r2", "r6"):
            assert rows[host]["measured"]["sha"] == decision, rows[host]
            assert rows[host]["measured"]["words"] == "Save All, no change"
            assert rows[host]["measured"]["changed"] is False
        assert rows["r6"]["golden_changed"]["sha"] == golden_sha != decision

    def test_the_intent_state_is_the_measurement_s_not_the_last_change_s(self, inv):
        """r2's golden was captured AT intent; intent then gains an NTP server, and a
        Save All reads r2 unchanged: r2 now departs (+1), which only that Save All
        knows. The old reader drew "at intent" from the older golden commit."""
        from modules.device_list import listing
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        texts = self._base(inv)
        _save_all(inv, texts)
        rows = {r["name"]: r for r in listing(_ref())["rows"]}
        assert rows["r2"]["intent"]["state"] == "at_intent"
        hv = hostvars.read_committed(inv["repo"], "r2")
        hv["ntp_servers"] = list(hv.get("ntp_servers") or []) + ["192.0.2.123"]
        hostvars.write_committed(inv["repo"], hv)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        out = _save_all(inv, texts)
        trailer = _git(inv["repo"], "log", "-1", "--format=%(trailers:key=Intent-Match,valueonly)",
                       out["commit"]).strip()
        assert trailer.startswith("no: r2 (+1"), trailer
        rows = {r["name"]: r for r in listing(_ref())["rows"]}
        assert rows["r2"]["intent"] == {"state": "departs", "words": "departs (+1)"}
        assert rows["r2"]["measured"]["sha"] == out["commit"][:7]

    def test_a_changing_save_all_names_every_device_it_read(self, inv):
        """r6 changes and r2 does not: `Devices:` names r6, `Devices-Measured:` both, and
        r2's last measurement is that commit with no change."""
        from modules.device_list import listing
        texts = self._base(inv)
        texts["r6"] = texts["r6"].replace("logging buffered 8192", "logging buffered 16384")
        out = _save_all(inv, texts)
        assert [c for c in out["changed"]] and out["unchanged"] == ["r2"], out
        trailers = _git(inv["repo"], "log", "-1", "--format=%(trailers)", out["commit"])
        assert "Devices: r6\n" in trailers and "Devices-Measured: r6,r2\n" in trailers, trailers
        rows = {r["name"]: r for r in listing(_ref())["rows"]}
        assert rows["r2"]["measured"]["sha"] == out["commit"][:7]
        assert rows["r2"]["measured"]["words"].startswith("Save All, no change")
        assert rows["r6"]["measured"]["words"].startswith("Save All, golden changed")
        assert rows["r6"]["golden_changed"]["sha"] == out["commit"][:7]

    def test_the_page_draws_last_measured_with_the_golden_change_on_hover(self, inv):
        texts = self._base(inv)
        out = _save_all(inv, texts)
        html = inv["client"].get("/v2/devices/table").get_data(as_text=True)
        assert '<th scope="col">Last measured</th>' in html and "Last capture" not in html
        assert "by Save All, no change" in html
        golden_sha = _git(inv["repo"], "log", "-1", "--format=%h", "--", "golden/r6.cfg").strip()
        assert re.search(rf'title="[^"]*golden last changed [^"]*\({golden_sha}\); measurement '
                         rf'{out["commit"][:7]}"', html), html

    def test_the_overview_says_when_it_was_last_measured(self, inv):
        texts = self._base(inv)
        out = _save_all(inv, texts)
        html = inv["client"].get("/v2/device/r2").get_data(as_text=True)
        assert "<dt>Last measured</dt>" in html and "by Save All, no change" in html
        assert f"measurement {out['commit'][:7]}" in html


class TestThePage:
    def _get(self, lab, url):
        r = lab["client"].get(url)
        return r, r.get_data(as_text=True)

    def test_the_page_draws_each_row_with_its_link(self, inv):
        from modules import csp
        r, html = self._get(inv, "/v2/devices")
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        for host in ("r2", "r6"):
            assert f'<a href="/v2/device/{host}">{host}</a>' in html
        assert "<h1>Devices <span class=\"muted\">· 2</span>" in html
        assert re.search(r'<a class="nav-item active" href="/v2/devices" aria-current="page">', html)

    def test_a_search_says_how_many_it_shows(self, inv):
        _r, html = self._get(inv, "/v2/devices/table?q=r6")
        assert html.lstrip().startswith('<section class="card devices" id="devices"')
        assert "Showing 1 of 2." in html and "/v2/device/r2" not in html
        _r, html = self._get(inv, "/v2/devices/table?q=nothing")
        assert 'No device of 2 matches "nothing".' in html

    def test_it_redraws_on_keys_v2_relays(self, inv):
        from modules import invalidation
        _r, html = self._get(inv, "/v2/devices/table")
        keys = re.findall(r"nmas:(\w+) from:body", re.search(r'hx-trigger="([^"]*)"', html).group(1))
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        assert keys == ["reachability", "goldens", "inventory"]   # inventory: a drained mark
        for k in keys:
            assert k in invalidation.VOCABULARY and f"NMAS.subscribe('{k}'" in src

    def test_the_selection_opens_v2_s_deploy_for_the_ticked_devices(self, inv):
        """The deploy is the Actions menu's first row (C593, board A), on v2 since 2026-10-10
        (board B): the bar's form sends the ticked devices to Devices › Plan a deploy."""
        _r, html = self._get(inv, "/v2/devices")
        form = re.search(r'<form method="get" action="/v2/devices/deploy" class="dev-form"[^>]*>'
                         r'(.*?)</form>', html, re.S)
        assert form and 'name="device" value="r6"' in form.group(1)
        assert "data-todays-page" not in form.group(0) and "(today's page)" not in form.group(1)
        assert "Plan a deploy for the ticked devices…" in form.group(1)

    def test_the_deploy_page_plans_the_ticked_devices_whole_intent(self, inv, monkeypatch):
        """The batch Apply's page with scope `intent`: the plan's empty scope (the whole
        committed intent), a Devices crumb, and the confirm body carrying `intent`."""
        seen = {}

        def plan(list_name, order, remove=None, authorise=None, scope="x"):
            seen["scope"], seen["order"] = scope, list(order)
            return [{"device": d, "deployable": False, "blocking_reasons": ["planted"],
                     "to_add": [], "removal_warnings": []} for d in order]
        monkeypatch.setattr("routes.deploy.plan_devices", plan)
        r, html = self._get(inv, "/v2/devices/deploy?device=r6&device=r7")
        assert r.status_code == 200, html[:300]
        assert seen == {"scope": "", "order": ["r6", "r7"]}
        assert "Deploy committed intent" in html and '<a href="/v2/devices' in html
        assert '<input type="hidden" name="scope" value="intent">' in html

    def test_the_confirm_runs_the_batch_on_the_whole_intent(self, inv, monkeypatch):
        """The confirm body says `intent`; the job is started with the plan's empty scope,
        never the profile's."""
        from modules import deploy_job
        got = {}
        monkeypatch.setattr("modules.nsot.listref.exists", lambda n: True)
        monkeypatch.setattr(deploy_job, "start", lambda *a, **k: got.update(k) or "job1")
        r = inv["client"].post("/v2/monitoring/apply/confirm", json={
            "list": "Lab", "scope": "intent", "order": ["r6"],
            "confirmations": {"r6": "c"}, "command_hashes": {"r6": "h"}})
        assert r.status_code == 202, r.get_data(as_text=True)
        assert got["scope"] == ""


class TestAPendingDevicesPage:
    """The brief's pending page (3.3): a device onboarded and not yet reached
    is in no inventory by design, so its row's link must not lead to a 404
    (f1863ba drew the row and its link, and the link 404'd)."""

    PENDING = {"identity": "uid:x", "name": "r7", "mgmt_ip": "", "address_source": "dhcp",
               "mgmt_mac": "aa:bb:cc:00:02:47", "reserved_address": "203.0.113.17",
               "onboarded_at": "2026-10-01T09:00:00Z", "age_seconds": 3600,
               "state": "in_flight", "credential_findable": True}

    def _get(self, lab, url):
        r = lab["client"].get(url)
        return r, r.get_data(as_text=True)

    def test_every_rows_link_answers(self, inv, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(self.PENDING)])
        _r, html = self._get(inv, "/v2/devices/table")
        links = re.findall(r'<a href="(/v2/device/[^"]+)">', html)
        assert "/v2/device/r7" in links and len(links) == 3
        for url in links:
            assert inv["client"].get(url).status_code == 200, url

    def test_the_pending_page_says_where_it_is_and_what_is_next(self, inv, monkeypatch):
        from modules import csp
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(self.PENDING)])
        r, html = self._get(inv, "/v2/device/r7")
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        assert "Pending onboarding: pending" in html
        assert "awaiting DHCP (Kea reservation → 203.0.113.17)" in html
        # Its three actions on v2 (cutover blocker 3), each a form carrying the network.
        for words, route in (("Verify…", "/v2/onboard/r7/verify/preview"),
                             ("Get the bootstrap config…", "/v2/onboard/r7/bootstrap"),
                             ("Abandon…", "/v2/onboard/r7/abandon/preview")):
            assert words in html and f'hx-post="{route}"' in html, words
        assert 'data-todays-page="onboard"' not in html
        assert '<a href="/v2/devices">Devices</a>' in html

    def test_a_credential_that_cannot_be_found_says_re_create(self, inv, monkeypatch):
        row = dict(self.PENDING, credential_findable=False, state="overdue")
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [row])
        _r, html = self._get(inv, "/v2/device/r7")
        assert "Abandon and re-create it: nothing has reached the device" in html

    def test_a_name_neither_in_the_inventory_nor_pending_is_still_a_404(self, inv, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [dict(self.PENDING)])
        assert inv["client"].get("/v2/device/r99").status_code == 404
