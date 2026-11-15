"""AI input and output schemas: Pydantic v2, strict (PHASE8_PLAN 15.4, 13.5).

Every model's answer is a `StrictModel` (`strict=True`, `extra="forbid"`), registered by name
and version, its generated JSON schema committed as a file (`schemas/ai/<name>.v<N>.json`,
one per model and version). `schema_for(model, provider)` derives what a provider is sent:
for Anthropic's structured outputs, the keywords it does not support are removed (Pydantic
still enforces them on the answer: ranges, lengths, counts), and every object says
`additionalProperties: false`. A CI test holds each committed file to its model and refuses
a keyword outside the provider's subset.

An enum compares without case, so no two members may differ only by case (13.5: a model's
"Ok" is the schema's "ok"; two such members would make that comparison ambiguous).
"""
import copy
import json
import os
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from modules.ai import profiles

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMITTED = os.path.join(ROOT, "schemas", "ai")


class StrictModel(BaseModel):
    """The base of every AI schema: no coercion, no extra field."""
    model_config = ConfigDict(strict=True, extra="forbid")


#: {(name, version): model}, by `register`.
REGISTRY: dict = {}


def register(name: str, version: int):
    """Register a `StrictModel` as the schema *name* at *version*; a name and version taken
    twice, a model that is not strict, or an enum with two members equal but for case is
    refused at import."""
    def wrap(model):
        if not issubclass(model, StrictModel):
            raise TypeError(f"{model.__name__}: an AI schema must be a StrictModel")
        if (name, version) in REGISTRY:
            raise ValueError(f"the AI schema {name} v{version} is registered twice")
        for enum in enums_of(model):
            folded = {}
            for member in enum:
                key = str(member.value).casefold()
                if key in folded:
                    raise ValueError(f"{model.__name__}: enum {enum.__name__} has "
                                     f"{folded[key]!r} and {member.value!r}, equal but for case")
                folded[key] = member.value
        REGISTRY[(name, version)] = model
        model.__ai_schema__ = (name, version)
        return model
    return wrap


def enums_of(model) -> list:
    """Every Enum class a model's fields use, nested models included."""
    out, seen = [], set()

    def walk(tp):
        if isinstance(tp, type) and issubclass(tp, Enum):
            if tp not in seen:
                seen.add(tp)
                out.append(tp)
        elif isinstance(tp, type) and issubclass(tp, BaseModel):
            for f in tp.model_fields.values():
                walk(f.annotation)
        for arg in getattr(tp, "__args__", ()) or ():
            walk(arg)
    walk(model)
    return out


#: JSON-schema keywords Anthropic's structured outputs do not take (its reference, read
#: 2026-10-25: numerical and string-length constraints, complex array constraints). Removed
#: from what is sent; Pydantic enforces them on the answer.
ANTHROPIC_UNSUPPORTED = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                         "multipleOf", "minLength", "maxLength", "minItems", "maxItems",
                         "uniqueItems", "pattern", "minProperties", "maxProperties")
#: What a schema sent to Anthropic may hold (the same reference's supported list, plus the
#: annotations it ignores).
ANTHROPIC_KEYWORDS = frozenset((
    "type", "properties", "required", "additionalProperties", "items", "enum", "const",
    "anyOf", "allOf", "$ref", "$defs", "format", "title", "description", "default"))


def json_schema(model) -> dict:
    """Pydantic's own JSON schema of *model* (what is committed)."""
    return model.model_json_schema()


# ── The grammar's complexity (the operator, 2026-11-15: v8 was refused by the provider) ──────

#: The provider's documented limits on every strict schema of ONE request, together
#: (platform.claude.com/docs/en/build-with-claude/structured-outputs, "Schema complexity
#: limits", read 2026-11-15): optional parameters (each property not in its object's
#: `required`) and parameters with a union type (`anyOf` or a type array). Past these, or past
#: an internal bound on the compiled grammar's size that the provider does not state, the
#: request is refused with HTTP 400 before any token is generated: v8 of AI troubleshooting's
#: answer (20 union parameters) was ("The compiled grammar is too large", 2026-11-15 17:18 UTC).
PROVIDER_OPTIONAL_LIMIT = 24
PROVIDER_UNION_LIMIT = 16


def complexity(schema: dict) -> dict:
    """*schema*'s grammar size as the provider counts it, each `$ref` followed once per use (a
    use is a place the grammar expands): ``{"optional", "union", "objects", "properties",
    "enum_values", "depth"}``."""
    defs = schema.get("$defs") or {}
    out = {"optional": 0, "union": 0, "objects": 0, "properties": 0, "enum_values": 0,
           "depth": 0}

    def deref(node):
        ref = node.get("$ref") if isinstance(node, dict) else None
        return (defs.get(ref.rsplit("/", 1)[-1]) or {}) if ref else node

    def union(node):
        return isinstance(node, dict) and bool(node.get("anyOf") or node.get("oneOf")
                                               or isinstance(node.get("type"), list))

    def walk(node, depth, stack):
        if not isinstance(node, dict):
            return
        if node.get("$ref"):
            name = node["$ref"].rsplit("/", 1)[-1]
            if name in stack:
                return
            stack = stack + (name,)
        node = deref(node)
        out["depth"] = max(out["depth"], depth)
        out["enum_values"] += len(node.get("enum") or [])
        for alt in (node.get("anyOf") or []) + (node.get("oneOf") or []):
            walk(alt, depth, stack)
        if node.get("type") == "object" or "properties" in node:
            out["objects"] += 1
            required = set(node.get("required") or [])
            for key, sub in (node.get("properties") or {}).items():
                out["properties"] += 1
                out["optional"] += key not in required
                out["union"] += union(sub) or union(deref(sub))
                walk(sub, depth + 1, stack)
        if "items" in node:
            walk(node["items"], depth + 1, stack)

    walk(schema, 0, ())
    return out


def flatten(schema: dict) -> dict:
    """*schema* with no optional and no union parameter: every property required, a nullable
    one its non-null branch, a union of scalars a string, no default. What a `FlatWire` model
    sends; "" or [] (or an object of nothing but those) stands for none, and the model's own
    validator reads it back as None (`unflatten`)."""
    schema = copy.deepcopy(schema)
    scalars = {"string", "integer", "number", "boolean"}

    def one(node):
        alts = node.get("anyOf")
        types = node.get("type")
        if alts:
            kept = [a for a in alts if a != {"type": "null"}]
            node.pop("anyOf")
            if len(kept) == 1:
                node.update(kept[0])
            elif all(set([a.get("type")]) <= scalars for a in kept):
                node["type"] = "string"
            else:
                raise ValueError(f"flatten: a union of non-scalars cannot be flattened: {kept}")
        elif isinstance(types, list):
            kept = [t for t in types if t != "null"]
            node["type"] = kept[0] if len(kept) == 1 else "string"
        node.pop("default", None)

    def walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                for sub in node["properties"].values():
                    one(sub)
                node["required"] = list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(schema)
    return schema


def _empty(value) -> bool:
    """Whether a flattened answer's *value* stands for none."""
    if value == "" or value == [] or value == {}:
        return True
    return isinstance(value, dict) and all(_empty(v) for v in value.values())


def unflatten(model, data):
    """*data* as `flatten`'s schema answers it, as *model* reads it: each Optional field whose
    value is empty ("" or [], or an object of nothing but those) or absent is None, nested
    models and lists of them included. Data already in the model's own shape (a recorded
    answer, its nones as null) is unchanged."""
    import typing

    if not (isinstance(data, dict) and isinstance(model, type) and issubclass(model, BaseModel)):
        return data
    out = dict(data)
    for name, field in model.model_fields.items():
        args = typing.get_args(field.annotation)
        optional = type(None) in args
        inner = next((a for a in args if a is not type(None)), field.annotation) if optional \
            else field.annotation
        value = out.get(name)
        if isinstance(inner, type) and issubclass(inner, BaseModel):
            value = unflatten(inner, value)
        elif typing.get_origin(inner) is list:
            item = (typing.get_args(inner) or (None,))[0]
            if isinstance(value, list) and isinstance(item, type) and issubclass(item, BaseModel):
                value = [unflatten(item, v) for v in value]
        if optional and (name not in out or _empty(value)):
            out[name] = None
        elif name in out:
            out[name] = value
    return out


class FlatWire(StrictModel):
    """A model whose JSON schema is sent flattened (`flatten`: within the provider's limits,
    `PROVIDER_UNION_LIMIT` and `PROVIDER_OPTIONAL_LIMIT`, by construction) and read back in its
    own shape (`unflatten`): the code that reads the answer reads it as it always did. Put it
    first among a schema's bases."""

    @classmethod
    def model_json_schema(cls, *args, **kw):
        return flatten(super().model_json_schema(*args, **kw))

    @model_validator(mode="before")
    @classmethod
    def _from_wire(cls, data):
        return unflatten(cls, data)


def schema_for(model, provider: str = profiles.ANTHROPIC) -> dict:
    """What *provider* is sent for *model*: Anthropic's strict subset of its JSON schema."""
    if provider != profiles.ANTHROPIC:
        raise ValueError(f"no schema rule for the provider {provider!r}")
    schema = copy.deepcopy(json_schema(model))

    def walk(node):
        if isinstance(node, dict):
            for key in ANTHROPIC_UNSUPPORTED:
                node.pop(key, None)
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(schema)
    return schema


def keywords(schema) -> set:
    """Every keyword used in *schema* (the keys of each schema object, not property names)."""
    found = set()

    def walk(node, in_properties=False):
        if isinstance(node, dict):
            for key, value in node.items():
                if not in_properties:
                    found.add(key)
                walk(value, in_properties=(key in ("properties", "$defs")
                                           and not in_properties))
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(schema)
    return found


def committed_path(name: str, version: int) -> str:
    return os.path.join(COMMITTED, f"{name}.v{version}.json")


def committed_text(model) -> str:
    """The committed file's exact text for *model*: its JSON schema, sorted, indented."""
    return json.dumps(json_schema(model), indent=2, sort_keys=True) + "\n"


def write_committed() -> list:
    """Write every registered schema's file (a developer's step after changing a schema; the
    CI test refuses a file that differs). The paths written."""
    os.makedirs(COMMITTED, exist_ok=True)
    out = []
    for (name, version), model in sorted(REGISTRY.items()):
        path = committed_path(name, version)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(committed_text(model))
        out.append(path)
    return out
