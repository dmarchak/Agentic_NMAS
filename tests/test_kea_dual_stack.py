"""A Kea lease is active by one rule, whichever family it is in.

`KeaIntegration._active_leases` decides which of Kea's leases are live, and
`lease_for` (onboarding and ZTP: which address a device took) reads it. It was
written for today's monitoring card, which counted only v4 and so never showed
`h4`, a host on the IPv6-only VLAN. The card left at 7.8, and its
family-by-family tests with it; the rule both families share stays.
"""

import time

from modules.integrations.kea import KeaIntegration


def _payload(leases):
    return {"arguments": {"leases": leases}}


def _lease(ip, name, state=0, age=0, lifetime=3600):
    return {"ip-address": ip, "hostname": name, "state": state,
            "cltt": time.time() - age, "valid-lft": lifetime}


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
