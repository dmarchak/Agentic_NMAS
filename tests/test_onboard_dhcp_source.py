"""DHCP as a stated address SOURCE, with the reservation as a PRECONDITION.

Two design decisions the tests exist to hold:

**A source, not an "address optional" flag.** `render_bootstrap()` refuses an
empty address because the failure it prevents is silent — the device boots,
reports healthy, answers its console, and is onboardable by nothing. A checkbox
would turn that refusal into something a person switches off, after which *"I
meant DHCP"* and *"I forgot the address"* look identical from the wizard.

**The reservation is checked at plan time and refused, not accepted and
verified later.** A dynamic lease is correct on the day it is recorded and
wrong at some renewal nothing is watching: the manifest, the CSV and NetBox
would all agree with each other and all disagree with the device. That is the
two-stores-disagreeing shape with a clock attached.
"""

import pytest


from modules.integrations.kea import KeaIntegration
from modules.nsot.bootstrap_config import (ManagementAddressRequired,
                                           manager_interface_lines)
from modules.nsot.onboard import OnboardPlan, build_plan


@pytest.fixture(autouse=True)
def _syslog_host(monkeypatch):
    """P.1: onboarding gives every device the syslog block and refuses while
    `syslog_host` is unset. Only that key is supplied; every other setting is
    read exactly as before."""
    import modules.settings_schema as ss
    real = ss.get_setting
    monkeypatch.setattr(ss, "get_setting", lambda k, *a, **kw: (
        "192.0.2.10" if k == "syslog_host" else real(k, *a, **kw)))


def _kea(entries, reachable=True, hook=False):
    """A Kea whose answers are given, not fetched."""
    client = KeaIntegration()

    def _command(command, service=None):
        if not reachable:
            return {"ok": False, "error": "Could not connect"}
        if command == "reservation-get-all":
            if not hook:
                return {"ok": False, "error": "unsupported command"}
            return {"ok": True, "result": [
                {"result": 0, "arguments": {"hosts": entries}}]}
        return {"ok": True, "result": [{"result": 0, "arguments": {
            "Dhcp4": {"subnet4": [{"reservations": entries}]}}}]}

    client.command = _command
    return client


RESERVED = [{"hw-address": "aa:bb:cc:dd:ee:01", "ip-address": "10.255.0.40"}]


class TestTheReservationIsThreeStatesNotTwo:
    """Absent and unreadable are different facts. A precondition that could
    not be checked has not passed."""

    def test_a_reservation_is_found_from_the_config(self):
        out = _kea(RESERVED).reservation_for("aa:bb:cc:dd:ee:01")
        assert out["state"] == KeaIntegration.RESERVED
        assert out["address"] == "10.255.0.40"
        assert out["source"] == "config"

    def test_the_hook_is_preferred_when_present(self):
        out = _kea(RESERVED, hook=True).reservation_for("aa:bb:cc:dd:ee:01")
        assert out["state"] == KeaIntegration.RESERVED
        assert out["source"] == "host_cmds"

    def test_a_missing_reservation_is_not_reserved(self):
        out = _kea(RESERVED).reservation_for("aa:bb:cc:dd:ee:99")
        assert out["state"] == KeaIntegration.NOT_RESERVED

    def test_an_unreachable_kea_is_UNKNOWN_not_not_reserved(self):
        """**The distinction that matters.** Collapsing these would let an
        unreachable Kea read as "no reservation", which is a different
        instruction to the operator."""
        out = _kea(RESERVED, reachable=False).reservation_for("aa:bb:cc:dd:ee:01")
        assert out["state"] == KeaIntegration.UNKNOWN
        assert "Could not connect" in out["error"]

    def test_the_mac_is_compared_case_and_separator_insensitively(self):
        for spelling in ("AA:BB:CC:DD:EE:01", "aa-bb-cc-dd-ee-01"):
            assert _kea(RESERVED).reservation_for(spelling)["state"] == \
                KeaIntegration.RESERVED


class TestTheGeneratorTakesDhcpAsASourceNotAnAbsence:

    def test_dhcp_emits_ip_address_dhcp(self):
        lines = manager_interface_lines("cisco_iosxe", interface="Gi2",
                                        address="dhcp", mask="dhcp")
        assert " ip address dhcp" in lines
        assert " no shutdown" in lines

    def test_a_missing_address_still_refuses(self):
        """**The floor.** The refusal is narrowed to `static`, not removed —
        and the state it prevents is a device that boots healthy and is
        onboardable by nothing."""
        with pytest.raises(ManagementAddressRequired):
            manager_interface_lines("cisco_iosxe", interface="Gi2",
                                    address="", mask="")

    def test_a_missing_mask_still_refuses(self):
        with pytest.raises(ManagementAddressRequired):
            manager_interface_lines("cisco_iosxe", interface="Gi2",
                                    address="10.255.0.32", mask="")

    def test_dhcp_still_needs_a_chosen_interface(self):
        """On a C8000v vrnetlab owns Gi1; the source of the address changes
        nothing about that."""
        with pytest.raises(ManagementAddressRequired):
            manager_interface_lines("cisco_iosxe", interface="",
                                    address="dhcp", mask="dhcp")

    def test_dhcp_output_is_still_printable_ascii(self):
        from modules.nsot.normalize import find_non_printable

        for line in manager_interface_lines("cisco_iosxe", interface="Gi2",
                                            address="dhcp", mask="dhcp"):
            assert not find_non_printable(line), line


class TestThePreconditionRefusesAtPlanTime:

    def _plan(self, tmp_path, monkeypatch, **kw):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.nsot.onboard._name_in_manifest",
                            lambda *a: (False, True))
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox",
                            lambda *a: (False, True))
        base = dict(hostname="bp-dhcp-a", platform="cisco_iosxe",
                    list_name="probe", secret="Secret123",
                    manager_interface="Gi2", mgmt_interface="Gi1")
        base.update(kw)
        return build_plan(**base)

    def test_a_reserved_mac_is_onboardable(self, tmp_path, monkeypatch):
        """**The floor.** Without it every refusal below is satisfied by a
        plan that refuses everything."""
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:dd:ee:01", kea=_kea(RESERVED))
        assert plan.reservation_state == "reserved"
        assert plan.onboardable, plan.blocking_reasons

    def test_no_reservation_blocks_and_says_why(self, tmp_path, monkeypatch):
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:dd:ee:99", kea=_kea(RESERVED))
        assert not plan.onboardable
        reason = " ".join(plan.blocking_reasons)
        assert "no host reservation" in reason
        assert "would move at a renewal" in reason

    def test_an_unreachable_kea_blocks_too(self, tmp_path, monkeypatch):
        """A check that did not run has not passed — and the refusal says so
        rather than reporting the device as unreserved."""
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:dd:ee:01",
                          kea=_kea(RESERVED, reachable=False))
        assert not plan.onboardable
        reason = " ".join(plan.blocking_reasons)
        assert "could not be asked" in reason
        assert "unchecked precondition" in reason

    def test_dhcp_without_a_mac_blocks(self, tmp_path, monkeypatch):
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          kea=_kea(RESERVED))
        assert not plan.onboardable
        assert any("no MAC address" in r for r in plan.blocking_reasons)

    def test_static_is_completely_unchanged(self, tmp_path, monkeypatch):
        """The whole point of a stated source: the existing path does not move."""
        plan = self._plan(tmp_path, monkeypatch, mgmt_ip="203.0.113.32",
                          mgmt_mask="255.255.255.0")
        assert plan.address_source == "static"
        assert plan.reservation_state == ""
        assert plan.onboardable, plan.blocking_reasons

    def test_static_with_no_address_still_blocks(self, tmp_path, monkeypatch):
        plan = self._plan(tmp_path, monkeypatch)
        assert not plan.onboardable
        assert any("no management address" in r for r in plan.blocking_reasons)

    def test_a_raising_kea_is_unknown_not_a_crash(self, tmp_path, monkeypatch):
        class _Boom:
            def reservation_for(self, _mac):
                raise RuntimeError("kea exploded")

        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:dd:ee:01", kea=_Boom())
        assert plan.reservation_state == "unknown"
        assert not plan.onboardable


class TestTheReviewScreenMakesACheckableClaim:
    """*"assigned by DHCP"* is a claim about what will happen later, which
    nothing here would notice failing. *"assigned by Kea reservation <mac> →
    <address>"* is one this tool checked a moment ago."""

    @staticmethod
    def _plan(**kw):
        return OnboardPlan(hostname="bp-dhcp-a", platform="cisco_iosxe",
                           list_name="probe", **kw)

    def test_a_reservation_is_named_with_its_address(self):
        claim = self._plan(address_source="dhcp", mgmt_mac="aa:bb:cc:dd:ee:01",
                           reservation_state="reserved",
                           reservation_address="10.255.0.40",
                           reservation_source="config").address_claim
        assert "Kea reservation aa:bb:cc:dd:ee:01" in claim
        assert "10.255.0.40" in claim

    def test_it_never_says_the_unfalsifiable_thing(self):
        """No state may render as a bare promise about the future."""
        for kw in (dict(reservation_state="reserved",
                        reservation_address="10.255.0.40"),
                   dict(reservation_state="not_reserved"),
                   dict(reservation_state="unknown",
                        reservation_error="Could not connect")):
            claim = self._plan(address_source="dhcp",
                               mgmt_mac="aa:bb:cc:dd:ee:01", **kw).address_claim
            assert claim.strip() != "assigned by DHCP"
            assert "will be assigned" not in claim

    def test_an_unchecked_reservation_says_unchecked(self):
        claim = self._plan(address_source="dhcp", mgmt_mac="aa:bb:cc:dd:ee:03",
                           reservation_state="unknown",
                           reservation_error="Could not connect").address_claim
        assert "could not be asked" in claim
        assert "unchecked, not confirmed" in claim

    def test_a_missing_reservation_says_the_record_would_go_stale(self):
        claim = self._plan(address_source="dhcp", mgmt_mac="aa:bb:cc:dd:ee:02",
                           reservation_state="not_reserved").address_claim
        assert "NO reservation" in claim
        assert "this record would not" in claim

    def test_static_shows_the_address_and_mask(self):
        claim = self._plan(mgmt_ip="203.0.113.32",
                           mgmt_mask="255.255.255.0").address_claim
        assert claim == "203.0.113.32 255.255.255.0"

    def test_the_claim_is_in_the_summary_the_screen_reads(self):
        """A field the payload carries and the screen does not name is the
        defect the field was added to prevent."""
        summary = self._plan(address_source="dhcp",
                             mgmt_mac="aa:bb:cc:dd:ee:01",
                             reservation_state="reserved",
                             reservation_address="10.255.0.40").summary
        assert "address_claim" in summary
        assert "10.255.0.40" in summary["address_claim"]
        assert summary["address_source"] == "dhcp"


class TestOkMeansKeaDidTheThing:
    """`ok: True` around `{"result": 1}` is a lie at the envelope level.

    Measured live: `command("config-reload", service="dhcp4")` returned
    `ok: True` wrapping `result: 1, text: "service value must be a list"`, and
    the reload had not happened. Every caller that checks `result["ok"]` and
    stops there believed a refused command ran — `success` meaning *no
    exception reached the top*, for the fifth time in this project after the
    background agent's 27 runs, `bind_credentials_step`,
    `_sync_list_to_netbox_impl` and the Oxidized sync's exit code.
    """

    @staticmethod
    def _client(body, status=200, captured=None):
        import types

        client = KeaIntegration()
        client.is_configured = lambda: True

        class _Response:
            status_code = status

            @staticmethod
            def json():
                return body

        def _post(url, json=None, timeout=None):
            if captured is not None:
                captured.update(json or {})
            return _Response()

        client.session = lambda: types.SimpleNamespace(post=_post, auth=None)
        return client

    def test_a_refused_command_is_not_ok(self):
        out = self._client([{"result": 1,
                             "text": "service value must be a list"}]).command("x")
        assert out["ok"] is False
        assert "service value must be a list" in out["error"]
        assert "result 1" in out["error"]

    def test_an_unsupported_command_is_not_ok(self):
        """`reservation-get-all` without the host_cmds hook answers 2, and the
        fallback to `config-get` depends on that being a failure."""
        out = self._client([{"result": 2,
                             "text": "unsupported command"}]).command("x")
        assert out["ok"] is False

    def test_success_is_still_ok(self):
        """**The floor.** A client that refused everything would satisfy both
        assertions above."""
        assert self._client([{"result": 0, "arguments": {}}]).command("x")["ok"]

    def test_EMPTY_is_a_success_not_a_failure(self):
        """Kea answers `result: 3` for a command that worked and returned
        nothing — `lease4-get-all` on a server with no leases. Treating it as
        a failure would print "v4: unavailable" for an empty pool, which is
        the absent-versus-empty error on the monitoring card."""
        out = self._client([{"result": 3, "text": "no leases"}]).command("x")
        assert out["ok"] is True

    def test_the_service_is_coerced_to_a_list(self):
        """The Control Agent requires a list and answers `result: 1` for a
        bare string. The settings default is already a list, so only a
        hand-written call hits it — which is exactly what happened."""
        captured = {}
        self._client([{"result": 0}], captured=captured).command(
            "config-reload", service="dhcp4")
        assert captured["service"] == ["dhcp4"]

    def test_a_list_is_passed_through(self):
        captured = {}
        self._client([{"result": 0}], captured=captured).command(
            "lease4-get-all", service=["dhcp4"])
        assert captured["service"] == ["dhcp4"]

    def test_the_monitoring_card_still_counts_an_empty_server(self):
        """End to end on the regression the EMPTY rule protects."""
        client = self._client([{"result": 3, "text": "no leases"}])
        out = client.monitor()
        assert out["ok"] is True
        assert "unavailable" not in out["metrics"][0]["value"]

    def test_a_refusal_reaches_the_monitoring_card_as_a_failure(self):
        client = self._client([{"result": 1, "text": "broken"}])
        out = client.monitor()
        assert out["ok"] is False
        assert "unavailable" in out["metrics"][0]["value"]


class TestADhcpDeviceHasCompleteBootstrapParameters:
    """A device created two minutes ago reported as a legacy one, with the
    remedy *"abandon and re-create"*.

    `bootstrap_artifact()` checked `params["address"]` alone. A DHCP device has
    **no address and no mask by construction**, so its complete set —
    `source`, `interface`, `mac`, `domain` — failed a presence test written
    against the static shape, and fell through to the one explanation the check
    knew. **Sixth message in one session describing a state that did not
    occur, and the most expensive**: the remedy would have destroyed a correct
    device and produced the identical result the second time.

    Completeness is judged **per source** now.
    """

    @staticmethod
    def _repo(tmp_path, monkeypatch, bootstrap):
        import os

        from modules.nsot import hostvars, repo as _repo

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE",
                            str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        hostvars.write_committed(repo, {"hostname": "bp-dhcp-a",
                                        "bootstrap": bootstrap})
        from modules.nsot.onboard import stage_bootstrap_credential

        stage_bootstrap_credential(repo, "bp-dhcp-a", "Secret123")
        return repo

    DHCP = {"source": "dhcp", "interface": "GigabitEthernet2",
            "mac": "aa:bb:cc:00:02:40", "domain": "rcn.lab",
            "platform": "cisco_iosxe", "address": "", "mask": ""}

    def test_a_dhcp_device_re_renders(self, tmp_path, monkeypatch):
        from modules.nsot.onboard import bootstrap_artifact

        repo = self._repo(tmp_path, monkeypatch, self.DHCP)
        out = bootstrap_artifact(repo, "bp-dhcp-a")
        assert out["ok"] is True, out["reason"]
        assert " ip address dhcp" in out["config"]

    def test_it_does_not_report_the_legacy_state(self, tmp_path, monkeypatch):
        """The message whose remedy destroys a correct device."""
        from modules.nsot.onboard import bootstrap_artifact

        repo = self._repo(tmp_path, monkeypatch, self.DHCP)
        out = bootstrap_artifact(repo, "bp-dhcp-a")
        assert "abandon and re-create" not in (out["reason"] or "")

    def test_a_dhcp_device_with_no_interface_is_refused_for_THAT_reason(
            self, tmp_path, monkeypatch):
        """The interface is chosen and never defaulted, so its absence is a
        real refusal — and it must name itself rather than the legacy state."""
        from modules.nsot.onboard import bootstrap_artifact

        repo = self._repo(tmp_path, monkeypatch,
                          {**self.DHCP, "interface": ""})
        out = bootstrap_artifact(repo, "bp-dhcp-a")
        assert out["ok"] is False
        assert "no committed interface" in out["reason"]
        assert "abandon and re-create" not in out["reason"]

    def test_the_genuine_legacy_state_still_says_so(self, tmp_path, monkeypatch):
        """**The floor.** The message is correct for the state it was written
        for — no source key and no address — and must survive."""
        from modules.nsot.onboard import bootstrap_artifact

        repo = self._repo(tmp_path, monkeypatch,
                          {"platform": "cisco_iosxe", "domain": "rcn.lab"})
        out = bootstrap_artifact(repo, "bp-dhcp-a")
        assert out["ok"] is False
        assert "abandon and re-create" in out["reason"]

    def test_a_pre_source_static_device_still_re_renders(self, tmp_path,
                                                        monkeypatch):
        """A document written before `source` existed: an address present means
        static, and it must not start failing."""
        from modules.nsot.onboard import bootstrap_artifact

        repo = self._repo(tmp_path, monkeypatch,
                          {"address": "203.0.113.32", "mask": "255.255.255.0",
                           "interface": "GigabitEthernet2", "gateway": "",
                           "domain": "rcn.lab", "platform": "cisco_iosxe"})
        out = bootstrap_artifact(repo, "bp-dhcp-a")
        assert out["ok"] is True, out["reason"]
        assert " ip address 203.0.113.32 255.255.255.0" in out["config"]


class TestThePendingRowSaysWhatIsExpected:
    """*"bp-dhcp-a at — pending just now"* is honest and useless: a reader
    cannot tell a device with no address from one whose address is simply not
    known **yet**, and for a DHCP device the second is the normal state until
    it boots."""

    @staticmethod
    def _row_html(row):
        import json as _json

        import dukpy as _dukpy

        from tests.js_source import read_shipped

        source = read_shipped(
            "static/js/gen/partials__onboard_pending.1.js")
        start = source.index("function pendingBannerHtml")
        depth, i, seen = 0, source.index("{", start), False
        while i < len(source):
            if source[i] == "{":
                depth += 1
                seen = True
            elif source[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        fn = source[start:i + 1]
        stub = """
        var document = { createElement: function () { return {
          set textContent(v) { this._t = v == null ? '' : String(v); },
          get innerHTML() { return this._t.replace(/&/g,'&amp;')
            .replace(/</g,'&lt;').replace(/>/g,'&gt;'); } }; } };
        """
        # `pending`, not `devices` — the key the banner reads. Getting it
        # wrong renders the empty string, which is what a passing test
        # against no rows would also do.
        payload = {"ok": True, "list": "probe", "pending": [row]}
        return _dukpy.evaljs(
            stub + _lift_pending(source) + fn
            + f"\npendingBannerHtml({_json.dumps(payload)});")

    def test_a_dhcp_row_names_the_reservation(self):
        html = self._row_html({
            "name": "bp-dhcp-a", "mgmt_ip": "", "address_source": "dhcp",
            "mgmt_mac": "aa:bb:cc:00:02:40",
            "reserved_address": "10.255.0.40",
            "state": "in_flight", "age_seconds": 30})
        assert "awaiting DHCP" in html
        assert "10.255.0.40" in html

    def test_a_dhcp_row_without_a_recorded_reservation_says_so(self):
        html = self._row_html({
            "name": "bp-dhcp-a", "mgmt_ip": "", "address_source": "dhcp",
            "mgmt_mac": "aa:bb:cc:00:02:40", "reserved_address": "",
            "state": "in_flight", "age_seconds": 30})
        assert "awaiting DHCP" in html
        assert "aa:bb:cc:00:02:40" in html

    def test_a_static_row_still_shows_its_address(self):
        """**The floor.** The DHCP branch must not capture the static case."""
        html = self._row_html({
            "name": "bp-onboard-c", "mgmt_ip": "203.0.113.31",
            "address_source": "static", "state": "in_flight",
            "age_seconds": 30})
        assert "203.0.113.31" in html
        assert "awaiting DHCP" not in html

    def test_a_static_row_with_no_address_says_that_rather_than_nothing(self):
        html = self._row_html({
            "name": "x", "mgmt_ip": "", "address_source": "static",
            "state": "in_flight", "age_seconds": 30})
        assert "no address recorded" in html


def _lift_pending(source):
    """`pendingAgeText` and `esc`, which the banner calls."""
    out = []
    for name in ("pendingAgeText",):   # `esc` is defined inside the banner
        try:
            start = source.index(f"function {name}(")
        except ValueError:
            continue
        depth, i, seen = 0, source.index("{", start), False
        while i < len(source):
            if source[i] == "{":
                depth += 1
                seen = True
            elif source[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(source[start:i + 1])
    return "\n".join(out) + "\n"


class TestTheAddressIsDiscoveredFromTheLeaseNotTheReservation:
    """The tool never wrote this address, so phase 2 has to **discover** it.

    **A lease is a fact about the device; a reservation is a statement of
    intent.** They are normally equal — that is the point of requiring one —
    and they can differ: a reservation edited after the device leased, or a
    device still holding an older lease. So they are read separately and never
    substituted for one another.
    """

    LEASE = [{"result": 0, "arguments": {"leases": [
        {"ip-address": "10.255.0.40", "hw-address": "aa:bb:cc:00:02:40",
         "hostname": "bp-dhcp-a", "state": 0, "expire": 9e9}]}}]

    def _kea(self, body, reachable=True):
        client = KeaIntegration()
        client.command = (lambda c, service=None:
                          {"ok": False, "error": "Could not connect"} if not reachable
                          else ({"ok": False, "error": "unsupported command"}
                                if "by-hw" in c else {"ok": True, "result": body}))
        return client

    def test_the_lease_is_what_is_used(self):
        from modules.nsot.onboard import discover_dhcp_address

        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.40",
                                    kea=self._kea(self.LEASE))
        assert out["ok"] is True
        assert out["address"] == "10.255.0.40"
        assert out["source"] == "lease"

    def test_a_disagreement_is_a_FINDING_not_a_tiebreak(self):
        """One of them is stale, the tool cannot know which, and writing
        either would make two stores disagree about one device — which is the
        shape the reservation precondition exists to prevent."""
        from modules.nsot.onboard import discover_dhcp_address

        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.99",
                                    kea=self._kea(self.LEASE))
        assert out["ok"] is False
        assert out["disagreement"] is True
        assert "10.255.0.40" in out["reason"] and "10.255.0.99" in out["reason"]
        assert "not a tiebreak" in out["reason"]

    def test_no_lease_does_NOT_fall_back_to_the_reservation(self):
        """*"What the device has"* has no answer then, and answering
        *"probably this"* is how an inventory acquires an address nobody
        verified."""
        from modules.nsot.onboard import discover_dhcp_address

        empty = [{"result": 3, "text": "no leases"}]
        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.40",
                                    kea=self._kea(empty))
        assert out["ok"] is False
        assert out["address"] == ""
        assert "not a substitute" in out["reason"]

    def test_an_unreachable_kea_refuses_and_says_why(self):
        from modules.nsot.onboard import discover_dhcp_address

        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.40",
                                    kea=self._kea(self.LEASE, reachable=False))
        assert out["ok"] is False
        assert "could not be asked" in out["reason"]
        assert "not what the device has" in out["reason"]

    def test_a_raising_kea_is_refused_not_a_crash(self):
        from modules.nsot.onboard import discover_dhcp_address

        class _Boom:
            def lease_for(self, _mac):
                raise RuntimeError("kea exploded")

        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.40",
                                    kea=_Boom())
        assert out["ok"] is False


class TestVerifyConnectsToTheDiscoveredAddress:
    """`mgmt_ip` is empty in the manifest by construction, so without the
    discovery every step of phase 2 — the credential lookup, `online()`,
    `reach()`, the capture, the golden, the CSV row — would be handed `""` and
    report `did_not_answer` with a list of causes every one of which is wrong.
    """

    @staticmethod
    def _repo(tmp_path, monkeypatch, **entry):
        import os

        from modules.nsot import manifest as _m, repo as _repo
        from modules.nsot.repo import GoldenItem, adopt_identity

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE",
                            str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        identity = adopt_identity(repo, GoldenItem("bp-dhcp-a", "", ""))
        _m.upsert_device(repo, identity, "bp-dhcp-a", platform="cisco_iosxe",
                         pending=True, **entry)
        return repo

    def _kea(self, address):
        client = KeaIntegration()
        body = [{"result": 0, "arguments": {"leases": [
            {"ip-address": address, "hw-address": "aa:bb:cc:00:02:40",
             "state": 0, "expire": 9e9}]}}]
        client.command = lambda c, service=None: (
            {"ok": False, "error": "unsupported"} if "by-hw" in c
            else {"ok": True, "result": body})
        return client

    def test_it_connects_to_the_leased_address(self, tmp_path, monkeypatch):
        from modules.nsot.onboard import verify_device

        repo = self._repo(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:00:02:40",
                          reserved_address="10.255.0.40")
        reached = {}

        def _reach(ip, *a, **k):
            reached["ip"] = ip
            return "bp-dhcp-a#"

        out = verify_device(repo, "bp-dhcp-a", "probe",
                            online=lambda ip: bool(ip), reach=_reach,
                            interface="GigabitEthernet2",
                            kea=self._kea("10.255.0.40"))
        assert out["answered"] is True, out
        assert reached["ip"] == "10.255.0.40", \
            "verify connected to the wrong address"
        assert out["mgmt_ip"] == "10.255.0.40"
        assert "Kea's lease" in out["address_note"]

    def test_a_disagreement_stops_verification_before_it_connects(
            self, tmp_path, monkeypatch):
        from modules.nsot.onboard import verify_device

        repo = self._repo(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:00:02:40",
                          reserved_address="10.255.0.99")
        touched = []
        out = verify_device(repo, "bp-dhcp-a", "probe",
                            online=lambda ip: touched.append(ip) or True,
                            reach=lambda *a, **k: touched.append("reach"),
                            interface="GigabitEthernet2",
                            kea=self._kea("10.255.0.40"))
        assert out["answered"] is False
        assert touched == [], "it connected despite the disagreement"
        assert "disagree" in out["error"]

    def test_a_static_device_is_untouched_by_any_of_this(self, tmp_path,
                                                         monkeypatch):
        """**The floor.** The discovery must not capture the static path, which
        reads its address from the manifest as it always has."""
        from modules.nsot.onboard import verify_device

        repo = self._repo(tmp_path, monkeypatch, mgmt_ip="203.0.113.31")
        reached = {}
        out = verify_device(repo, "bp-dhcp-a", "probe",
                            online=lambda ip: True,
                            reach=lambda ip, *a, **k: reached.setdefault("ip", ip)
                            or "bp-dhcp-a#",
                            interface="GigabitEthernet2")
        assert out["answered"] is True
        assert reached["ip"] == "203.0.113.31"
        assert out["address_note"] == ""


class TestTheCredentialIsKeyedOnSomethingThatExistsAtPlanTime:
    """The override is keyed on the management IP, and a DHCP device has none
    when phase 1 stages the credential — so it was keyed under the **empty
    string**, and `resolve()` at verify would look under the discovered address
    and find nothing.

    The reserved address is the right key because it is the address the device
    is *guaranteed* to get; that guarantee is why a reservation is a
    precondition. And a lease that disagrees with it refuses before anything
    asks for a credential, so a wrong key cannot be silently used.
    """

    def test_the_reserved_address_is_the_key_for_dhcp(self):
        import ast
        import inspect

        from modules.nsot import onboard

        source = inspect.getsource(onboard.bind_credentials_step)
        tree = ast.parse(source.strip())
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "reservation_address" in names, \
            "the credential is still keyed on an address a DHCP device lacks"
        assert "set_device_override(key" in source.replace("\n", " ")


class TestAProfileFallbackIsAlwaysAFindingDuringOnboarding:
    """The diagnostic that solved it was in the payload and not in the message.

    Measured 2026-09-24: verification reported `credential_source:
    "profile:default"` — the tool knew perfectly well it had fallen back to the
    list's default profile — and the causes list said *"only the credential is
    wrong"* with a console command. **A device mid-onboarding has never held
    any credential but the staged one**, so a profile cannot be right even by
    accident.

    The condition was a **denylist** (`none`, `unresolved`, `caller`), so
    `profile:default` walked past it. An allowlist of one cannot be outgrown by
    a source `credentials.resolve()` adds later.
    """

    @staticmethod
    def _causes(source):
        from modules.nsot.onboard import REFUSED_CREDENTIAL, _causes

        return _causes(REFUSED_CREDENTIAL, "10.255.0.40", "GigabitEthernet2",
                       "/tmp", "bp-dhcp-a", source)

    def test_a_profile_fallback_is_the_first_cause(self):
        causes = self._causes("profile:default")
        assert "fell back to a profile" in causes[0]["cause"]

    def test_it_says_a_profile_cannot_be_right_here(self):
        why = self._causes("profile:default")[0]["why"]
        assert "never held any credential but the staged one" in why
        assert "cannot be right here even by accident" in why

    def test_any_profile_flavour_is_caught_not_just_default(self):
        """`profile:role:…` and `profile:site:…` are the same finding."""
        for source in ("profile:default", "profile:role:router",
                       "profile:site:lab"):
            assert "fell back to a profile" in self._causes(source)[0]["cause"]

    def test_the_staged_override_offers_no_such_cause(self):
        """**The floor.** An allowlist of one must actually let that one
        through, or every successful resolution is reported as a failure."""
        causes = self._causes("device-override")
        assert not any("fell back" in c["cause"] for c in causes)
        assert not any("did not use the credential" in c["cause"] for c in causes)

    def test_an_unresolved_credential_keeps_its_own_wording(self):
        """`none` is a different fact from a profile fallback: the tool had
        nothing, rather than having the wrong thing."""
        causes = self._causes("none")
        assert "did not use the credential it holds" in causes[0]["cause"]

    def test_it_is_an_allowlist_not_a_denylist(self):
        import inspect

        from modules.nsot import onboard

        source = inspect.getsource(onboard._causes)
        assert "cred_source != STAGED_CREDENTIAL_SOURCE" in source, \
            "the condition is a denylist again, and the next source will pass"


class TestAnUnfindableStagedCredentialIsFlaggedBeforeVerify:
    """**A device in an unrecoverable state with no signal is the
    pending-forever shape the banner exists to prevent.**

    The override is keyed on the address `resolve()` looks under. A device
    staged before that key was corrected for DHCP has its credential under the
    empty string: Verify falls back to a profile, the device refuses it, and
    nothing before this said a word.
    """

    @staticmethod
    def _findable(entry, has_override):
        from modules.nsot import manifest as _m

        import modules.credentials as creds

        original = creds.has_device_override
        creds.has_device_override = lambda key: has_override(key)
        try:
            return _m._credential_findable(entry)
        finally:
            creds.has_device_override = original

    def test_a_credential_under_the_reserved_address_is_findable(self):
        assert self._findable({"reserved_address": "10.255.0.40"},
                              lambda k: k == "10.255.0.40") is True

    def test_a_credential_staged_under_the_empty_string_is_not(self):
        """The exact state of a device created before the key was corrected."""
        assert self._findable({"reserved_address": "10.255.0.40"},
                              lambda k: k == "") is False

    def test_a_device_with_no_address_at_all_is_not_findable(self):
        assert self._findable({}, lambda _k: True) is False

    def test_an_unreadable_store_answers_TRUE(self):
        """Flagging every pending device as broken because the store could not
        be read is a worse lie than the one this catches."""
        from modules.nsot import manifest as _m

        import modules.credentials as creds

        original = creds.has_device_override

        def _boom(_key):
            raise RuntimeError("store unreadable")

        creds.has_device_override = _boom
        try:
            assert _m._credential_findable(
                {"reserved_address": "10.255.0.40"}) is True
        finally:
            creds.has_device_override = original

    def test_the_banner_says_what_to_do_about_it(self):
        from tests.js_source import read_shipped

        js = read_shipped("static/js/gen/partials__onboard_pending.1.js")
        assert "credential_findable === false" in js
        assert "Abandon and re-create" in js
        assert "nothing has reached" in js, \
            "the row must say the recovery is safe, or it reads as destructive"


class TestADhcpPlanCarriesNoStaticAddress:
    """**The wrong-device path, and not the cosmetic one.**

    The wizard's reveal ran only on `change`, and a select's initial value is
    set without firing one — so a browser that remembered "dhcp" showed DHCP
    selected beside a visible, pre-filled Management IP and no MAC field. *The
    form said dhcp and collected static.*

    Measured which won: `onboardFormPayload()` reads every field
    unconditionally, so **the select wins** — the bootstrap config correctly
    emits `ip address dhcp` and contains no static address. And in the session
    where this appeared, Create would have been **refused**, because the hidden
    MAC field was empty and a DHCP plan without a MAC is a blocking reason.

    But the typed address rode along on the plan, and that is the hazard:
    `commit_step` records `plan.mgmt_ip` on the manifest, and `verify_device`
    starts with `mgmt_ip or entry["mgmt_ip"]` — so the stray address would have
    been written, found, and **the lease discovery skipped entirely**, sending
    verification at a torn-down device's old address.
    """

    def _plan(self, tmp_path, monkeypatch, **kw):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.nsot.onboard._name_in_manifest",
                            lambda *a: (False, True))
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox",
                            lambda *a: (False, True))

        class _Kea:
            @staticmethod
            def reservation_for(_mac):
                return {"state": "reserved", "address": "10.255.0.40",
                        "source": "config", "error": ""}

        base = dict(hostname="bp-dhcp-a", platform="cisco_iosxe",
                    list_name="probe", secret="S", manager_interface="Gi2",
                    mgmt_interface="Gi1", kea=_Kea())
        base.update(kw)
        return build_plan(**base)

    def test_a_stray_static_address_is_dropped(self, tmp_path, monkeypatch):
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:00:02:40",
                          mgmt_ip="10.255.0.31", mgmt_mask="255.255.255.0")
        assert plan.mgmt_ip == "", \
            "a DHCP plan carrying an address writes it to the manifest and " \
            "verification then skips the lease discovery"
        assert plan.mgmt_mask == ""
        assert plan.onboardable, plan.blocking_reasons

    def test_the_config_never_contained_it_anyway(self, tmp_path, monkeypatch):
        """The render was already correct — which is what made this subtle."""
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="aa:bb:cc:00:02:40",
                          mgmt_ip="10.255.0.31", mgmt_mask="255.255.255.0")
        assert " ip address dhcp" in plan.bootstrap_config
        assert "10.255.0.31" not in plan.bootstrap_config

    def test_the_session_that_showed_this_would_have_been_refused(
            self, tmp_path, monkeypatch):
        """The MAC field was hidden, so it was empty — and a DHCP plan without
        a MAC is a blocking reason. The precondition caught it incidentally."""
        plan = self._plan(tmp_path, monkeypatch, address_source="dhcp",
                          mgmt_mac="", mgmt_ip="10.255.0.31",
                          mgmt_mask="255.255.255.0")
        assert not plan.onboardable
        assert any("no MAC address" in r for r in plan.blocking_reasons)

    def test_static_keeps_its_address(self, tmp_path, monkeypatch):
        """**The floor.** Dropping the address for every plan would make the
        static path unusable."""
        plan = self._plan(tmp_path, monkeypatch, mgmt_ip="203.0.113.32",
                          mgmt_mask="255.255.255.0")
        assert plan.mgmt_ip == "203.0.113.32"
        assert plan.onboardable, plan.blocking_reasons


class TestTheRevealRunsOnOpenNotOnlyOnChange:
    """A select's initial value is set without firing `change`, so this
    appeared on the **second** use and never the first — which is why building
    and testing the fields did not reveal it."""

    @staticmethod
    def _js():
        from tests.js_source import read_shipped

        return read_shipped("static/js/gen/partials__onboard_wizard.1.js")

    def test_the_wizard_calls_it_on_open(self):
        js = self._js()
        opener = js[js.index("async function openOnboardWizard"):]
        assert "onboardAddressSourceChanged();" in opener[:900], \
            "the reveal runs only on change, so a remembered value is not applied"

    def test_it_reads_the_selects_CURRENT_value(self):
        js = self._js()
        fn = js[js.index("function onboardAddressSourceChanged"):]
        assert "source.value === 'dhcp'" in fn, \
            "it must read the value, not assume the default"

    def test_hidden_static_fields_are_CLEARED_not_just_hidden(self):
        """A hidden field still has a value, and autofill puts one there — so
        hiding alone leaves the payload carrying an address the operator cannot
        see and did not choose for this device."""
        js = self._js()
        fn = js[js.index("function onboardAddressSourceChanged"):]
        block = fn[:fn.index("\n}")]
        assert "obMgmtIp" in block and "value = ''" in block

    def test_the_mac_is_cleared_when_static_is_chosen(self):
        js = self._js()
        fn = js[js.index("function onboardAddressSourceChanged"):]
        assert "obMgmtMac" in fn[:fn.index("\n}")]

    def test_no_placeholder_names_a_real_fleet_address(self):
        """`10.255.0.31` is bp-onboard-c's address from the first probe — a
        torn-down device. A placeholder naming a live range invites typing that
        exact address, and an address that used to belong to something is the
        worst kind to reuse by accident."""
        from tests.js_source import read_shipped

        form = read_shipped("templates/partials/onboard_wizard.html")
        for real in ("10.255.0.31", "10.255.0.32", "10.255.1."):
            assert f'placeholder="{real}' not in form, real
        assert 'placeholder="192.0.2.10"' in form, \
            "the example address is gone — the check now proves nothing"


class TestAbandonClearsEveryKeyThatCouldHoldTheCredential:
    """**80b4e37 introduced this, and the live store showed it.**

    Abandon read `mgmt_ip` alone, guarded by `if mgmt_ip`. A pending DHCP
    device has none until verification discovers it, so the override keyed on
    the **reserved** address survived abandon untouched — and the `''` key left
    by a device created before the key was corrected survived for the same
    reason.

    A staged credential outliving the device it was staged for is a secret with
    no owner, in the one file where a device-specific credential lives.
    """

    def test_both_keys_are_cleared(self):
        import ast
        import inspect

        from modules.nsot import onboard

        source = inspect.getsource(onboard.abandon_onboarding)
        tree = ast.parse(source.strip())
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert "mgmt_ip" in literals
        assert "reserved_address" in literals, (
            "abandon still clears only the mgmt_ip key, so a pending DHCP "
            "device's credential survives it")

    def test_the_guard_is_per_key_not_on_mgmt_ip_alone(self):
        import inspect

        from modules.nsot import onboard

        source = inspect.getsource(onboard.abandon_onboarding)
        assert "if mgmt_ip and credentials.has_device_override" not in source


class TestAnUnkeyedCredentialIsRefused:
    """`''` means *"I do not know which device this is for"*, and a credential
    stored under it is worse than one not stored: nothing can look it up,
    nothing can attribute it, abandoning the device cannot clear it — and the
    **next** such device collides with it, which is one device's credential
    being served for another."""

    def test_an_empty_key_raises(self):
        from modules.credentials import UnkeyedCredential, set_device_override

        with pytest.raises(UnkeyedCredential):
            set_device_override("", "admin", "secret")

    def test_whitespace_is_not_a_key_either(self):
        from modules.credentials import UnkeyedCredential, set_device_override

        with pytest.raises(UnkeyedCredential):
            set_device_override("   ", "admin", "secret")

    def test_the_refusal_says_what_an_empty_key_costs(self):
        from modules.credentials import UnkeyedCredential, set_device_override

        with pytest.raises(UnkeyedCredential) as exc:
            set_device_override("", "admin", "secret")
        assert "nothing can find" in str(exc.value)

    def test_a_real_key_is_accepted(self, tmp_path, monkeypatch):
        """**The floor.** A setter that refused everything would satisfy the
        three above and make onboarding impossible."""
        from modules import credentials

        monkeypatch.setattr(credentials, "CRED_FILE",
                            str(tmp_path / "creds.json"), raising=False)
        monkeypatch.setattr("modules.secrets_store.KEY_FILE",
                            str(tmp_path / "key.key"))
        assert credentials.set_device_override(
            "10.255.0.40", "admin", "s3cret")["ok"] is True


class TestTheOverrideSurveyCanRun:
    """A secret store with no expiry and no owner check — the shape of the 29
    backup directories, except these hold credentials."""

    @staticmethod
    def _script():
        import importlib.util
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts", "nmas-credential-overrides")
        spec = importlib.util.spec_from_loader(
            "nmas_cred_overrides",
            importlib.machinery.SourceFileLoader("nmas_cred_overrides", path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_it_never_reads_a_value(self):
        """A tool auditing a secret store must not become a second place the
        secrets appear."""
        import inspect

        source = inspect.getsource(self._script())
        for leak in ("decrypt_value", "decrypt_field", '["password"]',
                     '["secret"]', "get_secret("):
            assert leak not in source, f"the survey reads a value: {leak}"

    def test_no_claims_at_all_is_UNPROVEN_not_all_orphans(self):
        """**The floor on the other side.** Zero claims means the inventories
        could not be read, and then every key looks like an orphan — a scan
        that could not run reporting the worst possible answer confidently."""
        import inspect

        source = inspect.getsource(self._script())
        assert "EXIT_UNPROVEN" in source
        assert "not result[\"claimed_total\"]" in source

    def test_it_does_not_delete_anything(self):
        """An override may be a deliberate break-glass credential, and removing
        a secret because a script could not attribute it is the wrong
        direction."""
        import inspect

        source = inspect.getsource(self._script())
        assert "clear_device_override(" in source, \
            "it must at least say what removes one"
        assert "credentials.clear_device_override(row" not in source
        assert "does not delete" in source


class TestTheLeaseCarriesItsSubnet:
    """NetBox recorded the leased address as a **host route** for an interface
    that is really on a /24.

    The mask is not in the manifest for a DHCP device — correctly, it is not
    known at plan time — so the NetBox record fell through to its last resort.
    **A host route where a subnet lives is NetBox being wrong about the
    network, which is the one thing NetBox is for.** The lease knows: it carries
    a `subnet-id`, and the server's own configuration has the CIDR.
    """

    @staticmethod
    def _kea(subnet_id=255, cidr="10.255.0.0/24", configurable=True):
        client = KeaIntegration()
        lease = [{"result": 0, "arguments": {"leases": [
            {"ip-address": "10.255.0.40", "hw-address": "aa:bb:cc:00:02:40",
             "state": 0, "expire": 9e9, "subnet-id": subnet_id}]}}]
        config = [{"result": 0, "arguments": {"Dhcp4": {"subnet4": [
            {"id": 255, "subnet": cidr}]}}}]

        def _command(command, service=None):
            if "by-hw" in command:
                return {"ok": False, "error": "unsupported command"}
            if command == "config-get":
                if not configurable:
                    return {"ok": False, "error": "Could not connect"}
                return {"ok": True, "result": config}
            return {"ok": True, "result": lease}

        client.command = _command
        return client

    def test_the_prefix_length_comes_back_with_the_lease(self):
        out = self._kea().lease_for("aa:bb:cc:00:02:40")
        assert out["address"] == "10.255.0.40"
        assert out["prefix_length"] == 24

    def test_an_unknown_subnet_is_ZERO_not_thirty_two(self):
        """**Not knowing and guessing are different, and only one is honest.**
        Guessing 32 here would move the defect rather than remove it."""
        assert self._kea(subnet_id=999).lease_for(
            "aa:bb:cc:00:02:40")["prefix_length"] == 0

    def test_an_unreadable_config_is_also_zero(self):
        assert self._kea(configurable=False).lease_for(
            "aa:bb:cc:00:02:40")["prefix_length"] == 0

    def test_the_discovery_carries_it(self):
        from modules.nsot.onboard import discover_dhcp_address

        out = discover_dhcp_address("aa:bb:cc:00:02:40", "10.255.0.40",
                                    kea=self._kea())
        assert out["ok"] is True
        assert out["prefix_length"] == 24

    def test_verification_reports_it_and_says_so(self):
        """The note names the subnet, because "discovered from a lease" and
        "discovered from a lease, on a /24" are different amounts of knowing."""
        import os
        import tempfile

        from modules.nsot import manifest as _m, repo as _repo
        from modules.nsot.onboard import verify_device
        from modules.nsot.repo import GoldenItem, adopt_identity
        import modules.config as cfg

        tmp = tempfile.mkdtemp()
        original = cfg.LISTS_DIR
        cfg.LISTS_DIR = tmp
        try:
            repo = os.path.join(tmp, "probe", "config_repo")
            os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
            _repo.init_repo(repo)
            identity = adopt_identity(repo, GoldenItem("bp-dhcp-a", "", ""))
            _m.upsert_device(repo, identity, "bp-dhcp-a", platform="cisco_iosxe",
                             pending=True, address_source="dhcp",
                             mgmt_mac="aa:bb:cc:00:02:40",
                             reserved_address="10.255.0.40")
            out = verify_device(repo, "bp-dhcp-a", "probe",
                                online=lambda ip: True,
                                reach=lambda *a, **k: "bp-dhcp-a#",
                                interface="GigabitEthernet2", kea=self._kea())
            assert out["answered"] is True, out
            assert out["prefix_length"] == 24
            assert "/24" in out["address_note"]
        finally:
            cfg.LISTS_DIR = original

    def test_netbox_uses_it_rather_than_a_host_route(self):
        """The last hop. A prefix the caller knows must reach the record."""
        import inspect

        from modules import netbox_client

        source = inspect.getsource(netbox_client._upsert_device)
        assert "mgmt_prefix_len" in source
        assert 'f"{ip}/32"' not in source, \
            "the host route is hardcoded again"
        assert "prefix if 0 < prefix <= 32 else 32" in source

    def test_netbox_keeps_the_host_route_when_the_prefix_is_unknown(self):
        """**The floor.** A golden with no addresses tells nobody the subnet,
        and a host route is the honest answer there — so the fallback must
        survive."""
        import inspect

        from modules import netbox_client

        source = inspect.getsource(netbox_client._upsert_device)
        assert "else 32" in source
        assert "honest about not knowing" in source or "honest" in source
