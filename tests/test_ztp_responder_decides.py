"""The ZTP responder's decision, whole (`ztp_responder.decide`, `_pending_ztp_devices`;
mutation run #31 of 2026-10-23, at 9d9e6b40).

The responder decides who receives a device's bootstrap, which carries its one-time credential,
and nobody watches this path. So every path is asserted as the WHOLE result (serve, config
bytes, device, list, reason), never a field of it: a refusal serves no bytes and names what it
compared; a served file is exactly the render, rendered for the right repository and device.
The cases: an IPv6 asker; reservations or manifests that cannot be read; a reserved address
reserved twice, claimed twice, or with no boot file named; a reservation naming no MAC; an
unreadable fragment named beside "no reservation"; the console gate's device rendered from its
own repository; and the manifest scan going past a network with no repository.

Helpers are test_ztp_responder.py's (the DHCP path) and test_console_ztp_static.py's (the
out-of-band gate). Documentation addresses (RFC 5737) throughout."""

from modules.nsot import console_ztp as Z
from modules.nsot import ztp_responder as r
from tests.test_console_ztp_static import ADDRESS, ENTRY, _held_by
from tests.test_ztp_responder import CONFIG, MAC, PEER, _pending, _reservation

REFUSED = {"serve": False, "config": b"", "device": "", "list": ""}


def _renders(calls):
    """An artifact reader that records each (repo, device) it is asked for."""
    def artifact(repo, name):
        calls.append((repo, name))
        return {"ok": True, "config": CONFIG}
    return artifact


def _decide(peer=PEER, filename="bp-ztp-a.cfg", *, fragment=None, pending=None, calls=None):
    calls = [] if calls is None else calls
    return r.decide(peer, filename,
                    fragment=fragment or (lambda: [_reservation()]),
                    pending=pending or _pending,
                    artifact=_renders(calls), holder=_held_by(None))


def _outcome(call):
    """The decision, or what it raised: a refusal is a result, never an exception."""
    try:
        return call()
    except Exception as exc:                      # noqa: BLE001
        return f"raised {type(exc).__name__}: {exc}"


def _boom(text):
    def raises():
        raise OSError(text)
    return raises


class TestTheWholeDecision:
    def test_a_served_file_is_exactly_the_render_with_no_reason(self):
        calls = []
        assert _decide(calls=calls) == {"serve": True, "config": CONFIG.encode("ascii"),
                                        "device": "bp-ztp-a", "list": "Lab", "reason": ""}
        assert calls == [("/repo", "bp-ztp-a")]

    def test_an_ipv6_asker_is_refused_whole_naming_the_address(self):
        calls = []
        got = _decide(peer="2001:db8::50", calls=calls)
        assert got == dict(REFUSED, reason="2001:db8::50 is an IPv6 address: ZTP reserves and "
                                           "serves IPv4 (DHCPv4) addresses only")
        assert calls == []

    def test_unreadable_reservations_are_refused_whole(self):
        got = _decide(fragment=_boom("fragment locked"))
        assert got == dict(REFUSED, reason="the tool's reservations could not be read: "
                                           "fragment locked")

    def test_unreadable_manifests_on_the_reserved_path_are_refused_whole(self):
        calls = []
        got = _decide(pending=_boom("manifest locked"), calls=calls)
        assert got == dict(REFUSED, reason="the manifests could not be read: manifest locked")
        assert calls == []


class TestTheReservation:
    def test_an_address_reserved_twice_is_refused_saying_how_many_times(self):
        calls = []
        got = _decide(fragment=lambda: [_reservation(), _reservation(mac="aa:bb:cc:00:02:51")],
                      calls=calls)
        assert got == dict(REFUSED, reason=f"{PEER} is reserved 2 times")
        assert calls == []

    def test_an_address_claimed_by_two_pending_devices_is_refused_saying_how_many(self):
        calls = []
        two = lambda: _pending() + _pending(name="bp-ztp-b")   # noqa: E731
        got = _decide(pending=two, calls=calls)
        assert got == dict(REFUSED, reason=f"2 pending ZTP devices claim {PEER}")
        assert calls == []

    def test_a_reservation_naming_no_boot_file_is_a_refusal_naming_both(self):
        """No option 67 (or no option data at all): refused, saying the reservation names no
        boot file (an absent name matches no asked file, absent or not: TestAbsentNeverMatches);
        never an exception, which the handler would log and the device would hear as nothing
        recorded."""
        bare = dict(_reservation(), **{"option-data": [{"name": "tftp-server-name",
                                                        "data": "192.0.2.10"}]})
        none = {k: v for k, v in _reservation().items() if k != "option-data"}
        for reservation in (bare, none):
            got = _outcome(lambda: _decide(fragment=lambda: [reservation]))
            assert got == dict(REFUSED, reason=f"{PEER}'s reservation names no boot file, so "
                                               "it is served to no device"), reservation

    def test_a_reservation_naming_no_mac_is_served_to_no_device(self):
        """A reserved address is served only to its MAC: a reservation with no hw-address (or
        an empty one) names no device, so a pending entry with no MAC recorded is no match for
        it; absent is not equal to absent."""
        nameless = [("Lab", "/repo", {"name": "bp-ztp-a", "reserved_address": PEER,
                                      "mgmt_mac": "", "address_source": "ztp"})]
        no_key = {k: v for k, v in _reservation().items() if k != "hw-address"}
        for reservation in (no_key, _reservation(mac="")):
            calls = []
            got = _decide(fragment=lambda: [reservation], pending=lambda: nameless,
                          calls=calls)
            assert got == dict(REFUSED, reason=f"{PEER}'s reservation names no hw-address, so "
                                               "it is served to no device"), reservation
            assert calls == []

    def test_unreadable_fragments_are_named_after_no_reservation(self):
        unread = [{"_unread": "/etc/kea/branch.json (Branch): denied"},
                  {"_unread": "/etc/kea/edge.json (Edge): gone"}]
        got = _decide(fragment=lambda: unread, pending=lambda: [])
        assert got == dict(REFUSED, reason=(
            f"{PEER} holds no reservation the tool wrote; these fragments could not be read, "
            "so it may be reserved there: /etc/kea/branch.json (Branch): denied; "
            "/etc/kea/edge.json (Edge): gone"))


class TestWhatIsRendered:
    def test_the_reserved_device_is_rendered_from_its_own_list_s_repo(self):
        calls = []
        lists = lambda: [   # noqa: E731
            ("Branch", "/lists/branch/config_repo",
             {"name": "br-a", "reserved_address": "192.0.2.60", "mgmt_mac": MAC,
              "address_source": "ztp"}),
            ("Lab", "/lists/lab/config_repo",
             {"name": "bp-ztp-a", "reserved_address": PEER, "mgmt_mac": MAC,
              "address_source": "ztp"})]
        got = _decide(pending=lists, calls=calls)
        assert got == {"serve": True, "config": CONFIG.encode("ascii"), "device": "bp-ztp-a",
                       "list": "Lab", "reason": ""}
        assert calls == [("/lists/lab/config_repo", "bp-ztp-a")]

    def test_the_console_gate_s_device_is_rendered_from_its_own_repo(self):
        calls = []
        got = r.decide(ADDRESS, "s5.cfg", fragment=lambda: [],
                       pending=lambda: [("Lab", "/lists/lab/config_repo", ENTRY)],
                       holder=_held_by(Z.OP_KICKSTART), artifact=_renders(calls))
        assert got == {"serve": True, "config": CONFIG.encode("ascii"), "device": "s5",
                       "list": "Lab", "reason": ""}
        assert calls == [("/lists/lab/config_repo", "s5")]


def test_the_manifest_scan_goes_past_a_network_with_no_repository(tmp_path, monkeypatch):
    """A network whose list has no config repository yet is skipped; the networks after it are
    still read (a stop there would refuse every device listed later)."""
    from modules import config, device
    from modules.nsot import manifest

    lists = tmp_path / "lists"
    repo = lists / "lab" / "config_repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(config, "LISTS_DIR", str(lists))
    monkeypatch.setattr(device, "get_device_lists", lambda: [
        {"name": "Ghost", "filename": "ghost"}, {"name": "Lab", "filename": "lab"}])
    manifest.upsert_device(str(repo), "uid:1", "bp-ztp-a", pending=True,
                           address_source="ztp", mgmt_mac=MAC, reserved_address=PEER)
    found = r._pending_ztp_devices()
    assert [(ln, rp, e["name"]) for ln, rp, e in found] == [("Lab", str(repo), "bp-ztp-a")]
    assert not (lists / "ghost").exists(), "reading must never create a list"


class TestAbsentNeverMatches:
    """An absent value equals nothing, not even another absent one (the operator, 2026-10-23,
    after run #31's empty MAC matched an empty MAC): every comparison in the gate and in
    `decide` that chooses who receives a bootstrap, each with both sides absent."""

    def _gate(self, peer, entry, filename):
        return r.console_gate(peer, filename, pending=lambda: [("Lab", "/repo", entry)],
                              holder=_held_by(Z.OP_KICKSTART))

    def test_an_entry_with_no_planned_address_is_planned_nowhere(self):
        for missing in ({"mgmt_ip": ""}, {"mgmt_ip": None}, {"mgmt_ip": "  "}):
            got = self._gate("", dict(ENTRY, **missing), "s5.cfg")
            assert got == {"serve": False, "device": "", "list": "", "repo": "",
                           "reason": "no pending out-of-band (console) device is planned at "}, \
                missing

    def test_a_pending_device_with_no_name_is_served_nothing(self):
        got = self._gate(ADDRESS, dict(ENTRY, name=""), ".cfg")
        assert got == {"serve": False, "device": "", "list": "Lab", "repo": "/repo",
                       "reason": f"the pending out-of-band device planned at {ADDRESS} has no "
                                 "name: no bootstrap is served"}

    def test_a_reservation_with_no_address_is_reserved_nowhere(self):
        calls = []
        got = _decide(peer="", filename="bp-ztp-a.cfg", calls=calls,
                      fragment=lambda: [_reservation(ip="")], pending=lambda: [])
        assert got == dict(REFUSED, reason=" holds no reservation the tool wrote")
        assert calls == []

    def test_a_reservation_naming_no_boot_file_serves_no_one_asking_for_none(self):
        calls = []
        got = _decide(filename="", calls=calls, fragment=lambda: [_reservation(file="")])
        assert got == dict(REFUSED, reason=f"{PEER}'s reservation names no boot file, so it is "
                                           "served to no device")
        assert calls == []

    def test_a_mac_matches_its_reservation_whatever_the_case_of_either_side(self):
        """Kea and the manifest may write the same MAC in different case (Kea keeps what it was
        given; the manifest keeps what onboarding read): the match is the MAC, not its letters,
        on both sides (mutation run #32 at 85095f8f: every survivor of the case-folding)."""
        upper = MAC.upper()
        for reserved, recorded in ((upper, MAC), (MAC, upper)):
            calls = []
            got = _decide(calls=calls, fragment=lambda r=reserved: [_reservation(mac=r)],
                          pending=lambda m=recorded: _pending(mac=m))
            assert got == {"serve": True, "config": CONFIG.encode("ascii"),
                           "device": "bp-ztp-a", "list": "Lab", "reason": ""}, (reserved, recorded)
            assert calls == [("/repo", "bp-ztp-a")]

    def test_a_reserved_device_with_no_name_is_rendered_for_no_one(self):
        calls = []
        got = _decide(calls=calls, pending=lambda: _pending(name=""))
        assert got == dict(REFUSED, list="Lab",
                           reason=f"the pending ZTP device holding {MAC} -> {PEER} has no "
                                  "name: no bootstrap is served")
        assert calls == []
