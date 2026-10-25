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

from pydantic import BaseModel, ConfigDict

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
