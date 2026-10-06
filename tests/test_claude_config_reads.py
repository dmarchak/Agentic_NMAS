"""C536 (the operator, 2026-10-06): the agent's own tooling reads goldens and configs only
through Mercury's masking, and nothing else gets through.

The slip: a read of a committed golden on the host, searching for `ntp`, printed s1's
`username` line whole, because the secret hash held the substring.

1. `scripts/nmas-config-read`, run exactly as it runs on a host (the laptop's copy fed to
   `python3 -`): a search matching INSIDE a secret prints the line, masked, and never the
   secret, for every kind of secret line the operator named (username, enable, line
   password, community, key); the plain line it was looking for prints as it is.
2. `scripts/nmas-config-read`'s stanza read masks too.
3. `scripts/nmas-config-read` refuses nothing it should read and names a path it could not.
4. `scripts/hooks/claude-no-raw-config-reads`, driven as Claude Code drives it: the slip's
   own shape and every other raw read refused; the reader, Loki reads, history reads and
   ordinary repository work allowed; no tracked file is a "store".
5. It is wired in the committed settings for Bash, Read and Grep.
"""

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = os.path.join(ROOT, "scripts", "nmas-config-read")
HOOK = os.path.join(ROOT, "scripts", "hooks", "claude-no-raw-config-reads")
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")

#: Every secret holds the substring `ntp`, as s1's hash did; none is a real value.
SECRETS = {
    "username": ("username admin privilege 15 secret 9 $9$Xx1ntpYy2Zz3abcdefghijklmnopqrstuv",
                 "$9$Xx1ntpYy2Zz3abcdefghijklmnopqrstuv"),
    "username_password": ("username ops password 0 Plainntp4Word", "Plainntp4Word"),
    "enable": ("enable secret 9 $9$Ab1ntpCd2Ef3ghijklmnopqrstuvwxyz", "$9$Ab1ntpCd2Ef3ghijklmnopqrstuvwxyz"),
    "line_password": (" password 7 0822ntp55D0A16", "0822ntp55D0A16"),
    "community": ("snmp-server community Commntp9x RO", "Commntp9x"),
    "trap_community": ("snmp-server host 192.0.2.9 traps version 2c Trapntp7y", "Trapntp7y"),
    "key_string": (" key-string 7 1511ntp021F0725", "1511ntp021F0725"),
    "server_key": ("tacacs-server key 7 0475ntp1A0B", "0475ntp1A0B"),
}
GOLDEN = "\n".join([
    "hostname s1",
    SECRETS["username"][0],
    SECRETS["username_password"][0],
    SECRETS["enable"][0],
    SECRETS["community"][0],
    SECRETS["trap_community"][0],
    SECRETS["server_key"][0],
    "ntp server 192.0.2.10",
    "interface GigabitEthernet0/2",
    " description P2P to r1 Gi3",
    " ip address 192.0.2.1 255.255.255.254",
    "!",
    "key chain K",
    " key 1",
    SECRETS["key_string"][0],
    "!",
    "line vty 0 4",
    SECRETS["line_password"][0],
    "!",
]) + "\n"


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "config_repo"
    (path / "golden").mkdir(parents=True)
    (path / "golden" / "s1.cfg").write_text(GOLDEN, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "golden"]):
        subprocess.run(["git", "-C", str(path), *cmd], check=True, env=env,
                       capture_output=True)
    return path


def read_as_on_a_host(repo, *args):
    """The laptop's copy fed to `python3 -`, as `nmas-host nmas -- python3 - ... < it`."""
    with open(READER, encoding="utf-8") as fh:
        return subprocess.run([sys.executable, "-", "--checkout", ROOT, "--repo", str(repo),
                               *args], stdin=fh, capture_output=True, text=True, cwd=str(repo))


class TestTheReaderMasks:
    def test_a_search_matching_inside_a_secret_prints_the_masked_line(self, repo):
        r = read_as_on_a_host(repo, "--grep", "ntp", "golden/s1.cfg")
        assert r.returncode == 0, r.stderr
        for kind, (line, secret) in SECRETS.items():
            assert secret not in r.stdout, kind
        assert "username admin privilege 15 secret 9 <redacted:user_password>" in r.stdout
        assert "enable secret 9 <redacted:enable_secret>" in r.stdout
        assert "snmp-server community <redacted:snmp_community> RO" in r.stdout
        assert "<redacted:" in r.stdout.split("key-string", 1)[1].splitlines()[0]

    def test_every_secret_line_is_found_and_none_printed(self, repo):
        """The population: one printed line per secret line (each holds `ntp`), plus the
        plain `ntp server` line, which prints as it is."""
        r = read_as_on_a_host(repo, "--grep", "ntp", "golden/s1.cfg")
        printed = r.stdout.splitlines()
        assert len(printed) == len(SECRETS) + 1, printed
        assert all(p.startswith("golden/s1.cfg: ") for p in printed)
        assert sum("<redacted:" in p for p in printed) == len(SECRETS), printed
        assert "golden/s1.cfg: ntp server 192.0.2.10" in printed

    def test_a_whole_file_read_masks_too(self, repo):
        r = read_as_on_a_host(repo, "golden/s1.cfg")
        assert r.returncode == 0 and "hostname s1" in r.stdout
        for kind, (line, secret) in SECRETS.items():
            assert secret not in r.stdout, kind

    def test_a_stanza_read_masks_and_stops_at_the_bang(self, repo):
        r = read_as_on_a_host(repo, "--stanza", "^line vty", "golden/s1.cfg")
        assert r.stdout.splitlines() == ["golden/s1.cfg: line vty 0 4",
                                         "golden/s1.cfg:  password 7 <redacted:line_password>"]
        r = read_as_on_a_host(repo, "--stanza", "^interface GigabitEthernet0/2$",
                              "golden/s1.cfg")
        assert r.stdout.splitlines()[1:] == ["golden/s1.cfg:  description P2P to r1 Gi3",
                                             "golden/s1.cfg:  ip address 192.0.2.1 "
                                             "255.255.255.254"]

    def test_a_path_not_committed_is_named_and_the_rest_still_read(self, repo):
        r = read_as_on_a_host(repo, "golden/s9.cfg", "golden/s1.cfg")
        assert r.returncode == 1
        assert "golden/s9.cfg is not in HEAD" in r.stderr and "hostname s1" in r.stdout

    def test_run_as_a_file_it_finds_its_own_checkout(self, repo):
        r = subprocess.run([sys.executable, READER, "--repo", str(repo), "--grep", "ntp",
                            "golden/s1.cfg"], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert SECRETS["username"][1] not in r.stdout and "<redacted:user_password>" in r.stdout


def hook(name, **tool_input):
    payload = json.dumps({"tool_name": name, "tool_input": tool_input})
    return subprocess.run([sys.executable, HOOK], input=payload, capture_output=True,
                          text=True)


@pytest.fixture
def scripts(tmp_path):
    """Scratch scripts outside the checkout, as the agent writes them."""
    slip = tmp_path / "ntp_read.py"
    slip.write_text('got = subprocess.run(["git", "-C", repo, "show", f"HEAD:{path}"])\n'
                    'for path in (f"host_vars/{dev}.yml", f"golden/{dev}.cfg"):\n',
                    encoding="utf-8")
    loki = tmp_path / "syslog_read.py"
    loki.write_text("from modules.integrations.loki import LokiIntegration\n"
                    "loki._get('loki/api/v1/query_range', query='{job=\"x\"} |~ `INTVULN`')\n",
                    encoding="utf-8")
    local = tmp_path / "peek.py"
    local.write_text("from modules.config import LISTS_DIR\nprint(LISTS_DIR)\n",
                     encoding="utf-8")
    return {"slip": str(slip), "loki": str(loki), "local": str(local)}


def refused_bash(scripts):
    s = scripts
    return [
        # The slip itself: a scratch script naming goldens, redirected into the host.
        f"scripts/nmas-host nmas -- env PYTHONDONTWRITEBYTECODE=1 python3 - < {s['slip']}",
        f"cat {s['slip']} | scripts/nmas-host nmas -- python3 -",
        "scripts/nmas-host nmas -- bash -c 'cd ~/app && git -C data/lists/default/config_repo "
        "show HEAD:golden/s1.cfg | grep ntp'",
        "scripts/nmas-host nmas -- grep -rn ntp /srv/app/golden",
        "scripts/nmas-host nmas -- cat /srv/app/x/r1.cfg",
        "ssh someone@host 'show running-config'",
        "cat data/lists/default/config_repo/golden/s1.cfg",
        "grep -rn ntp data/lists",
        "git -C data/lists/default/config_repo show HEAD:golden/s1.cfg",
        "ls data/config_cache/ && cat data/config_cache/r1.txt",
        # A separator does not carry the reader's allowance to the next command.
        "scripts/nmas-config-read golden/s1.cfg; cat /x/lists/default/golden_configs/s1.cfg",
        f"python3 {s['local']}",
    ]


def allowed_bash(scripts):
    return [
        "scripts/nmas-host nmas -- env PYTHONDONTWRITEBYTECODE=1 python3 - --checkout "
        "/srv/app --grep '^ntp ' golden/s1.cfg < scripts/nmas-config-read",
        "scripts/nmas-config-read --grep ntp golden/s1.cfg golden/s2.cfg | head -5",
        f"scripts/nmas-host nmas -- env PYTHONDONTWRITEBYTECODE=1 python3 - < {scripts['loki']}",
        "scripts/nmas-host nmas -- git -C /srv/app log -1 --format=%h",
        "scripts/nmas-host nmas -- bash -c 'cd /srv/app && git status --porcelain | wc -l'",
        'grep -rn "golden/" modules routes | head',
        "scripts/nmas-test tests/test_repo.py -q",
        "git diff --stat",
    ]


class TestTheHook:
    def test_the_slip_and_every_raw_read_are_refused(self, scripts):
        for command in refused_bash(scripts):
            r = hook("Bash", command=command)
            assert r.returncode == 2, (command, r.stderr)
            assert "nmas-config-read" in r.stderr, command

    def test_the_reader_and_ordinary_work_run(self, scripts):
        for command in allowed_bash(scripts):
            r = hook("Bash", command=command)
            assert r.returncode == 0, (command, r.stderr)

    def test_read_and_grep_of_a_store_are_refused(self):
        for name, key, path in (
                ("Read", "file_path", f"{ROOT}/data/lists/default/config_repo/golden/s1.cfg"),
                ("Read", "file_path", f"{ROOT}/data/lists/default/backups/r1.cfg"),
                ("Grep", "path", f"{ROOT}/data"),
                ("Grep", "path", f"{ROOT}/data/lists/default/golden_configs"),
                ("Grep", "path", f"{ROOT}/data/config_cache")):
            r = hook(name, **{key: path, "pattern": "ntp"})
            assert r.returncode == 2, (name, path, r.stderr)

    def test_read_and_grep_of_the_code_run(self):
        for name, key, path in (("Read", "file_path", f"{ROOT}/modules/backups.py"),
                                ("Read", "file_path", f"{ROOT}/docs/manual/screens/backups.md"),
                                ("Grep", "path", f"{ROOT}/modules"),
                                ("Grep", "path", "")):
            r = hook(name, **{key: path, "pattern": "ntp"})
            assert r.returncode == 0, (name, path, r.stderr)

    def test_no_tracked_file_is_a_store(self):
        """Floor and population: the whole tracked tree, none of it a store, so the hook
        never refuses work on the repository itself."""
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.SourceFileLoader("claude_no_raw_config_reads", HOOK)
        module = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        files = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True,
                               text=True, check=True).stdout.split()
        assert len(files) > 1000
        refused = [f for f in files if module.path_offence(os.path.join(ROOT, f))]
        assert refused == []
        # The planted case, through the same function: a store path is found.
        assert module.path_offence(os.path.join(ROOT, "data", "lists", "x", "config_repo"))

    def test_an_unreadable_input_is_a_visible_hook_error(self):
        r = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True,
                           text=True)
        assert r.returncode == 1 and "could not read the tool call" in r.stderr


class TestTheSettings:
    def test_wired_for_bash_read_and_grep(self):
        settings = json.load(open(SETTINGS, encoding="utf-8"))
        wired = set()
        for entry in settings["hooks"]["PreToolUse"]:
            if any(h["command"].endswith("/scripts/hooks/claude-no-raw-config-reads")
                   for h in entry["hooks"]):
                wired |= set(entry["matcher"].split("|"))
        assert {"Bash", "Read", "Grep"} <= wired, wired
