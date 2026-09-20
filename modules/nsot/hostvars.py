"""nsot/hostvars.py

Reading and writing extracted ``host_vars`` YAML.

Phase 3a is **read-only with respect to git**. Extractions land in
``config_repo/.nsot/staging/host_vars/<device>.yml``, which is gitignored.
Phase 3b adds "Review and commit extracted host_vars" with a diff, so the first
commit has a human in the loop.

Secrets never appear in YAML. The extractor replaces every secret value with a
``secret_ref`` and hands the value to the credential store. For a hashed secret
the *value is the hash string* — ``9 $9$…`` carries a per-hash salt and cannot
be regenerated, so the store holds it verbatim and the template emits it
verbatim. Storing plaintext there would make those lines fail every round trip,
permanently.
"""

import logging
import os

log = logging.getLogger(__name__)

STAGING_REL = os.path.join(".nsot", "staging", "host_vars")

#: Secret kinds that must be emitted verbatim and never re-derived.
HASH_KINDS = ("secret", "password")


def staging_dir(repo: str) -> str:
    path = os.path.join(repo, STAGING_REL)
    os.makedirs(path, exist_ok=True)
    return path


def staging_path(repo: str, hostname: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in hostname)
    return os.path.join(staging_dir(repo), f"{safe}.yml")


def to_yaml(host_vars: dict) -> str:
    """Serialise host_vars deterministically, with secrets removed.

    ``sort_keys=True`` matters: the fixed-point test requires that extracting
    twice produces byte-identical YAML, and dict ordering would otherwise make
    that depend on insertion order.
    """
    import yaml

    payload = {k: v for k, v in host_vars.items() if k != "secrets"}
    # `lineno` points into the source document, not the model. Rendering moves
    # lines around, so keeping it would break the fixed-point property for a
    # reason that has nothing to do with what was extracted.
    payload["unmodeled"] = [
        {k: v for k, v in entry.items() if k != "lineno"}
        for entry in host_vars.get("unmodeled", [])
    ]
    payload["secret_refs"] = sorted((host_vars.get("secrets") or {}).keys())
    return yaml.safe_dump(payload, sort_keys=True, default_flow_style=False,
                          allow_unicode=True, width=10000)


def from_yaml(text: str) -> dict:
    import yaml
    return yaml.safe_load(text) or {}


def write_staged(repo: str, host_vars: dict) -> str:
    """Write an extraction to the staging area. Nothing is committed."""
    hostname = host_vars.get("hostname") or "unknown"
    path = staging_path(repo, hostname)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(to_yaml(host_vars))
    log.info("hostvars: staged %s (not committed)", path)
    return path


def read_staged(repo: str, hostname: str):
    path = staging_path(repo, hostname)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return from_yaml(fh.read())


def list_staged(repo: str) -> list:
    directory = os.path.join(repo, STAGING_REL)
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-4] for f in os.listdir(directory) if f.endswith(".yml"))


def store_secrets(host_vars: dict, hostname: str, dry_run: bool = True) -> dict:
    """Move extracted secret values into the credential store.

    Returns what was moved — names only, never values. With *dry_run* (the
    Phase 3a default) nothing is written; the report just says what would move.
    """
    secrets = host_vars.get("secrets") or {}
    moved = []
    for ref, value in sorted(secrets.items()):
        kind = "hash" if _looks_hashed(value) else "plaintext"
        moved.append({"ref": f"{hostname}:{ref}", "kind": kind})
        if not dry_run:
            from modules.credentials import set_template_secret
            set_template_secret(f"{hostname}:{ref}", value, secret_kind=kind)
    return {"moved": moved, "dry_run": dry_run, "count": len(moved)}


def _looks_hashed(value: str) -> bool:
    """True for an IOS password hash, which must be emitted verbatim.

    Type 5 (``$1$``), type 8 (``$8$``), type 9 (``$9$``), and the numeric
    ``<type> <hash>`` form all carry salts that cannot be regenerated.
    """
    text = (value or "").strip()
    if text.startswith(("$1$", "$5$", "$8$", "$9$")):
        return True
    parts = text.split(None, 1)
    return len(parts) == 2 and parts[0] in ("5", "7", "8", "9")
