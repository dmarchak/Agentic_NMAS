"""`scripts/nmas-host`: the ONE choice between a host's LAN address and its
Cloudflare tunnel hostname (the operator, 2026-09-29).

The LAN check is a real TCP connect, driven against a loopback listener and a
closed loopback port. ssh itself is never run (the network guard refuses it):
a recording runner stands in, so what would be sent is asserted instead.
"""

import json
import os
import socket
import subprocess
from importlib.machinery import SourceFileLoader

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = SourceFileLoader("nmas_host", os.path.join(ROOT, "scripts", "nmas-host")).load_module()

# The real hosts are in a local, gitignored file; the tests use documentation
# addresses (RFC 5737) and example names in a file of their own.
FAKE_HOSTS = {"nmas": {"user": "op", "lan": "192.0.2.11", "tunnel": "ssh-nmas.example.net"},
              "clab": {"user": "op", "lan": "192.0.2.10", "tunnel": "ssh-clab.example.net"},
              "pve": {"user": "root", "lan": "192.0.2.80", "tunnel": "ssh-pve.example.net"}}


@pytest.fixture(autouse=True)
def _hosts_file(tmp_path, monkeypatch):
    path = tmp_path / "lab_hosts.json"
    path.write_text(json.dumps(FAKE_HOSTS))
    monkeypatch.setenv(H.HOSTS_FILE_ENV, str(path))
    return path


# The tunnel's own words when the Access token has expired (the operator's report).
EXPIRED = ("websocket: bad handshake\n"
           "Connection closed by UNKNOWN port 65535\n")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Runner:
    def __init__(self, rc=0, err=""):
        self.rc, self.err, self.calls = rc, err, []

    def __call__(self, argv):
        self.calls.append(argv)
        return self.rc, self.err


class TestTheLanCheckIsARealConnect:
    def test_a_listener_answers(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        try:
            assert H.lan_answers("127.0.0.1", srv.getsockname()[1], timeout=1)
        finally:
            srv.close()

    def test_a_closed_port_does_not(self):
        assert not H.lan_answers("127.0.0.1", _free_port(), timeout=1)

    def test_the_bound_is_the_operators_three_seconds(self):
        assert H.LAN_TIMEOUT_S == 3.0 and H.SSH_PORT == 22


class TestTheOneChoice:
    @pytest.mark.parametrize("name,lan,tunnel,user", [
        ("nmas", "192.0.2.11", "ssh-nmas.example.net", "op"),
        ("clab", "192.0.2.10", "ssh-clab.example.net", "op"),
        ("pve", "192.0.2.80", "ssh-pve.example.net", "root")])
    def test_lan_when_it_answers_and_the_tunnel_when_it_does_not(self, name, lan, tunnel, user):
        seen = []
        up = H.choose(name, probe=lambda a: seen.append(a) or True)
        down = H.choose(name, probe=lambda a: False)
        assert seen == [lan], "the probe asks the LAN address, never the tunnel"
        assert (up["path"], up["target"]) == ("LAN", f"{user}@{lan}")
        assert (down["path"], down["target"]) == ("tunnel", f"{user}@{tunnel}")

    def test_the_path_is_said_before_anything_runs(self, capsys):
        runner = Runner()
        assert H.main(["nmas", "--", "uptime"], probe=lambda a: False, runner=runner) == 0
        err = capsys.readouterr().err
        assert err.index("nmas: via tunnel") < err.index("nmas: running: uptime")

    def test_target_prints_the_chosen_address_for_scp(self, capsys):
        assert H.main(["pve", "--target"], probe=lambda a: True, runner=Runner()) == 0
        out = capsys.readouterr()
        assert out.out.strip() == "root@192.0.2.80" and "pve: via LAN" in out.err


class TestHostsOnlyNeverDevices:
    def test_every_session_clears_forwardings(self):
        runner = Runner()
        H.main(["clab", "--", "docker", "ps"], probe=lambda a: True, runner=runner)
        (argv,) = runner.calls
        assert "ClearAllForwardings=yes" in argv and "ForwardAgent=no" in argv
        assert not {"-L", "-R", "-D", "-J", "-W"} & set(argv)
        assert argv[-1] == "docker ps" and argv[-2] == "--"

    @pytest.mark.parametrize("argv", [["nmas", "-L", "1:192.0.2.1:22", "--", "true"],
                                      ["nmas", "-J", "x", "--", "true"],
                                      ["r1", "--", "show", "version"],
                                      ["nmas"],
                                      ["nmas", "--target", "--", "true"]])
    def test_anything_else_is_refused_before_a_connection(self, argv):
        runner, asked = Runner(), []
        with pytest.raises(SystemExit) as exc:
            H.main(argv, probe=lambda a: asked.append(a) or True, runner=runner)
        assert exc.value.code == 2 and runner.calls == [] and asked == []

    def test_a_flag_after_the_separator_is_the_remote_commands_own(self):
        runner = Runner()
        H.main(["nmas", "--", "ls", "-l", "--", "x"], probe=lambda a: True, runner=runner)
        assert runner.calls[0][-1] == "ls -l -- x"


class TestTheExpiredTokenStops:
    def test_it_is_recognised_names_the_host_and_is_not_retried(self, capsys):
        runner = Runner(rc=255, err=EXPIRED)
        rc = H.main(["pve", "--", "pvesh", "get", "/version"], probe=lambda a: False,
                    runner=runner)
        assert rc == H.EXIT_TOKEN_EXPIRED == 75
        assert len(runner.calls) == 1, "one attempt, never a loop"
        err = capsys.readouterr().err
        assert "STOP" in err and "cloudflared access login https://ssh-pve.example.net" in err

    def test_another_ssh_failure_is_not_called_an_expired_token(self, capsys):
        runner = Runner(rc=255, err="ssh: connect to host x port 22: Connection refused\n")
        assert H.main(["nmas", "--", "true"], probe=lambda a: False, runner=runner) == 255
        assert "STOP" not in capsys.readouterr().err

    def test_the_lan_path_never_reads_as_a_token_failure(self):
        runner = Runner(rc=255, err=EXPIRED)
        assert H.main(["nmas", "--", "true"], probe=lambda a: True, runner=runner) == 255

    def test_the_marks_are_the_tunnels_own_words(self):
        assert H.token_expired(EXPIRED) and not H.token_expired("Permission denied (publickey).")


class TestTheHostsAreNotPublished:
    def test_the_script_carries_no_address_user_or_hostname(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-host"), encoding="utf-8").read()
        import re
        assert not re.search(r"\b10\.0\.0\.\d+", src)
        assert "HOSTS = {" not in src, "the hosts come from the local file, never a literal"

    def test_a_missing_file_refuses_naming_it_and_runs_nothing(self, tmp_path, monkeypatch, capsys):
        missing = tmp_path / "absent.json"
        monkeypatch.setenv(H.HOSTS_FILE_ENV, str(missing))
        runner, asked = Runner(), []
        rc = H.main(["nmas", "--", "true"], probe=lambda a: asked.append(a) or True, runner=runner)
        assert rc == H.EXIT_NO_HOSTS == 78 and runner.calls == [] and asked == []
        err = capsys.readouterr().err
        assert str(missing) in err and "Nothing was run" in err

    def test_an_unreadable_file_refuses_too(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        monkeypatch.setenv(H.HOSTS_FILE_ENV, str(bad))
        assert H.main(["nmas", "--", "true"], probe=lambda a: True, runner=Runner()) == 78

    def test_the_default_file_is_under_the_gitignored_data_directory(self):
        assert H.HOSTS_FILE == os.path.join(ROOT, "data", "lab_hosts.json")

    def test_a_field_is_read_without_asking_the_network(self, capsys):
        asked = []
        assert H.main(["clab", "--field", "lan"], probe=lambda a: asked.append(a) or True,
                      runner=Runner()) == 0
        assert capsys.readouterr().out.strip() == "192.0.2.10" and asked == []
        H.main(["clab", "--field", "user"], probe=lambda a: True, runner=Runner())
        assert capsys.readouterr().out.strip() == "op"

    def test_a_field_with_a_command_is_refused(self):
        with pytest.raises(SystemExit) as exc:
            H.main(["clab", "--field", "lan", "--", "true"], probe=lambda a: True,
                   runner=Runner())
        assert exc.value.code == 2


class TestTheUnitTemplates:
    """deploy/systemd holds TEMPLATES since 2026-09-29 (the repository is
    public); scripts/nmas-render-units fills them from the hosts file."""

    R = SourceFileLoader("render_units", os.path.join(ROOT, "scripts", "nmas-render-units")).load_module()
    UNITS = sorted(os.path.join(ROOT, "deploy", "systemd", f)
                   for f in os.listdir(os.path.join(ROOT, "deploy", "systemd")))

    def _hosts(self, tmp_path, monkeypatch, **nmas):
        doc = dict(FAKE_HOSTS)
        doc["nmas"] = {**FAKE_HOSTS["nmas"], **nmas}
        path = tmp_path / "hosts.json"
        path.write_text(json.dumps(doc))
        monkeypatch.setenv(H.HOSTS_FILE_ENV, str(path))

    def test_every_template_renders_with_nothing_left(self, tmp_path, monkeypatch):
        self._hosts(tmp_path, monkeypatch, home="/srv/op", checkout="/srv/op/nmas")
        out = tmp_path / "units"
        assert self.R.main(["--out", str(out), *self.UNITS]) == 0
        assert len(os.listdir(out)) == len(self.UNITS) >= 10
        text = (out / "nmas-ztp-responder.service").read_text()
        assert "User=op" in text and "ExecStart=/srv/op/nmas/scripts/nmas-ztp-responder" in text
        assert "nmas-backup@192.0.2.80" in (out / "netbox-backup.env.example").read_text()
        for f in out.iterdir():
            assert not self.R.PLACEHOLDER.search(f.read_text()), f.name

    def test_the_templates_carry_placeholders_not_a_host(self):
        joined = "".join(open(u, encoding="utf-8").read() for u in self.UNITS)
        assert "@NMAS_USER@" in joined and "@NMAS_CHECKOUT@" in joined

    def test_a_missing_hosts_file_refuses_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv(H.HOSTS_FILE_ENV, str(tmp_path / "absent.json"))
        out = tmp_path / "units"
        with pytest.raises(SystemExit) as exc:
            self.R.main(["--out", str(out), *self.UNITS])
        assert exc.value.code == 78 and not out.exists()
        assert "absent.json does not exist" in capsys.readouterr().err

    def test_a_folder_that_already_holds_a_file_is_refused_and_untouched(self, tmp_path,
                                                                        monkeypatch, capsys):
        """The operator, 2026-10-01: the shared /tmp/nmas-units still held units
        rendered for the updater's install, and a glob over it would have
        reinstalled them. Only a fresh folder is rendered into."""
        self._hosts(tmp_path, monkeypatch, home="/srv/op", checkout="/srv/op/nmas")
        out = tmp_path / "units"
        out.mkdir()
        (out / "nmas-update.service").write_text("left from an earlier render\n")
        rc = self.R.main(["--out", str(out), *self.UNITS])
        assert rc == 78 and sorted(os.listdir(out)) == ["nmas-update.service"]
        assert (out / "nmas-update.service").read_text() == "left from an earlier render\n"
        err = capsys.readouterr().err
        assert "already holds 1 file(s) (nmas-update.service)" in err and "mktemp -d" in err
        assert "lab_hosts.json" not in err                 # not a hosts-file refusal
        rc = self.R.main(["--out", "", *self.UNITS])
        assert rc == 78 and "--out is empty" in capsys.readouterr().err
        fresh = tmp_path / "fresh"
        fresh.mkdir()                                      # mktemp -d's empty folder
        assert self.R.main(["--out", str(fresh), *self.UNITS]) == 0

    def test_a_value_it_cannot_establish_refuses_naming_the_placeholder(self, tmp_path, monkeypatch,
                                                                        capsys):
        self._hosts(tmp_path, monkeypatch, user="no-such-user-here")   # no home to find
        out = tmp_path / "units"
        rc = self.R.main(["--out", str(out), *self.UNITS])
        assert rc == 78 and not out.exists()
        assert "@NMAS_HOME@" in capsys.readouterr().err


class TestTheSanitiserReadsTheHostsFile:
    """oxidized-to-config.sh's host defaults, EXECUTED under bash: an unset
    NMAS_URL is read through nmas-host, and a missing file refuses (exit 2,
    the script's could-not-run code) naming it."""

    def _block(self):
        src = open(os.path.join(ROOT, "scripts", "oxidized-to-config.sh"), encoding="utf-8").read()
        start = src.index("lab_value() {")
        end = src.index('  NMAS_URL="http://$LAB_VALUE:5000"\nfi\n') + len('  NMAS_URL="http://$LAB_VALUE:5000"\nfi\n')
        return src[start:end]

    def _run(self, env):
        script = (f'HERE={os.path.join(ROOT, "scripts")!r}\nNMAS_URL="${{NMAS_URL:-}}"\n'
                  + self._block() + '\necho "URL=$NMAS_URL"\n')
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env={**os.environ, **env}, timeout=30)

    def test_an_unset_url_is_read_from_the_file(self, _hosts_file):
        out = self._run({H.HOSTS_FILE_ENV: str(_hosts_file)})
        assert out.returncode == 0 and "URL=http://192.0.2.11:5000" in out.stdout, out

    def test_a_missing_file_refuses_naming_it(self, tmp_path):
        out = self._run({H.HOSTS_FILE_ENV: str(tmp_path / "absent.json")})
        assert out.returncode == 2 and "REFUSED - NMAS_URL is not set" in out.stdout
        assert "absent.json does not exist" in out.stdout
        # Anchored: the refusal itself says "set NMAS_URL=", so a bare search
        # for "URL=" matches the sentence explaining the refusal.
        assert not [l for l in out.stdout.splitlines() if l.startswith("URL=")]

    def test_an_explicit_url_wins_and_reads_nothing(self, tmp_path):
        out = self._run({H.HOSTS_FILE_ENV: str(tmp_path / "absent.json"),
                         "NMAS_URL": "http://192.0.2.99:5000"})
        assert out.returncode == 0 and "URL=http://192.0.2.99:5000" in out.stdout


class TestItReadsTheSuitesStoreNotTheCheckouts:
    def test_the_data_directory_follows_nmas_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv(H.HOSTS_FILE_ENV, raising=False)
        monkeypatch.setenv("NMAS_DATA_DIR", str(tmp_path))
        assert H.hosts_path() == str(tmp_path / "lab_hosts.json")

    def test_without_either_it_is_the_checkouts_data_directory(self, monkeypatch):
        monkeypatch.delenv(H.HOSTS_FILE_ENV, raising=False)
        monkeypatch.delenv("NMAS_DATA_DIR", raising=False)
        assert H.hosts_path() == H.HOSTS_FILE
