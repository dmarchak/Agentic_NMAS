"""The laptop kit refuses to start when any setting points at the NMAS host's services, its golden
repository or a GitHub config repository (the operator, 2026-11-05; docs/LAB9_LAPTOP_RUN.md).

    python3 -I kit_check.py DATA_DIR

Reads the kit's settings (the installation's user_settings.json and every list's settings.json)
and every list's config repository's git remotes. The NMAS host's names come from the
environment (KIT_NMAS_LAN, KIT_NMAS_TUNNEL), which `kit` fills from data/lab_hosts.json through
scripts/nmas-host --field, so no address is written here. Prints key names, never a value.
Exit 0 when clean, 1 naming each key that points where it must not.
"""
import ipaddress
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def forbidden() -> list:
    """The substrings no kit setting may hold: the NMAS host's LAN address, its tunnel name and
    that name's domain, and GitHub."""
    out = ["github.com", "githubusercontent.com"]
    lan = os.environ.get("KIT_NMAS_LAN", "").strip()
    tunnel = os.environ.get("KIT_NMAS_TUNNEL", "").strip().lower()
    if lan:
        out.append(lan)
    if tunnel:
        out.append(tunnel)
        parts = tunnel.split(".")
        if len(parts) > 2:
            out.append("." + ".".join(parts[1:]))      # any service under the tunnel's domain
    return out


def _walk(value, path):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(value, str):
        yield path, value


def _host_of(value: str) -> str:
    try:
        return (urlsplit(value if "//" in value else "//" + value).hostname or "").lower()
    except ValueError:
        return ""


def problems(data_dir: str, git=None) -> list:
    """Each problem as words naming the file and key, never the value."""
    out = []
    tokens = [t.lower() for t in forbidden()]
    files = [os.path.join(data_dir, "user_settings.json")]
    lists = os.path.join(data_dir, "lists")
    slugs = sorted(os.listdir(lists)) if os.path.isdir(lists) else []
    files += [os.path.join(lists, s, "settings.json") for s in slugs]
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as exc:
            out.append(f"{os.path.relpath(f, data_dir)} cannot be read ({type(exc).__name__})")
            continue
        for key, value in _walk(doc, ""):
            low = value.lower()
            if any(t in low for t in tokens):
                out.append(f"{os.path.relpath(f, data_dir)}: {key} points at the NMAS host's "
                           "services or GitHub")
    settings = os.path.join(data_dir, "user_settings.json")
    try:
        with open(settings, encoding="utf-8") as fh:
            top = json.load(fh)
    except (OSError, ValueError):
        top = {}
    if str(top.get("flask_host", "127.0.0.1")) not in LOOPBACK_HOSTS:
        out.append("user_settings.json: flask_host is not a loopback address")
    nb = _host_of(str(top.get("netbox_url", "")))
    if nb and nb not in LOOPBACK_HOSTS:
        try:
            if not ipaddress.ip_address(nb).is_loopback:
                out.append("user_settings.json: netbox_url is not the kit's own NetBox")
        except ValueError:
            out.append("user_settings.json: netbox_url names a host, not the kit's own NetBox")
    run = git or (lambda repo: subprocess.run(["git", "-C", repo, "remote"], text=True,
                                              capture_output=True).stdout)
    for s in slugs:
        repo = os.path.join(lists, s, "config_repo")
        if os.path.isdir(os.path.join(repo, ".git")) and run(repo).strip():
            out.append(f"lists/{s}/config_repo has a git remote: the kit's lists keep none")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isabs(sys.argv[1]):
        sys.exit(__doc__)
    found = problems(sys.argv[1])
    if not os.environ.get("KIT_NMAS_LAN") or not os.environ.get("KIT_NMAS_TUNNEL"):
        found.append("the NMAS host's names were not given (KIT_NMAS_LAN, KIT_NMAS_TUNNEL), so "
                     "the check cannot rule them out")
    for p in found:
        print(f"REFUSED: {p}")
    print("check: PASS" if not found else f"check: FAIL ({len(found)})")
    sys.exit(1 if found else 0)
