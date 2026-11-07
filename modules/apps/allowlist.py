"""A controller app's allowlist, separate from a job's (C2635; the SDN platform design revision
7, section 11c.6; the operator, 2026-11-07). A job runs in Mercury's sandbox through the SDK
only (`modules/jobs/gate.py`, `modules/jobs/runner.py`'s `SAFE_STDLIB`, unchanged); an app is a
Ryu controller app, and the app gate (`modules/apps/gate.py`) holds its code and tests to this
one instead. Nothing here runs the app's code: every rule is read from the source.

**The one table, `IMPORTS`:** each module an app may import, and each it may not, with why.
- allowed: `ryu` and its submodules (but the few that open their own connections or load code
  by name), the app SDK `mercury_app` (`SDK`; its contract stub is
  `modules/apps/sdk/mercury_app/`, which the container harness and the controller deploy
  beside the app), and the standard library's data modules, each named;
- refused by name: every network, process, file or interpreter module an app might reach for
  (`socket`, `urllib`, `subprocess`, `os`, `threading`, `importlib`, ...); any module not in
  the table is refused too, as not on the allowlist;
- a name of an allowed module that reaches a file, a process or the network
  (`logging.FileHandler`, `ryu.lib.hub.connect`, `uuid.getnode`) is refused by name, and so is
  any private (`_`) name of one.

Besides the table: the app's own modules (imported by name, never relatively); in its tests,
pytest's `raises` and `modules.jobs`' `covers` and `refused` (`TEST_ONLY`); and the job
allowlist's rules for every other node (`modules.jobs.gate.node_problems`: no `open`, `exec`,
`eval`, `getattr` or other forbidden builtin, no dunder or frame attribute, no bare except).

**The network only through `mercury_app.egress`, to a destination the manifest declares.** An
egress call's destination (its first argument, or `destination=`) is a string literal naming
an entry of `manifest.yml`'s `egress`; an undeclared name, a computed one, `egress` used as a
value (passed, stored or wrapped) or reached through the app's own modules is refused, naming
the file and line. The calls found are listed in the passed check, beside the manifest's
declared destinations, for the reviewer.

**Python 3.9, the controller's interpreter** (lab/sdn/ryu/Dockerfile: Ryu 4.34 on
`python:3.9-slim`): every file is parsed with `ast.parse(..., feature_version=(3, 9))`. That
refuses the grammar 3.9 lacks that the parser gates (measured on CI's Python 3.12.3,
2026-11-06): `match` statements, `except*`, the `type` statement and type parameter lists. It
does NOT refuse, being best-effort: parenthesized context managers, PEP 701 f-strings (a quote
reused inside), `a[*b]`, an `int | str` annotation evaluated at run time, or any library call
newer than 3.9 (`itertools.pairwise`, `zip(strict=...)`). Those are found only by running the
tests on 3.9, in the container harness.

**This is the check a person can read, not the boundary:** the controller's container and its
network policy are. Ryu's own modules reach the network in ways a static list cannot follow
everywhere; the table refuses the ones named.
"""

import ast
from dataclasses import dataclass, field

from modules.jobs import gate as job_gate
from modules.jobs import runner

#: The app SDK's import name, and its one network call.
SDK = "mercury_app"
EGRESS = "egress"
#: The SDK's published names (held to the stub's `__all__` by tests/test_app_allowlist.py).
SDK_NAMES = frozenset({"EgressRefused", "NotDeployed", "egress"})
#: The controller's interpreter: lab/sdn/ryu/Dockerfile's `python:3.9-slim`.
PYTHON = (3, 9)
#: What an app's tests may import besides the app's own allowlist, `{module: names}`.
TEST_ONLY = {runner.PYTEST: frozenset({"raises"}), "modules.jobs": frozenset({"covers",
                                                                             "refused"})}
#: Why a forbidden builtin is refused, in an app's words.
APP_REACH = ("an app reaches the network only by mercury_app.egress, reads no file, and runs "
             "no code it builds")

NETWORK = ("a network module: an app reaches the network only by mercury_app.egress, to a "
           "destination its manifest declares")
PROCESS = ("a process or thread module: an app runs in the controller's own loop "
           "(ryu.lib.hub's spawn and sleep)")
FILES = ("a file or operating-system module: an app is given its config by Mercury, and reads "
         "no file")
INTERPRETER = "it reaches the interpreter's internals or loads code by name"


@dataclass(frozen=True)
class Rule:
    """One entry of `IMPORTS`: whether the module is allowed, why, whether its submodules are
    too, and the names of it that are refused, `{name: why}`."""

    allowed: bool
    why: str
    submodules: bool = False
    refused_names: dict = field(default_factory=dict)


def _refused(why: str) -> Rule:
    return Rule(False, why, submodules=True)


_HUB_NETWORK = "it opens a connection or a listening socket of its own"

#: The one table (see the module's docstring).
IMPORTS = {
    # The controller framework, and the app SDK.
    "ryu": Rule(True, "the controller framework the app runs in", submodules=True),
    "ryu.lib.hub": Rule(True, "Ryu's green threads: spawn, sleep, Event, Queue",
                        refused_names={"connect": _HUB_NETWORK, "listen": _HUB_NETWORK,
                                       "StreamServer": _HUB_NETWORK,
                                       "StreamClient": _HUB_NETWORK,
                                       "WSGIServer": _HUB_NETWORK}),
    "ryu.lib.rpc": _refused("an RPC endpoint over its own socket: " + NETWORK),
    "ryu.lib.ovs": _refused("it connects to an OVSDB server itself: " + NETWORK),
    "ryu.lib.snortlib": _refused("it listens on a socket of its own: " + NETWORK),
    "ryu.services": _refused("protocol speakers (BGP, OVSDB, VRRP, Zebra) with sockets of their "
                             "own: " + NETWORK),
    "ryu.contrib": _refused("libraries Ryu vendors, network clients among them: " + NETWORK),
    "ryu.cmd": _refused("Ryu's command lines start managers and processes: " + PROCESS),
    "ryu.utils": _refused("it loads modules and files by name: " + INTERPRETER),
    SDK: Rule(True, "the app SDK: mercury_app.egress, the app's one way to the network"),
    # The standard library's data modules.
    "base64": Rule(True, "encodes and decodes bytes as text"),
    "collections": Rule(True, "containers (deque, OrderedDict, Counter; collections.abc)",
                        submodules=True),
    "copy": Rule(True, "copies plain data"),
    "dataclasses": Rule(True, "records as classes"),
    "datetime": Rule(True, "dates, times and durations"),
    "enum": Rule(True, "named constants"),
    "fnmatch": Rule(True, "a name matched against a shell-style pattern"),
    "functools": Rule(True, "caching and partial functions over plain data"),
    "hashlib": Rule(True, "digests of bytes"),
    "ipaddress": Rule(True, "IPv4 and IPv6 addresses and networks as values; it opens no "
                            "connection"),
    "itertools": Rule(True, "iteration over plain data"),
    "json": Rule(True, "JSON text to and from plain data (its load and dump take an open "
                       "file, which an app has none of)"),
    "logging": Rule(True, "the app's log lines (RyuApp's self.logger is a logging.Logger)",
                    refused_names={"FileHandler": "it writes a file: log through the "
                                                  "controller's logger",
                                   "basicConfig": "it can open a file and replaces the "
                                                  "controller's handlers",
                                   "handlers": "logging.handlers writes files and sends to "
                                               "sockets",
                                   "config": "logging.config opens files and listens on a "
                                             "socket"}),
    "logging.handlers": _refused("it writes files and sends to sockets: " + NETWORK),
    "logging.config": _refused("it opens files and listens on a socket: " + NETWORK),
    "math": Rule(True, "arithmetic"),
    "re": Rule(True, "regular expressions"),
    "string": Rule(True, "string constants and templates"),
    "struct": Rule(True, "packs and unpacks a packet's fields"),
    "time": Rule(True, "the clock and sleeps: a TTL, a timeout"),
    "typing": Rule(True, "type annotations"),
    "uuid": Rule(True, "random identifiers (uuid4)",
                 refused_names={"uuid1": "it reads the host's hardware address, which can "
                                         "start a process",
                                "getnode": "it reads the host's hardware address, which can "
                                           "start a process"}),
    # Refused by name (any module not in this table is refused too).
    **{m: _refused(NETWORK) for m in (
        "aiohttp", "asyncio", "ftplib", "http", "httpx", "imaplib", "poplib", "requests",
        "select", "selectors", "smtplib", "socket", "socketserver", "ssl", "telnetlib",
        "urllib", "urllib3", "xmlrpc")},
    **{m: _refused(PROCESS) for m in (
        "_thread", "concurrent", "eventlet", "greenlet", "multiprocessing", "pty", "signal",
        "subprocess", "threading")},
    **{m: _refused(FILES) for m in (
        "glob", "io", "os", "pathlib", "shelve", "shutil", "sys", "tempfile")},
    **{m: _refused(INTERPRETER) for m in (
        "ast", "builtins", "code", "codeop", "ctypes", "gc", "importlib", "inspect", "marshal",
        "pickle", "runpy", "types")},
}


def allowed_modules() -> list:
    """The table's allowed entries, sorted (what the authoring guide lists)."""
    return sorted(m for m, r in IMPORTS.items() if r.allowed)


def lookup(module: str):
    """`(key, rule)` of the table's entry governing *module*: the longest entry that is the
    module or a package of it; `(None, None)` when none is."""
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        key = ".".join(parts[:i])
        if key in IMPORTS:
            return key, IMPORTS[key]
    return None, None


def module_problem(module: str) -> str:
    """Why an app may not import *module*, or "" when it may."""
    key, rule = lookup(module)
    if rule is None:
        return (f"`{module}` is not on the app allowlist: an app imports ryu, {SDK} and the "
                f"standard library's data modules ({', '.join(allowed_modules())})")
    if not rule.allowed:
        return f"`{module}` is refused: {rule.why}"
    if key != module and not rule.submodules:
        return (f"`{module}` is refused: the app allowlist allows {key} itself, not its "
                "submodules")
    return ""


def name_problem(module: str, name: str) -> str:
    """Why an app may not reach *name* of the allowed *module*, or "" when it may: a submodule
    the table refuses, a name its entry refuses, or a private name."""
    full = f"{module}.{name}"
    key, rule = lookup(module)
    sub_key, _sub = lookup(full)
    if sub_key is not None and sub_key != key:
        return module_problem(full)
    if module == SDK:
        return "" if name in SDK_NAMES else (
            f"`{full}` is not among {SDK}'s published names ({', '.join(sorted(SDK_NAMES))})")
    if rule is not None and name in rule.refused_names:
        return f"`{full}` is refused: {rule.refused_names[name]}"
    if name.startswith("_") and not (name.startswith("__") and name.endswith("__")):
        return f"`{full}` is refused: a private name of {module}"
    return ""


# ── the check ────────────────────────────────────────────────────────────────────────────────

#: A binding's target for the app's own modules: never checked against the table.
_OWN = "own:"


@dataclass
class Found:
    """The allowlist's answer on a folder: one line per refusal (`problems`), and each egress
    call it allowed (`egress`), as the reviewer reads them."""

    problems: list
    egress: list


class _File:
    """One file's walk: its bindings (`{name: dotted target}`), and its refusals."""

    def __init__(self, tree, file: str, own: set, is_test: bool, declared):
        self.tree, self.file, self.own, self.is_test = tree, file, own, is_test
        self.declared = declared
        self.bindings, self.problems, self.egress = {}, [], []
        self.modules = set()                # the bound names that are modules of the table
        self.parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent

    def where(self, node) -> str:
        return f"{self.file} line {getattr(node, 'lineno', 0)}"

    def refuse(self, node, words: str) -> None:
        self.problems.append(f"{self.where(node)}: {words}")

    # imports ─────────────────────────────────────────────────────────────────────────────

    def visit_import(self, node) -> None:
        for alias in node.names:
            name = alias.name
            bound = alias.asname or name.partition(".")[0]
            target = name if alias.asname else name.partition(".")[0]
            if name in self.own:
                self.bindings[bound] = _OWN + name
                continue
            if name == runner.PYTEST and self.is_test:
                self.bindings[bound] = name
                continue
            if name.partition(".")[0] == "modules":
                self.refuse(node, f"`import {name}`: "
                            + (f"write `from {name} import <names>`" if self.is_test and
                               name in TEST_ONLY else
                               "an app imports no Mercury module but, in its tests, "
                               "modules.jobs' covers and refused"))
                continue
            problem = module_problem(name)
            if problem:
                self.refuse(node, f"`import {name}`: {problem}")
            else:
                self.bindings[bound] = target
                self.modules.add(bound)

    def visit_import_from(self, node) -> None:
        module, names = node.module or "", [a.name for a in node.names]
        if node.level:
            self.refuse(node, "a relative import; the folder's modules are imported by name "
                              "(`from <module> import ...`)")
            return
        if "*" in names:
            self.refuse(node, f"`from {module} import *` hides what is imported; name each")
            return
        if module in self.own:
            for alias in node.names:
                if alias.name in (EGRESS, SDK):
                    self.refuse(node, f"`from {module} import {alias.name}`: {SDK}.egress is "
                                      f"imported from {SDK} itself, where each call is read")
                self.bindings[alias.asname or alias.name] = _OWN + f"{module}.{alias.name}"
            return
        if module in TEST_ONLY:
            if not self.is_test:
                self.refuse(node, f"`from {module} import ...`: {module} is for the app's "
                                  "tests, not its code")
                return
            extra = [n for n in names if n not in TEST_ONLY[module]]
            if extra:
                self.refuse(node, f"`from {module} import {', '.join(extra)}`: an app's tests "
                                  f"take {', '.join(sorted(TEST_ONLY[module]))} from {module}")
            for alias in node.names:
                self.bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
            return
        if module.partition(".")[0] == "modules":
            self.refuse(node, f"`from {module} import ...`: an app imports no Mercury module "
                              "but, in its tests, modules.jobs' covers and refused")
            return
        problem = module_problem(module)
        if problem:
            self.refuse(node, f"`from {module} import ...`: {problem}")
            return
        for alias in node.names:
            problem = name_problem(module, alias.name)
            if problem:
                self.refuse(node, f"`from {module} import {alias.name}`: {problem}")
            else:
                self.bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
                if f"{module}.{alias.name}" in IMPORTS:
                    self.modules.add(alias.asname or alias.name)

    # names and attributes ────────────────────────────────────────────────────────────────

    def resolve(self, node):
        """`(target, attrs)`: the binding a Name or an Attribute chain starts from and the
        attributes after it, or `(None, ())` when it starts from no imported name."""
        attrs = []
        while isinstance(node, ast.Attribute):
            attrs.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name) and node.id in self.bindings \
                and isinstance(node.ctx, ast.Load):
            return self.bindings[node.id], tuple(reversed(attrs))
        return None, ()

    def visit_reference(self, node) -> None:
        """A Name or the outermost Attribute of a chain: its names checked against the table,
        and `egress` held to being called with a declared destination."""
        target, attrs = self.resolve(node)
        if target is None:
            return
        if target.startswith(_OWN):
            for attr in attrs:
                if attr in (EGRESS, SDK):
                    self.refuse(node, f"`.{attr}` reached through the app's own module: "
                                      f"{SDK}.egress is called from {SDK} itself, where each "
                                      "call is read")
                    return
            return
        current = target
        for attr in attrs:
            problem = name_problem(current, attr) if lookup(current)[1] is not None else ""
            if problem:
                self.refuse(node, problem)
                return
            current = f"{current}.{attr}"
        if not attrs and isinstance(node, ast.Name) and node.id in self.modules:
            self.refuse(node, f"the module `{node.id}` used as a value (passed, stored or "
                              "returned): reach its names directly, so each can be read")
        elif current == f"{SDK}.{EGRESS}":
            parent = self.parents.get(node)
            if isinstance(parent, ast.Call) and parent.func is node:
                self.visit_egress(parent)
            else:
                self.refuse(node, f"`{EGRESS}` used as a value (passed, stored or wrapped): "
                                  "call it directly, its destination a string literal, so "
                                  "the destination can be read")

    def visit_egress(self, call) -> None:
        dest = call.args[0] if call.args else next(
            (k.value for k in call.keywords if k.arg == "destination"), None)
        if self.declared is None:
            names = "manifest.yml is refused, so it declares no destination"
        else:
            names = ("manifest.yml declares " + ", ".join(repr(n) for n in self.declared)
                     if self.declared else "manifest.yml declares none")
        if dest is None:
            self.refuse(call, f"an egress call names no destination ({names})")
        elif not (isinstance(dest, ast.Constant) and isinstance(dest.value, str)):
            self.refuse(call, f"an egress call's destination is `{ast.unparse(dest)}`, not a "
                              f"string literal naming a declared destination ({names}): a "
                              "computed destination cannot be reviewed")
        elif self.declared is None or dest.value not in self.declared:
            self.refuse(call, f"an egress call to {dest.value!r}, which is not a destination "
                              f"the manifest declares ({names})")
        else:
            self.egress.append(f"{self.where(call)}: egress to {dest.value!r}")

    def walk(self) -> None:
        # Imports first, so a name used above its import (in a function body) is still bound.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.visit_import(node)
            elif isinstance(node, ast.ImportFrom):
                self.visit_import_from(node)
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, (ast.Name, ast.Attribute)) and not isinstance(
                    self.parents.get(node), ast.Attribute):
                self.visit_reference(node)
            self.problems.extend(job_gate.node_problems(node, self.where(node), APP_REACH))


def parse_problem(text: str, file: str):
    """`(tree, "")` for *text* parsed as Python 3.9, or `(None, why)`."""
    try:
        return ast.parse(text, filename=file, feature_version=PYTHON), ""
    except SyntaxError as exc:
        return None, (f"{file} line {exc.lineno}: does not parse as Python "
                      f"{'.'.join(map(str, PYTHON))}, the controller's interpreter "
                      f"({exc.msg})")
    except ValueError as exc:
        return None, f"{file}: does not parse ({exc})"


def _shadowing(module: str) -> bool:
    top = module.partition(".")[0]
    return top in {k.partition(".")[0] for k in IMPORTS} or top in (runner.PYTEST, "modules")


def check(sources: "runner.Sources", declared) -> Found:
    """The app allowlist over *sources* (`runner.load_sources`'s): every module and test parsed
    as Python 3.9 and walked (see the module's docstring). *declared* is the manifest's egress
    names, or None when the manifest is refused."""
    own = set(sources.job)
    problems, egress = [], []
    for module in sorted(own):
        if _shadowing(module):
            problems.append(f"{sources.job_file(module)}: an app's module is named like one it "
                            f"may import or is refused ({module!r}); name it for the app")
    files = [(sources.job_file(m), t, False) for m, t in sources.job.items()]
    files += [(name, t, True) for name, t in sources.tests.items()]
    for file, text, is_test in files:
        tree, why = parse_problem(text, file)
        if tree is None:
            problems.append(why)
            continue
        walk = _File(tree, file, own, is_test, declared)
        walk.walk()
        problems.extend(walk.problems)
        egress.extend(walk.egress)
    return Found(problems, egress)
