"""Can any stored baseline be re-applied? A reader job (the operator,
2026-09-28).

**What it answers.** Every baseline on the host predated a credential
rotation: eleven would change s1's credential (the oldest, all eight
devices'), which the restore's own guard refuses (C75), and the one that did
not was the withdrawn broken state (C177). So the fleet had no usable restore
point, and the Baselines panel said so twelve times, once per row, without
saying it once. A BASELINE'S USEFULNESS DECAYS WITH EVERY CREDENTIAL ROTATION,
and nothing tracked it.

**Why a reader.** The answer is the Baselines panel's per-row credential
check (`restore.baseline_credential_gaps`), and that costs 8 to 9 s on the
host for twelve tags (measured 2026-09-28: git reads per tag per device), so
Needs attention cannot ask it per request (section 0a). It depends only on
the repository: the tags, and HEAD's goldens and intent. So each cycle asks
two cheap questions (HEAD's sha and the tag list) and recomputes only when
either moved; otherwise the stored value stands, still true.

**Usable** means: not withdrawn, and no device whose credential the baseline
would change (``stale`` empty). A device the baseline predates is left as it
is by a re-apply, so it does not make the baseline unusable for the rest.
"""

from modules import reader_job

INTERVAL_SECONDS = 300


def _repo_for(list_name: str) -> str:
    import os

    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def judge(repo: str, list_name: str, baselines: list) -> dict:
    """Newest first, each baseline's credential state and whether it is usable."""
    from modules.nsot.restore import baseline_credential_gaps
    from modules.nsot.repo import devices_at

    rows = []
    for b in baselines:
        if b.get("deleted"):
            continue
        # What its commit recorded it earned, and why withdrawn: History's
        # Baselines tab draws both from this stored value (no read per tag).
        entry = {"tag": b["tag"], "created": b.get("created", ""),
                 "withdrawn": bool(b.get("withdrawn")),
                 "withdrawn_why": (b.get("withdrawn") or {}).get("why", "")
                 if isinstance(b.get("withdrawn"), dict) else "",
                 "decision": b.get("decision", ""), "decision_detail": b.get("decision_detail", ""),
                 "commit": b.get("commit", ""), "stale": [], "guarded": [], "silent": []}
        if not entry["withdrawn"]:
            gaps = baseline_credential_gaps(repo, b["tag"], list_name,
                                            devices_at(repo, b["tag"]))
            entry.update(stale=sorted(gaps["stale"]), guarded=gaps["guarded"],
                         silent=gaps["silent"])
        entry["usable"] = not entry["withdrawn"] and not entry["stale"]
        rows.append(entry)
    usable = next((r["tag"] for r in rows if r["usable"]), "")
    return {"baselines": rows, "usable": usable, "count": len(rows)}


def read(lists=None, previous=None) -> dict:
    from modules.device import get_device_lists
    from modules.nsot.repo import git, list_baselines

    names = lists if lists is not None else [d["name"] for d in get_device_lists()]
    if not names:
        raise ValueError("no device lists are registered, so no baseline can be judged")
    if previous is None:
        got = reader_job.read_cached("baseline-usability")
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    out = {}
    for name in names:
        repo = _repo_for(name)
        try:
            head = git(repo, "rev-parse", "HEAD")[1].strip()
            tags = git(repo, "tag", "--list", "baseline/*")[1].split()
            # "v2": rows carry what each baseline earned (History, 2026-10-02); a
            # stored answer from before is recomputed once.
            key = f"v2|{head}|{','.join(sorted(tags))}"
            before = (previous.get("lists") or {}).get(name) or {}
            if before.get("key") == key and "usable" in before:
                out[name] = before          # nothing moved: the stored answer stands
                continue
            out[name] = {"key": key, "head": head[:12],
                         **judge(repo, name, list_baselines(repo))}
        except Exception as exc:                     # noqa: BLE001
            out[name] = {"error": f"the judgement raised {type(exc).__name__}: {exc}"}
    return {"lists": out}


READER = reader_job.register(reader_job.Reader(
    name="baseline-usability",
    what="whether any stored baseline can be re-applied without changing a held credential",
    endpoints=("each list's config repository: HEAD, the baseline tags, and the goldens "
               "and intent at each tag",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the answer moves only when a commit or a tag does; a cycle with "
                    "neither costs two git reads, and a full judgement 8 to 9 s for twelve "
                    "tags (measured on the host, 2026-09-28), so it is never done per request"),
    read=read,
    invalidates=("baselines",),
    remedy="Read the error above: it names the list and what the judgement raised",
    window="the repository at the read: the tags and HEAD",
))
