"""The final SDN lab's laptop kit (lab/sdn-laptop, docs/LAB9_LAPTOP_RUN.md; the operator,
2026-11-05).

Held here:
- the kit refuses to start when any setting points at the NMAS host's services, its golden
  repository or a GitHub config repository (`kit_check.problems`), naming the key and never the
  value;
- nmas-deploy refuses to run from the kit's installation (its marker).

The NMAS host's names are planted as 192.0.2.x and an example domain, never the real ones.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAN, TUNNEL = "192.0.2.211", "ssh-nmas.example.org"


def _load(name, rel):
    path = os.path.join(ROOT, *rel.split("/"))
    loader = importlib.machinery.SourceFileLoader(name, path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def check(monkeypatch):
    monkeypatch.setenv("KIT_NMAS_LAN", LAN)
    monkeypatch.setenv("KIT_NMAS_TUNNEL", TUNNEL)
    return _load("kit_check", "lab/sdn-laptop/kit_check.py")


def _data(tmp_path, top=None, lists=None):
    d = tmp_path / "data"
    (d / "lists").mkdir(parents=True)
    (d / "user_settings.json").write_text(json.dumps(top or {"flask_host": "127.0.0.1",
                                                            "netbox_url": "http://127.0.0.1:8001"}))
    for slug, settings in (lists or {}).items():
        (d / "lists" / slug).mkdir()
        (d / "lists" / slug / "settings.json").write_text(json.dumps(settings))
    return str(d)


class TestTheSettingsCheck:
    def test_a_clean_kit_passes(self, check, tmp_path):
        assert check.problems(_data(tmp_path, lists={"lab9": {"values": {}}})) == []

    @pytest.mark.parametrize("value", [
        f"http://{LAN}:3000",                      # the host's LAN address
        f"ssh://{TUNNEL}/config",                  # the tunnel's name
        "https://grafana.example.org",             # a service under the tunnel's domain
        "https://github.com/someone/configs.git",  # a GitHub config repository
    ])
    def test_a_setting_at_the_host_or_github_is_refused_by_key(self, check, tmp_path, value):
        got = check.problems(_data(tmp_path, lists={"lab9": {"values": {"grafana_url": value}}}))
        assert got == ["lists/lab9/settings.json: values.grafana_url points at the NMAS host's "
                       "services or GitHub"]
        assert value not in " ".join(got)

    def test_the_installations_own_settings_are_read_too(self, check, tmp_path):
        got = check.problems(_data(tmp_path, top={"flask_host": "127.0.0.1",
                                                  "loki_url": f"http://{LAN}:3100"}))
        assert got == ["user_settings.json: loki_url points at the NMAS host's services or "
                       "GitHub"]

    def test_a_list_with_any_git_remote_is_refused(self, check, tmp_path):
        data = _data(tmp_path, lists={"lab9": {"values": {}}})
        repo = os.path.join(data, "lists", "lab9", "config_repo")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "remote", "add", "origin", "/srv/elsewhere.git"],
                       check=True)
        assert check.problems(data) == ["lists/lab9/config_repo has a git remote: the kit's "
                                        "lists keep none"]

    @pytest.mark.parametrize("top,words", [
        ({"flask_host": "0.0.0.0"}, "flask_host is not a loopback address"),
        ({"flask_host": "127.0.0.1", "netbox_url": "http://192.0.2.50:8000"},
         "netbox_url is not the kit's own NetBox"),
        ({"flask_host": "127.0.0.1", "netbox_url": "http://[2001:db8::5]:8000"},
         "netbox_url is not the kit's own NetBox"),
    ])
    def test_mercury_and_netbox_stay_on_loopback(self, check, tmp_path, top, words):
        assert any(words in p for p in check.problems(_data(tmp_path, top=top)))

    def test_ipv6_loopback_netbox_passes(self, check, tmp_path):
        top = {"flask_host": "127.0.0.1", "netbox_url": "http://[::1]:8001"}
        assert check.problems(_data(tmp_path, top=top)) == []

    def test_without_the_hosts_names_the_check_refuses(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KIT_NMAS_LAN", raising=False)
        monkeypatch.delenv("KIT_NMAS_TUNNEL", raising=False)
        r = subprocess.run(["python3", "-I", os.path.join(ROOT, "lab", "sdn-laptop",
                                                          "kit_check.py"), _data(tmp_path)],
                           capture_output=True, text=True)
        assert r.returncode == 1 and "cannot rule them out" in r.stdout


class TestTheComposeFile:
    """lab/sdn-laptop/compose.yml parses, and binds NetBox to loopback only (its first real
    `kit init`, 2026-11-05, failed: `${KIT_HOME:?…}` inside a YAML flow list did not parse)."""

    def test_it_parses_as_yaml_with_every_service(self):
        import yaml

        doc = yaml.safe_load(open(os.path.join(ROOT, "lab", "sdn-laptop", "compose.yml"),
                                  encoding="utf-8"))
        assert set(doc["services"]) == {"netbox", "netbox-worker", "postgres", "valkey"}
        for name in ("netbox", "postgres", "valkey"):
            env = doc["services"][name]["env_file"]
            assert env == ["${KIT_HOME:?KIT_HOME is unset}/netbox/secrets.env"], name

    def test_netbox_is_published_on_loopback_only(self):
        import yaml

        doc = yaml.safe_load(open(os.path.join(ROOT, "lab", "sdn-laptop", "compose.yml"),
                                  encoding="utf-8"))
        ports = [p for s in doc["services"].values() for p in s.get("ports", [])]
        assert ports and all(p.startswith("127.0.0.1:") for p in ports), ports


class TestTheForwardingGuard:
    """lab9guard (the operator, 2026-11-05): nothing forwarded to or from the lab interface,
    forwarding left on for everything else. The fixture is nft 1.1.6's own answer
    (`nft -j list table inet lab9guard`) for lab9guard.nft.in rendered on enp129s0, loaded in
    a private user and network namespace (`unshare -rn`), 2026-11-05; each failing case is
    that capture with one edit."""

    FIXTURE = os.path.join(ROOT, "tests", "fixtures", "nft", "lab9guard-enp129s0.json")

    @pytest.fixture
    def guard(self):
        return _load("kit_guard_check", "lab/sdn-laptop/kit_guard_check.py")

    def _doc(self):
        return json.load(open(self.FIXTURE, encoding="utf-8"))

    def test_the_real_table_is_in_force(self, guard):
        ok, words = guard.judge(self._doc(), "enp129s0")
        assert ok, words
        assert words.startswith("lab9guard in force on enp129s0")

    def test_another_interface_is_not_guarded(self, guard):
        ok, words = guard.judge(self._doc(), "enp130s0")
        assert not ok and "iifname or oifname 'enp130s0'" in words

    def test_a_missing_direction_fails_naming_it(self, guard):
        doc = self._doc()
        doc["nftables"] = [i for i in doc["nftables"]
                           if "lab9guard: nothing forwarded to the lab" not in json.dumps(i)]
        ok, words = guard.judge(doc, "enp129s0")
        assert not ok and "no counted drop for oifname 'enp129s0'" in words

    @pytest.mark.parametrize("edit,words", [
        ({"hook": "input"}, "no chain is hooked on forward"),
        ({"prio": 0}, "priority -10"),
    ])
    def test_a_chain_not_hooked_before_dockers_fails(self, guard, edit, words):
        doc = self._doc()
        for i in doc["nftables"]:
            if "chain" in i:
                i["chain"].update(edit)
        ok, said = guard.judge(doc, "enp129s0")
        assert not ok and words in said

    def test_no_table_fails(self, guard):
        ok, words = guard.judge({}, "enp129s0")
        assert not ok and "not loaded" in words

    def test_a_rule_without_its_counter_fails(self, guard):
        doc = self._doc()
        for i in doc["nftables"]:
            if "rule" in i:
                i["rule"]["expr"] = [e for e in i["rule"]["expr"] if "counter" not in e]
        assert not guard.judge(doc, "enp129s0")[0]

    def test_the_template_renders_both_directions_and_the_priority(self):
        src = open(os.path.join(ROOT, "lab", "sdn-laptop", "lab9guard.nft.in"),
                   encoding="utf-8").read().replace("@LAB_IF@", "enp129s0")
        assert "type filter hook forward priority -10; policy accept;" in src
        assert 'iifname "enp129s0" counter drop' in src
        assert 'oifname "enp129s0" counter drop' in src
        assert "@LAB_IF@" not in src

    def test_start_installs_it_and_stop_removes_it(self):
        src = open(os.path.join(ROOT, "lab", "sdn-laptop", "kit"), encoding="utf-8").read()
        start = src[src.index("cmd_start() {"):src.index("cmd_stop() {")]
        stop = src[src.index("cmd_stop() {"):src.index("cmd_status() {")]
        assert "guard_on" in start and start.index("guard_on") < start.index('"${COMPOSE[@]}" up')
        assert "guard_off" in stop
        assert "sudo nft delete table inet lab9guard" in src


class TestTheDualHomedLaptop:
    """The lab profile is ready on the lab interface (active once a cable is in), and the
    default route stays on the Wi-Fi (the operator, 2026-11-05). The fixtures are the laptop's
    own `nmcli` and `ip` answers of 2026-11-05 ~03:4x UTC, cable unplugged, with minimal
    edits: the Wi-Fi profile's name and the home LAN's addresses replaced (192.0.2.x,
    fe80::1)."""

    FIX = os.path.join(ROOT, "tests", "fixtures", "nm")

    @pytest.fixture
    def net(self):
        return _load("kit_net_check", "lab/sdn-laptop/kit_net_check.py")

    def _f(self, name):
        return open(os.path.join(self.FIX, name), encoding="utf-8").read()

    def test_unplugged_the_profile_is_ready_not_active(self, net):
        ok, words = net.judge_profile(self._f("lab9-profile.txt"),
                                      self._f("active-unplugged.txt"), False, "enp129s0", "lab9")
        assert ok and "ready on enp129s0" in words and "no carrier" in words

    def test_with_a_cable_it_must_be_active_on_the_lab_interface(self, net):
        args = (self._f("lab9-profile.txt"), self._f("active-unplugged.txt"), True,
                "enp129s0", "lab9")
        ok, words = net.judge_profile(*args)
        assert not ok and "its active connection is 'none'" in words
        active = self._f("active-unplugged.txt") + "lab9:enp129s0\n"
        ok, words = net.judge_profile(args[0], active, True, "enp129s0", "lab9")
        assert ok and "active on enp129s0" in words

    def test_another_profile_active_on_it_fails(self, net):
        active = self._f("active-unplugged.txt") + "Wired connection 1:enp129s0\n"
        ok, words = net.judge_profile(self._f("lab9-profile.txt"), active, True, "enp129s0",
                                      "lab9")
        assert not ok and "'Wired connection 1'" in words

    @pytest.mark.parametrize("line,field", [(1, "ipv4.never-default"), (2, "ipv6.never-default"),
                                            (3, "ipv4.ignore-auto-dns"),
                                            (4, "ipv6.ignore-auto-dns")])
    def test_each_setting_must_be_yes(self, net, line, field):
        vals = self._f("lab9-profile.txt").splitlines()
        vals[line] = "no"
        ok, words = net.judge_profile("\n".join(vals), "", False, "enp129s0", "lab9")
        assert not ok and f"{field} 'no'" in words

    def test_a_profile_on_another_interface_or_absent_fails(self, net):
        vals = self._f("lab9-profile.txt").replace("enp129s0", "enp130s0")
        assert "bound to 'enp130s0'" in net.judge_profile(vals, "", False, "enp129s0", "lab9")[1]
        assert "was not found" in net.judge_profile("", "", False, "enp129s0", "lab9")[1]

    def test_the_default_routes_stay_on_the_wifi(self, net):
        ok, words = net.judge_routes(self._f("route4.txt"), self._f("route6.txt"), "wlp130s0",
                                     "enp129s0")
        assert ok and words == "IPv4 via wlp130s0, IPv6 via wlp130s0"

    @pytest.mark.parametrize("family", ["4", "6"])
    def test_a_default_route_via_the_lab_fails_naming_it(self, net, family):
        r4, r6 = self._f("route4.txt"), self._f("route6.txt")
        if family == "4":
            r4 += "default via 192.0.2.254 dev enp129s0 proto dhcp metric 100\n"
        else:
            r6 += "default via fe80::2 dev enp129s0 proto ra metric 100\n"
        ok, words = net.judge_routes(r4, r6, "wlp130s0", "enp129s0")
        assert not ok and "via enp129s0 (the lab interface)" in words
        assert f"IPv{family}" in words

    def test_no_ipv4_default_route_fails(self, net):
        assert not net.judge_routes("", self._f("route6.txt"), "wlp130s0", "enp129s0")[0]


class TestNetBoxsV2TokenPepper:
    """NetBox 4.6 saves a v2 token only with API_TOKEN_PEPPERS (the operator's first run,
    2026-11-05: "Unable to save v2 tokens: API_TOKEN_PEPPERS is not defined"). The image builds
    it from API_TOKEN_PEPPER_1, so `kit ensure-pepper` (which `kit init` runs) puts one in the
    owner-only secrets.env once, never prints it, and never replaces it."""

    KIT = os.path.join(ROOT, "lab", "sdn-laptop", "kit")

    def _run(self, home):
        return subprocess.run(["bash", self.KIT, "ensure-pepper"], capture_output=True,
                              text=True, env=dict(os.environ, KIT_HOME=str(home)))

    def _home(self, tmp_path, secrets="DB_PASSWORD=d\nSECRET_KEY=s\n"):
        (tmp_path / "netbox").mkdir()
        f = tmp_path / "netbox" / "secrets.env"
        f.write_text(secrets)
        f.chmod(0o600)
        return tmp_path, f

    def test_a_missing_pepper_is_added_owner_only_never_printed(self, tmp_path):
        home, f = self._home(tmp_path)
        r = self._run(home)
        assert r.returncode == 0, r.stderr
        lines = f.read_text().splitlines()
        assert lines[:2] == ["DB_PASSWORD=d", "SECRET_KEY=s"]           # the others kept
        pepper = [ln.split("=", 1)[1] for ln in lines if ln.startswith("API_TOKEN_PEPPER_1=")]
        assert len(pepper) == 1 and len(pepper[0]) >= 50
        assert pepper[0] not in r.stdout + r.stderr
        assert oct(f.stat().st_mode & 0o777) == "0o600"

    def test_an_existing_pepper_is_never_replaced(self, tmp_path):
        home, f = self._home(tmp_path, "API_TOKEN_PEPPER_1=" + "a" * 64 + "\n")
        before = f.read_text()
        r = self._run(home)
        assert r.returncode == 0 and f.read_text() == before
        assert "is set (id 1, 64 characters" in r.stdout

    def test_a_short_pepper_is_refused(self, tmp_path):
        home, _f = self._home(tmp_path, "API_TOKEN_PEPPER_1=short\n")
        r = self._run(home)
        assert r.returncode != 0 and "under NetBox's 50" in r.stderr

    def test_init_runs_it_and_the_image_reads_that_name(self):
        src = open(self.KIT, encoding="utf-8").read()
        init = src[src.index("cmd_init() {"):src.index("cmd_check() {")]
        assert "cmd_ensure_pepper" in init
        assert "API_TOKEN_PEPPER_1" in src     # the netbox image's configuration.py reads it

    def test_the_preflight_reads_netboxs_own_settings(self):
        src = open(self.KIT, encoding="utf-8").read()
        pre = src[src.index("cmd_preflight() {"):src.index("cmd_netbox_admin() {")]
        assert "manage.py" in pre and "API_TOKEN_PEPPERS" in pre
        assert "NetBox can save a v2 token" in pre


class TestNetBoxWritesOnForAFreshKit:
    """C2548's bridge (2026-11-05): a fresh install cannot turn NetBox writes on through Mercury
    (an import's confirm turns them on, and an import is not offered for a network with no
    devices, while onboarding a first device needs them on). `kit netbox-writes-on "<why>"`
    writes the switch through Mercury's own path and records it in History with its reason,
    as the identity exception is. Run as the kit runs it, a child process on its own data
    folder."""

    def _run(self, data, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                            "kit_settings.py"),
                               "netbox-writes-on", *args], cwd=ROOT, capture_output=True,
                              text=True, env=dict(os.environ, NMAS_DATA_DIR=str(data)))

    def _records(self, data):
        out = []
        for path in data.rglob("*"):
            if path.is_file() and path.suffix in (".jsonl", ".json"):
                for line in path.read_text(errors="replace").splitlines():
                    if '"netbox_writes_on"' in line:
                        out.append(json.loads(line))
        return out

    def test_it_turns_writes_on_and_records_who_why_and_the_change(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._run(data, "the first sitting's onboarding")
        assert r.returncode == 0, r.stderr
        assert "netbox writes: ON (recorded in History)" in r.stdout
        settings = json.loads((data / "user_settings.json").read_text())
        assert settings["netbox_allow_writes"] is True
        (rec,) = self._records(data)
        assert rec["card"] == "netbox" and rec["fields"] == ["netbox_allow_writes"]
        assert rec["changes"][0]["old"] is False and rec["changes"][0]["new"] is True
        assert "the first sitting's onboarding" in rec["reason"]

    def test_already_on_writes_nothing_more(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        assert self._run(data, "first").returncode == 0
        r = self._run(data, "again")
        assert r.returncode == 0 and "already ON, nothing written" in r.stdout
        assert len(self._records(data)) == 1

    def test_a_reason_is_required(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._run(data, "   ")
        assert r.returncode != 0 and "need a reason" in (r.stdout + r.stderr)
        assert not (data / "user_settings.json").exists() or \
            not json.loads((data / "user_settings.json").read_text()).get("netbox_allow_writes")


class TestNmasDeployRefusesTheKit:
    def test_a_repo_holding_the_marker_is_refused_before_anything_moves(self, tmp_path, capsys):
        nd = _load("nmas_deploy", "scripts/nmas-deploy")
        (tmp_path / nd.LAB_KIT_MARKER).write_text("the kit\n")
        calls = []
        code = nd.main(["--repo", str(tmp_path)], get=lambda *a, **k: calls.append(a),
                       run=lambda *a, **k: calls.append(a))
        assert code == nd.LOCAL_REFUSED and calls == []
        assert "laptop kit" in capsys.readouterr().err

    def test_the_kit_writes_the_marker_nmas_deploy_reads(self):
        nd = _load("nmas_deploy", "scripts/nmas-deploy")
        src = open(os.path.join(ROOT, "lab", "sdn-laptop", "kit"), encoding="utf-8").read()
        assert f'"$WT/{nd.LAB_KIT_MARKER}"' in src
