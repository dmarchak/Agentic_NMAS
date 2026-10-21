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

    def test_the_literal_read_is_the_pattern_it_replaced(self):
        """C855: `_intent_of` compiled `(?:^no: |; )<host> \\(([^)]*)\\)` for each device it
        was asked about (past `re`'s 512-entry cache, every time). Its literal read answers
        as that pattern did, on trailers built to reach its corners: a host that prefixes
        another or holds a pattern character, a nested or missing parenthesis, a host named
        twice, a `; ` first, a newline."""
        import random

        from modules.device_list import _intent_of

        def pattern(host, trailer):                # the reader before C855, verbatim
            m = re.search(rf"(?:^no: |; ){re.escape(host)} \(([^)]*)\)", trailer)
            return m.group(1) if m else None

        hosts = ["r1", "r10", "r1.x", "a+b", "s(1)", "x)y", "e f"]
        details = ["+1 -1", "-2", "unknown (no committed intent)", "unknown", "", "a\nb",
                   "unknown (cut", "+3"]
        rng, seen = random.Random(855), set()
        for _ in range(4000):
            parts = [f"{rng.choice(hosts)} ({rng.choice(details)})"[:rng.choice((99, 99, 6))]
                     for _ in range(rng.randint(1, 4))]
            trailer = rng.choice(("no: ", "no: ", "; ", "")) + rng.choice(("; ", ";", ", ")
                                                                        ).join(parts)
            for host in hosts:
                want = pattern(host, trailer)
                got = _intent_of(host, trailer)
                seen.add(got["state"])
                if want is None:
                    assert got == {"state": "at_intent", "words": "at intent"}, (host, trailer)
                elif want.startswith("unknown"):
                    why = want[len("unknown"):].strip().lstrip("(").strip()
                    assert got == {"state": "unknown", "words": "unknown",
                                   "why": why or "not established"}, (host, trailer, got)
                else:
                    assert got == {"state": "departs", "words": f"departs ({want})"}, (
                        host, trailer, got)
        assert seen == {"at_intent", "departs", "unknown"}


def _log(*records):
    """`git log`'s output in `last_measured`'s format: each record (sha, ct, Source,
    Device-Name, Devices, Devices-Measured, Intent-Match, Baseline)."""
    return "".join("\x1f".join(r) + "\x1e\n" for r in records)


class TestOneDevicesMeasurement:
    """C855: the device page asks `last_measured` for ITS device (*only*) and gets exactly
    that device's entry of the whole answer, by the same rule over the same log: every
    trailer shape a save wrote, a host that prefixes another, a host named twice, a name
    with a comma or a space, a device the log never measured."""

    LOG = _log(
        ("a" * 40, "500", "save_all", "", "r2", "r1,r2, r3",
         "no: r2 (+1 -1); r3 (unknown (no committed intent))", ""),
        ("b" * 40, "400", "capture", "r4", "", "", "yes (1 of 1)", "earned 2026-10-01"),
        ("c" * 40, "300", "pipeline", "", "r5, r1 ,r6", "", "no: r6 (-2)", ""),
        ("d" * 40, "200", "save", "", "r7", " , ", "no: r7 (+1)", ""),
        ("e" * 40, "150", "repair", "r10,r1x", "", "r10,r1x,r8,r8", "no: r10 (+3)", ""),
        ("f" * 40, "100", "", "", "", "", "", ""),
        ("1" * 40, "50", "onboarding", "r9", "", "", "", ""))

    def test_one_device_is_its_entry_of_all(self, monkeypatch):
        from modules import device_list

        monkeypatch.setattr("modules.nsot.repo.git", lambda *_a, **_k: (0, self.LOG, ""))
        every, err = device_list.last_measured("/nowhere")
        assert err == "" and set(every) == {"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8",
                                            "r9", "r10", "r1x"}, every
        assert every["r1"]["sha"] == "aaaaaaa" and every["r6"]["changed"] is True
        assert every["r1"]["changed"] is False and every["r4"]["baseline"] is True
        for host in sorted(every) + ["r11", "r", "", " r1", "r1,r2", "r1 "]:
            got = device_list.last_measured("/nowhere", only=host)
            assert got == (({host: every[host]} if host in every else {}), ""), host

    def test_an_unreadable_log_is_its_error_either_way(self, monkeypatch):
        from modules import device_list

        monkeypatch.setattr("modules.nsot.repo.git", lambda *_a, **_k: (128, "", "bad"))
        assert device_list.last_measured("/nowhere", only="r1") == ({}, "bad")


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
        """The scale rule: five git reads for two devices and for sixty (the golden history,
        the measurements, committed intent, and since C532 what moved intent since each
        measurement and the order to judge it by)."""
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
        assert two == calls == ["log", "log", "ls-tree", "log", "rev-list"], (two, calls)

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


class TestAPendingRowReadsItsProgress:
    """C1477 (the operator, 2026-10-21, R6's redo): the list said "awaiting DHCP · pending: not
    reached yet" for a ZTP device whose page said "fetched 12 times" and "Answering: ready to
    Verify". A pending row reads the onboarding-progress reader's stored value as the page
    does (its ZTP stage and its probe's answer), ONE read for every pending row, says ZTP for a
    ZTP device and the value's age, and its fragment redraws on `pending`. The stored value is
    made by the reader's own code (`onboarding_progress.read`) with the device's answers at its
    two seams, as tests/test_onboarding_progress.py does."""

    CREATED = "2026-10-21T01:50:00Z"
    VALUE_AT = "2026-10-21T02:14:10Z"
    R7 = {"name": "r7", "address_source": "ztp", "mgmt_ip": "", "mgmt_mac": "52:54:00:00:07:01",
          "reserved_address": "192.0.2.17", "onboarded_at": CREATED, "state": "in_flight"}
    R8 = {"name": "r8", "address_source": "static", "mgmt_ip": "192.0.2.18",
          "onboarded_at": CREATED, "state": "in_flight"}
    FETCHED = ("fetched its config 12 time(s) between 2026-10-21T02:01:13Z and "
               "2026-10-21T02:12:40Z (sha256 0123456789ab); next, Verify must reach it over "
               "SSH with the staged credential")

    def _pending(self, monkeypatch, *rows):
        monkeypatch.setattr("modules.nsot.manifest.pending_devices",
                            lambda repo: [dict(r) for r in rows])

    def _stored(self, monkeypatch, rows, answers=True, stage="fetched_not_reached"):
        """The reader's store holding *rows*' reads; returns the list of reads asked of it."""
        from modules import reader_job
        from modules.readers import onboarding_progress as OP

        def probe(ip):
            return (True, "accepted a TCP connection on port 22 within 2 s") if answers else (
                False, "answered neither ICMP nor TCP 22 within 2 s each")
        value = OP.read(pop=[("Lab", dict(r)) for r in rows], clock=lambda: 1_792_550_050.0,
                        progress=lambda row, list_name="": {"stage": stage,
                                                            "summary": self.FETCHED},
                        probe=probe)
        asked, real = [], reader_job.read_cached

        def cached(name):
            if name != OP.READER_NAME:
                return real(name)
            asked.append(name)
            return {"state": "ok", "doc": {"last_good": {"value": value,
                                                         "value_at": self.VALUE_AT}}}
        monkeypatch.setattr(reader_job, "read_cached", cached)
        return asked

    def _rows(self):
        from modules import device_list
        return {r["name"]: r for r in device_list.listing(_ref())["rows"]}

    def test_a_ztp_device_that_fetched_and_answers_says_so_with_its_age(self, inv, monkeypatch):
        self._pending(monkeypatch, self.R7)
        self._stored(monkeypatch, [self.R7])
        r7 = self._rows()["r7"]
        assert r7["intent"]["words"] == "answering: ready to Verify", r7["intent"]
        assert "fetched its config 12 time(s)" in r7["intent"]["why"]
        assert "accepted a TCP connection on port 22" in r7["intent"]["why"]
        assert r7["address"] == "awaiting ZTP (192.0.2.17)", "a ZTP device said DHCP"
        assert r7["progress"] == {"at": self.VALUE_AT}

    def test_fetched_and_not_answering_is_its_stage(self, inv, monkeypatch):
        self._pending(monkeypatch, self.R7, self.R8)
        self._stored(monkeypatch, [self.R7, self.R8], answers=False)
        rows = self._rows()
        assert rows["r7"]["intent"]["words"] == "ZTP: fetched its config; not answering yet"
        assert rows["r8"]["intent"]["words"] == "pending: not answering yet"
        assert rows["r8"]["address"] == "192.0.2.18"

    def test_a_read_of_an_earlier_device_of_the_name_is_not_its_progress(self, inv,
                                                                         monkeypatch):
        """C1476's class: the stored read was made for an r7 created before this one."""
        self._pending(monkeypatch, self.R7)
        self._stored(monkeypatch, [dict(self.R7, onboarded_at="2026-10-20T15:00:00Z")])
        r7 = self._rows()["r7"]
        assert r7["intent"]["words"] == "pending: not read yet", r7["intent"]
        assert "since its Create" in r7["intent"]["why"]

    def test_no_stored_value_is_said_as_that(self, inv, monkeypatch):
        from modules import reader_job
        self._pending(monkeypatch, self.R7)
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {
            "state": "absent", "doc": None, "why": "the reader has never run"})
        r7 = self._rows()["r7"]
        assert r7["intent"] == {"state": "pending", "words": "pending: not read yet",
                                "why": "the reader has never run"}
        assert r7["progress"] is None

    def test_one_read_for_every_pending_row(self, inv, monkeypatch):
        many = [dict(self.R8, name=f"p{i}", mgmt_ip=f"192.0.2.{100 + i}") for i in range(30)]
        self._pending(monkeypatch, self.R7, *many)
        asked = self._stored(monkeypatch, [self.R7, *many])
        rows = self._rows()
        assert asked == ["onboarding-progress"], asked
        assert sum(r["intent"]["words"] == "answering: ready to Verify"
                   for r in rows.values()) == 31

    def test_the_fragment_draws_the_words_and_the_values_age(self, inv, monkeypatch):
        self._pending(monkeypatch, self.R7)
        self._stored(monkeypatch, [self.R7])
        html = inv["client"].get("/v2/devices/table").get_data(as_text=True)
        assert "answering: ready to Verify" in html and "awaiting ZTP (192.0.2.17)" in html
        assert f'read <time class="stamp" datetime="{self.VALUE_AT}"' in html
        assert "nmas:pending from:body" in re.search(r'hx-trigger="([^"]*)"', html).group(1)


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
        # inventory: a drained mark; intent and templates: what an intent state is judged
        # against moved (C532), so the state becomes "intent changed since measured"; pending:
        # a pending onboarding's progress moved (C1477, the onboarding-progress reader).
        assert keys == ["reachability", "goldens", "intent", "templates", "inventory", "pending"]
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
        from tests.v2_confirm import post_confirm
        r = post_confirm(inv["client"], "/v2/monitoring/apply/confirm", {
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


NTP = "ntp server 192.0.2.123"


def _ntp_into_intent(lab, host="r2"):
    """A real intent commit: *host*'s committed intent gains the NTP server."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars
    hv = hostvars.read_committed(lab["repo"], host)
    hv["ntp_servers"] = list(hv.get("ntp_servers") or []) + ["192.0.2.123"]
    hostvars.write_committed(lab["repo"], hv)
    assert save_host_vars("Lab", [host], actor="t", source="extraction")["ok"]


def _commit_file(lab, rel, text):
    """A real commit of one file through `repo.commit` (its config check included)."""
    from modules.nsot import repo as R
    path = os.path.join(lab["repo"], rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with R.repo_lock(lab["repo"]):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        assert R.git(lab["repo"], "add", "--", rel)[0] == 0
        rc, _sha, err = R.commit(lab["repo"], f"test: {rel}\n\nSource: test\nActor: t\n",
                                 list_name="Lab", paths=[rel], publish_now=False)
    assert rc == 0, err


class TestOneIntentState:
    """C532: the Devices list said s1 "departs (+1)" from its last measurement's trailer while
    s1's page, comparing live, said it matched: an intent commit after the measurement left the
    list drawing a stale departure. ONE function (`device_list.intent_state`) decides a device's
    intent state, and the list's row and the device page are both drawn from it. On a real
    repository; the expected words come from git and from the commits each step made."""

    def _both(self, inv, host="r2"):
        """(the list's row state, the device page's state, the device page's HTML)."""
        from modules import device_page
        from modules.device_list import listing
        row = {r["name"]: r for r in listing(_ref())["rows"]}[host]["intent"]
        dev = next(dict(r) for r in inv["rows"] if r["hostname"] == host)
        page = device_page.records(_ref(), dev)["intent_state"]
        html = inv["client"].get(f"/v2/device/{host}").get_data(as_text=True)
        return row, page, html

    def _texts(self, inv):
        return {"r2": inv["captured"].replace("\nend", f"\n{NTP}\nend"), "r6": inv["r6"]}

    def test_a_stale_departure_is_said_by_both_and_a_new_measurement_clears_it(self, inv):
        texts = self._texts(inv)
        # 1. A golden that departs: r2 runs an NTP server its intent lacks.
        _capture("r2", texts["r2"])
        row, page, _html = self._both(inv)
        assert row == page and row["state"] == "departs", (row, page)
        measured = _git(inv["repo"], "log", "-1", "--format=%h %ct", "--", "golden/r2.cfg").split()
        # 2. An intent commit after it: the trailer's departure is no longer known to be true.
        _ntp_into_intent(inv)
        intent = _git(inv["repo"], "log", "-1", "--format=%h", "--", "host_vars/r2.yml").strip()
        row, page, html = self._both(inv)
        assert row == page, (row, page)
        assert row["state"] == "intent_moved" and row["words"] == "intent changed since measured"
        assert row["recorded"]["state"] == "departs"
        assert row["why"].startswith(
            f"its committed intent (host_vars/r2.yml) changed in {intent} at "), row["why"]
        assert f"after its last measurement ({measured[0]}, " in row["why"], row["why"]
        # The device page draws that state and its live comparison, and says which is which.
        assert "<dt>Intent state</dt>" in html and "intent changed since measured" in html
        assert "the Intent check compares it now" in html
        assert "<strong>Intent</strong>: matches its committed intent" in html
        # The Overview redraws when what decides the state moves.
        trigger = re.search(r'id="overview"[^>]*hx-trigger="([^"]*)"', html, re.S).group(1)
        assert {"goldens", "intent", "templates"} <= set(re.findall(r"nmas:(\w+) from:body",
                                                                    trigger)), trigger
        table = inv["client"].get("/v2/devices/table").get_data(as_text=True)
        assert ">intent changed since measured</span>" in table and ">departs (" not in table
        assert "; that measurement read departs (-1)\"" in table     # what it recorded, on hover
        # 3. A new measurement that matches: both say "at intent".
        out = _save_all(inv, texts)
        assert out.get("commit"), out
        row, page, html = self._both(inv)
        assert row == page == {"state": "at_intent", "words": "at intent"}, (row, page)
        assert "intent changed since measured" not in html

    def test_commits_in_one_second_are_ordered_by_history(self, inv, monkeypatch):
        """An intent edit and the capture after it often share a commit time: their place in
        history decides, never the conservative tie."""
        monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-10-16T12:00:00+0000")
        texts = self._texts(inv)
        _capture("r2", texts["r2"])
        _ntp_into_intent(inv)
        row, page, _html = self._both(inv)
        assert row == page and row["state"] == "intent_moved", (row, page)
        _save_all(inv, texts)
        times = set(_git(inv["repo"], "log", "-3", "--format=%ct").split())
        assert len(times) == 1, times                 # the three commits share one second
        row, page, _html = self._both(inv)
        assert row == page == {"state": "at_intent", "words": "at intent"}, (row, page)

    def test_the_template_library_moves_every_device_and_an_approval_moves_none(self, inv):
        from modules.nsot import templates_repo
        texts = self._texts(inv)
        _ntp_into_intent(inv)
        _save_all(inv, texts)
        before = {h: self._both(inv, h)[0]["state"] for h in ("r2", "r6")}
        assert "intent_moved" not in before.values(), before
        # Approving a template renders nothing differently.
        _commit_file(inv, "templates/.approvals.json", '{"approvals": {}}\n')
        assert {h: self._both(inv, h)[0]["state"] for h in ("r2", "r6")} == before
        # An edit to the library does: every device's recorded state may no longer hold.
        rel = templates_repo.template_for_device(inv["repo"], "r2", "cisco_iosxe")
        body = templates_repo.read_template(inv["repo"], rel)
        _commit_file(inv, f"templates/{rel}", body + "{# C532 #}\n")
        for host in ("r2", "r6"):
            row, page, _html = self._both(inv, host)
            assert row == page and row["state"] == "intent_moved", (host, row, page)
            assert row["why"].startswith("the template library changed in "), row["why"]

    def test_a_truncated_read_of_intent_commits_says_not_established(self, inv, monkeypatch):
        """A read that returns its whole bound may be truncated: a device measured before its
        oldest commit and not seen in it says so, never "at intent"."""
        from modules import device_list
        texts = self._texts(inv)
        _save_all(inv, texts)
        _ntp_into_intent(inv, "r6")
        _ntp_into_intent(inv, "r2")
        monkeypatch.setattr(device_list, "INTENT_BOUND", 1)
        r6, page6, _html = self._both(inv, "r6")
        assert r6 == page6 and r6["state"] == "unknown", r6
        assert "is not established: the read of intent commits reaches back 1 commits" in r6["why"]
        r2, _page, _html = self._both(inv, "r2")
        assert r2["state"] == "intent_moved", r2

    def test_after_orders_by_history_then_by_time(self):
        from modules.device_list import _after
        a = {"commit": "a" * 40, "at": 100}
        b = {"commit": "b" * 40, "at": 100}
        assert _after(a, b, {"a" * 40: 0, "b" * 40: 1}) is True
        assert _after(a, b, {"a" * 40: 1, "b" * 40: 0}) is False
        assert _after(a, b, {"a" * 40: 0}) is True       # b older than the window
        assert _after(a, b, {"b" * 40: 0}) is False      # a older than the window
        assert _after(a, a, {}) is False                 # one commit is not after itself
        assert _after(dict(a, at=99), b, {}) is False
        assert _after(dict(a, at=101), b, {}) is True
        assert _after(a, b, {}) is True                  # a tie nothing orders: said as moved
