"""nsot/templates_repo.py

The per-network template library, living in the list's NSoT repo under
``config_repo/templates/``.

Built-in seeds ship in ``modules/nsot/templates/``. Seeding **copies** them into
the repo on first use; it never moves them, so the built-ins stay available as a
reference and Phase 3a's fleet tests keep running against them.

Templates are **per-platform**, not per-device. A per-device template is a
config file with extra steps — it defeats the point of templatising. Per-device
divergence belongs in ``host_vars``, and the one legitimate exception (a device
that genuinely needs different structure) is an explicit override in
``bindings.yml``.

``bindings.yml`` stores only the mapping:

```yaml
platforms:
  cisco_ios:   cisco_ios/base.j2
  cisco_iosxe: cisco_iosxe/base.j2
overrides:
  s3: cisco_ios/core-switch.j2
```

It deliberately does **not** store the resolved device list. That list is
computed from the manifest on demand: a stored copy drifts from the manifest and
then the two disagree silently, which is precisely the class of bug this project
keeps finding.
"""

import logging
import os
import shutil

log = logging.getLogger(__name__)

BUILTIN_ROOT = os.path.join(os.path.dirname(__file__), "templates")
TEMPLATES_REL = "templates"
BINDINGS_FILE = "bindings.yml"

DEFAULT_BINDINGS = {
    "platforms": {"cisco_ios": "cisco_ios/base.j2",
                  "cisco_iosxe": "cisco_iosxe/base.j2"},
    "overrides": {},
}


def templates_dir(repo: str) -> str:
    path = os.path.join(repo, TEMPLATES_REL)
    os.makedirs(path, exist_ok=True)
    return path


def bindings_path(repo: str) -> str:
    return os.path.join(templates_dir(repo), BINDINGS_FILE)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def builtin_platforms() -> list:
    if not os.path.isdir(BUILTIN_ROOT):
        return []
    return sorted(d for d in os.listdir(BUILTIN_ROOT)
                  if os.path.isdir(os.path.join(BUILTIN_ROOT, d)))


def seed_templates(repo: str, platform: str = "", overwrite: bool = False) -> dict:
    """Copy built-in seed templates into the repo. Idempotent.

    Existing files are left alone unless *overwrite* is set, so seeding can
    never silently discard an operator's edits.
    """
    root = templates_dir(repo)
    copied, skipped = [], []

    platforms = [platform] if platform else builtin_platforms()
    for plat in platforms:
        src_dir = os.path.join(BUILTIN_ROOT, plat)
        if not os.path.isdir(src_dir):
            continue
        dst_dir = os.path.join(root, plat)
        os.makedirs(dst_dir, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            if not name.endswith(".j2"):
                continue
            src, dst = os.path.join(src_dir, name), os.path.join(dst_dir, name)
            rel = f"{plat}/{name}"
            if os.path.exists(dst) and not overwrite:
                skipped.append(rel)
                continue
            shutil.copy2(src, dst)
            copied.append(rel)

    # The shared macro file lives at the root of the template tree.
    shared = os.path.join(BUILTIN_ROOT, "_common.j2")
    shared_dst = os.path.join(root, "_common.j2")
    if os.path.exists(shared) and (overwrite or not os.path.exists(shared_dst)):
        shutil.copy2(shared, shared_dst)
        copied.append("_common.j2")

    if not os.path.exists(bindings_path(repo)):
        save_bindings(repo, DEFAULT_BINDINGS)
        copied.append(BINDINGS_FILE)

    log.info("templates: seeded %d file(s) into %s (%d already present)",
             len(copied), root, len(skipped))
    return {"ok": True, "copied": copied, "skipped": skipped}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_templates(repo: str) -> list:
    root = templates_dir(repo)
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".j2"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            found.append({"path": rel,
                          "size": os.path.getsize(os.path.join(dirpath, name))})
    return sorted(found, key=lambda t: t["path"])


def read_template(repo: str, rel_path: str):
    full = _safe_join(repo, rel_path)
    if full is None or not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8") as fh:
        return fh.read()


def write_template(repo: str, rel_path: str, content: str) -> dict:
    """Write a template after a Jinja syntax check. Does not commit."""
    full = _safe_join(repo, rel_path)
    if full is None:
        return {"ok": False, "error": "Invalid template path"}

    ok, error = check_syntax(content)
    if not ok:
        return {"ok": False, "error": error}

    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return {"ok": True, "path": rel_path}


def check_syntax(content: str) -> tuple:
    """Parse a template without rendering it. Returns ``(ok, error)``."""
    from jinja2 import Environment, StrictUndefined, TemplateSyntaxError
    try:
        Environment(undefined=StrictUndefined, trim_blocks=True).parse(content)
        return True, ""
    except TemplateSyntaxError as exc:
        return False, f"line {exc.lineno}: {exc.message}"
    except Exception as exc:                  # noqa: BLE001
        return False, str(exc)


def _safe_join(repo: str, rel_path: str):
    """Resolve *rel_path* inside the template tree, refusing traversal."""
    root = os.path.abspath(templates_dir(repo))
    full = os.path.abspath(os.path.join(root, rel_path))
    if not full.startswith(root + os.sep):
        log.warning("templates: refused path outside the template tree: %r", rel_path)
        return None
    if not full.endswith((".j2", ".yml")):
        return None
    return full


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------

def load_bindings(repo: str) -> dict:
    import yaml

    path = bindings_path(repo)
    if not os.path.exists(path):
        return {k: dict(v) for k, v in DEFAULT_BINDINGS.items()}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:                  # noqa: BLE001
        log.error("templates: unreadable bindings (%s) — using defaults", exc)
        return {k: dict(v) for k, v in DEFAULT_BINDINGS.items()}
    return {"platforms": dict(data.get("platforms") or {}),
            "overrides": dict(data.get("overrides") or {})}


def save_bindings(repo: str, bindings: dict) -> dict:
    import yaml

    payload = {"platforms": dict(bindings.get("platforms") or {}),
               "overrides": dict(bindings.get("overrides") or {})}
    path = bindings_path(repo)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(payload, fh, sort_keys=True, default_flow_style=False)
    return {"ok": True}


def template_for_device(repo: str, device: str, platform: str) -> str:
    """The template governing *device*: an override, else its platform's."""
    bindings = load_bindings(repo)
    override = bindings["overrides"].get(device)
    if override:
        return override
    return bindings["platforms"].get(platform, f"{platform}/base.j2")


def devices_for_template(repo: str, rel_path: str) -> list:
    """Devices currently bound to *rel_path*.

    Computed from the manifest every time. Never persisted: a stored device
    list drifts from the manifest and then the two disagree silently.
    """
    from modules.nsot import manifest as _manifest

    bindings = load_bindings(repo)
    devices = []
    for identity, entry in _manifest.load(repo)["devices"].items():
        name = entry.get("name", "")
        if not name:
            continue
        platform = _platform_slug(entry.get("platform", ""))
        bound = bindings["overrides"].get(name) or bindings["platforms"].get(
            platform, f"{platform}/base.j2")
        if bound == rel_path:
            devices.append({"device": name, "identity": identity,
                            "platform": platform})
    return sorted(devices, key=lambda d: d["device"])


def _platform_slug(platform: str) -> str:
    """Map a NetBox platform slug to the parser platform the templates key on."""
    from modules.nsot.parsers import REGISTRY
    cls = REGISTRY.get((platform or "").strip().lower())
    return cls.platform if cls else (platform or "cisco_ios")


def render_with_template(repo: str, host_vars: dict, rel_path: str,
                         secret_lookup=None) -> str:
    """Render *host_vars* through a template from the repo's library."""
    from modules.nsot import roundtrip

    root = templates_dir(repo)
    platform_dir = os.path.dirname(rel_path) or host_vars.get("platform", "")
    name = os.path.basename(rel_path)
    return roundtrip.render(host_vars, platform_dir, secret_lookup,
                            template_root=root, template_name=name)


# ---------------------------------------------------------------------------
# Seed status: has the SHIPPED template moved since this network's copy?
# ---------------------------------------------------------------------------

#: The four answers (OPEN_FINDINGS C6). **"edited" is not a defect**: a
#: network may change a template deliberately, and a tool that reports that
#: as a problem gets ignored. The one that asks for attention is "stale" --
#: the shipped template changed and this network's copy did not -- and
#: "edited_and_stale", where both moved and a person has to merge.
SEED_STATES = ("current", "stale", "edited", "edited_and_stale")

#: When history cannot answer. Named, never folded into one of the four.
SEED_UNCLASSIFIED = ("absent", "no_shipped_history", "no_common_base",
                     "not_classified")


def _git_ro(cwd: str, *args) -> tuple:
    """Read-only git, deliberately NOT `repo.git()`: that tops up
    `.gitignore` on every call, which is right for a config repo and wrong
    for the application checkout this also reads."""
    import subprocess

    try:
        p = subprocess.run(["git", "-C", cwd, *args], capture_output=True,
                           text=True, timeout=30)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def _blob_of_file(path: str) -> str:
    """The git blob id of *path*'s raw bytes.

    ABSOLUTE, and with no filters. Measured live: `git -C <dir> hash-object
    <relative path>` resolves the path from inside <dir>, doubles it, fails,
    and returns "" -- so every file compared unequal and the whole library
    read `edited_and_stale` while two files were byte-identical to shipped.
    The tests passed, because they only ever passed absolute paths.
    `--no-filters` keeps a repository's `.gitattributes` from changing what
    is hashed."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return ""
    rc, out, _ = _git_ro(os.path.dirname(path), "hash-object", "--no-filters",
                         path)
    return out if rc == 0 else ""


def _history(cwd: str, rel: str) -> list:
    """``[(commit, iso date, blob)]`` for *rel*, newest first; commits where
    the path did not exist are skipped."""
    rc, out, _ = _git_ro(cwd, "log", "--format=%H %cI", "--", rel)
    if rc != 0:
        return []
    rows = []
    for line in out.splitlines():
        commit, _, date = line.partition(" ")
        rc, blob, _ = _git_ro(cwd, "rev-parse", "--verify", "-q",
                              f"{commit}:{rel}")
        if rc == 0 and blob:
            rows.append((commit, date, blob))
    return rows


def _shipped_files(builtin_root: str) -> list:
    out = []
    for base, _dirs, files in os.walk(builtin_root):
        for name in files:
            if name.endswith(".j2"):
                out.append(os.path.relpath(os.path.join(base, name),
                                           builtin_root).replace(os.sep, "/"))
    return sorted(out)


def seed_status(repo: str, builtin_root: str = "") -> dict:
    """Classify every seeded template in *repo* against the shipped one.

    **Read-only, and needs no record that does not already exist.** Git holds
    both histories: the application's (every shipped version of each file)
    and the network's (every version its copy has been). For each file:

    * ``current`` -- the network copy IS today's shipped file;
    * ``stale`` -- it is an OLDER shipped version, unedited: the shipped fix
      has not reached this network;
    * ``edited`` -- it matches no shipped version, and the shipped file has
      not moved since the version it was last in step with. Deliberate local
      change; nothing to do;
    * ``edited_and_stale`` -- edited here AND the shipped file moved since:
      a merge a person has to make.

    Where history cannot answer, the file is ``unclassified`` with the
    reason, never guessed into one of the four.
    """
    builtin_root = builtin_root or BUILTIN_ROOT
    rc, app_root, err = _git_ro(builtin_root, "rev-parse", "--show-toplevel")
    report = {"ok": True, "reason": "", "files": [], "unclassified": []}
    if rc != 0:
        report.update(ok=False, reason=(
            "the application is not a git checkout, so no shipped version "
            f"but today's is known: {err or 'no repository'}"))
    tdir = templates_dir(repo)

    for rel in _shipped_files(builtin_root):
        shipped_path = os.path.join(builtin_root, rel)
        net_path = os.path.join(tdir, rel)
        entry = {"path": rel}
        if not os.path.exists(net_path):
            report["unclassified"].append({**entry, "state": "absent",
                "reason": "not seeded into this network yet; the Templates "
                          "tab seeds missing files when it loads"})
            continue
        shipped_now = _blob_of_file(shipped_path)
        mine = _blob_of_file(net_path)
        if mine and mine == shipped_now:
            report["files"].append({**entry, "state": "current"})
            continue
        if not report["ok"]:
            report["unclassified"].append({**entry,
                "state": "no_shipped_history", "reason": report["reason"]})
            continue
        app_rel = os.path.relpath(shipped_path, app_root).replace(os.sep, "/")
        shipped = {}
        for commit, date, blob in _history(app_root, app_rel):
            shipped.setdefault(blob, (commit, date))   # newest commit wins
        if mine in shipped:
            commit, date = shipped[mine]
            report["files"].append({**entry, "state": "stale",
                "detail": f"this network has the shipped version of "
                          f"{commit[:8]} ({date}); the shipped file has "
                          "changed since and the change has not reached it"})
            continue
        base = next(((c, d, b) for c, d, b in
                     _history(repo, f"templates/{rel}") if b in shipped), None)
        if base is None:
            report["unclassified"].append({**entry, "state": "no_common_base",
                "reason": "no version of this network's copy ever equalled a "
                          "shipped version, so whether the shipped file moved "
                          "since cannot be said"})
            continue
        s_commit, s_date = shipped[base[2]]
        if base[2] == shipped_now:
            report["files"].append({**entry, "state": "edited",
                "detail": f"changed here (last in step with shipped "
                          f"{s_commit[:8]}); the shipped file has not moved "
                          "since -- a deliberate local change, nothing to do"})
        else:
            report["files"].append({**entry, "state": "edited_and_stale",
                "detail": f"changed here since it matched shipped "
                          f"{s_commit[:8]} ({s_date}), AND the shipped file "
                          "has changed since then -- a person has to merge"})

    report["unclassified"].append({
        "path": BINDINGS_FILE, "state": "not_classified",
        "reason": "seeded from a code constant (DEFAULT_BINDINGS), not a "
                  "file, and bindings are per-network by design"})
    return report
