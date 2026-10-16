"""C906: no device session opens around the host-key check.

Every SSH session to a device opens in `connection.open_ssh`, which hands Netmiko Mercury's
host-key policy before it signs in (`_pin_host_key`); the NETCONF push takes its verification
from the same record (`host_keys.netconf_args`). This holds the SHAPE of the program to that,
parsed, never matched as text:

- `ConnectHandler(`, paramiko's `SSHClient(` and `Transport(` are called only in
  `modules/connection.py` (and the hand-run timing probe, which must pass `ssh_strict=True`);
- nothing sets a missing-host-key policy, names `AutoAddPolicy` or `WarningPolicy`, or passes
  `hostkey_verify=False` or `ssh_strict=False`;
- an ncclient connect takes its host-key arguments only from `host_keys.netconf_args`, spread
  in (`**`), never one named by hand (ncclient's IOS-XE handler overrides a hand-named
  unknown-host answer and accepts any key: tests/test_host_keys.py measures it);
- `open_ssh` hands the policy over after building the session and before it signs in.

The population: every tracked Python file under modules/, routes/ and scripts/ (extensionless
scripts parsed when they are Python), and app.py; its floor and a planted case of each rule.
"""

import ast
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Files that may build a session themselves, and what each may call.
OPENERS = {
    "modules/connection.py": {"ConnectHandler", "Transport"},
    "scripts/netmiko_timing_probe.py": {"ConnectHandler"},
}
SESSION_CALLS = {"ConnectHandler", "SSHClient", "Transport"}
LAX_POLICIES = {"AutoAddPolicy", "WarningPolicy"}
NETCONF_KEYS = {"hostkey_verify", "hostkey_b64", "unknown_host_cb", "device_params"}


def _name(node) -> str:
    return getattr(node, "id", getattr(node, "attr", ""))


def _manager_aliases(tree) -> set:
    """The names this module binds to ncclient's manager (or its connect functions)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ncclient"):
            for a in node.names:
                if a.name in ("manager", "connect", "connect_ssh"):
                    names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("ncclient"):
                    names.add((a.asname or a.name).split(".")[0])
    return names


def _netconf_connect(call, aliases) -> bool:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id in aliases and f.id in ("connect", "connect_ssh")
    if isinstance(f, ast.Attribute) and f.attr in ("connect", "connect_ssh"):
        base = f.value
        while isinstance(base, ast.Attribute):
            base = base.value
        return isinstance(base, ast.Name) and base.id in aliases
    return False


def problems(sources: dict) -> list:
    """Each way a file in *sources* (``{relative path: text}``) opens a device session around
    the host-key check, as words naming the file and line."""
    out = []
    for rel, text in sorted(sources.items()):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        aliases = _manager_aliases(tree)
        functions = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if isinstance(node, (ast.Name, ast.Attribute)) and _name(node) in LAX_POLICIES:
                out.append(f"{rel}:{node.lineno}: names {_name(node)}, which keeps any key")
            if not isinstance(node, ast.Call):
                continue
            called = _name(node.func)
            if called in SESSION_CALLS and called not in OPENERS.get(rel, set()):
                out.append(f"{rel}:{node.lineno}: calls {called}(), a session that does not "
                           "go through connection.open_ssh")
            if called == "set_missing_host_key_policy":
                out.append(f"{rel}:{node.lineno}: sets a missing-host-key policy of its own")
            for kw in node.keywords:
                if kw.arg in ("hostkey_verify", "ssh_strict") and \
                        isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    out.append(f"{rel}:{node.lineno}: passes {kw.arg}=False")
            if called == "ConnectHandler" and rel != "modules/connection.py" and not any(
                    kw.arg == "ssh_strict" and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True for kw in node.keywords):
                out.append(f"{rel}:{node.lineno}: ConnectHandler() without ssh_strict=True")
            if aliases and _netconf_connect(node, aliases):
                named = sorted(kw.arg for kw in node.keywords if kw.arg in NETCONF_KEYS)
                spread = [kw for kw in node.keywords if kw.arg is None]
                around = [f for f in functions
                          if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
                asks = any(isinstance(c, ast.Call) and _name(c.func) == "netconf_args"
                           for f in around for c in ast.walk(f))
                if named:
                    out.append(f"{rel}:{node.lineno}: an ncclient connect names "
                               f"{', '.join(named)} itself, not from host_keys.netconf_args")
                if not spread or not asks:
                    out.append(f"{rel}:{node.lineno}: an ncclient connect whose host-key "
                               "check is not host_keys.netconf_args, spread in")
    return out


def _sources() -> dict:
    found = {}
    for base in ("modules", "routes", "scripts"):
        for path in tracked(base):
            if base != "scripts" and not path.endswith(".py"):
                continue
            try:
                found[os.path.relpath(path, ROOT)] = open(path, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
    found["app.py"] = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    return found


class TestNoSessionGoesAround:
    def test_the_program_holds_the_shape(self):
        sources = _sources()
        assert len(sources) >= 300, len(sources)
        assert problems(sources) == []

    def test_the_anchors_are_in_the_population(self):
        """The scan reached what it holds: the one opener, the NETCONF push and the probe."""
        sources = _sources()
        for rel in ("modules/connection.py", "modules/pipeline.py",
                    "scripts/netmiko_timing_probe.py"):
            assert rel in sources, rel
        tree = ast.parse(sources["modules/pipeline.py"])
        assert any(isinstance(n, ast.Call) and _netconf_connect(n, _manager_aliases(tree))
                   for n in ast.walk(tree)), "the NETCONF connect is found and judged"


class TestOpenSshHandsThePolicyOverBeforeSigningIn:
    def test_the_order(self):
        tree = ast.parse(open(os.path.join(ROOT, "modules", "connection.py"),
                              encoding="utf-8").read())
        (fn,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "open_ssh"]
        lines = {}
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                lines.setdefault(_name(node.func), node.lineno)
        missing = {"ConnectHandler", "_pin_host_key", "login"} - set(lines)
        assert not missing, f"open_ssh no longer calls {sorted(missing)}"
        assert lines["ConnectHandler"] < lines["_pin_host_key"] < lines["login"], lines

    def test_the_policy_is_what_netmiko_uses(self):
        """`key_policy` is the attribute Netmiko's own client builder reads (netmiko 4.3.0,
        `BaseConnection._build_ssh_client`): if a Netmiko release renames it, this fails."""
        import inspect

        from netmiko.base_connection import BaseConnection
        src = inspect.getsource(BaseConnection._build_ssh_client)
        assert "set_missing_host_key_policy(self.key_policy)" in src
        assert "load_system_host_keys" in src and "if self.system_host_keys" in src


class TestEachRuleFindsItsPlantedCase:
    PLANTED = {
        "modules/elsewhere.py": (
            "import paramiko\n"
            "from netmiko import ConnectHandler\n"
            "from ncclient import manager as m\n"
            "def a(): ConnectHandler(device_type='cisco_ios', ip='x')\n"
            "def b(): paramiko.SSHClient().set_missing_host_key_policy(paramiko.AutoAddPolicy())\n"
            "def c(): paramiko.Transport(None)\n"
            "def d(): m.connect(host='x', hostkey_verify=False)\n"
            "def e(): m.connect(host='x', device_params={'name': 'iosxe'})\n"),
        "scripts/netmiko_timing_probe.py": "ConnectHandler(device_type='cisco_ios')\n",
    }

    def test_every_one_is_found(self):
        found = "\n".join(problems(self.PLANTED))
        for words in ("elsewhere.py:4: calls ConnectHandler()",
                      "elsewhere.py:5: calls SSHClient()",
                      "elsewhere.py:5: sets a missing-host-key policy",
                      "elsewhere.py:5: names AutoAddPolicy",
                      "elsewhere.py:6: calls Transport()",
                      "elsewhere.py:7: passes hostkey_verify=False",
                      "elsewhere.py:7: an ncclient connect whose host-key check is not",
                      "elsewhere.py:8: an ncclient connect names device_params itself",
                      "netmiko_timing_probe.py:1: ConnectHandler() without ssh_strict=True"):
            assert words in found, (words, found)

    def test_the_shape_it_allows_is_allowed(self):
        ok = {"modules/fine.py": (
            "from ncclient import manager as m\n"
            "from modules import host_keys\n"
            "def push(ip):\n"
            "    verify, seen = host_keys.netconf_args(ip)\n"
            "    return m.connect(host=ip, port=830, **verify)\n")}
        assert problems(ok) == []
