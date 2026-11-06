"""The job contract (the SDN design (rev. 4), section 11, I-1; phase P1: the contracts as
stubs). A job is a class extending `Job`, declaring `meta` (a `JobMeta`), its typed `Inputs` (a
`JobInputs`) and `run(ctx, inputs)`. It reaches the world only through `ctx`
(`modules/jobs/sdk.py`), and a write is a call on `ctx.changes` that builds a plan.

What P1 builds: the shapes and their validation, so a job's pure logic can be written and
unit-tested against fixtures with no Mercury running (`modules/jobs/testing.py`). What it does
not: the runner, the sandbox, the broker that enforces the scope at run time, the commit path
and the `job_runs` store (P4).

**Every refusal names the field, the value and the rule it was compared with**
(`ContractError`; CLAUDE.md: a refusal names the comparison it made and both operands).

The names (one home for both kinds, so the lifecycle and the manifest share them):
- a job's name: `JOB_NAME`, lower case with hyphens (`trace-path`), as the CLI types it;
- a controller app's name: `APP_NAME`, lower case with underscores, the rule section 10's apply
  script checks (an app is a Python module path on the controller, where a hyphen cannot go);
- a version: `VERSION`, three dot-separated numbers, the same rule as the script's.

The scope (`Scope`): the NetBox object types and the device roles a job may reach. **There is no
wildcard: an empty list reaches nothing**, so a composition of two jobs (`composed_reach`, the
intersection, never the union) can be empty and still be a scope.
"""

import re
from typing import ClassVar, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, ValidationError, \
    field_validator, model_validator

JOB_NAME = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
APP_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
#: A NetBox object type as its API names it (`dcim.device`: the app label, a dot, the model).
OBJECT_TYPE = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
#: A NetBox slug (a device role's, a protected class's).
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
PERMISSIONS = ("read", "write")
SUMMARY_MAX = 200
LABEL_MAX = 100
#: How much of a refused value a refusal quotes.
QUOTE_MAX = 80


class ContractError(ValueError):
    """A contract refused: `what` was refused, and `problems` holds one line per field, each
    naming the field, the value and the rule."""

    def __init__(self, what: str, problems):
        self.what = what
        self.problems = list(problems)
        super().__init__(f"{what} refused: " + "; ".join(self.problems))


class ScopeError(ContractError):
    """A call outside a job's declared scope, naming the call and the scope."""


def quoted(value) -> str:
    """*value* as a refusal quotes it: its repr, cut to `QUOTE_MAX` characters."""
    text = repr(value)
    return text if len(text) <= QUOTE_MAX else text[:QUOTE_MAX - 3] + "..."


def problems_of(exc: ValidationError) -> list:
    """One line per error in pydantic's *exc*: the field's dotted path, the value and why."""
    out = []
    for err in exc.errors(include_url=False):
        where = ".".join(str(part) for part in err.get("loc") or ()) or "(the whole)"
        why = err.get("msg") or err.get("type") or "refused"
        if why.startswith("Value error, "):
            why = why[len("Value error, "):]
        kind = err.get("type")
        if kind == "missing":
            out.append(f"{where}: missing (a required field)")
        elif kind == "extra_forbidden":
            out.append(f"{where}: not a field of this contract (given {quoted(err.get('input'))})")
        else:
            out.append(f"{where}: {quoted(err.get('input'))} refused: {why}")
    return out


def matches(rule: re.Pattern, value, what: str) -> str:
    """*value* if it is a string matching *rule*; otherwise a ValueError naming the value and
    the rule (pydantic adds the field)."""
    if not isinstance(value, str):
        raise ValueError(f"{what} is a string, not a {type(value).__name__}")
    if not rule.fullmatch(value):
        raise ValueError(f"{what} {value!r} does not match {rule.pattern}")
    return value


def no_duplicates(values, what: str):
    seen, twice = set(), []
    for v in values:
        if v in seen and v not in twice:
            twice.append(v)
        seen.add(v)
    if twice:
        raise ValueError(f"{what} lists {', '.join(repr(t) for t in twice)} more than once")
    return values


class _ContractType(type(BaseModel)):
    """Turns pydantic's error into `ContractError` where a contract is CALLED (`JobMeta(...)`).
    The class's own `__init__` is left alone: pydantic calls an overridden `__init__` for every
    nested contract too, which would wrap each nested refusal in its parent's instead of naming
    its field's dotted path."""

    def __call__(cls, *args, **kwargs):
        try:
            return super().__call__(*args, **kwargs)
        except ValidationError as exc:
            raise ContractError(cls.__name__, problems_of(exc)) from None


class Contract(BaseModel, metaclass=_ContractType):
    """A frozen contract that refuses an unknown field and raises `ContractError` (naming each
    field, its value and the rule) instead of pydantic's own error, whether it is built by its
    constructor or from a mapping (`parse`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @classmethod
    def parse(cls, data, what: str = ""):
        """*data* (a mapping) validated as this contract."""
        if not isinstance(data, dict):
            raise ContractError(what or cls.__name__,
                                [f"(the whole): a mapping, not a {type(data).__name__}"])
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ContractError(what or cls.__name__, problems_of(exc)) from None


# ── the scope ─────────────────────────────────────────────────────────────────────────────────

class Scope(Contract):
    """What a job may reach: NetBox object types (`dcim.device`) and device roles (slugs). No
    wildcard: an empty list reaches nothing. Order does not matter; a duplicate is refused."""

    object_types: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()

    @field_validator("object_types")
    @classmethod
    def _object_types(cls, values):
        for v in values:
            matches(OBJECT_TYPE, v, "an object type")
        return no_duplicates(values, "object_types")

    @field_validator("roles")
    @classmethod
    def _roles(cls, values):
        for v in values:
            matches(SLUG, v, "a role")
        return no_duplicates(values, "roles")

    def words(self) -> str:
        types = ", ".join(self.object_types) or "none"
        roles = ", ".join(self.roles) or "none"
        return f"object types [{types}], roles [{roles}]"

    def intersect(self, other: "Scope") -> "Scope":
        """The scope both reach: the intersection, never the union (section 11's composition)."""
        return Scope(object_types=tuple(sorted(set(self.object_types) & set(other.object_types))),
                     roles=tuple(sorted(set(self.roles) & set(other.roles))))

    def check(self, call: str, object_type: str, role: Optional[str] = None) -> None:
        """Raise `ScopeError` naming *call* and this scope when *object_type* (or *role*, when
        the object has one) is outside it. P4's broker makes this check on every SDK call; the
        test double makes it too, so a unit test sees the refusal the runner will give."""
        problems = []
        if object_type not in self.object_types:
            problems.append(f"{call} reads {object_type!r}, outside the scope's "
                            f"{self.words()}")
        if role is not None and role not in self.roles:
            problems.append(f"{call} reaches role {role!r}, outside the scope's {self.words()}")
        if problems:
            raise ScopeError(f"the call {call}", problems)


# ── the job's declaration ────────────────────────────────────────────────────────────────────

class JobMeta(Contract):
    """A job's declaration (section 11's code block). `permission` is "read" or "write"; a read
    job declares `max_changes` 0, a write job at least 1; `autonomous` is a strict boolean."""

    name: str
    version: str
    summary: str
    permission: Literal["read", "write"]
    scope: Scope
    max_changes: StrictInt = 0
    autonomous: StrictBool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return matches(JOB_NAME, v, "a job's name")

    @field_validator("version")
    @classmethod
    def _version(cls, v):
        return matches(VERSION, v, "a version")

    @field_validator("summary")
    @classmethod
    def _summary(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("a summary is a non-empty sentence")
        if len(v) > SUMMARY_MAX:
            raise ValueError(f"a summary is at most {SUMMARY_MAX} characters, not {len(v)}")
        return v

    @field_validator("max_changes")
    @classmethod
    def _max_changes(cls, v):
        if v < 0:
            raise ValueError(f"max_changes is 0 or more, not {v}")
        return v

    @model_validator(mode="after")
    def _permission_and_reach(self):
        if self.permission == "read" and self.max_changes != 0:
            raise ValueError(f"permission 'read' makes no change, so max_changes is 0, not "
                             f"{self.max_changes}")
        if self.permission == "write" and self.max_changes < 1:
            raise ValueError(f"permission 'write' declares max_changes of at least 1, not "
                             f"{self.max_changes}")
        if not self.scope.object_types:
            raise ValueError("scope.object_types names at least one NetBox object type: a job "
                             "that reaches nothing is not a job")
        return self


def composed_reach(outer: JobMeta, inner: JobMeta) -> dict:
    """What a job calling a job may do (section 11): the intersection of their permissions and
    scopes, never the union. `{"permission", "scope", "max_changes"}`."""
    both_write = outer.permission == "write" and inner.permission == "write"
    return {"permission": "write" if both_write else "read",
            "scope": outer.scope.intersect(inner.scope),
            "max_changes": min(outer.max_changes, inner.max_changes) if both_write else 0}


# ── the inputs ───────────────────────────────────────────────────────────────────────────────

class JobInputs(Contract):
    """A job's inputs: subclass it with typed fields (`src: HostRef`). Frozen, and an unknown
    input is refused by name."""


class NetBoxRef(Contract):
    """An object picked from NetBox: its NetBox ID (the identity) and its name (a label)."""

    id: StrictInt
    name: str

    @field_validator("id")
    @classmethod
    def _id(cls, v):
        if v < 1:
            raise ValueError(f"a NetBox ID is 1 or more, not {v}")
        return v

    @field_validator("name")
    @classmethod
    def _label(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("a name is a non-empty label")
        if len(v) > LABEL_MAX or any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError(f"a name is at most {LABEL_MAX} printable characters")
        return v


class DeviceRef(NetBoxRef):
    """A managed device, by its NetBox ID."""

    kind: Literal["device"] = "device"


class HostRef(NetBoxRef):
    """A host (the `host` kind, section 9a: an end host or the controller's host), by its
    NetBox ID."""

    kind: Literal["host"] = "host"


# ── the job ──────────────────────────────────────────────────────────────────────────────────

class Job:
    """A job: subclass it with `meta`, `Inputs` and `run`. A subclass that lacks one is refused
    when the class is defined, naming the class and what is missing."""

    meta: ClassVar[JobMeta]
    Inputs: ClassVar[type] = JobInputs

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        problems = []
        meta = getattr(cls, "meta", None)
        if not isinstance(meta, JobMeta):
            problems.append(f"meta is a JobMeta, not {type(meta).__name__}")
        inputs = getattr(cls, "Inputs", None)
        if not (isinstance(inputs, type) and issubclass(inputs, JobInputs)):
            problems.append(f"Inputs is a subclass of JobInputs, not {quoted(inputs)}")
        if cls.run is Job.run:
            problems.append("run(self, ctx, inputs) is not defined")
        if problems:
            raise ContractError(f"the job class {cls.__name__}", problems)

    def run(self, ctx, inputs) -> None:
        raise NotImplementedError("a job defines run(self, ctx, inputs)")
