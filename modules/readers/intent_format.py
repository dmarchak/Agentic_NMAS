"""Does every network's committed intent round-trip through Mercury's serialiser? A reader job
(C1693, the operator's order (b) of 2026-10-27).

**What it answers.** A device whose committed `host_vars/<device>.yml` is not Mercury's own
serialisation of itself (``hostvars.round_trips``: a hand edit's comments, an indented list,
other quoting) cannot be patched: Change it in words and bulk intent refuse it as
hand-formatted. Four of the lab's twelve devices were such when this was measured
(2026-10-27). Every intent write path saves in the canonical format since C1693, so a new one
arrives only from before then, or from a file written outside Mercury and committed; this
finds each, and Needs attention names it with Normalise as its action, until a normalising
commit clears it.

**Its population is what each network's repository HOLDS at HEAD**, every `host_vars/*.yml`
`git ls-tree` lists, never a list's inventory: an intent file whose device left the inventory
is still committed intent.

**Why a reader, and its cost.** Needs attention cannot read every device's document per
request (CLAUDE.md, enterprise scale). Each cycle asks each network's repository one
`git ls-tree HEAD host_vars/` and reads only the blobs it has not judged before: a blob's text
never changes, so its verdict is kept by its sha, and a cycle in which nothing was committed
reads no document at all. Reads git, never a working file (C104).
"""

from modules import reader_job

NAME = "intent-format"
INTERVAL_SECONDS = 300


def _repo_for(list_name: str) -> str:
    import os

    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def judge(repo: str, known: dict = None) -> dict:
    """``{"head", "blobs": {blob: round_trips}, "files": [{"device", "blob"}], "hand":
    [device], "read": n}`` for *repo*'s committed intent at HEAD; *known* is the previous
    cycle's ``blobs``, whose verdicts are kept. Raises when git cannot answer, so the failure
    is a job-health row, never an empty list."""
    from modules.nsot import hostvars
    from modules.nsot.repo import git, git_raw

    rc, head, err = git(repo, "rev-parse", "HEAD")
    if rc != 0:
        raise RuntimeError(f"git rev-parse HEAD failed in {repo}: {err or rc}")
    rc, listing, err = git(repo, "ls-tree", "HEAD", f"{hostvars.COMMITTED_REL}/")
    if rc != 0:
        raise RuntimeError(f"git ls-tree HEAD host_vars/ failed in {repo}: {err or rc}")
    known, blobs, files, read = dict(known or {}), {}, [], 0
    for line in listing.splitlines():
        meta, _tab, path = line.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "blob" or not path.endswith(".yml"):
            continue
        blob, device = parts[2], path.rsplit("/", 1)[-1][:-4]
        if blob not in known:
            rc, text, err = git_raw(repo, "cat-file", "blob", blob)
            if rc != 0:
                raise RuntimeError(f"git cat-file {blob[:12]} ({path}) failed: {err or rc}")
            known[blob] = hostvars.round_trips(text)
            read += 1
        blobs[blob] = known[blob]
        files.append({"device": device, "blob": blob})
    return {"head": head.strip(), "blobs": blobs, "files": files, "read": read,
            "hand": sorted(f["device"] for f in files if not blobs[f["blob"]])}


def read(lists=None, previous=None) -> dict:
    """``{"lists": {name: judge(...) or {"error"}}}`` for every registered network."""
    from modules.device import get_device_lists

    names = lists if lists is not None else [d["name"] for d in get_device_lists()]
    if not names:
        raise ValueError("no device lists are registered, so no intent can be judged")
    if previous is None:
        got = reader_job.read_cached(NAME)
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    out = {}
    for name in names:
        before = (previous.get("lists") or {}).get(name) or {}
        try:
            out[name] = judge(_repo_for(name), before.get("blobs"))
        except Exception as exc:                     # noqa: BLE001 - said per network
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return {"lists": out}


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="whether each network's committed intent round-trips through Mercury's serialiser, "
         "so a patch (Change it in words, bulk intent) can change it",
    endpoints=("each list's config repository: HEAD, git ls-tree HEAD host_vars/, and each "
               "intent blob not judged before",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the answer moves only when intent is committed, which wakes it at once "
                    "(reader_wakes); a cycle with no commit costs one ls-tree per network and "
                    "reads no document (a blob's verdict is kept by its sha), so five minutes "
                    "keeps a commit made outside Mercury from waiting long"),
    read=read,
    invalidates=("intent",),
    remedy="Read the error above: it names the network and what git answered",
    window="each network's repository at HEAD, at the read",
))
