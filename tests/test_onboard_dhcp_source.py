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
