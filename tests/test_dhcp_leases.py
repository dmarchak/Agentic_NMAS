"""C1403 part 1: releasing a Kea lease (`modules/dhcp_leases.py`), the one home for it.

0d's run 2 (2026-10-19): a ZTP onboarding abandoned and created again met its own earlier lease
(Kea: `ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT`, "conflicting reservation ... with existing
lease"), and Kea answered none of 238 requests until the lease was deleted by hand with
`lease4-del`, a step Mercury lacked. Three callers now share one release: DHCP › Leases'
Release lease… (previewed, confirmed by hash as a verified person with a reason), Retire, and a
ZTP device's Abandon.

On Kea as captured (tests/fixtures/kea: the lab's leases, both families), behind a fake that
answers `lease4-del` and `lease6-del` as Kea's `lease_cmds` hook does (result 0 deleted, 3 no
lease there) and deletes the lease from what it answers next.
"""

import ipaddress
import json
import os
import re
import types

import pytest

from modules import dhcp_leases as L
from tests.test_dhcp_reservations import FakeKea, kea_dir  # noqa: F401 (the fixture)
from tests.test_dhcp_v2 import web  # noqa: F401 (the fixture)

#: C1522: its tests write reader stores, or wake readers that do; each test keeps them
#: in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

RIG = {"family": "IPv4", "address": "10.10.10.102"}
RIG6 = {"family": "IPv6", "address": "2001:db8:10::103"}
#: The MAC whose client holds 10.10.10.100 and three IPv6 leases (by its DUID-LL).
MAC = "aa:c1:ab:99:f6:e2"


class LeaseKea(FakeKea):
    """Kea as captured, answering a lease delete as the `lease_cmds` hook does. *deletes*
    False is a Kea that answers the delete and keeps the lease (the read-back's case)."""

    def __init__(self, files, deletes=True, unreadable=()):
        super().__init__(files)
        self.deletes, self.unreadable, self.dels = deletes, set(unreadable), []

    def _leases(self, svc):
        return self.leases[svc][0]["arguments"]["leases"]

    def command(self, cmd, service=None, arguments=None):
        svc = service if isinstance(service, str) else (service or ["dhcp4"])[0]
        if cmd.endswith("-get-all") and svc in self.unreadable:
            return {"ok": False, "error": "connection refused"}
        if cmd in ("lease4-del", "lease6-del"):
            self.sent.append((cmd, svc))
            self.dels.append((cmd, dict(arguments or {})))
            want = ipaddress.ip_address(arguments["ip-address"])
            hit = [x for x in self._leases(svc) if ipaddress.ip_address(x["ip-address"]) == want]
            if not hit:
                return {"ok": True, "result": [{"result": 3, "text": "lease not found"}]}
            if self.deletes:
                self._leases(svc)[:] = [x for x in self._leases(svc) if x not in hit]
            return {"ok": True, "result": [{"result": 0, "text": "lease deleted"}]}
        return super().command(cmd, service)


@pytest.fixture
def kea(kea_dir):  # noqa: F811 (the fixture imported above)
    return LeaseKea(kea_dir["files"])


def _recorder(kept):
    def record(list_name, outcomes, **kw):
        kept.append((list_name, [o["outcome"] for o in outcomes], kw))
        return {"ok": True, "commit": "a1b2c3d4e5", "owner": list_name, "error": ""}
    return record


# ── the preview ─────────────────────────────────────────────────────────────────────────────

class TestThePreview:
    def test_it_names_the_lease_and_its_client_and_binds_a_hash(self, kea):
        p = L.plan("Lab", RIG, kea=kea)
        assert p["ok"], p["refused"]
        assert len(p["change"]) == 1 and p["change"][0][0] == "-"
        assert p["change"][0][1].startswith("lease 10.10.10.102 (IPv4, MAC aa:c1:ab:b0:85:65, ends ")
        assert p["title"] == "Release 10.10.10.102" and re.fullmatch(r"[0-9a-f]{64}", p["hash"])
        assert p["checks"][0][0] == "note" and "keeps using it until it next renews" in \
            p["checks"][0][1]
        assert any("Kea keeps no copy of a deleted lease" in n for n in p["survives"])

    def test_an_ipv6_lease_by_any_spelling_and_its_duid(self, kea):
        p = L.plan("Lab", dict(RIG6, address="2001:DB8:10:0:0:0:0:103"), kea=kea)
        assert p["ok"], p["refused"]
        assert p["address"] == "2001:db8:10::103"
        assert p["lease"]["by"] == "DUID" and p["lease"]["mac"] == "aa:c1:ab:b0:85:65"

    def test_a_preview_releases_nothing(self, kea):
        L.plan("Lab", RIG, kea=kea)
        assert kea.dels == [] and {c for c, _s in kea.sent} <= {"lease4-get-all", "config-get"}

    @pytest.mark.parametrize("values, words", [
        ({"family": "IPv5", "address": "10.10.10.102"}, "'IPv5' is not IPv4 or IPv6"),
        ({"family": "IPv4", "address": "10.10.10"}, "'10.10.10' is not an address"),
        ({"family": "IPv6", "address": "10.10.10.102"}, "10.10.10.102 is not an IPv6 address"),
        ({"family": "IPv4", "address": "10.10.10.199"}, "Kea holds no lease on 10.10.10.199 now"),
        ({"family": "IPv6", "address": "2001:db8:10::199"},
         "Kea holds no lease on 2001:db8:10::199 now"),
    ], ids=["family", "address", "family-mismatch", "no-lease-v4", "no-lease-v6"])
    def test_what_it_cannot_release_is_refused_by_name(self, kea, values, words):
        p = L.plan("Lab", values, kea=kea)
        assert not p["ok"] and words in p["refused"], p["refused"]
        assert p["hash"] == ""

    def test_kea_not_configured_is_refused(self, kea):
        kea.is_configured = lambda: False
        p = L.plan("Lab", RIG, kea=kea)
        assert not p["ok"] and "Kea is not configured for this network" in p["refused"]

    def test_kea_not_answering_is_could_not_read_never_no_lease(self, kea_dir):  # noqa: F811
        p = L.plan("Lab", RIG, kea=LeaseKea(kea_dir["files"], unreadable={"dhcp4"}))
        assert not p["ok"] and "holds no lease" not in p["refused"], p["refused"]


# ── the apply ───────────────────────────────────────────────────────────────────────────────

class TestTheApply:
    def test_it_releases_exactly_that_lease_reads_back_and_records(self, kea):
        kept = []
        h = L.plan("Lab", RIG, kea=kea)["hash"]
        got = L.apply("Lab", RIG, h, actor="op@example.invalid", reason="VM recreated",
                      kea=kea, record_with=_recorder(kept))
        assert got["ok"], got["error"]
        assert kea.dels == [("lease4-del", {"ip-address": "10.10.10.102"})]
        assert [x["ip-address"] for x in kea._leases("dhcp4")] == ["10.10.10.100", "10.10.20.101"]
        assert got["at"] == "record" and "Kea holds no lease on 10.10.10.102" in got["read_back"]
        assert kept == [("Lab", ["released"], {"actor": "op@example.invalid",
                                               "reason": "VM recreated", "source": "DHCP › Leases",
                                               "subject": "dhcp: IPv4 lease 10.10.10.102 released "
                                                          "(aa:c1:ab:b0:85:65)"})]

    def test_an_ipv6_release_names_its_type(self, kea):
        h = L.plan("Lab", RIG6, kea=kea)["hash"]
        got = L.apply("Lab", RIG6, h, actor="op", reason="gone", kea=kea,
                      record_with=_recorder([]))
        assert got["ok"], got["error"]
        assert kea.dels == [("lease6-del", {"ip-address": "2001:db8:10::103", "type": "IA_NA"})]

    def test_a_lease_that_moved_since_the_preview_is_refused_and_nothing_sent(self, kea):
        h = L.plan("Lab", RIG, kea=kea)["hash"]
        lease = next(x for x in kea._leases("dhcp4") if x["ip-address"] == "10.10.10.102")
        lease["hw-address"] = "aa:c1:ab:00:00:01"          # another client holds it now
        got = L.apply("Lab", RIG, h, actor="op", reason="gone", kea=kea,
                      record_with=_recorder([]))
        assert not got["ok"] and "has changed" in got["error"] and "nothing was released" in \
            got["error"]
        assert kea.dels == [] and "at" not in got

    def test_no_reason_is_refused_before_kea_is_asked(self, kea):
        got = L.apply("Lab", RIG, "0" * 64, actor="op", reason="  ", kea=kea)
        assert not got["ok"] and "a reason is recorded with every release" in got["error"]
        assert kea.sent == []

    def test_a_delete_kea_answers_and_does_not_carry_out_fails_at_the_read_back(self,
                                                                                kea_dir):  # noqa: F811
        kea = LeaseKea(kea_dir["files"], deletes=False)
        kept = []
        h = L.plan("Lab", RIG, kea=kea)["hash"]
        got = L.apply("Lab", RIG, h, actor="op", reason="gone", kea=kea,
                      record_with=_recorder(kept))
        assert not got["ok"] and got["at"] == "read_back"
        assert "was answered, and Kea still holds the lease" in got["error"]
        assert kept == [], "a release Kea does not show was recorded"

    def test_a_record_that_fails_says_released_and_not_recorded(self, kea):
        h = L.plan("Lab", RIG, kea=kea)["hash"]
        got = L.apply("Lab", RIG, h, actor="op", reason="gone", kea=kea,
                      record_with=lambda *a, **k: {"ok": False, "error": "repo locked"})
        assert not got["ok"] and got["at"] == "record"
        assert got["error"] == "released in Kea and read back; the record failed: repo locked"


class TestTheOneRelease:
    """`release` is what Retire and Abandon call too: it reads Kea again first, so only the
    lease named goes, and a lease now another client's is left and said."""

    def _row(self, kea, address, family="IPv4"):
        return next(r for r in L.read(kea, family) if r["address"] == address)

    def test_a_lease_now_another_client_s_is_kept(self, kea):
        r = self._row(kea, "10.10.10.102")
        lease = next(x for x in kea._leases("dhcp4") if x["ip-address"] == "10.10.10.102")
        lease["hw-address"] = "aa:c1:ab:00:00:01"
        got = L.release(kea, [r])
        assert got["ok"] and got["outcomes"][0]["outcome"] == "kept"
        assert "is leased now to MAC aa:c1:ab:00:00:01" in got["outcomes"][0]["detail"]
        assert kea.dels == []

    def test_a_lease_already_gone_is_absent_not_failed(self, kea):
        r = dict(self._row(kea, "10.10.10.102"), address="10.10.10.150")
        got = L.release(kea, [r])
        assert got["ok"] and got["outcomes"][0]["outcome"] == "absent" and kea.dels == []

    def test_kea_unreadable_before_the_release_sends_nothing(self, kea_dir):  # noqa: F811
        kea = LeaseKea(kea_dir["files"])
        r = self._row(kea, "10.10.10.102")
        kea.unreadable = {"dhcp4"}
        got = L.release(kea, [r])
        assert not got["ok"] and "could not be read again before the release" in got["error"]
        assert kea.dels == []


class TestTheRecord:
    def test_earlier_releases_are_kept_and_the_new_one_added(self, kea, monkeypatch):
        from modules import dhcp_reservations as D
        import yaml
        written = []

        def commit_in_owner(list_name, path, text_for, message, actor):
            written.append((path, text_for("Lab"), message, actor))
            return {"ok": True, "commit": "c0ffee", "owner": "Lab", "error": ""}

        monkeypatch.setattr(D, "commit_in_owner", commit_in_owner)
        monkeypatch.setattr(L, "_committed", lambda owner: [{"address": "10.10.10.9"}])
        got = L.release(kea, [next(r for r in L.read(kea, "IPv4")
                                   if r["address"] == "10.10.10.102")])
        rec = L.record("Lab", got["outcomes"], actor="op", reason="VM recreated",
                       source="DHCP › Leases", subject="dhcp: released")
        assert rec["ok"]
        path, text, message, actor = written[0]
        doc = yaml.safe_load(text)
        assert path == "dhcp/released-leases.yml" and actor == "op"
        assert message == "dhcp: released\n\nVM recreated"
        assert [x["address"] for x in doc["released"]] == ["10.10.10.9", "10.10.10.102"]
        assert doc["released"][1]["by_person"] == "op" and doc["released"][1]["reason"] == \
            "VM recreated"

    def test_nothing_released_commits_nothing(self, monkeypatch):
        from modules import dhcp_reservations as D
        monkeypatch.setattr(D, "commit_in_owner", lambda *a, **k: pytest.fail("committed"))
        assert L.record("Lab", [{"outcome": "kept", "lease": {}}], actor="op", reason="r",
                        source="s", subject="s") == {"ok": True, "commit": "", "owner": "",
                                                     "error": ""}


# ── a device's leases: Retire and Abandon ───────────────────────────────────────────────────

class TestADevicesLeases:
    def test_by_its_mac_in_both_families(self, kea):
        got = L.held(kea, macs=[MAC.upper().replace(":", "-")])
        assert got["ok"] and sorted((r["family"], r["address"]) for r in got["leases"]) == [
            ("IPv4", "10.10.10.100"), ("IPv6", "2001:db8:10::101"), ("IPv6", "2001:db8:10::105"),
            ("IPv6", "2001:db8:10::107")]

    def test_by_an_address_it_was_known_by_whatever_client_holds_it(self, kea):
        """0d's case: the lease on the reserved address was held under the old client-id."""
        lease = next(x for x in kea._leases("dhcp4") if x["ip-address"] == "10.10.20.101")
        lease["hw-address"], lease["client-id"] = "", "00:39:4a:4c:4e:58:47"
        got = L.held(kea, addresses=["10.10.20.101", "2001:DB8:30:0::103"])
        assert sorted(r["address"] for r in got["leases"]) == ["10.10.20.101",
                                                               "2001:db8:30::103"]
        old = next(r for r in got["leases"] if r["family"] == "IPv4")
        assert old["by"] == "client-id" and old["identity"] == "00:39:4a:4c:4e:58:47"

    def test_kea_not_answering_is_not_ok_never_an_empty_list(self, kea_dir):  # noqa: F811
        got = L.held(LeaseKea(kea_dir["files"], unreadable={"dhcp6"}), macs=[MAC])
        assert not got["ok"] and "IPv6:" in got["error"]

    def test_kea_not_configured_holds_nothing_and_says_so(self, kea):
        kea.is_configured = lambda: False
        assert L.held(kea, macs=[MAC]) == {"ok": True, "configured": False, "leases": [],
                                           "error": ""}

    def test_release_for_device_releases_and_records_each(self, kea, monkeypatch):
        kept = []
        monkeypatch.setattr(L, "record", _recorder(kept))
        leases = L.held(kea, macs=[MAC])["leases"]
        got = L.release_for_device("Lab", leases, actor="op", reason="r1 retired",
                                   source="retire", device="r1", kea=kea)
        assert got["ok"] and got["commit"] == "a1b2c3d4e5", got
        assert [d[1]["ip-address"] for d in kea.dels] == [
            "10.10.10.100", "2001:db8:10::101", "2001:db8:10::105", "2001:db8:10::107"]
        assert kept[0][1] == ["released"] * 4 and kept[0][2]["subject"] == \
            "dhcp: r1's lease(s) released (retire)"


class TestAbandonReleasesAZtpDevicesLeases:
    """A ZTP device's Abandon (`onboard.ZTP_ABANDON_STEPS`): its reservation, then its leases,
    by its recorded MAC and its reserved address."""

    ZMAC, ZADDR = "52:54:00:aa:bb:01", "10.255.96.2"

    def _repo(self, tmp_path, monkeypatch):
        from modules.nsot import manifest as _m, repo as _repo
        from modules.nsot.repo import GoldenItem, adopt_identity

        list_dir = tmp_path / "probe"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda _n: str(list_dir))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(tmp_path / "key.key"))
        _repo.init_repo(repo)
        identity = adopt_identity(repo, GoldenItem("zr6", "", ""))
        _m.upsert_device(repo, identity, "zr6", platform="cisco_iosxe", pending=True,
                         address_source="ztp", mgmt_mac=self.ZMAC, reserved_address=self.ZADDR)
        return repo

    def _abandon(self, repo, read, release, **kw):
        from modules.nsot import onboard
        return onboard.abandon_onboarding(
            repo, "zr6", "probe", actor="op@example.com",
            remove_netbox=lambda *a, **k: {"ok": True, "deleted": [], "skipped": []},
            remove_reservation=lambda mac: {"ok": True, "outcomes": {
                mac: {"outcome": "removed", "detail": "gone"}}},
            read_leases=read, release_leases=release, **kw)

    def _lease(self):
        return L.row({"ip-address": self.ZADDR, "hw-address": "", "subnet-id": 256,
                      "client-id": "00:39:4a:4c:4e:58:47", "cltt": 1760911000,
                      "valid-lft": 604800, "state": 0}, "IPv4")

    def test_its_old_lease_is_read_by_mac_and_address_and_released(self, tmp_path,
                                                                     monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        asked, released = [], []
        out = self._abandon(
            repo, lambda l, macs, addresses: asked.append((l, macs, addresses)) or {
                "ok": True, "configured": True, "leases": [self._lease()], "error": ""},
            lambda l, leases, **kw: released.append((leases, kw)) or {
                "ok": True, "outcomes": [{"outcome": "released", "detail": "released"}],
                "commit": "feedbeef", "error": ""})
        assert asked == [("probe", [self.ZMAC], [self.ZADDR])]
        assert [r["address"] for r in released[0][0]] == [self.ZADDR]
        assert released[0][1]["reason"] == "zr6's onboarding abandoned"
        step = next(s for s in out["steps"] if s["step"] == "leases")
        assert step["ok"] and "recorded (feedbeef)" in step["detail"]
        assert out["ok"] and out["released"] == "zr6", out

    def test_a_dry_run_names_the_lease_and_releases_nothing(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        out = self._abandon(
            repo, lambda l, macs, addresses: {"ok": True, "configured": True,
                                              "leases": [self._lease()], "error": ""},
            lambda *a, **k: pytest.fail("released in a dry run"), dry_run=True)
        step = next(s for s in out["steps"] if s["step"] == "leases")
        assert "would release from Kea 10.255.96.2 (IPv4, client-id 00:39:4a:4c:4e:58:47)" in \
            step["detail"]

    def test_kea_unreadable_is_a_failed_step_naming_how_to_finish(self, tmp_path, monkeypatch):
        repo = self._repo(tmp_path, monkeypatch)
        out = self._abandon(
            repo, lambda *a, **k: {"ok": False, "error": "connection refused"},
            lambda *a, **k: pytest.fail("released what could not be read"))
        step = next(s for s in out["steps"] if s["step"] == "leases")
        assert not step["ok"] and "could not be read (connection refused)" in step["detail"]
        assert any(r["step"] == "leases" and "Release lease…" in r.get("how_to_finish", "")
                   for r in out["remaining"]), out["remaining"]


# ── the page: DHCP › Leases › Release lease… ────────────────────────────────────────────────

@pytest.fixture
def page(web, kea, monkeypatch):  # noqa: F811 (the fixtures above)
    """The page with Kea as captured behind it, answering deletes, and the record kept here."""
    kept = []
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    monkeypatch.setattr(L, "record", _recorder(kept))
    return dict(web, kea=kea, kept=kept)


def _preview(page, **args):
    from urllib.parse import urlencode
    return page["client"].get("/v2/dhcp/lease?" + urlencode(dict(args, list="Lab")))


def _as_person(monkeypatch):
    from modules import identity
    who = types.SimpleNamespace(actor="operator@example.invalid", kind="person",
                                peer="192.0.2.5", is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "request_actor", lambda: who.actor)


def test_each_lease_row_offers_release_lease(web):  # noqa: F811
    from tests.test_dhcp_v2 import FakeKea as ReaderKea, _store, _value
    _store(_value(kea=ReaderKea()))
    html = web["client"].get("/v2/dhcp/view?list=Lab&tab=lea").get_data(as_text=True)
    links = re.findall(r'href="(/v2/dhcp/lease\?[^"]+)"', html)
    assert len(links) == html.count(">Release lease…</a>") >= 9, len(links)
    assert any("family=IPv4" in u and "address=10.10.10.102" in u for u in links)
    assert any("family=IPv6" in u and re.search(r"address=2001(:|%3A)db8(:|%3A)10(:|%3A){2}103", u, re.I)
               for u in links), links
    assert "/v2/help/dhcp-lease-release" in html


def test_the_preview_draws_the_lease_its_checks_and_its_confirm(page):
    html = _preview(page, **RIG).get_data(as_text=True)
    assert 'id="dh-op"' in html and "Release 10.10.10.102" in html
    assert "- lease 10.10.10.102 (IPv4, MAC aa:c1:ab:b0:85:65, ends " in html
    assert re.search(r'name="hash" value="[0-9a-f]{64}"', html) and 'name="reason"' in html
    assert page["kea"].dels == []


def test_a_refused_preview_says_why_and_offers_no_confirm(page):
    html = _preview(page, family="IPv4", address="10.10.10.199").get_data(as_text=True)
    assert "Not released" in html and "Kea holds no lease on 10.10.10.199 now" in html
    assert 'name="hash"' not in html


@pytest.mark.real_identity
def test_the_confirm_needs_a_verified_person(page):
    html = _preview(page, **RIG).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{64})"', html).group(1)
    r = page["client"].post("/v2/dhcp/lease?list=Lab", data=dict(RIG, hash=h, reason="gone"))
    assert r.status_code in (401, 403)
    assert page["kea"].dels == []


def test_the_confirm_releases_reads_back_and_records_in_place(page, monkeypatch):
    _as_person(monkeypatch)
    html = _preview(page, **RIG).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{64})"', html).group(1)
    r = page["client"].post("/v2/dhcp/lease?list=Lab",
                            data=dict(RIG, hash=h, reason="VM recreated"))
    done = r.get_data(as_text=True)
    assert r.status_code == 200, done
    assert "released" in done and "a1b2c3d" in done
    assert "Actor: operator@example.invalid" in done
    assert page["kea"].dels == [("lease4-del", {"ip-address": "10.10.10.102"})]
    assert page["kept"][0][2]["reason"] == "VM recreated"
    # The same preview confirmed again: the lease is gone, so nothing is sent again.
    again = page["client"].post("/v2/dhcp/lease?list=Lab",
                                data=dict(RIG, hash=h, reason="twice"))
    assert again.status_code == 409
    assert "Nothing was released." in again.get_data(as_text=True)
    assert len(page["kea"].dels) == 1


def test_a_network_that_inherits_its_kea_is_refused_naming_the_owner(page, monkeypatch):
    from modules import list_settings
    monkeypatch.setattr(list_settings, "kea_owner", lambda name: ("Default", "inherited"))
    monkeypatch.setattr(list_settings, "same_network", lambda a, b: False)
    html = _preview(page, **RIG).get_data(as_text=True)
    assert re.search(r"Lab uses Default('|&#39;)s Kea \(inherited\)", html) and 'name="hash"' not in html
    assert page["kea"].sent == []


def test_the_record_s_file_is_named_where_the_manual_says():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "docs", "manual", "how-it-works", "dhcp-lease-release.md"),
              encoding="utf-8") as fh:
        assert L.RECORD in fh.read()
    assert json.dumps(L.DELETE) == '{"IPv4": "lease4-del", "IPv6": "lease6-del"}'
