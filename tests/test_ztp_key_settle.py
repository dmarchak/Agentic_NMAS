"""C1400: Verify's first contact with a ZTP device waits until its SSH key has settled.

0d (2026-10-19, an IOS-XE 17 C8000v): probe-zr4 fetched its bootstrap at 21:41:13; Verify's
preview at 21:41:45 met one SSH key and kept it on first contact; its capture at 21:42:02 met
another and was refused, and a pending device cannot be re-keyed, so the onboarding was
abandoned and redone. `onboard.ztp_key_settling` refuses Verify while no key is kept for the
device's address and its last fetch is less than KEY_SETTLE_S (about 2.5x the 49 s measured)
behind, naming the fetch's time and when to press it; it reaches nothing.
"""

import pytest

from modules.nsot import onboard

ZTP = {"name": "zr4", "address_source": "ztp", "reserved_address": "10.255.0.94",
       "mgmt_mac": "52:54:00:aa:bb:01", "onboarded_at": "2026-10-19T21:30:00Z"}
#: 0d's times: the fetch, and the preview 32 s after it.
FETCHED = "2026-10-19T21:41:13Z"
FETCH_EPOCH = 1792446073.0


def _progress(state="fetched", at=FETCHED):
    return lambda entry, list_name="": {"fetch": {"state": state, "at": at}}


def _settling(entry=ZTP, *, after, held=None, progress=None):
    return onboard.ztp_key_settling(entry, "Default", hostname="zr4", now=FETCH_EPOCH + after,
                                    progress=progress or _progress(),
                                    held=held or (lambda ip: None))


def test_the_epoch_is_the_fetch():
    from modules import host_keys
    assert host_keys._epoch(FETCHED) == FETCH_EPOCH                      # noqa: SLF001


class TestTheWait:
    def test_0d_s_preview_32_s_after_the_fetch_is_refused_naming_both_times(self):
        why = _settling(after=32)
        assert "fetched its bootstrap at 2026-10-19T21:41:13Z (32 s ago)" in why
        assert "waits until 21:43:13 UTC" in why and "89 s from now" in why
        assert "Nothing was reached" in why

    def test_at_the_bound_it_goes_ahead(self):
        assert _settling(after=onboard.KEY_SETTLE_S) == ""

    def test_the_bound_is_about_2_5x_the_measured_49_s(self):
        assert 2.0 * 49 <= onboard.KEY_SETTLE_S <= 3.0 * 49

    @pytest.mark.parametrize("entry, held, progress", [
        (dict(ZTP, address_source="dhcp"), None, None),
        (ZTP, lambda ip: {"fingerprint": "SHA256:x"}, None),
        (ZTP, None, _progress("none")),
        (ZTP, None, _progress("refused")),
    ], ids=["not-ztp", "a-key-is-kept", "not-fetched", "fetch-refused"])
    def test_it_waits_only_for_a_ztp_device_s_first_contact_after_a_fetch(self, entry, held,
                                                                         progress):
        assert _settling(entry, after=5, held=held, progress=progress) == ""

    def test_the_key_is_looked_for_at_the_reserved_address(self):
        asked = []
        _settling(after=5, held=lambda ip: asked.append(ip))
        assert asked == ["10.255.0.94"]


def test_verify_s_preview_refuses_before_it_reaches_anything(monkeypatch):
    """`phase_two_plan` asks it after its own checks and before `verify_device`."""
    from modules.nsot import manifest
    entry = dict(ZTP)
    monkeypatch.setattr(manifest, "find_by_name", lambda repo, name: ("uid-1", entry))
    monkeypatch.setattr(onboard, "ztp_key_settling",
                        lambda e, l, hostname="": f"wait ({hostname}, {e['reserved_address']})")
    monkeypatch.setattr(onboard, "verify_device",
                        lambda *a, **k: pytest.fail("reached a device whose key is settling"))
    p = onboard.phase_two_plan("/nonexistent", "zr4", "Default")
    assert not p["ok"] and p["reason"] == "wait (zr4, 10.255.0.94)"
