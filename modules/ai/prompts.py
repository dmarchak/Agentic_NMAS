"""The prompt registry: prompts are versioned files in `prompts/` (PHASE8_PLAN 4: "prompts
are versioned code"), `prompts/<name>.v<N>.md`, read whole, each with its sha256 so a call's
record names the exact text it sent. A changed prompt is a new version, never an edit of a
released one (a recorded evaluation's responses answer the text they were recorded for).

What a prompt may not say (13.5): it never asks for JSON. The schema rides in the request
(`output_config.format`), and a prompt asking for JSON as well describes the answer twice.
"""
import hashlib
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "prompts")
_NAME = re.compile(r"^([a-z][a-z0-9_]*)\.v([1-9][0-9]*)\.md$")


class PromptError(ValueError):
    """A prompt that cannot be used, named with its file."""


def path(name: str, version: int) -> str:
    return os.path.join(DIR, f"{name}.v{version}.md")


def available() -> list:
    """Every prompt file's ``(name, version)``, sorted."""
    if not os.path.isdir(DIR):
        return []
    out = []
    for entry in os.listdir(DIR):
        m = _NAME.match(entry)
        if m:
            out.append((m.group(1), int(m.group(2))))
    return sorted(out)


def load(name: str, version: int) -> dict:
    """``{"name", "version", "text", "sha256"}`` of a prompt; PromptError names a file that is
    absent, empty, not printable text, or asks for JSON."""
    p = path(name, version)
    try:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        raise PromptError(f"no prompt {name} v{version}: {os.path.relpath(p, ROOT)} is absent")
    except UnicodeDecodeError as exc:
        raise PromptError(f"{os.path.relpath(p, ROOT)} is not UTF-8 text ({exc})")
    if not text.strip():
        raise PromptError(f"{os.path.relpath(p, ROOT)} is empty")
    bad = [c for c in text if not (c.isprintable() or c in "\n\t")]
    if bad:
        raise PromptError(f"{os.path.relpath(p, ROOT)} holds a control character "
                          f"({bad[0]!r})")
    if re.search(r"\bjson\b", text, re.I):
        raise PromptError(f"{os.path.relpath(p, ROOT)} asks for JSON: the schema rides in the "
                          "request, never in the prompt (PHASE8_PLAN 13.5)")
    return {"name": name, "version": version, "text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
