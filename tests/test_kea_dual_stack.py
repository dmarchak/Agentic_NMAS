"""The Kea card counts both families, and each fails on its own.

Measured on the deployed panel: `h4` sits on the IPv6-only VLAN and only ever
holds a DHCPv6 lease, so it never appeared. The card queried `lease4-get-all`
only and reported "active leases: 3".

That number was not wrong so much as **silently scoped**. Nothing on the card
said a whole address family was unread, so the honest reading of "3" -- every
lease Kea is handing out -- was false, and the one host that would have
revealed it was the one being left out. A count with an unstated scope is
worse than a missing one, because it is believed.
"""

import time

import pytest

from modules.integrations.kea import KeaIntegration


def _payload(leases):
    return {"arguments": {"leases": leases}}


def _lease(ip, name, state=0, age=0, lifetime=3600):
    return {"ip-address": ip, "hostname": name, "state": state,
            "cltt": time.time() - age, "valid-lft": lifetime}


@pytest.fixture
def kea(monkeypatch):
    """A client whose per-service answers the test controls."""
    answers = {}
    asked = []

    def fake_command(self, command, service=None):
        asked.append((command, tuple(service or ())))
        reply = answers.get(command)
        if reply is None:
            return {"ok": False, "error": "not configured for this test"}
        return reply

    monkeypatch.setattr(KeaIntegration, "command", fake_command)
    client = KeaIntegration()
    return {"client": client, "answers": answers, "asked": asked}


class TestBothFamiliesAreCounted:
    def test_a_v6_only_host_appears(self, kea):
        """h4 is the reason this exists."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload(
            [_lease("10.0.10.5", "r1"), _lease("10.0.10.6", "s1"),
             _lease("10.0.10.7", "s2")])}
        kea["answers"]["lease6-get-all"] = {"ok": True, "result": _payload(
            [_lease("2001:db8:30::4", "h4")])}

        out = kea["client"].monitor()
        assert out["ok"] is True
        assert out["metrics"][0]["value"] == "v4: 3 · v6: 1"
        assert any(row["text"] == "h4" for row in out["detail"])

    def test_the_v6_row_is_labelled(self, kea):
        """Two families in one list need to say which is which."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload([])}
        kea["answers"]["lease6-get-all"] = {"ok": True, "result": _payload(
            [_lease("2001:db8:30::4", "h4")])}

        row = next(r for r in kea["client"].monitor()["detail"] if r["text"] == "h4")
        assert row["note"] == "v6"

    def test_each_family_names_its_own_service(self, kea):
        """`kea_services` may list both, and sending lease4-get-all to dhcp6
        is an error rather than an empty answer."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload([])}
        kea["answers"]["lease6-get-all"] = {"ok": True, "result": _payload([])}
        kea["client"].monitor()
        assert kea["asked"] == [("lease4-get-all", ("dhcp4",)),
                                ("lease6-get-all", ("dhcp6",))]

    def test_a_v6_lease_identified_only_by_duid_still_shows(self, kea):
        """DHCPv6 has no hw-address; a client with no hostname carries a DUID,
        and falling through to '?' would make the host unidentifiable on the
        very card added to reveal it."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload([])}
        kea["answers"]["lease6-get-all"] = {"ok": True, "result": {"arguments": {
            "leases": [{"ip-address": "2001:db8:30::9", "state": 0,
                        "duid": "00:03:00:01:aa:bb", "cltt": time.time(),
                        "valid-lft": 3600}]}}}
        row = kea["client"].monitor()["detail"][0]
        assert row["text"] == "00:03:00:01:aa:bb"


class TestActiveMeansTheSameThingForBoth:
    """Counting v4 one way and v6 another would make one line two different
    measurements printed as though they were one."""

    def test_declined_leases_are_not_active(self):
        leases = KeaIntegration._active_leases(
            _payload([_lease("a", "ok"), _lease("b", "declined", state=1)]))
        assert [l["hostname"] for l in leases] == ["ok"]

    def test_expired_reclaimed_leases_are_not_active(self):
        leases = KeaIntegration._active_leases(
            _payload([_lease("a", "ok"), _lease("b", "reclaimed", state=2)]))
        assert [l["hostname"] for l in leases] == ["ok"]

    def test_a_lease_past_its_lifetime_is_not_active(self):
        leases = KeaIntegration._active_leases(
            _payload([_lease("a", "fresh"),
                      _lease("b", "stale", age=7200, lifetime=3600)]))
        assert [l["hostname"] for l in leases] == ["fresh"]

    def test_an_explicit_expire_field_is_honoured(self):
        """Some Kea versions send `expire` directly rather than cltt+lifetime."""
        now = time.time()
        leases = KeaIntegration._active_leases({"arguments": {"leases": [
            {"ip-address": "a", "hostname": "live", "state": 0, "expire": now + 60},
            {"ip-address": "b", "hostname": "gone", "state": 0, "expire": now - 60},
        ]}}, now=now)
        assert [l["hostname"] for l in leases] == ["live"]

    def test_a_lease_with_no_expiry_information_is_kept(self):
        """Dropping what cannot be read would undercount silently, which is
        the failure that hid h4 in the first place."""
        leases = KeaIntegration._active_leases(
            {"arguments": {"leases": [{"ip-address": "a", "hostname": "x",
                                       "state": 0}]}})
        assert len(leases) == 1

    def test_a_lease_with_no_state_field_counts_as_active(self):
        """Kea omits `state` when it is the default."""
        leases = KeaIntegration._active_leases(
            {"arguments": {"leases": [{"ip-address": "a", "hostname": "x",
                                       "expire": time.time() + 60}]}})
        assert len(leases) == 1

    def test_a_list_wrapped_response_is_unwrapped(self):
        """The Control Agent answers with one entry per service."""
        leases = KeaIntegration._active_leases([_payload([_lease("a", "x")])])
        assert len(leases) == 1

    def test_an_empty_response_is_zero_not_a_crash(self):
        assert KeaIntegration._active_leases({}) == []
        assert KeaIntegration._active_leases([]) == []
        assert KeaIntegration._active_leases(None) == []


class TestEachFamilyFailsIndependently:
    def test_dhcp6_down_still_shows_the_v4_count(self, kea):
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload(
            [_lease("10.0.10.5", "r1"), _lease("10.0.10.6", "s1")])}
        kea["answers"]["lease6-get-all"] = {"ok": False,
                                            "error": "server dhcp6 is not running"}

        out = kea["client"].monitor()
        assert out["ok"] is True, "a v6 outage must not blank the card"
        assert out["metrics"][0]["value"] == "v4: 2 · v6: unavailable"

    def test_the_v6_error_is_shown_not_swallowed(self, kea):
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload([])}
        kea["answers"]["lease6-get-all"] = {"ok": False,
                                            "error": "server dhcp6 is not running"}

        detail = kea["client"].monitor()["detail"]
        assert detail[0]["state"] == "down"
        assert "dhcp6" in detail[0]["text"]
        assert "not running" in detail[0]["text"]

    def test_the_error_comes_before_the_leases(self, kea):
        """A reason below ten lease rows is a reason nobody reads."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload(
            [_lease("10.0.10.%d" % n, "d%d" % n) for n in range(5)])}
        kea["answers"]["lease6-get-all"] = {"ok": False, "error": "down"}
        assert kea["client"].monitor()["detail"][0]["state"] == "down"

    def test_dhcp4_down_still_shows_the_v6_count(self, kea):
        """The mirror case. Not symmetric by assumption -- by test."""
        kea["answers"]["lease4-get-all"] = {"ok": False, "error": "dhcp4 down"}
        kea["answers"]["lease6-get-all"] = {"ok": True, "result": _payload(
            [_lease("2001:db8:30::4", "h4")])}

        out = kea["client"].monitor()
        assert out["ok"] is True
        assert out["metrics"][0]["value"] == "v4: unavailable · v6: 1"

    def test_both_down_reports_not_ok_with_both_reasons(self, kea):
        kea["answers"]["lease4-get-all"] = {"ok": False, "error": "dhcp4 down"}
        kea["answers"]["lease6-get-all"] = {"ok": False, "error": "dhcp6 down"}

        out = kea["client"].monitor()
        assert out["ok"] is False
        assert "dhcp4 down" in out["error"] and "dhcp6 down" in out["error"]

    def test_a_partial_failure_marks_the_metric_down(self, kea):
        """The count is real but incomplete, and the card should say so."""
        kea["answers"]["lease4-get-all"] = {"ok": True, "result": _payload([])}
        kea["answers"]["lease6-get-all"] = {"ok": False, "error": "down"}
        assert kea["client"].monitor()["metrics"][0]["state"] == "down"


class TestThePanelRouteSurfacesIt:
    def test_a_partial_failure_reaches_the_card_as_up(self, monkeypatch):
        """The route treats `ok` as the card's state, so a v6 outage must not
        arrive as a dead tool."""
        import app as nmas
        import modules.integrations as integrations

        class Partial:
            label, name = "Kea DHCP", "kea"

            def __init__(self, timeout=5):
                pass

            def is_configured(self):
                return True

            def monitor(self):
                return {"ok": True,
                        "metrics": [{"label": "active leases",
                                     "value": "v4: 2 · v6: unavailable",
                                     "state": "down"}],
                        "detail": [{"text": "dhcp6: down", "state": "down"}]}

        original = integrations.REGISTRY["kea"]
        integrations.REGISTRY["kea"] = Partial
        try:
            data = nmas.app.test_client().get("/monitoring/stack/kea").get_json()
        finally:
            integrations.REGISTRY["kea"] = original

        assert data["state"] == "up"
        assert "v6: unavailable" in data["metrics"][0]["value"]
        assert data["detail"][0]["state"] == "down"
