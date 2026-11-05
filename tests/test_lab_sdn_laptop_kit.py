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
