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
        assert set(doc["services"]) == {"netbox", "netbox-worker", "postgres", "valkey",
                                        "prometheus"}
        for name in ("netbox", "postgres", "valkey"):
            env = doc["services"][name]["env_file"]
            assert env == ["${KIT_HOME:?KIT_HOME is unset}/netbox/secrets.env"], name

    def test_netbox_is_published_on_loopback_only(self):
        import yaml

        doc = yaml.safe_load(open(os.path.join(ROOT, "lab", "sdn-laptop", "compose.yml"),
                                  encoding="utf-8"))
        ports = [p for s in doc["services"].values() for p in s.get("ports", [])]
        assert ports and all(p.startswith("127.0.0.1:") for p in ports), ports

    def test_prometheus_is_published_on_loopback_only(self):
        ports = _compose()["services"]["prometheus"]["ports"]
        assert ports == ["127.0.0.1:${PROMETHEUS_PORT:-9090}:9090"]


def _compose():
    import yaml

    return yaml.safe_load(open(os.path.join(ROOT, "lab", "sdn-laptop", "compose.yml"),
                               encoding="utf-8"))


def _wide_ports(doc) -> list:
    """Each ``(service, port)`` of a Compose document published anywhere but 127.0.0.1 or
    [::1]: a port with no host address is published on every address."""
    return [(name, p) for name, svc in sorted(doc["services"].items())
            for p in svc.get("ports", [])
            if not (p.startswith("127.0.0.1:") or p.startswith("[::1]:"))]


def _fake_docker(tmp_path, body):
    """A `docker` on PATH that answers as *body* (a shell script's lines): no container is
    run, and every call is appended to ``calls`` beside it."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text("#!/bin/sh\necho \"$@\" >> \"$(dirname \"$0\")/calls\"\n"
                                 + body + "\n")
    (fake / "docker").chmod(0o755)
    return fake


def _kit_home(tmp_path, env_lines=("PIN_SHA=0000000",)):
    home = tmp_path / "kit"
    (home / "run").mkdir(parents=True, exist_ok=True)
    (home / "kit.env").write_text("\n".join(env_lines) + "\n")
    return home


def _settings_init(data, **env):
    """`kit_settings.py init` as the kit runs it, a child process on its own data folder."""
    base = {k: v for k, v in os.environ.items() if k != "PROMETHEUS_PORT"}
    base["NMAS_DATA_DIR"] = str(data)
    return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                        "kit_settings.py"), "init"],
                          cwd=ROOT, capture_output=True, text=True, env=dict(base, **env))


class TestTheKitsPrometheus:
    """The operator's work order after the Lab 9 sitting (2026-11-10): "Prometheus as part of
    the kit (started and stopped by ./kit, pinned v2.53.0, loopback)". Held on the kit's files,
    no container run: Docker is a stand-in on PATH that records what the kit asked of it."""

    KIT = os.path.join(ROOT, "lab", "sdn-laptop", "kit")
    NAME, PROJECT = "kit-prometheus", "nmas-sdn-lab-netbox"

    def _kit(self, tmp_path, docker, *args, env_lines=("PIN_SHA=0000000",)):
        home = _kit_home(tmp_path, env_lines)
        fake = _fake_docker(tmp_path, docker)
        r = subprocess.run(["bash", self.KIT, *args], capture_output=True, text=True,
                           env=dict(os.environ, KIT_HOME=str(home),
                                    PATH=f"{fake}:{os.environ['PATH']}"))
        calls = (fake / "calls").read_text() if (fake / "calls").exists() else ""
        return r, calls

    def test_the_image_is_pinned_as_the_others_are(self):
        doc = _compose()
        assert doc["services"]["prometheus"]["image"] == "docker.io/prom/prometheus:v2.53.0"
        for name, svc in doc["services"].items():
            image = svc["image"]
            assert image.startswith("docker.io/") and ":" in image.rsplit("/", 1)[-1], name
            assert not image.endswith(":latest"), name

    def test_its_configuration_is_the_kits_file_read_only_and_its_data_a_volume(self):
        doc = _compose()
        svc = doc["services"]["prometheus"]
        assert svc["volumes"] == [
            "${KIT_FILES:?KIT_FILES is unset}/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
            "prometheus-data:/prometheus"]
        assert "prometheus-data" in doc["volumes"]
        src = open(self.KIT, encoding="utf-8").read()
        assert 'KIT_FILES="$HERE"' in src and "export KIT_FILES" in src
        assert os.path.isfile(os.path.join(ROOT, "lab", "sdn-laptop", "prometheus.yml"))

    def test_it_scrapes_nothing_and_says_why(self):
        import yaml

        path = os.path.join(ROOT, "lab", "sdn-laptop", "prometheus.yml")
        doc = yaml.safe_load(open(path, encoding="utf-8"))
        assert doc["scrape_configs"] == [], "no target is invented"
        assert not any(k in doc for k in ("remote_write", "remote_read", "alerting",
                                          "rule_files")), "nothing leaves the laptop"
        assert "It scrapes NOTHING, on purpose" in open(path, encoding="utf-8").read()

    def test_the_kits_names_are_the_compose_files(self):
        doc = _compose()
        src = open(self.KIT, encoding="utf-8").read()
        assert doc["name"] == self.PROJECT and f"PROJECT={self.PROJECT}\n" in src
        assert doc["services"]["prometheus"]["container_name"] == self.NAME
        assert f"PROM={self.NAME}\n" in src

    def test_start_stop_and_reset_are_the_one_compose_project(self):
        src = open(self.KIT, encoding="utf-8").read()
        start = src[src.index("cmd_start() {"):src.index("cmd_stop() {")]
        stop = src[src.index("cmd_stop() {"):src.index("cmd_status() {")]
        # Asked before anything is changed: the guard and the identity exception come after.
        assert start.index("prom_not_ours") < start.index("guard_on") \
            < start.index("exception-on") < start.index('"${COMPOSE[@]}" up -d')
        assert "prometheus: started as $PROM on 127.0.0.1:$PROMETHEUS_PORT" in start
        assert '"${COMPOSE[@]}" stop' in stop and "netbox and prometheus: stopped" in stop
        # Nothing removes a container by name: the one `rm` is in the refusal's words.
        assert src.count("docker rm") == 1 and "Remove that one yourself" in src
        assert "docker rm" in src[src.index("prom_not_ours() {"):src.index("guard_on() {")]

    def test_a_container_of_that_name_the_kit_did_not_make_is_refused_and_kept(self, tmp_path):
        """The operator's hand-run one: no Compose label. The kit names it and the one command
        that removes it, and asks Docker nothing but that one read."""
        r, calls = self._kit(tmp_path, 'echo ""', "prometheus-check")
        assert r.returncode == 1
        assert ("kit: refused to start: a container named kit-prometheus exists that this kit "
                "did not make (its Compose project label is 'none', the kit's is "
                "'nmas-sdn-lab-netbox')") in r.stderr
        assert "removes nothing it did not make" in r.stderr
        assert r.stderr.rstrip().endswith("then start again: docker rm -f kit-prometheus")
        assert calls.splitlines() == [
            'container inspect -f {{ index .Config.Labels "com.docker.compose.project" }} '
            "kit-prometheus"], "one read, and no rm, stop or run"

    def test_another_projects_container_of_that_name_is_refused_naming_its_project(
            self, tmp_path):
        r, _calls = self._kit(tmp_path, "echo someone-elses", "prometheus-check")
        assert r.returncode == 1 and "label is 'someone-elses'" in r.stderr

    def test_the_kits_own_container_and_no_container_both_pass(self, tmp_path):
        r, _calls = self._kit(tmp_path, f"echo {self.PROJECT}", "prometheus-check")
        assert r.returncode == 0, r.stderr
        assert "prometheus: no container named kit-prometheus but the kit's own" in r.stdout
        r, _calls = self._kit(tmp_path, "exit 1", "prometheus-check")     # no such container
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("stack,line", [
        ("netbox running\nprometheus running\n",
         "prometheus: running (kit-prometheus, 127.0.0.1:9090)"),
        ("netbox running\nprometheus exited\n",
         "prometheus: exited (kit-prometheus, 127.0.0.1:9090)"),
        ("netbox running\n",
         "prometheus: not created (kit start makes it) (kit-prometheus, 127.0.0.1:9090)"),
    ])
    def test_status_shows_it_by_name_and_where_it_is_published(self, tmp_path, stack, line):
        (tmp_path / "stack").write_text(stack)
        r, calls = self._kit(tmp_path, f'cat "{tmp_path}/stack"', "status")
        assert r.returncode == 0, r.stderr
        assert line in r.stdout.splitlines()
        assert "netbox stack: netbox running" in r.stdout.splitlines()
        assert not [ln for ln in r.stdout.splitlines() if ln.startswith("netbox stack: prom")]
        assert " ps -a --format {{.Service}} {{.State}}" in calls

    def test_status_takes_the_port_from_kit_env(self, tmp_path):
        (tmp_path / "stack").write_text("prometheus running\n")
        r, _calls = self._kit(tmp_path, f'cat "{tmp_path}/stack"', "status",
                              env_lines=("PIN_SHA=0000000", "PROMETHEUS_PORT=9191"))
        assert "prometheus: running (kit-prometheus, 127.0.0.1:9191)" in r.stdout

    def test_a_new_kit_env_names_its_port_and_an_old_one_takes_the_default(self):
        src = open(self.KIT, encoding="utf-8").read()
        init = src[src.index("cmd_init() {"):src.index("ensure_code_repo() {")]
        assert "\nPROMETHEUS_PORT=9090\n" in init
        assert '"${PROMETHEUS_PORT:=9090}"' in src and "export PROMETHEUS_PORT" in src

    def test_the_preflight_asks_it_and_judges_what_listens_on_its_port(self):
        src = open(os.path.join(ROOT, "lab", "sdn-laptop", "kit_preflight.sh"),
                   encoding="utf-8").read()
        assert 'http://127.0.0.1:$PROMETHEUS_PORT/-/ready' in src
        assert 'loopback_only Prometheus "$PROMETHEUS_PORT"' in src
        assert 'loopback_only Mercury "$MERCURY_PORT"' in src
        body = src[src.index("loopback_only() {"):src.index("loopback_only Mercury")]
        assert 'ss -ltnH "sport = :$2"' in body and "kit_net_check.py\" listen" in body


class TestInitSetsTheKitsPrometheus:
    """`kit init` and `kit repin` write the kit's own Prometheus's URL into the installation's
    settings through Mercury's write path, when the key is absent: Topology has it with no
    hand step, and a URL set in Settings is kept. Run as the kit runs it."""

    def _line(self, r):
        return next(ln for ln in r.stdout.splitlines() if ln.startswith("installation settings"))

    def test_a_fresh_kit_is_given_the_loopback_url_on_the_kits_port(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = _settings_init(data, PROMETHEUS_PORT="9191")
        assert r.returncode == 0, r.stderr
        settings = json.loads((data / "user_settings.json").read_text())
        assert settings["prometheus_url"] == "http://127.0.0.1:9191"
        assert "prometheus_url" in self._line(r).split("; kept ", 1)[0]

    def test_the_default_port_is_composes(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = _settings_init(data)
        assert r.returncode == 0, r.stderr
        url = json.loads((data / "user_settings.json").read_text())["prometheus_url"]
        port = _compose()["services"]["prometheus"]["ports"][0]
        assert url == "http://127.0.0.1:9090" and port == "127.0.0.1:${PROMETHEUS_PORT:-9090}:9090"

    def test_a_url_set_before_is_kept(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "user_settings.json").write_text(json.dumps(
            {"prometheus_url": "http://[::1]:9099"}))
        r = _settings_init(data)
        assert r.returncode == 0, r.stderr
        settings = json.loads((data / "user_settings.json").read_text())
        assert settings["prometheus_url"] == "http://[::1]:9099"
        assert "prometheus_url" in self._line(r).split("; kept ", 1)[1]

    def test_the_kit_hands_its_port_to_the_settings_init(self):
        src = open(os.path.join(ROOT, "lab", "sdn-laptop", "kit"), encoding="utf-8").read()
        in_wt = src[src.index("in_wt() {"):src.index("nmas_names() {")]
        assert 'PROMETHEUS_PORT="$PROMETHEUS_PORT"' in in_wt


class TestEveryServiceListensOnLoopbackOnly:
    """The kit's loopback rule ("Kit stays loopback-only; nothing is exposed to teammates"),
    judged on what LISTENS on a service's port (`kit_net_check.judge_listen`, the preflight's
    "Mercury on loopback only" and "Prometheus on loopback only"). The fixtures are `ss -ltnH
    "sport = :<port>"`'s own answers (iproute2 6.19.0, 2026-11-11) for four listeners started
    in a private user and network namespace (`unshare -rn`): 127.0.0.1:9090, 0.0.0.0:9091, a
    dual-stack wildcard on 9092 and [::1]:9093, unedited.

    The accept set is exactly the one the preflight's line had before `judge_listen` judged
    it, 127.0.0.1 and [::1] as `ss` writes them (the operator: "Don't weaken or bypass the
    check"): an address that is also loopback and is neither is refused too."""

    FIX = os.path.join(ROOT, "tests", "fixtures", "ss")

    @pytest.fixture
    def net(self):
        return _load("kit_net_check", "lab/sdn-laptop/kit_net_check.py")

    def _f(self, name):
        return open(os.path.join(self.FIX, name), encoding="utf-8").read()

    @pytest.mark.parametrize("name,port,said", [("loopback4.txt", "9090", "127.0.0.1"),
                                                ("loopback6.txt", "9093", "[::1]")])
    def test_a_loopback_listener_passes_in_either_family(self, net, name, port, said):
        assert net.judge_listen(self._f(name), port) == (True, said)

    @pytest.mark.parametrize("name,port,wide", [("wide4.txt", "9091", "0.0.0.0"),
                                                ("wide-dual.txt", "9092", "*")])
    def test_a_wider_binding_is_refused_naming_it(self, net, name, port, wide):
        ok, words = net.judge_listen(self._f(name), port)
        assert not ok
        assert words == (f"listening on {wide}: {wide} is not 127.0.0.1 or [::1], so port "
                         f"{port} is not known to listen on loopback only")

    def test_one_wide_listener_beside_a_loopback_one_still_fails(self, net):
        """Docker publishing on every address is a listener per family: one loopback line
        beside it must not carry the port."""
        both = self._f("loopback4.txt") + self._f("wide4.txt").replace(":9091", ":9090")
        ok, words = net.judge_listen(both, "9090")
        assert not ok and words.startswith("listening on 0.0.0.0 127.0.0.1: 0.0.0.0 is not")

    @pytest.mark.parametrize("address", ["192.0.2.7", "[2001:db8::7]", "[::]"])
    def test_a_lan_address_of_either_family_and_the_ipv6_wildcard_fail(self, net, address):
        planted = self._f("loopback4.txt").replace("127.0.0.1:9090", f"{address}:9090")
        ok, words = net.judge_listen(planted, "9090")
        assert not ok and f"{address} is not 127.0.0.1 or [::1]" in words

    @pytest.mark.parametrize("address", ["127.0.0.2", "127.1.2.3", "[::1%lo]", "::1",
                                         "[::ffff:127.0.0.1]", "localhost"])
    def test_another_loopback_address_is_refused_as_the_old_check_refused_it(self, net,
                                                                             address):
        """Each is, or names, a loopback address, and none is 127.0.0.1 or [::1] as `ss`
        writes them: the preflight's pattern before `judge_listen` refused each, so this
        does. The accept set is the operator's, never widened here."""
        import re

        planted = self._f("loopback4.txt").replace("127.0.0.1:9090", f"{address}:9090")
        ok, words = net.judge_listen(planted, "9090")
        assert (ok, words) == (False, f"listening on {address}: {address} is not 127.0.0.1 or "
                                      "[::1], so port 9090 is not known to listen on loopback "
                                      "only")
        # The line it replaced, as kit_preflight.sh had it at 6a7d61f1: a FAIL when it matches.
        old = re.compile(r"^(127\.0\.0\.1|\[::1\]| )+$")
        assert not old.match(f"{address} "), "the old check refused it too"

    def test_the_accept_set_is_the_old_patterns_two_addresses_and_no_more(self, net):
        import re

        old = re.compile(r"^(127\.0\.0\.1|\[::1\]| )+$")
        assert net.ACCEPTED == ("127.0.0.1", "[::1]")
        assert all(old.match(f"{a} ") for a in net.ACCEPTED)
        both = self._f("loopback4.txt") + self._f("loopback6.txt").replace(":9093", ":9090")
        assert net.judge_listen(both, "9090") == (True, "127.0.0.1 [::1]")

    def test_nothing_listening_fails_too(self, net):
        assert net.judge_listen("", "9090") == (False, "nothing listens on port 9090")

    def test_the_preflights_line_for_a_wide_prometheus_is_a_fail(self):
        """The script as the preflight runs it: a planted wider binding, and the refusal."""
        r = subprocess.run(
            ["python3", "-I", os.path.join(ROOT, "lab", "sdn-laptop", "kit_net_check.py"),
             "listen"], capture_output=True, text=True,
            env=dict(os.environ, LISTEN=self._f("wide4.txt"), PORT="9091", LABEL="Prometheus"))
        assert r.returncode == 1
        assert r.stdout.strip() == ("FAIL Prometheus on loopback only: listening on 0.0.0.0: "
                                    "0.0.0.0 is not 127.0.0.1 or [::1], so port 9091 is not "
                                    "known to listen on loopback only")

    def test_the_preflights_line_for_mercury_on_loopback_passes(self):
        r = subprocess.run(
            ["python3", "-I", os.path.join(ROOT, "lab", "sdn-laptop", "kit_net_check.py"),
             "listen"], capture_output=True, text=True,
            env=dict(os.environ, LISTEN=self._f("loopback4.txt"), PORT="9090", LABEL="Mercury"))
        assert r.returncode == 0 and r.stdout.strip() == "PASS Mercury on loopback only: 127.0.0.1"

    def test_a_compose_port_published_wider_is_refused_by_the_files_own_check(self):
        """The same rule on the file: a planted wider publication of Prometheus's port."""
        doc = _compose()
        assert _wide_ports(doc) == []
        for wide in ("9090:9090", "0.0.0.0:9090:9090", "[::]:9090:9090", "192.0.2.7:9090:9090"):
            doc["services"]["prometheus"]["ports"] = [wide]
            assert _wide_ports(doc) == [("prometheus", wide)], wide


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


class TestRevealForTheS1SittingOnly:
    """C2897 (the operator's approval of 2026-11-10: the kit's identity exception widened to
    reveal "scoped to the S1 sitting only, expiring automatically after it"): `exception-on
    UNTIL --reveal` opens reveal too, recorded, and is refused after REVEAL_UNTIL; the stop's
    `exception-off` closes reveal whatever opened it; safety passes an open reveal only before
    the cap. KIT_NOW stands in for the clock."""

    BEFORE, AFTER = "2026-11-10T15:00Z", "2026-11-11T08:00Z"

    def _run(self, data, now, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                            "kit_settings.py"), *args],
                              cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, NMAS_DATA_DIR=str(data), KIT_NOW=now))

    def _gates(self, data):
        s = json.loads((data / "user_settings.json").read_text())
        return {a: s.get(f"require_identity_for_{a}", True)
                for a in ("configure", "confirm", "approve", "reveal")}

    def test_reveal_opens_with_the_exception_and_the_stop_closes_it(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._run(data, self.BEFORE, "exception-on", "2026-11-11T05:00Z", "--reveal")
        assert r.returncode == 0, r.stderr
        assert "reveal open too, C2897" in r.stdout
        assert self._gates(data) == {"configure": False, "confirm": False, "approve": False,
                                     "reveal": False}
        safety = self._run(data, self.BEFORE, "safety")
        assert "PASS reveal gated (or open for the sitting" in safety.stdout
        r = self._run(data, self.BEFORE, "exception-off", "the kit's stop")
        assert r.returncode == 0, r.stderr
        assert all(self._gates(data).values()), "the stop closes reveal too"

    def test_without_reveal_it_stays_gated(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        assert self._run(data, self.BEFORE, "exception-on", "2026-11-11T05:00Z").returncode == 0
        assert self._gates(data)["reveal"] is True

    def test_after_the_cap_reveal_is_refused_and_nothing_is_written(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._run(data, self.AFTER, "exception-on", "2026-11-12T05:00Z", "--reveal")
        assert r.returncode != 0 and "--reveal refused" in (r.stdout + r.stderr)
        assert not (data / "user_settings.json").exists() or self._gates(data)["reveal"] is True

    def test_an_open_reveal_after_the_cap_fails_the_safety_check(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        assert self._run(data, self.BEFORE, "exception-on", "2026-11-11T05:00Z",
                         "--reveal").returncode == 0
        safety = self._run(data, self.AFTER, "safety")
        assert "FAIL reveal gated (or open for the sitting" in safety.stdout


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


class TestInitMarksTheKitAndOpensOnLab9:
    """C2521 (the operator, 2026-11-05): `kit init` writes `installation_kind: laptop_kit`, so
    Needs attention marks the server's own checks not applicable (tests/test_installation_kind),
    and makes lab9 the installation's current network, so Mercury opens on it: the kit has no
    verified person whose own choice the picker could record. Run as the kit runs it."""

    def _init(self, data):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                            "kit_settings.py"), "init"],
                              cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, NMAS_DATA_DIR=str(data)))

    def _records(self, data):
        path = data / "settings_record.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()
                if '"network_current"' in line] if path.exists() else []

    def test_it_sets_the_kind_and_makes_lab9_current_recorded(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._init(data)
        assert r.returncode == 0, r.stderr
        settings = json.loads((data / "user_settings.json").read_text())
        assert settings["installation_kind"] == "laptop_kit"
        registry = json.loads((data / "device_lists.json").read_text())
        assert registry["current_list"] == "lab9" and "lab9" in registry["lists"]
        assert "lab9: the installation's current network (recorded in History)" in r.stdout
        (rec,) = self._records(data)
        assert rec["changes"][0]["old"] == "Default" and rec["changes"][0]["new"] == "lab9"
        assert rec["actor"] == "lab kit (scripts: lab/sdn-laptop)"

    def test_a_second_init_records_nothing_more(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        assert self._init(data).returncode == 0
        r = self._init(data)
        assert r.returncode == 0, r.stderr
        assert "current network is lab9, set before: kept" in r.stdout
        assert len(self._records(data)) == 1


class TestLab9sCodeRepository:
    """The operator's decision of 2026-11-10 (Drafts reach the code repository only through
    Mercury's Add an app as a Draft…): `kit init` and `kit repin` make lab9's code repository,
    bare and empty on main, under KIT_HOME when it is absent, never replacing one; the
    settings init sets lab9's `code_repository` to it through Mercury's per-network write when
    lab9 has none, recorded, and never sets who may publish (`code_review`), the operator's
    choice. Run as the kit runs them."""

    KIT = os.path.join(ROOT, "lab", "sdn-laptop", "kit")

    def _ensure(self, home):
        return subprocess.run(["bash", self.KIT, "ensure-code-repo"], capture_output=True,
                              text=True, env=dict(os.environ, KIT_HOME=str(home)))

    def _init(self, data, home):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                            "kit_settings.py"), "init"],
                              cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, NMAS_DATA_DIR=str(data), KIT_HOME=str(home)))

    def _setting(self, data):
        path = data / "lists" / "lab9" / "settings.json"
        return json.loads(path.read_text()).get("values", {}) if path.exists() else {}

    def _records(self, data):
        path = data / "lists" / "lab9" / "settings_record.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()
                if '"code_repository"' in line] if path.exists() else []

    def test_the_kit_makes_it_bare_and_empty_once(self, tmp_path):
        repo = tmp_path / "code" / "lab9.git"
        r = self._ensure(tmp_path)
        assert r.returncode == 0 and "made (bare, empty, branch main)" in r.stdout, r.stderr
        git = ["git", "-C", str(repo)]
        assert subprocess.run(git + ["rev-parse", "--is-bare-repository"], capture_output=True,
                              text=True).stdout.strip() == "true"
        assert subprocess.run(git + ["symbolic-ref", "HEAD"], capture_output=True,
                              text=True).stdout.strip() == "refs/heads/main"
        (repo / "kept").write_text("a Draft added since\n")
        r = self._ensure(tmp_path)
        assert r.returncode == 0 and "kept" in r.stdout and (repo / "kept").exists()

    def test_init_and_repin_make_it_before_the_settings_init(self):
        src = open(self.KIT, encoding="utf-8").read()
        for start, end in (("cmd_init() {", "ensure_code_repo() {"),
                           ("cmd_after_repin() {", "cmd_check() {")):
            body = src[src.index(start):src.index(end)]
            assert body.index("ensure_code_repo") < body.index("kit_settings.py\" init")

    def test_init_sets_lab9s_to_it_recorded_and_never_who_may_publish(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        assert self._ensure(tmp_path).returncode == 0
        r = self._init(data, tmp_path)
        assert r.returncode == 0, r.stderr
        repo = str(tmp_path / "code" / "lab9.git")
        assert f"code repository: lab9's set to {repo}, branch main (recorded)" in r.stdout
        s = self._setting(data)
        assert s["code_repository"] == repo and s["code_repository_branch"] == "main"
        assert "code_review" not in s, "who may publish is the operator's"
        (rec,) = self._records(data)
        assert rec["after"] == f"{repo}\nmain" and rec["actor"] == "lab kit (scripts: lab/sdn-laptop)"
        r = self._init(data, tmp_path)
        assert "code repository: lab9's is set before: kept" in r.stdout
        assert len(self._records(data)) == 1

    def test_with_no_repository_init_sets_nothing(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        r = self._init(data, tmp_path)
        assert r.returncode == 0 and "(kit init makes it): not set" in r.stdout, r.stderr
        assert "code_repository" not in self._setting(data) and self._records(data) == []


#: The operator's own values, planted before init or repin runs again: each must survive.
OPERATOR = {"netbox_url": "http://[::1]:8101", "netbox_auth_scheme": "Token",
            "heal_mode": "dry_run"}
OPERATOR_ENV = {"CONTROLLER_ADDR": "192.0.2.50", "LAB_IF": "enp9s0", "WIFI_IF": "wlp2s0",
                "LAB_PROFILE": "lab9-bench", "MERCURY_PORT": "5081", "NETBOX_PORT": "8002"}
#: A token built by concatenation, never a literal one; it is never printed.
TOKEN = "plant" + "ed-" + "kit-token-" + "0042"
_PLANT = ("import os, sys; sys.path.insert(0, os.getcwd()); "
          "from modules.settings_schema import write_settings; import json; "
          "from modules.secrets_store import encrypt_value; "
          "got = write_settings(dict(json.loads(os.environ['PLANT']), "
          "netbox_token=encrypt_value(os.environ['PLANT_TOKEN'])), actor='the operator'); "
          "sys.exit(0 if got.get('ok') else 1)")


def _plant_operator(data, cwd=ROOT):
    r = subprocess.run([sys.executable, "-c", _PLANT], cwd=cwd, capture_output=True, text=True,
                       env=dict(os.environ, NMAS_DATA_DIR=str(data), PLANT=json.dumps(OPERATOR),
                                PLANT_TOKEN=TOKEN, PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, "the operator's values could not be planted"
    return json.loads((data / "user_settings.json").read_text())


def _assert_kept(before, data):
    after = json.loads((data / "user_settings.json").read_text())
    for key, value in OPERATOR.items():
        assert after[key] == value, f"{key} was overwritten"
    # Compared as booleans, so a failure prints no part of the token.
    unchanged = after["netbox_token"] == before["netbox_token"]
    in_clear = TOKEN in after["netbox_token"]
    assert unchanged is True, "the stored token was changed"
    assert in_clear is False, "the token is stored in the clear"
    assert after["installation_kind"] == "laptop_kit", "a missing key was not added"
    return after


class TestInitAddsOnlyWhatIsMissing:
    """The operator, 2026-11-05: init runs again on every `kit repin`, so it writes a setting
    only when its key is absent from the stored file, and says which it added and kept by
    name; lab9 is made current only when no current network was set."""

    def _init(self, data):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lab", "sdn-laptop",
                                                            "kit_settings.py"), "init"],
                              cwd=ROOT, capture_output=True, text=True,
                              env=dict(os.environ, NMAS_DATA_DIR=str(data)))

    def test_the_operators_values_survive_and_the_missing_are_added(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        before = _plant_operator(data)
        r = self._init(data)
        assert r.returncode == 0, r.stderr
        _assert_kept(before, data)
        line = next(ln for ln in r.stdout.splitlines() if ln.startswith("installation settings"))
        added, kept = line.split("; kept ", 1)
        assert "installation_kind" in added and "flask_host" in added
        for key in ("heal_mode", "netbox_url"):
            assert key in kept and key not in added
        printed = TOKEN in r.stdout + r.stderr
        assert printed is False, "the token was printed"

    def test_a_current_network_set_before_is_kept(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "device_lists.json").write_text(json.dumps(
            {"current_list": "Branch", "lists": {"Default": "default", "Branch": "branch"}}))
        r = self._init(data)
        assert r.returncode == 0, r.stderr
        assert json.loads((data / "device_lists.json").read_text())["current_list"] == "Branch"
        assert "current network is Branch, set before: kept" in r.stdout


class TestRepinRunsInitAndKeepsTheOperatorsValues:
    """`kit repin` moves the worktree, changes only kit.env's PIN_SHA, and runs init again.
    Run as the operator runs it, on a planted kit: a throwaway repository holding the kit's
    two scripts and the product's code by link, a worktree of it at one commit, a fake
    `systemctl` that says Mercury is stopped, and the operator's values planted."""

    GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}

    def _git(self, *args):
        r = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], capture_output=True,
                           text=True, env=dict(os.environ, **self.GIT))
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    @pytest.fixture
    def kit(self, tmp_path):
        import shutil

        repo = tmp_path / "repo"
        (repo / "lab" / "sdn-laptop").mkdir(parents=True)
        for name in ("kit", "kit_settings.py"):
            shutil.copy2(os.path.join(ROOT, "lab", "sdn-laptop", name),
                         repo / "lab" / "sdn-laptop" / name)
        for name in ("modules", "routes"):
            os.symlink(os.path.join(ROOT, name), repo / name)
        self._git("init", "-q", str(repo))
        self._git("-C", str(repo), "add", "-A")
        self._git("-C", str(repo), "commit", "-q", "-m", "one")
        one = self._git("-C", str(repo), "rev-parse", "HEAD")
        self._git("-C", str(repo), "commit", "-q", "--allow-empty", "-m", "two")
        two = self._git("-C", str(repo), "rev-parse", "HEAD")
        home = tmp_path / "kit"
        (home / "data").mkdir(parents=True)
        (home / "run").mkdir()
        self._git("-C", str(repo), "worktree", "add", "-q", "--detach", str(home / "mercury"), one)
        env_lines = [f"PIN_SHA={one}"] + [f"{k}={v}" for k, v in OPERATOR_ENV.items()]
        (home / "kit.env").write_text("\n".join(env_lines) + "\n")
        fake = tmp_path / "bin"
        fake.mkdir()
        (fake / "systemctl").write_text("#!/bin/sh\nexit 3\n")
        (fake / "systemctl").chmod(0o755)
        before = _plant_operator(home / "data", cwd=str(home / "mercury"))
        return {"repo": repo, "home": home, "one": one, "two": two, "before": before,
                "env": dict(os.environ, KIT_HOME=str(home), KIT_PYTHON=sys.executable,
                            PATH=f"{fake}:{os.environ['PATH']}")}

    def _repin(self, kit):
        return subprocess.run([str(kit["repo"] / "lab" / "sdn-laptop" / "kit"), "repin",
                               kit["two"]], capture_output=True, text=True, env=kit["env"])

    def test_repin_keeps_every_operator_value_and_adds_the_missing(self, kit):
        r = self._repin(kit)
        assert r.returncode == 0, r.stderr
        assert "kit: repinned at" in r.stdout and "installation settings: added" in r.stdout
        _assert_kept(kit["before"], kit["home"] / "data")
        env = dict(ln.split("=", 1) for ln in
                   (kit["home"] / "kit.env").read_text().splitlines() if "=" in ln)
        assert env.pop("PIN_SHA") == kit["two"], "PIN_SHA did not move"
        assert env == OPERATOR_ENV, "kit.env changed beyond PIN_SHA"
        printed = TOKEN in r.stdout + r.stderr
        assert printed is False, "the token was printed"

    def test_repin_still_refuses_a_dirty_worktree(self, kit):
        (kit["home"] / "mercury" / "stray.txt").write_text("x")
        r = self._repin(kit)
        assert r.returncode != 0 and "is not clean" in r.stderr
        assert f"PIN_SHA={kit['one']}" in (kit["home"] / "kit.env").read_text()
        settings = json.loads((kit["home"] / "data" / "user_settings.json").read_text())
        assert "installation_kind" not in settings, "init ran on a refused repin"

    def test_the_steps_after_the_move_are_the_new_commits(self, kit):
        """C2569 (the operator's repin to ee620634, 2026-11-05): run from the worktree it
        moves, as the operator runs it, a repin's steps after the checkout come from the NEW
        commit's script; bash had read the old one's function first, so a step the new commit
        added to repin itself never ran (its init, there)."""
        path = kit["repo"] / "lab" / "sdn-laptop" / "kit"
        text = path.read_text()
        anchor = "cmd_after_repin() {   # the steps a repin runs after the move"
        assert text.count(anchor) == 1
        path.write_text(text.replace(anchor, "cmd_after_repin() {\n  echo \"the new "
                                     "commit's own step\"  # the steps a repin runs after the move"))
        self._git("-C", str(kit["repo"]), "commit", "-q", "-am", "three")
        three = self._git("-C", str(kit["repo"]), "rev-parse", "HEAD")
        r = subprocess.run([str(kit["home"] / "mercury" / "lab" / "sdn-laptop" / "kit"),
                            "repin", three], capture_output=True, text=True, env=kit["env"])
        assert r.returncode == 0, r.stderr
        assert "the new commit's own step" in r.stdout, r.stdout
        assert "installation settings: added" in r.stdout
        assert f"PIN_SHA={three}" in (kit["home"] / "kit.env").read_text()


class TestMakeCurrent:
    """`network_admin.make_current`, the installation's current network, for an installation
    with no person to choose (C2521): refused for a network that is not registered, naming it."""

    @pytest.fixture
    def registry(self, tmp_path, monkeypatch):
        from modules import config, device

        path = tmp_path / "device_lists.json"
        path.write_text(json.dumps({"current_list": "Default",
                                    "lists": {"Default": "default", "lab9": "lab9"}}))
        monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(path))
        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
        return path

    def test_an_unregistered_network_is_refused_naming_it(self, registry):
        from modules import network_admin

        with pytest.raises(network_admin.Refused, match="'lab10'.*Default, lab9"):
            network_admin.make_current("lab10", "test", "none")
        assert json.loads(registry.read_text())["current_list"] == "Default"

    def test_a_registered_one_is_made_current(self, registry):
        from modules import network_admin

        got = network_admin.make_current("lab9", "test", "none")
        assert got["changed"] and got["recorded"]
        assert json.loads(registry.read_text())["current_list"] == "lab9"


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
