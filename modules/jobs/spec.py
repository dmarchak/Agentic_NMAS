"""The spec card, `spec.yml` (the SDN platform design rev. 6, section 11a, item 1: the FORMAT; the
assistant that drafts one is part (b)). It is the first file in a job's or app's folder, and
the person confirms it, never the code. `load_spec(folder)` reads and validates it, and
**refuses each malformed field by name**, naming the value and the rule (`SpecError`, one line
per problem, the field's dotted path first).

The fields:
- `kind`: `job` (the default) or `app`; a job's `name` follows `JOB_NAME` (hyphens), an app's
  `APP_NAME` (underscores), as the lifecycle names them;
- `summary`: one sentence, at most `SUMMARY_MAX` characters;
- `permission`: `read` or `write`;
- `scope`: `object_types` and `roles`, the job contract's own `Scope` (no wildcard);
- `inputs` and `outputs`: each a mapping of a field's name (`FIELD_NAME`) to its type, written
  `src: HostRef` or `src: {type: HostRef, description: ...}`. An input's type is one of
  `INPUT_TYPES` or `list[<one of them>]`; an output's one of `OUTPUT_TYPES` (a table, a log,
  a file, the change plan, or a value);
- `examples`: two or more acceptance examples, each a `name` (unique), `given`, `when`, `then`
  in plain words, and the `fixture` its data comes from: `ryu_recorded` (the recorded Ryu,
  `tests/fixtures/sdn/ryu_recorded.py`) or `netbox_export` (the masked NetBox export, with
  P1b).

**An open question refuses the card by name.** The assistant drafting a card never guesses: a
field it cannot fill holds `ask:`, written `permission: {ask: "read or write?"}` or
`permission: "ask: read or write?"`, anywhere in the card. Each is refused with its dotted
path and its question, before any other field is checked, so the card's own problems are not
confused with its open questions.

The file itself: a regular file (never a link) of at most `MAX_BYTES`, one YAML mapping, a
key given twice refused (the manifest's reader, `modules/apps/manifest.load_yaml`).
"""

import os
import re
from typing import Dict, Literal, Tuple

from pydantic import field_validator, model_validator

from modules.jobs.base import APP_NAME, JOB_NAME, SUMMARY_MAX, Contract, ContractError, \
    Scope, matches, no_duplicates, quoted

SPEC = "spec.yml"
MAX_BYTES = 64 * 1024
FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
#: A value an input takes: a scalar, a device or host picked from NetBox, a datapath id.
INPUT_TYPES = ("str", "int", "float", "bool", "HostRef", "DeviceRef", "dpid")
_LIST = re.compile(r"^list\[([A-Za-z]+)\]$")
#: What a run gives: `ctx.output`'s three, the change plan, or a value.
OUTPUT_TYPES = ("table", "log", "file", "plan", "str", "int", "float", "bool")
FIXTURES = ("ryu_recorded", "netbox_export")
MIN_EXAMPLES = 2
EXAMPLE_NAME_MAX = 120
TEXT_MAX = 1000
#: The key, or the leading word of a string, that marks an open question.
ASK = "ask"


class SpecError(ContractError):
    """A spec card refused: one line per problem, each naming the field, the value and the
    rule."""


def _text(v, what: str, limit: int = TEXT_MAX) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{what} is plain words, a non-empty string")
    if len(v) > limit:
        raise ValueError(f"{what} is at most {limit} characters, not {len(v)}")
    return v


class Field(Contract):
    type: str
    description: str = ""


def _fields(values, allowed, what: str):
    """*values* (`{name: type or {type, description}}`) as `{name: Field}`, each name and type
    checked against *allowed*."""
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError(f"{what} is a mapping of a name to its type, not {quoted(values)}")
    out = {}
    for name, given in values.items():
        matches(FIELD_NAME, name, f"{what}' name")
        field = given if isinstance(given, dict) else {"type": given}
        kind = field.get("type")
        inner = _LIST.match(kind) if isinstance(kind, str) and what == "inputs" else None
        if not isinstance(kind, str) or (kind not in allowed
                                          and not (inner and inner.group(1) in allowed)):
            lists = " or list[<one of them>]" if what == "inputs" else ""
            raise ValueError(f"{what}.{name}'s type {quoted(kind)} is not one of "
                             f"{', '.join(allowed)}{lists}")
        out[name] = field
    return out


class Example(Contract):
    """One acceptance example, in plain Given/When/Then, naming its fixture data."""

    name: str
    given: str
    when: str
    then: str
    fixture: Literal["ryu_recorded", "netbox_export"]

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return _text(v, "an example's name", EXAMPLE_NAME_MAX)

    @field_validator("given", "when", "then")
    @classmethod
    def _words(cls, v, info):
        return _text(v, f"an example's {info.field_name}")


class SpecCard(Contract):
    """The spec card (see the module's docstring)."""

    kind: Literal["job", "app"] = "job"
    name: str
    summary: str
    permission: Literal["read", "write"]
    scope: Scope
    inputs: Dict[str, Field] = {}
    outputs: Dict[str, Field] = {}
    examples: Tuple[Example, ...]

    @field_validator("summary")
    @classmethod
    def _summary(cls, v):
        return _text(v, "a summary", SUMMARY_MAX)

    @field_validator("inputs", mode="before")
    @classmethod
    def _inputs(cls, v):
        return _fields(v, INPUT_TYPES, "inputs")

    @field_validator("outputs", mode="before")
    @classmethod
    def _outputs(cls, v):
        return _fields(v, OUTPUT_TYPES, "outputs")

    @field_validator("examples")
    @classmethod
    def _examples(cls, v):
        if len(v) < MIN_EXAMPLES:
            raise ValueError(f"a card gives at least {MIN_EXAMPLES} acceptance examples, not "
                             f"{len(v)}")
        no_duplicates([e.name for e in v], "examples' names")
        return v

    @model_validator(mode="after")
    def _name_by_kind(self):
        rule = JOB_NAME if self.kind == "job" else APP_NAME
        if not isinstance(self.name, str) or not rule.fullmatch(self.name):
            whose = "a job's" if self.kind == "job" else "an app's"
            raise ValueError(f"name {quoted(self.name)} is not {whose} name: it matches "
                             f"{rule.pattern}")
        if not self.scope.object_types:
            raise ValueError("scope.object_types names at least one NetBox object type: a "
                             "job that reaches nothing is not a job")
        return self

    def example_names(self) -> list:
        return [e.name for e in self.examples]


def open_questions(data, where: str = "") -> list:
    """One line per `ask:` in *data* (the card as YAML read it), each with its dotted path
    and its question."""
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{where}.{key}" if where else str(key)
            if key == ASK:
                found.append(f"{where or '(the whole)'}: an open question, {quoted(value)}: "
                             "answer it before the card is checked")
            else:
                found.extend(open_questions(value, path))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            found.extend(open_questions(value, f"{where}[{i}]"))
    elif isinstance(data, str) and data.strip().lower().startswith(ASK + ":"):
        found.append(f"{where or '(the whole)'}: an open question, {quoted(data)}: answer it "
                     "before the card is checked")
    return found


def parse_spec(text: str, source: str = SPEC) -> SpecCard:
    """*text* (a card's YAML) validated, or `SpecError` naming *source* and each problem."""
    from modules.apps.manifest import load_yaml

    data = load_yaml(text, source, SpecError, "a spec card")
    questions = open_questions(data)
    if questions:
        raise SpecError(source, questions)
    try:
        return SpecCard.parse(data, source)
    except ContractError as exc:
        raise SpecError(source, exc.problems) from None


def load_spec(folder) -> SpecCard:
    """The spec card in *folder*, validated (see the module's docstring)."""
    path = os.path.join(os.fspath(folder), SPEC)
    if os.path.islink(path):
        raise SpecError(path, ["is a symbolic link; a spec card is a regular file"])
    if not os.path.isfile(path):
        raise SpecError(path, [f"is not a file: a job's folder holds its {SPEC}, the first "
                               "file written"])
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        raise SpecError(path, [f"is {size} bytes, more than the {MAX_BYTES} a card may be"])
    with open(path, encoding="utf-8") as fh:
        return parse_spec(fh.read(), path)
