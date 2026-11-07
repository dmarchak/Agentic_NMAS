"""The controller's Python, as `mercury app check` targets it (the operator's decision,
2026-11-07): an app is checked against the MEASURED minor version of its network's controller
app runtime, never a constant.

**The target** (`Target`) is a version, `(major, minor)`, and the words that say where it came
from: the network's record (`modules/sdn/controller_runtime.target`), measured by a read of the
controller host, or why it is not known. A target that is not known, or older than `OLDEST`
(the tables here start at 3.5), is "can't tell", and the app's `static` check fails on it:
never passed, never assumed.

**What the parser does not refuse.** `ast.parse(..., feature_version=<target>)` refuses some
grammar newer than the target and parses the rest (measured on CPython 3.12.3 and 3.14.4,
2026-11-07, with the target 3.5): it refuses variable annotations, numeric underscores,
`async for` in a comprehension, `:=` and positional-only parameters; it PARSES f-strings, async
generators, `await` in a comprehension, decorators that are any expression and a parenthesized
`with`. So Mercury's own checks (`GRAMMAR`, read from the tree and the tokens) refuse what the
tree shows, each with the version that introduced it, and do not rely on the parser for any of
it: the parser's refusal comes first when it has one.

**What the standard library lacks** (`MODULES`, `NAMES`, `BUILTINS`): each entry is a module or
name with the version that introduced it, as the Python documentation's "New in version" note
gives it, written from the documentation as known, not re-read at writing (2026-11-07). A name
added in a patch release (`typing.ClassVar`, 3.5.3) counts from the next minor, since a
network's record holds the minor alone: refusing by resemblance is safe, allowing by it is not.

**What no check here can see:** a method of a value (`str.removeprefix`, 3.9), an operator on
a type (`dict | dict`, 3.9), a keyword argument newer than the call (`zip(strict=...)`, 3.10),
behaviour (dicts keep insertion order only from 3.7), and grammar the tree does not keep (a
parenthesized `with`, `f"{x=}"`, `a[*b]`). Only a run on the controller's version finds those:
the container harness's.
"""

import ast
import io
import re
import tokenize
from dataclasses import dataclass

#: The oldest version the tables below start at.
OLDEST = (3, 5)


def shown(version) -> str:
    return ".".join(str(n) for n in version)


@dataclass(frozen=True)
class Target:
    """The version an app is checked against, and where it came from (`words`). `version` is
    `(major, minor)`, or None when it is not known; `provisional` when the network's record
    holds a provisional value, not yet measured by the interpreter read (checked against, and
    said so)."""

    version: tuple = None
    words: str = ""
    provisional: bool = False

    def problem(self) -> str:
        """"" when the version can be checked against, else the "can't tell" words."""
        if self.version is None:
            return self.words or "can't tell: the controller's Python is not measured"
        if tuple(self.version) < OLDEST:
            return (f"can't tell: the controller's Python is {shown(self.version)} "
                    f"({self.words}), older than {shown(OLDEST)}, where the check's tables "
                    "start")
        return ""


def not_measured(network: str) -> Target:
    if not network:
        return Target(None, "can't tell: no network was named, so the controller's Python is "
                            "not known (name it: --network <network>)")
    return Target(None, f"can't tell: the controller's Python is not measured for {network}")


def as_target(python) -> Target:
    """*python* as a `Target`: a Target as it is; `(3, 5)` or ``"3.5"`` as given; None as not
    known (no network was named)."""
    if isinstance(python, Target):
        return python
    if python is None:
        return not_measured("")
    if isinstance(python, str):
        python = tuple(int(p) for p in python.split("."))
    version = tuple(python)[:2]
    return Target(version, f"Python {shown(version)}, as given to the check")


def available_from(docs: str) -> tuple:
    """The first minor version in which every release has a name the docs say is "New in
    version *docs*" (one version, or several, comma-separated, for a name added to more than
    one line in patch releases): `3.7` is (3, 7); `3.5.3` is (3, 6); `3.5.4, 3.6.1` is
    (3, 7)."""
    latest = max(tuple(int(p) for p in v.strip().split(".")) for v in docs.split(","))
    major, minor = latest[0], latest[1]
    patch = latest[2] if len(latest) > 2 else 0
    return (major, minor + 1) if patch else (major, minor)


# ── the grammar ───────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Feature:
    """One piece of grammar: its words, the version that introduced it, and what to write
    instead on an older controller."""

    words: str
    since: str
    instead: str


F_STRING = Feature("an f-string", "3.6", "use str.format or %")
VARIABLE_ANNOTATION = Feature("a variable annotation (`x: int = 1`)", "3.6",
                              "leave it out, or write a `# type:` comment")
NUMERIC_UNDERSCORE = Feature("an underscore in a numeric literal (`1_000`)", "3.6",
                             "write the digits without it")
ASYNC_GENERATOR = Feature("an asynchronous generator (`yield` in an `async def`)", "3.6",
                          "a Ryu app runs on ryu.lib.hub's green threads: spawn and sleep")
AWAIT_IN_COMPREHENSION = Feature("`await` in a comprehension", "3.6",
                                 "await each in a loop")
ASYNC_COMPREHENSION = Feature("`async for` in a comprehension", "3.6",
                              "write the loop out")
WALRUS = Feature("an assignment expression (`:=`)", "3.8", "assign on its own line first")
POSITIONAL_ONLY = Feature("a positional-only parameter (`/`)", "3.8", "leave the `/` out")
DECORATOR_EXPRESSION = Feature("a decorator that is not a dotted name or a call of one "
                               "(PEP 614)", "3.9", "bind it to a name first")
MATCH = Feature("a `match` statement", "3.10", "use if and elif")
EXCEPT_STAR = Feature("`except*`", "3.11", "use except")
TYPE_STATEMENT = Feature("the `type` statement", "3.12", "assign the alias")
TYPE_PARAMETERS = Feature("a type parameter list (`def f[T]`)", "3.12", "leave it out")

#: Every feature the check refuses on a controller older than it, in the order of `since`.
GRAMMAR = (F_STRING, VARIABLE_ANNOTATION, NUMERIC_UNDERSCORE, ASYNC_GENERATOR,
           AWAIT_IN_COMPREHENSION, ASYNC_COMPREHENSION, WALRUS, POSITIONAL_ONLY,
           DECORATOR_EXPRESSION, MATCH, EXCEPT_STAR, TYPE_STATEMENT, TYPE_PARAMETERS)

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _dotted(node) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name)


def _decorator_ok(node) -> bool:
    """A decorator before 3.9: a dotted name, or one call of a dotted name."""
    return _dotted(node.func) if isinstance(node, ast.Call) else _dotted(node)


def _enclosing(node, parents, kinds):
    """The nearest ancestor of *node* that is a function or a comprehension, if it is one of
    *kinds*; None otherwise."""
    node = parents.get(node)
    while node is not None:
        if isinstance(node, _FUNCTIONS + _COMPREHENSIONS + (ast.ClassDef,)):
            return node if isinstance(node, kinds) else None
        node = parents.get(node)
    return None


def _features(tree, text: str):
    """`(feature, line)` for each piece of `GRAMMAR` in *tree* (and *text*'s tokens)."""
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.JoinedStr):
            # A format spec inside an f-string is a JoinedStr of the same f-string: one
            # finding per outermost one.
            if not isinstance(parents.get(node), (ast.FormattedValue, ast.JoinedStr)):
                yield F_STRING, line
        elif isinstance(node, ast.AnnAssign):
            yield VARIABLE_ANNOTATION, line
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            if _enclosing(node, parents, (ast.AsyncFunctionDef,)) is not None:
                yield ASYNC_GENERATOR, line
        elif isinstance(node, ast.Await):
            if _enclosing(node, parents, _COMPREHENSIONS) is not None:
                yield AWAIT_IN_COMPREHENSION, line
        elif isinstance(node, ast.comprehension) and node.is_async:
            yield ASYNC_COMPREHENSION, getattr(node.target, "lineno", 0)
        elif isinstance(node, ast.NamedExpr):
            yield WALRUS, line
        elif isinstance(node, ast.arguments) and node.posonlyargs:
            yield POSITIONAL_ONLY, getattr(node.posonlyargs[0], "lineno", 0)
        elif isinstance(node, ast.Match):
            yield MATCH, line
        elif type(node).__name__ == "TryStar":
            yield EXCEPT_STAR, line
        elif type(node).__name__ == "TypeAlias":
            yield TYPE_STATEMENT, line
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if getattr(node, "type_params", None):
                yield TYPE_PARAMETERS, line
            for decorator in node.decorator_list:
                if not _decorator_ok(decorator):
                    yield DECORATOR_EXPRESSION, decorator.lineno
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.NUMBER and "_" in token.string:
                yield NUMERIC_UNDERSCORE, token.start[0]
    except (tokenize.TokenError, SyntaxError):
        pass                                # the tree parsed: what it holds was read above


def grammar_problems(tree, text: str, file: str, target: Target) -> list:
    """One line per use in *tree* of grammar newer than *target*, naming the file, the line,
    the feature, its version and what to write instead; [] when the target cannot be checked
    against (its "can't tell" is the caller's)."""
    if target.problem():
        return []
    out = []
    for feature, line in sorted(_features(tree, text), key=lambda f: f[1]):
        since = available_from(feature.since)
        if tuple(target.version) < since:
            out.append(f"{file} line {line}: {feature.words} needs Python {shown(since)}, and "
                       f"the controller's Python is {shown(target.version)}: "
                       f"{feature.instead}")
    return out


# ── the standard library ────────────────────────────────────────────────────────────────────

#: A module and the version that introduced it ("New in version", the Python docs, as known).
#: Only `dataclasses` is on the app allowlist; the rest are listed for the guide, since an app
#: would plausibly reach for them (the allowlist refuses them whatever the version).
MODULES = {
    "dataclasses": "3.7",
    "secrets": "3.6",
    "contextvars": "3.7",
    "graphlib": "3.9",
    "zoneinfo": "3.9",
    "tomllib": "3.11",
}

#: A name of a module the app allowlist allows, and the version that introduced it ("New in
#: version", the Python docs, as known). A name the docs give two versions for was added in a
#: patch release of each line.
NAMES = {
    "base64.b32hexdecode": "3.10",
    "base64.b32hexencode": "3.10",
    "base64.z85decode": "3.13",
    "base64.z85encode": "3.13",
    "collections.abc.AsyncGenerator": "3.6",
    "collections.abc.Buffer": "3.12",
    "collections.abc.Collection": "3.6",
    "collections.abc.Reversible": "3.6",
    "copy.replace": "3.13",
    "datetime.UTC": "3.11",
    "datetime.date.fromisocalendar": "3.8",
    "datetime.date.fromisoformat": "3.7",
    "datetime.datetime.fromisocalendar": "3.8",
    "datetime.datetime.fromisoformat": "3.7",
    "datetime.time.fromisoformat": "3.7",
    "enum.EnumCheck": "3.11",
    "enum.EnumType": "3.11",
    "enum.Flag": "3.6",
    "enum.FlagBoundary": "3.11",
    "enum.IntFlag": "3.6",
    "enum.ReprEnum": "3.11",
    "enum.StrEnum": "3.11",
    "enum.auto": "3.6",
    "enum.global_enum": "3.11",
    "enum.member": "3.11",
    "enum.nonmember": "3.11",
    "enum.property": "3.11",
    "enum.verify": "3.11",
    "functools.cache": "3.9",
    "functools.cached_property": "3.8",
    "functools.singledispatchmethod": "3.8",
    "hashlib.blake2b": "3.6",
    "hashlib.blake2s": "3.6",
    "hashlib.file_digest": "3.11",
    "hashlib.scrypt": "3.6",
    "hashlib.sha3_224": "3.6",
    "hashlib.sha3_256": "3.6",
    "hashlib.sha3_384": "3.6",
    "hashlib.sha3_512": "3.6",
    "hashlib.shake_128": "3.6",
    "hashlib.shake_256": "3.6",
    "itertools.batched": "3.12",
    "itertools.pairwise": "3.10",
    "logging.getHandlerByName": "3.12",
    "logging.getHandlerNames": "3.12",
    "logging.getLevelNamesMapping": "3.11",
    "math.cbrt": "3.11",
    "math.comb": "3.8",
    "math.dist": "3.8",
    "math.exp2": "3.11",
    "math.fma": "3.13",
    "math.isqrt": "3.8",
    "math.lcm": "3.9",
    "math.nextafter": "3.9",
    "math.perm": "3.8",
    "math.prod": "3.8",
    "math.remainder": "3.7",
    "math.sumprod": "3.12",
    "math.tau": "3.6",
    "math.ulp": "3.9",
    "re.Match": "3.7",
    "re.NOFLAG": "3.11",
    "re.Pattern": "3.7",
    "re.PatternError": "3.13",
    "re.RegexFlag": "3.6",
    "string.Template.get_identifiers": "3.11",
    "string.Template.is_valid": "3.11",
    "time.clock_gettime_ns": "3.7",
    "time.clock_settime_ns": "3.7",
    "time.monotonic_ns": "3.7",
    "time.perf_counter_ns": "3.7",
    "time.process_time_ns": "3.7",
    "time.thread_time": "3.7",
    "time.thread_time_ns": "3.7",
    "time.time_ns": "3.7",
    "typing.Annotated": "3.9",
    "typing.AsyncContextManager": "3.5.4, 3.6.2",
    "typing.AsyncGenerator": "3.6.1",
    "typing.AsyncIterable": "3.5.2",
    "typing.AsyncIterator": "3.5.2",
    "typing.Awaitable": "3.5.2",
    "typing.ChainMap": "3.5.4, 3.6.1",
    "typing.ClassVar": "3.5.3",
    "typing.Collection": "3.6",
    "typing.Concatenate": "3.10",
    "typing.ContextManager": "3.5.4, 3.6.0",
    "typing.Coroutine": "3.5.3",
    "typing.Counter": "3.5.4, 3.6.1",
    "typing.DefaultDict": "3.5.2",
    "typing.Deque": "3.5.4, 3.6.1",
    "typing.Final": "3.8",
    "typing.Literal": "3.8",
    "typing.LiteralString": "3.11",
    "typing.Never": "3.11",
    "typing.NewType": "3.5.2",
    "typing.NoReturn": "3.5.4, 3.6.2",
    "typing.NotRequired": "3.11",
    "typing.OrderedDict": "3.7.2",
    "typing.ParamSpec": "3.10",
    "typing.Protocol": "3.8",
    "typing.ReadOnly": "3.13",
    "typing.Required": "3.11",
    "typing.Self": "3.11",
    "typing.SupportsIndex": "3.8",
    "typing.TYPE_CHECKING": "3.5.2",
    "typing.Text": "3.5.2",
    "typing.Type": "3.5.2",
    "typing.TypeAlias": "3.10",
    "typing.TypeAliasType": "3.12",
    "typing.TypeGuard": "3.10",
    "typing.TypeIs": "3.13",
    "typing.TypeVarTuple": "3.11",
    "typing.TypedDict": "3.8",
    "typing.Unpack": "3.11",
    "typing.assert_never": "3.11",
    "typing.assert_type": "3.11",
    "typing.dataclass_transform": "3.11",
    "typing.final": "3.8",
    "typing.get_args": "3.8",
    "typing.get_origin": "3.8",
    "typing.is_typeddict": "3.10",
    "typing.override": "3.12",
    "typing.reveal_type": "3.11",
    "typing.runtime_checkable": "3.8",
    "uuid.uuid6": "3.14",
    "uuid.uuid7": "3.14",
    "uuid.uuid8": "3.14",
}

#: A builtin name and the version that introduced it ("New in version", the Python docs, as
#: known); checked where the file binds no name of its own by that name.
BUILTINS = {
    "ModuleNotFoundError": "3.6",
    "EncodingWarning": "3.10",
    "aiter": "3.10",
    "anext": "3.10",
    "BaseExceptionGroup": "3.11",
    "ExceptionGroup": "3.11",
}


def since(dotted: str):
    """The docs' "New in version" text for a module, a name of one, or a builtin, or None
    when no table holds it."""
    return MODULES.get(dotted) or NAMES.get(dotted) or BUILTINS.get(dotted)


def name_problem(dotted: str, target: Target) -> str:
    """Why the controller's Python lacks *dotted* (a module, a name of one or a builtin),
    naming its version and the controller's, or "" when it has it or no table says."""
    docs = since(dotted)
    if docs is None or target.problem():
        return ""
    first = available_from(docs)
    if tuple(target.version) >= first:
        return ""
    what = "module" if dotted in MODULES else "builtin" if dotted in BUILTINS else "name"
    return (f"`{dotted}` is refused for this controller: the {what} is new in Python "
            f"{shown(first)} (the docs' \"New in version {docs}\"), and the controller's "
            f"Python is {shown(target.version)}")


def missing_at(version) -> list:
    """`(dotted, docs)` of every module, name and builtin the tables say *version* lacks."""
    out = []
    for table in (MODULES, NAMES, BUILTINS):
        out += [(d, docs) for d, docs in table.items() if tuple(version) < available_from(docs)]
    return sorted(out)


VERSION = re.compile(r"Python (\d+)\.(\d+)(?:\.(\d+))?\S*\Z")


def parse_answer(answer: str):
    """`(major, minor, patch or None)` from an interpreter's `--version` answer (`Python
    3.5.2`), or None when it is not that shape."""
    match = VERSION.match(str(answer or "").strip())
    if not match:
        return None
    patch = match.group(3)
    return int(match.group(1)), int(match.group(2)), int(patch) if patch else None
