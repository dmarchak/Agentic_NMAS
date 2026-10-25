"""C1181: a Kea server has ONE owning network (the operator's design, 2026-10-17).

In W4 (2026-10-17) every DHCP confirm of section D was made on a DHCP page reading "network: W4
walk", which inherits Kea from Default, so eight commits for the installation's one Kea landed
in W4 walk's repository and left with it when W4 walk was deleted. The design:

- the owner is the network where Kea's connection is SET, never one inheriting it; measured from
  the settings layers (`list_settings.kea_owner`), never from a name;
- every DHCP record (reservations, subnets, exclusions) is committed in the OWNER's repository
  and published with the owner's remote, whatever network it was made from; the commit names
  that network in a `From-Network:` trailer when it is another;
- a DHCP preview or confirm from a network that does not own its Kea is refused, naming both;
- two networks may not each set the same Kea as their own: Settings refuses the second, naming
  the network that has it (the Control Agent's URL, normalised: host, port and path);
- ZTP's reservation (onboarding's reserve step, and Abandon's removal) is written on the OWNER's
  Kea and recorded in the owner's repository the same way (C1243, C1235): it was written on the
  installation's Kea, through a client built for no network, and committed nowhere.

Driven on real repositories and real settings stores in a temporary data folder, with the lab's
captured Kea answers (tests/test_dhcp_reservations' fake Kea loading Mercury's files).
"""

import json
import os
import re
import subprocess
import types

import pytest

from modules import config
from modules import dhcp_exclusions as E
from modules import dhcp_reservations as D
from modules import dhcp_subnets as S
from modules import list_settings as L
from tests.test_dhcp_reservations import ADD, FakeKea, kea_dir  # noqa: F401 (a fixture)

DEFAULT_KEA = "http://192.0.2.53:8000"
OTHER_KEA = "http://192.0.2.54:8000"


@pytest.fixture
def nets(tmp_path, monkeypatch):
    """Three networks: Default sets Kea; Branch and Lab start inheriting it."""
    lists = tmp_path / "lists"
    lists.mkdir()
    monkeypatch.setattr(config, "LISTS_DIR", str(lists))
    registry = tmp_path / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Default", "lists": {
        "Default": "default", "Branch": "branch", "Lab": "lab"}}), encoding="utf-8")
    monkeypatch.setattr("modules.device.DEVICE_LISTS_CONFIG", str(registry))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"kea_url": DEFAULT_KEA}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    published = []
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit",
                        lambda context: published.append(dict(context)))
    return {"lists": lists, "published": published, "settings": settings}


def _own(nets, name, slug, url):
    """*name* sets its own Kea at *url* (the store as `list_settings.write` leaves it)."""
    folder = nets["lists"] / slug
    folder.mkdir(exist_ok=True)
    (folder / "settings.json").write_text(json.dumps({"values": {"kea_url": url}}),
                                          encoding="utf-8")


def _log(nets, slug):
    """The repository's DHCP commits (``Source: dhcp``), newest first, each its full message;
    [] for none (the repository's own first commit is not one)."""
    repo = nets["lists"] / slug / "config_repo"
    if not (repo / ".git").is_dir():
        return []
    out = subprocess.run(["git", "-C", str(repo), "log", "--format=%B%x00"],
                         capture_output=True, text=True, check=False).stdout
    return [m.strip() for m in out.split("\x00")
            if "Source: dhcp" in m.strip().splitlines()]


def _from(nets, slug):
    """Each DHCP commit's From-Network trailer lines, newest first."""
    return [[line for line in m.splitlines() if line.startswith("From-Network:")]
            for m in _log(nets, slug)]


def _published(nets):
    """The networks whose remote each DHCP commit was handed to, in order."""
    return [c["list_name"] for c in nets["published"] if c["source"] == "dhcp"]


def _files(nets, slug):
    repo = nets["lists"] / slug / "config_repo"
    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD"],
                         capture_output=True, text=True, check=False).stdout
    return out.split()


# ------------------------------------------------------------------------- the owner, measured

class TestTheOwner:
    def test_a_network_inheriting_kea_is_owned_by_default(self, nets):
        assert L.kea_owner("Branch") == ("Default", "Branch inherits Kea from Default")

    def test_default_owns_its_own(self, nets):
        assert L.kea_owner("Default")[0] == "Default"

    def test_a_network_with_its_own_different_kea_owns_it(self, nets):
        """Control: a network that sets its own Kea is its owner, whatever Default sets."""
        _own(nets, "Lab", "lab", OTHER_KEA)
        assert L.kea_owner("Lab") == ("Lab", "Kea is set on Lab")

    def test_measured_from_the_layers_never_the_name(self, nets):
        """A standalone network takes nothing from Default: its Kea, not configured, is its own,
        and no other network's name decides it."""
        folder = nets["lists"] / "branch"
        folder.mkdir()
        (folder / "settings.json").write_text(json.dumps({"values": {}, "mode": "standalone"}),
                                              encoding="utf-8")
        assert L.kea_owner("Branch")[0] == "Branch"

    @pytest.mark.parametrize("a, b", [
        ("http://192.0.2.53:8000", "http://192.0.2.53:8000/"),
        ("http://192.0.2.53", "http://192.0.2.53:80"),
        ("https://KEA.example.invalid", "https://kea.example.invalid:443/"),
        ("http://user:secret@192.0.2.53:8000", "http://192.0.2.53:8000"),
        ("http://[2001:db8:0::1]:8000", "http://[2001:db8::1]:8000"),
    ])
    def test_one_kea_by_its_control_agent_s_url_normalised(self, a, b):
        assert L.service_identity(a) == L.service_identity(b)

    @pytest.mark.parametrize("url, words", [
        ("http://[2001:DB8:0::1]:8000/", "[2001:db8::1]:8000"),
        ("http://192.0.2.53:8000/", "192.0.2.53:8000"),
    ])
    def test_the_place_is_written_as_a_person_reads_it(self, url, words):
        """The refusal names the place (`taken_words`): an IPv6 one in brackets, so its port is
        not read as the address's last group."""
        assert L.service_identity(url) == words

    def test_another_port_or_host_is_another_kea(self):
        assert L.service_identity(DEFAULT_KEA) != L.service_identity(OTHER_KEA)
        assert L.service_identity(DEFAULT_KEA) != L.service_identity("http://192.0.2.53:8001")
        assert "secret" not in L.service_identity("http://user:secret@192.0.2.53:8000")


# ------------------------------------------------------------- the record, in the owner's repo

def _apply(network, kea_dir, values=None):  # noqa: F811 (the fixture's value)
    kea = FakeKea(kea_dir["files"])
    values = values or ADD()
    p = D.plan(network, values, kea=kea)
    assert p["ok"], p["refused"]
    return D.apply(network, values, p["hash"], actor="person@example.invalid",
                   reason="h5 is the printer", kea=kea, run_test=lambda path: (True, "ok"))


class TestTheRecord:
    def test_a_write_from_an_inheriting_network_records_in_the_owner_s_repository(
            self, nets, kea_dir):  # noqa: F811
        out = _apply("Branch", kea_dir)
        assert out["ok"], out["error"]
        default = _log(nets, "default")
        assert len(default) == 1 and out["commit"], default
        assert default[0].startswith("dhcp: h5 reserved 10.10.20.150")
        assert "From-Network: Branch" in default[0].splitlines()
        assert "Actor: person@example.invalid" in default[0].splitlines()
        assert "dhcp/reservations.yml" in _files(nets, "default")
        assert _log(nets, "branch") == [], "a record of Default's Kea went to Branch's repository"
        # Published with the OWNER's remote.
        assert _published(nets) == ["Default"]

    def test_the_owner_s_own_write_is_unchanged(self, nets, kea_dir):  # noqa: F811
        """Control: Default's own write records in Default's repository with no From-Network."""
        out = _apply("Default", kea_dir)
        assert out["ok"], out["error"]
        assert _from(nets, "default") == [[]]
        assert _published(nets) == ["Default"]

    def test_a_network_with_its_own_kea_records_in_its_own(self, nets, kea_dir):  # noqa: F811
        """Control: Lab's own, different Kea is Lab's, recorded in Lab's repository."""
        _own(nets, "Lab", "lab", OTHER_KEA)
        out = _apply("Lab", kea_dir)
        assert out["ok"], out["error"]
        assert len(_log(nets, "lab")) == 1 and _log(nets, "default") == []
        assert _from(nets, "lab") == [[]]

    def test_a_subnet_record_from_an_inheriting_network_goes_to_the_owner(
            self, nets, kea_dir):  # noqa: F811
        got = S.record_commit("Branch", {"subject": "dhcp: subnet 20 changed"},
                              actor="person@example.invalid", reason="a wider pool")
        assert got["ok"], got
        assert _from(nets, "default") == [["From-Network: Branch"]]
        assert _log(nets, "branch") == []

    def test_an_exclusion_is_recorded_and_read_where_the_owner_keeps_it(
            self, nets, kea_dir):  # noqa: F811
        record = {"exclusions": [{"family": "IPv4", "subnet": 20,
                                  "range": "10.10.20.150 - 10.10.20.150",
                                  "reason": "a printer", "source": "operator"}],
                  "pools": {"IPv4:20": "10.10.20.100 - 10.10.20.200"}}
        got = E.record_commit("Branch", {"subject": "dhcp: 10.10.20.150 excluded",
                                         "record": record},
                              actor="person@example.invalid", reason="a printer")
        assert got["ok"], got
        assert _from(nets, "default") == [["From-Network: Branch"]]
        # Every page showing Default's Kea reads the one record: the owner's.
        got = E.read_committed("Branch")["exclusions"]
        assert [e["range"] for e in got] == ["10.10.20.150 - 10.10.20.150"]
        assert E.read_committed("Default") == E.read_committed("Branch")


# ------------------------------------------------------------------ the routes, refused by name

@pytest.fixture
def web(nets, kea_dir, monkeypatch):  # noqa: F811
    """The DHCP page over the reader's stored value (the lab's capture), Kea a fake loading
    Mercury's files, and a verified person."""
    from modules import identity, reader_job
    from modules.nsot import ztp
    from tests.test_dhcp_v2 import _store, _value

    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    monkeypatch.setattr("modules.dhcp_page._devices", lambda name: set())
    kea = FakeKea(kea_dir["files"])
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: kea)
    monkeypatch.setattr(ztp, "_run_kea_test", lambda path, program="kea-dhcp4": (True, "ok"))
    who = types.SimpleNamespace(actor="operator@example.invalid", kind="person",
                                peer="192.0.2.5", is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "request_actor", lambda: who.actor)
    path = _store(_value())
    import app as A
    yield dict(nets, client=A.app.test_client(), kea=kea, files=kea_dir["files"])
    if os.path.exists(path):
        os.remove(path)


BOTH = re.compile(r"Branch uses Default(&#39;|')s Kea \(Branch inherits Kea from Default\): a "
                  r"change to it is made on Default(&#39;|')s DHCP page")

CONFIRMS = {
    "reservation": dict(ADD(), where="IPv4:20", reason="h5 is the printer"),
    "subnet": {"op": "edit", "family": "IPv4", "id": "20", "pool": "10.10.20.100-10.10.20.180",
               "reason": "a narrower pool"},
    "exclusion": {"op": "add", "family": "IPv4", "id": "20", "range": "10.10.20.150",
                  "why": "a printer", "reason": "a printer"},
}


@pytest.mark.parametrize("what", sorted(CONFIRMS))
def test_a_confirm_from_an_inheriting_network_is_refused_naming_both(web, what):
    before = {k: open(p, encoding="utf-8").read() for k, p in web["files"].items()}
    r = web["client"].post(f"/v2/dhcp/{what}?list=Branch",
                           data=dict(CONFIRMS[what], hash="0" * 64))
    html = r.get_data(as_text=True)
    assert r.status_code == 409, html
    assert BOTH.search(html), html[-3000:]
    assert "Nothing was written" in html
    assert not [c for c in web["kea"].sent if c[0] == "config-reload"]
    assert {k: open(p, encoding="utf-8").read() for k, p in web["files"].items()} == before
    assert _log(web, "default") == [] and _log(web, "branch") == []


@pytest.mark.parametrize("what", sorted(CONFIRMS))
def test_a_preview_from_an_inheriting_network_offers_no_confirm(web, what):
    from urllib.parse import urlencode
    r = web["client"].get(f"/v2/dhcp/{what}?" + urlencode(dict(CONFIRMS[what], list="Branch")))
    html = r.get_data(as_text=True)
    assert BOTH.search(html), html[-3000:]
    assert 'name="hash"' not in html


def _write_links(html):
    """Every Add, Edit or Remove the page draws: a link to one of the three previews."""
    return sorted(set(re.findall(r'href="(/v2/dhcp/(?:subnet|reservation|exclusion)\?[^"]*)"', html)))


@pytest.mark.parametrize("tab", ["", "res", "exc"])
def test_an_inheriting_network_s_page_is_read_only_and_links_to_the_owner(web, tab):
    """C1181's page: Branch inherits Default's Kea, so its DHCP page draws Kea's data with no
    Add, Edit or Remove, and says whose Kea it is, linking to the owner's page."""
    html = web["client"].get(f"/v2/dhcp?list=Branch&tab={tab}").get_data(as_text=True)
    assert re.search(r"Branch uses Default(&#39;|')s Kea", html), html[:3000]
    assert 'href="/v2/dhcp?list=Default"' in html
    assert _write_links(html) == []


@pytest.mark.parametrize("tab", ["res", "exc"])
def test_the_owner_s_page_draws_its_controls_and_no_owner_line(web, tab):
    """Control: Default's own page draws its Add (the fixture holds no Mercury subnet, so the
    subnets tab has none to draw) and no "uses <owner>'s Kea"."""
    html = web["client"].get(f"/v2/dhcp?list=Default&tab={tab}").get_data(as_text=True)
    assert "dh-owner" not in html
    assert [u for u in _write_links(html) if "op=add" in u], _write_links(html)


def test_the_owner_s_confirm_is_unchanged(web):
    """Control: on Default's own page the same reservation is previewed, written and recorded
    in Default's repository."""
    from urllib.parse import urlencode
    values = dict(CONFIRMS["reservation"], list="Default")
    p = web["client"].get("/v2/dhcp/reservation?" + urlencode(values)).get_data(as_text=True)
    h = re.search(r'name="hash" value="([0-9a-f]{64})"', p).group(1)
    r = web["client"].post("/v2/dhcp/reservation?list=Default", data=dict(values, hash=h))
    assert r.status_code == 200, r.get_data(as_text=True)[-3000:]
    assert len(_log(web, "default")) == 1


# --------------------------------------------------------- Settings: no second "Its own" Kea

class TestOneOwnerPerKea:
    def test_a_second_network_setting_the_same_kea_is_refused_naming_the_owner(self, nets):
        out = L.write("Branch", {"kea_url": DEFAULT_KEA + "/"})
        assert not out["ok"]
        assert "Kea at 192.0.2.53:8000/ is already Default's own" not in out["error"]
        assert "Kea at 192.0.2.53:8000 is already Default's own: Branch may not" in out["error"]
        assert not (nets["lists"] / "branch" / "settings.json").exists()

    def test_the_switch_to_its_own_with_the_same_kea_is_refused_at_its_confirm(self, nets):
        plan = L.plan_group("Branch", "kea", L.OWN, entering=True)
        with pytest.raises(L.SwitchRefused, match="is already Default's own: Branch may not"):
            L.apply_group("Branch", "kea", L.OWN, plan["fingerprint"], "person@example.invalid",
                          values={"kea_url": DEFAULT_KEA}, seen=plan["operands"])
        assert L.kea_owner("Branch")[0] == "Default"

    def test_default_may_not_take_a_kea_another_network_owns(self, nets):
        _own(nets, "Lab", "lab", OTHER_KEA)
        out = L.write("Default", {"kea_url": OTHER_KEA})
        assert not out["ok"] and "is already Lab's own: Default may not" in out["error"]
        assert json.loads(nets["settings"].read_text())["kea_url"] == DEFAULT_KEA

    def test_a_different_kea_is_saved(self, nets):
        """Control: a network setting its own, different Kea is saved and owns it."""
        assert L.write("Branch", {"kea_url": OTHER_KEA})["ok"]
        assert L.kea_owner("Branch")[0] == "Branch"

    def test_the_owner_saving_its_own_kea_again_is_not_refused(self, nets):
        """Control: the network that has the Kea is never its own rival."""
        _own(nets, "Lab", "lab", OTHER_KEA)
        assert L.write("Lab", {"kea_url": OTHER_KEA + "/"})["ok"]

    def test_an_unreadable_network_refuses_rather_than_reading_as_no_owner(self, nets):
        folder = nets["lists"] / "lab"
        folder.mkdir()
        (folder / "settings.json").write_text("{not json", encoding="utf-8")
        out = L.write("Branch", {"kea_url": OTHER_KEA})
        assert not out["ok"] and "Lab's settings could not be read" in out["error"]


# ------------------------------------- ZTP's reservation, on the owner's Kea and in its record

ZTP_MAC = "aa:bb:cc:00:02:50"
ZTP_ADDR = "10.255.0.50"          # in the captured ZTP subnet, 255 (10.255.0.0/24)
ZTP_HOST = "bp-ztp-a"
ACTOR = "person@example.invalid"


def _settings(path, **values):
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc.update(values)
    path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def ztp_world(nets, kea_dir, monkeypatch):  # noqa: F811
    """Default sets Kea and its ZTP fragment (subnet 255's file, which Kea's IPv4 configuration
    includes); Kea is the captured fake loading Mercury's files, each client built recorded with
    what it was built for; D4's DNS condition measured silent, and this host's address on the
    ZTP subnet given (the real `plan_check` otherwise)."""
    from modules.nsot import ztp

    fragment = kea_dir["files"][("dhcp4", 255)]
    _settings(nets["settings"], kea_ztp_fragment=fragment,
              kea_dhcp4_config=kea_dir["main"]["IPv4"])
    kea = FakeKea(kea_dir["files"])
    built = []
    monkeypatch.setattr("modules.integrations.kea.KeaIntegration",
                        lambda **kw: built.append(kw) or kea)
    monkeypatch.setattr(ztp, "_run_kea_test", lambda path, program="kea-dhcp4": (True, "ok"))
    real = ztp.plan_check
    monkeypatch.setattr(ztp, "plan_check", lambda mac, address, **kw: real(
        mac, address, dns=lambda source: {"state": "silent", "measured_at": 1.0},
        addrs={"ztp0": ["10.255.0.1"]}, **kw))
    monkeypatch.setattr("modules.secrets_store.KEY_FILE", str(kea_dir["dir"] / "key.key"))
    return dict(nets, kea=kea, built=built, fragment=fragment, kea_dir=kea_dir)


def _ztp_plan(network):
    from modules.nsot.onboard import OnboardPlan
    return OnboardPlan(hostname=ZTP_HOST, platform="cisco_iosxe", list_name=network,
                       address_source="ztp", mgmt_mac=ZTP_MAC, reservation_address=ZTP_ADDR)


def _repo_of(world, slug):
    return str(world["lists"] / slug / "config_repo")


def _reserve(world, network):
    """Create's reserve step as production assembles it (`real_steps`), or why it raised."""
    from modules.config import list_slug
    from modules.nsot import onboard

    step = onboard.real_steps(_repo_of(world, list_slug(network)), actor=ACTOR)["reserve"]
    try:
        return step(_ztp_plan(network))
    except RuntimeError as exc:
        return {"raised": str(exc)}


def _fragment_macs(path):
    with open(path, encoding="utf-8") as fh:
        return [r.get("hw-address") for r in json.load(fh)]


def _recorded(world, slug):
    """ZTP's record as committed at HEAD of *slug*'s repository, parsed; None for none."""
    import yaml
    out = subprocess.run(["git", "-C", _repo_of(world, slug), "show",
                          "HEAD:dhcp/ztp-reservations.yml"],
                         capture_output=True, text=True, check=False)
    return yaml.safe_load(out.stdout) if out.returncode == 0 else None


def _refusing_commits(world, slug):
    """*slug*'s repository refuses every commit, by its own pre-commit hook: a real git
    failure, so the record's commit fails where it would."""
    from modules.nsot import repo as R

    repo = _repo_of(world, slug)
    R.init_repo(repo)
    hook = os.path.join(repo, ".git", "hooks", "pre-commit")
    with open(hook, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\necho refused by the test hook >&2\nexit 1\n")
    os.chmod(hook, 0o755)


class TestZtpReservationRecordedInTheOwner:
    def test_a_reservation_from_an_inheriting_network_is_recorded_in_the_owner_s_repository(
            self, ztp_world):
        out = _reserve(ztp_world, "Branch")
        assert ZTP_MAC in _fragment_macs(ztp_world["fragment"]), out
        commits = _log(ztp_world, "default")
        assert len(commits) == 1, (out, commits)
        lines = commits[0].splitlines()
        assert lines[0] == f"ztp: {ZTP_HOST} reserved {ZTP_MAC} -> {ZTP_ADDR}", lines
        assert "From-Network: Branch" in lines and f"Actor: {ACTOR}" in lines, lines
        assert _recorded(ztp_world, "default")["reservations"] == [
            {"mac": ZTP_MAC, "address": ZTP_ADDR, "hostname": ZTP_HOST,
             "server": "10.255.0.1", "file": f"{ZTP_HOST}.cfg"}]
        assert _log(ztp_world, "branch") == [], "a record of Default's Kea in Branch's repository"
        assert _published(ztp_world) == ["Default"]
        rec = out.get("record") or {}
        assert rec.get("ok") and rec.get("owner") == "Default" and rec.get("commit"), out

    def test_the_owner_s_own_reservation_carries_no_from_network(self, ztp_world):
        """Control: Default onboarding on its own Kea records in its own repository, with no
        From-Network."""
        out = _reserve(ztp_world, "Default")
        assert (out.get("record") or {}).get("ok"), out
        assert _from(ztp_world, "default") == [[]]

    def test_the_check_and_the_write_ask_the_owner_s_kea(self, ztp_world):
        """C1235: Kea's client is built for the owning network, at the write-time check and at
        the write, never for no network."""
        _reserve(ztp_world, "Branch")
        assert ztp_world["built"], "no Kea client was built"
        assert [kw.get("list_name") for kw in ztp_world["built"]] == \
            ["Default"] * len(ztp_world["built"]), ztp_world["built"]

    def test_a_network_with_its_own_kea_reserves_on_its_own_and_records_there(
            self, ztp_world, tmp_path):
        """C1235: Lab sets its own Kea and fragment; Default's fragment is absent, so a writer
        reading Default's settings writes nothing."""
        absent = str(tmp_path / "default-kea" / "reservations-255.json")
        _settings(ztp_world["settings"], kea_ztp_fragment=absent)
        folder = ztp_world["lists"] / "lab"
        folder.mkdir(exist_ok=True)
        (folder / "settings.json").write_text(json.dumps({"values": {
            "kea_url": OTHER_KEA, "kea_ztp_fragment": ztp_world["fragment"],
            "kea_dhcp4_config": ztp_world["kea_dir"]["main"]["IPv4"]}}), encoding="utf-8")
        out = _reserve(ztp_world, "Lab")
        assert ZTP_MAC in _fragment_macs(ztp_world["fragment"]), out
        assert [kw.get("list_name") for kw in ztp_world["built"]] == \
            ["Lab"] * len(ztp_world["built"]), ztp_world["built"]
        assert len(_log(ztp_world, "lab")) == 1 and _from(ztp_world, "lab") == [[]], out
        assert _log(ztp_world, "default") == []

    def test_a_record_that_fails_to_commit_is_create_s_partial_never_silent(self, ztp_world):
        """The reservation is in Kea and its record is not committed: Create's result says so
        in place (never green), and nothing is undone."""
        from modules.nsot import onboard
        from modules.preview_confirm import onboard_create_result

        _refusing_commits(ztp_world, "default")
        plan = _ztp_plan("Branch")
        steps = onboard.real_steps(_repo_of(ztp_world, "branch"), actor=ACTOR)
        run = onboard.run_onboarding(
            types.SimpleNamespace(**{**plan.__dict__, "onboardable": True}),
            bind_credentials=lambda p: None, commit=lambda p: "c0ffee", render=lambda p: "",
            reserve=steps["reserve"])
        assert ZTP_MAC in _fragment_macs(ztp_world["fragment"]), run
        kept = run.get("reserve_record") or {}
        assert kept and not kept.get("ok"), run
        assert "refused by the test hook" in kept.get("error", ""), kept
        drawn = onboard_create_result(run, plan)
        assert drawn["record"].get("written") is False, drawn["record"]
        assert drawn["level"] != "success"
        said = " ".join(i["text"] for i in drawn["did_not"]["items"])
        assert "NOT committed in Default's repository" in said, said
        assert "NOT committed in Default's repository" in drawn["record"]["statement"]

    def test_the_config_check_holds_the_record_to_its_shape(self, ztp_world):
        """ZTP's record is one of the DHCP records the commit's config check reads: one whose
        reservations are not a list is refused, naming the file; the writer's own passes."""
        from modules.nsot import config_check, ztp

        assert (_reserve(ztp_world, "Default").get("record") or {}).get("commit")
        repo = _repo_of(ztp_world, "default")
        path = os.path.join(repo, ztp.RECORD)
        assert config_check.precommit(repo, [ztp.RECORD], list_name="Default") == ""
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("reservations: not a list\n")
        refused = config_check.precommit(repo, [ztp.RECORD], list_name="Default")
        assert "not a DHCP record" in refused and ztp.RECORD in refused, refused


def _pending_ztp_device(world, slug):
    """A pending ZTP device in *slug*'s repository, as Create's commit step leaves it."""
    from modules.nsot import manifest as _m
    from modules.nsot.repo import adopt_identity, init_repo

    repo = _repo_of(world, slug)
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    init_repo(repo)
    identity = adopt_identity(hostname=ZTP_HOST, mgmt_ip="")
    _m.upsert_device(repo, identity, ZTP_HOST, platform="cisco_iosxe", pending=True,
                     address_source="ztp", mgmt_mac=ZTP_MAC, reserved_address=ZTP_ADDR)
    return repo


def _reserved_by_hand(world):
    """The reservation in the fragment and in Kea, with no record of it anywhere."""
    from modules.nsot import ztp

    with open(world["fragment"], "w", encoding="utf-8") as fh:
        json.dump([ztp.reservation_entry(ZTP_MAC, ZTP_ADDR, ZTP_HOST, "10.255.0.1")], fh)
    world["kea"].command("config-reload")


def _abandon(world, repo, network):
    from modules.nsot import onboard
    return onboard.abandon_onboarding(
        repo, ZTP_HOST, network, actor=ACTOR,
        remove_netbox=lambda *a, **k: {"ok": True, "deleted": [], "skipped": []})


class TestZtpAbandonRecordedInTheOwner:
    def test_abandon_s_removal_is_recorded_in_the_owner_s_repository(self, ztp_world):
        repo = _pending_ztp_device(ztp_world, "branch")
        _reserved_by_hand(ztp_world)
        out = _abandon(ztp_world, repo, "Branch")
        assert ZTP_MAC not in _fragment_macs(ztp_world["fragment"]), out
        assert out["ok"] and out["released"] == ZTP_HOST, out
        commits = _log(ztp_world, "default")
        assert len(commits) == 1, (out["steps"], commits)
        lines = commits[0].splitlines()
        assert lines[0] == f"ztp: {ZTP_HOST}'s reservation removed ({ZTP_MAC})", lines
        assert "From-Network: Branch" in lines and f"Actor: {ACTOR}" in lines, lines
        assert _recorded(ztp_world, "default")["reservations"] == []
        assert _log(ztp_world, "branch") == []
        step = [s for s in out["steps"] if s["step"] == "reservation"][0]
        assert "recorded in Default's repository" in step["detail"], step

    def test_a_removal_whose_record_fails_releases_the_name_and_says_so(self, ztp_world):
        """The reservation is gone, so the name is released; the run is not drawn as done, and
        it says the record was not committed and that the name is free."""
        from modules.nsot import onboard
        from modules.preview_confirm import onboard_abandon_result

        repo = _pending_ztp_device(ztp_world, "branch")
        _reserved_by_hand(ztp_world)
        _refusing_commits(ztp_world, "default")
        out = _abandon(ztp_world, repo, "Branch")
        assert ZTP_MAC not in _fragment_macs(ztp_world["fragment"]), out
        step = [s for s in out["steps"] if s["step"] == "reservation"][0]
        assert not step["ok"] and "NOT committed in Default's repository" in step["detail"], step
        assert out["released"] == ZTP_HOST and not out["ok"], out
        row = onboard.record_run(repo, "abandon", "Branch", ZTP_HOST, ACTOR, out)["row"]
        drawn = onboard_abandon_result(row)
        assert drawn["level"] == "partial", drawn["level"]
        assert "not free" not in drawn["happened"]["summary"], drawn["happened"]["summary"]
