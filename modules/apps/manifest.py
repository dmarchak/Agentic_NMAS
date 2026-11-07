"""A controller app's manifest (`apps/<app>/manifest.yml`; the SDN design (rev. 4), section
12, I-2; phase P1: the schema and its loader). `load_manifest(folder)` reads and validates it,
and **refuses each malformed field by name**, naming the value and the rule (`ManifestError`,
one line per problem).

The fields:
- `name`: `^[a-z][a-z0-9_]{0,40}$`, and `version`: `^[0-9]+\\.[0-9]+\\.[0-9]+$` (the rules
  section 10's apply script checks again on the controller's host);
- `summary`: one sentence (optional);
- `controllers`: each controller kind with its version requirement (`ryu: ">=4.34"`), at least
  one; a requirement is comma-separated clauses of an operator and a dotted number;
- `openflow_versions`: the OpenFlow versions the app speaks, quoted (`"1.3"`: YAML reads an
  unquoted 1.3 as a number, and 1.10 as 1.1);
- `requires`: the other apps it needs loaded first, by name (optional; never itself);
- `config_schema`: the JSON Schema (draft 2020-12) its config is validated by, whose top level
  is an object (`validate_config` checks a config against it, `jsonschema`);
- `rest`: its `prefix` and `endpoints`, each a path with its methods; **`/health` answering GET
  is required**, and `/validate`, if offered, answers POST;
- `owns_flows`: the cookie prefix and mask its flows carry, and the protected classes it owns,
  for B (optional; a cookie is 64-bit hex, the prefix having no bit outside the mask);
- `egress`: every network destination the app reaches, each a `name` (unique), the
  `from_config` key whose value is its address (dotted, `verdict_service.url`: a string key
  the `config_schema` declares through `properties`) and its `purpose` (one sentence); the
  app reaches the network only by `mercury_app.egress("<name>", ...)` (C2635; the app
  allowlist, `modules/apps/allowlist.py`, refuses any other), and `mercury app check` prints
  each for the reviewer (optional: none means the app reaches no destination of its own);
- `tests`: its unit tests, as paths relative to the app's folder (optional; the app gate
  holds each to the layout rule, a `test_*.py` file at the root or in `tests/`).

The file itself: a regular file (never a link) of at most `MAX_BYTES`, one YAML mapping, and a
key given twice is refused (YAML would otherwise keep the last silently).

Nothing here parses an address: where an app's config takes one (the DNS blacklist's verdict
service), its own `config_schema` says how, and an IPv6 literal goes bracketed in a URL.
"""

import os
import re
from collections.abc import Hashable
from typing import Dict, Literal, Optional, Tuple

import yaml
from pydantic import field_validator, model_validator

from modules.jobs.base import APP_NAME, SLUG, SUMMARY_MAX, VERSION, Contract, ContractError, \
    matches, no_duplicates

MANIFEST = "manifest.yml"
MAX_BYTES = 64 * 1024
CONTROLLER_KIND = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
_CLAUSE = r"\s*(?:>=|<=|==|!=|~=|>|<)\s*[0-9]+(?:\.[0-9]+)*\s*"
REQUIREMENT = re.compile(rf"^{_CLAUSE}(?:,{_CLAUSE})*$")
OPENFLOW_VERSIONS = ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5")
REST_PREFIX = re.compile(r"^/[a-z][a-z0-9_-]{0,40}$")
ENDPOINT_PATH = re.compile(r"^/[a-z0-9_{}/-]{0,100}$")
COOKIE = re.compile(r"^0x[0-9a-f]{1,16}$")
TEST_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
HEALTH, VALIDATE = "/health", "/validate"
#: An egress destination's name: what the app's `mercury_app.egress` call writes.
EGRESS_NAME = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
#: A config key, dotted through the schema's `properties` (`verdict_service.url`).
CONFIG_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}(?:\.[A-Za-z_][A-Za-z0-9_]{0,63}){0,7}$")


class ManifestError(ContractError):
    """A manifest refused: one line per field, each naming the field, the value and the rule."""


class Endpoint(Contract):
    path: str
    methods: Tuple[Literal["GET", "POST", "PUT", "PATCH", "DELETE"], ...]
    summary: str = ""

    @field_validator("path")
    @classmethod
    def _path(cls, v):
        return matches(ENDPOINT_PATH, v, "an endpoint's path")

    @field_validator("methods")
    @classmethod
    def _methods(cls, v):
        if not v:
            raise ValueError("an endpoint answers at least one method")
        return no_duplicates(v, "methods")


class Rest(Contract):
    prefix: str
    endpoints: Tuple[Endpoint, ...]

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, v):
        return matches(REST_PREFIX, v, "a REST prefix")

    @model_validator(mode="after")
    def _health_and_validate(self):
        no_duplicates([e.path for e in self.endpoints], "rest.endpoints' paths")
        paths = {e.path: e for e in self.endpoints}
        if HEALTH not in paths or "GET" not in paths[HEALTH].methods:
            got = sorted(paths[HEALTH].methods) if HEALTH in paths else "absent"
            raise ValueError(f"an app declares {HEALTH} answering GET (Mercury's post-check "
                             f"reads it); {HEALTH} here: {got}")
        if VALIDATE in paths and "POST" not in paths[VALIDATE].methods:
            raise ValueError(f"{VALIDATE}, when offered, answers POST, not "
                             f"{sorted(paths[VALIDATE].methods)}")
        return self


class OwnsFlows(Contract):
    cookie_prefix: str
    cookie_mask: str
    classes: Tuple[str, ...] = ()

    @field_validator("cookie_prefix", "cookie_mask")
    @classmethod
    def _cookie(cls, v):
        return matches(COOKIE, v, "a cookie")

    @field_validator("classes")
    @classmethod
    def _classes(cls, v):
        for c in v:
            matches(SLUG, c, "a protected class")
        return no_duplicates(v, "classes")

    @model_validator(mode="after")
    def _prefix_inside_its_bits(self):
        prefix, mask = int(self.cookie_prefix, 16), int(self.cookie_mask, 16)
        if mask == 0:
            raise ValueError("cookie_mask 0x0 selects no bit, so it owns every cookie")
        if prefix & ~mask:
            raise ValueError(f"cookie_prefix {self.cookie_prefix} has bits outside "
                             f"cookie_mask {self.cookie_mask}")
        return self


class Egress(Contract):
    """One network destination the app reaches (see the module's docstring)."""

    name: str
    from_config: str
    purpose: str

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return matches(EGRESS_NAME, v, "an egress destination's name")

    @field_validator("from_config")
    @classmethod
    def _from_config(cls, v):
        return matches(CONFIG_KEY, v, "a dotted config key")

    @field_validator("purpose")
    @classmethod
    def _purpose(cls, v):
        if not v.strip() or len(v) > SUMMARY_MAX:
            raise ValueError(f"a purpose is one sentence, 1 to {SUMMARY_MAX} characters, not "
                             f"{len(v)}")
        return v

    def words(self) -> str:
        """The destination as `app check` prints it for the reviewer."""
        return (f"egress {self.name!r}: to the address in the config's {self.from_config}: "
                f"{self.purpose}")


def config_key_problem(schema: dict, key: str) -> str:
    """Why *key* (dotted) is not a string key *schema* declares through `properties`, or ""
    when it is. A `$ref` is not followed: an address's key is declared where it is read."""
    node, walked = schema, []
    for part in key.split("."):
        props = node.get("properties") if isinstance(node, dict) else None
        here = ".".join(walked) or "the config"
        if not isinstance(props, dict) or part not in props:
            declared = ", ".join(sorted(props)) if isinstance(props, dict) else "nothing"
            return (f"{key!r} is not a key config_schema declares: {here} declares "
                    f"{declared}, not {part!r}")
        node = props[part]
        walked.append(part)
    if not isinstance(node, dict) or node.get("type") != "string":
        got = node.get("type") if isinstance(node, dict) else node
        return f"{key!r} carries an address, a string, and config_schema types it {got!r}"
    return ""


class Manifest(Contract):
    name: str
    version: str
    summary: str = ""
    controllers: Dict[str, str]
    openflow_versions: Tuple[str, ...]
    requires: Tuple[str, ...] = ()
    config_schema: dict
    rest: Rest
    owns_flows: Optional[OwnsFlows] = None
    egress: Tuple[Egress, ...] = ()
    tests: Tuple[str, ...] = ()

    def egress_names(self) -> tuple:
        return tuple(e.name for e in self.egress)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        return matches(APP_NAME, v, "an app's name")

    @field_validator("version")
    @classmethod
    def _version(cls, v):
        return matches(VERSION, v, "a version")

    @field_validator("summary")
    @classmethod
    def _summary(cls, v):
        if len(v) > SUMMARY_MAX:
            raise ValueError(f"a summary is at most {SUMMARY_MAX} characters, not {len(v)}")
        return v

    @field_validator("controllers")
    @classmethod
    def _controllers(cls, v):
        if not v:
            raise ValueError("an app names at least one controller with its versions")
        for kind, requirement in v.items():
            matches(CONTROLLER_KIND, kind, "a controller kind")
            if not REQUIREMENT.fullmatch(requirement):
                raise ValueError(f"{kind}'s requirement {requirement!r} is not clauses like "
                                 "'>=4.34' or '>=4.34,<5'")
        return v

    @field_validator("openflow_versions", mode="before")
    @classmethod
    def _openflow_versions(cls, v):
        if not isinstance(v, (list, tuple)) or not v:
            raise ValueError("openflow_versions is a non-empty list, such as [\"1.3\"]")
        for item in v:
            if not isinstance(item, str):
                raise ValueError(f"{item!r} is a {type(item).__name__}: write each OpenFlow "
                                 "version quoted, as \"1.3\"")
            if item not in OPENFLOW_VERSIONS:
                raise ValueError(f"{item!r} is not one of {', '.join(OPENFLOW_VERSIONS)}")
        return no_duplicates(tuple(v), "openflow_versions")

    @field_validator("requires")
    @classmethod
    def _requires(cls, v):
        for r in v:
            matches(APP_NAME, r, "a required app's name")
        return no_duplicates(v, "requires")

    @field_validator("config_schema")
    @classmethod
    def _config_schema(cls, v):
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError

        try:
            Draft202012Validator.check_schema(v)
        except SchemaError as exc:
            where = "/".join(str(p) for p in exc.path) or "(its top)"
            raise ValueError(f"not a JSON Schema at {where}: {exc.message}") from None
        if v.get("type") != "object":
            raise ValueError(f"an app's config is a mapping, so the schema's top-level type is "
                             f"'object', not {v.get('type')!r}")
        return v

    @field_validator("tests")
    @classmethod
    def _tests(cls, v):
        for t in v:
            if not TEST_PATH.fullmatch(t) or any(part in ("", ".", "..")
                                                 for part in t.split("/")):
                raise ValueError(f"a test is a path inside the app's folder, relative and "
                                 f"without '..', not {t!r}")
        return no_duplicates(v, "tests")

    @model_validator(mode="after")
    def _not_itself(self):
        if self.name in self.requires:
            raise ValueError(f"{self.name} requires itself")
        return self

    @model_validator(mode="after")
    def _egress_from_declared_keys(self):
        no_duplicates([e.name for e in self.egress], "egress names")
        problems = [f"egress {e.name!r}: from_config {why}" for e in self.egress
                    for why in [config_key_problem(self.config_schema, e.from_config)] if why]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class _UniqueKeys(yaml.SafeLoader):
    """YAML's safe loader, refusing a key given twice in one mapping."""


def _mapping(loader, node, deep=False):
    seen = set()
    for key_node, _value in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if isinstance(key, Hashable):
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"the key {key!r} is given twice", key_node.start_mark)
            seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_yaml(text: str, source: str, error=ContractError, what: str = "a manifest"):
    """*text* read as YAML by the safe loader refusing a key given twice (the one reader the
    manifest and the job's spec card share), or *error* naming *source* and the line."""
    try:
        return yaml.load(text, Loader=_UniqueKeys)  # noqa: S506 - a SafeLoader subclass
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark is not None else "the file"
        why = getattr(exc, "problem", None) or str(exc)
        raise error(source, [f"{where}: not YAML {what} can be read from ({why})"]) from None


def parse_manifest(text: str, source: str = MANIFEST) -> Manifest:
    """*text* (a manifest's YAML) validated, or `ManifestError` naming *source* and each
    problem."""
    data = load_yaml(text, source, ManifestError)
    try:
        return Manifest.parse(data, source)
    except ContractError as exc:
        raise ManifestError(source, exc.problems) from None


def load_manifest(folder) -> Manifest:
    """The manifest in app folder *folder*, validated (see the module's docstring)."""
    path = os.path.join(os.fspath(folder), MANIFEST)
    if os.path.islink(path):
        raise ManifestError(path, ["is a symbolic link; a manifest is a regular file"])
    if not os.path.isfile(path):
        raise ManifestError(path, ["is not a file: an app's folder holds its manifest.yml"])
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        raise ManifestError(path, [f"is {size} bytes, more than the {MAX_BYTES} a manifest may "
                                   "be"])
    with open(path, encoding="utf-8") as fh:
        return parse_manifest(fh.read(), path)


def effective_config(manifest: Manifest, config):
    """*config* with every schema `default` filled where its key is absent, at every level of
    objects the schema declares (`properties`), as Mercury compiles it for the app. A key that is
    present keeps its value; *config* itself is not changed."""
    import copy

    def fill(schema, value):
        if not isinstance(schema, dict) or not isinstance(value, dict):
            return value
        for key, sub in (schema.get("properties") or {}).items():
            if key not in value and isinstance(sub, dict) and "default" in sub:
                value[key] = copy.deepcopy(sub["default"])
            if key in value:
                value[key] = fill(sub, value[key])
        return value

    return fill(manifest.config_schema, copy.deepcopy(config))


def validate_config(manifest: Manifest, config) -> list:
    """Each way *config* fails *manifest*'s `config_schema`, as `<path>: <why>` lines in path
    order (empty when it passes)."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(manifest.config_schema)
    errors = sorted(validator.iter_errors(config), key=lambda e: [str(p) for p in e.path])
    return [f"{'/'.join(str(p) for p in e.path) or '(the config)'}: {e.message}"
            for e in errors]
