"""A test run leaves the person's home untouched (C391, C392; not a test module).

The operator, 2026-10-03: 45 test records in the laptop's Downloads (the export tests' downloads,
Firefox saving to its default), and 442 empty session folders in the snap's directory with a
geckodriver still running for each. `tests/browser.py` now keeps both in a session's own folder;
this is the check that a run proves it, as `store_guard` proves the checkout's data/ untouched.

WHAT IS WATCHED: the person's download folder (XDG_DOWNLOAD_DIR, else `user-dirs.dirs`, else
~/Downloads), every entry; and each folder a browser session may be made in, the entries named
like THIS run's sessions (`nmas-browser-<run>-`, `nmas-upload-<run>-`). Judged once, by the process that ran the
whole session (the xdist controller, or a run without workers), so a session still open in
another worker is never mistaken for one left behind.

WHAT IT CANNOT TELL APART: a file the person downloads during a run is new too, and fails the
run naming it. Refusing by resemblance is safe; the message says so.
"""
import os
import re
import tempfile

#: This run's id, set by the process that starts the run and inherited by its xdist workers:
#: the gate runs three shards AT ONCE, so a shard must judge only its own sessions' folders.
RUN_ENV = "NMAS_TEST_RUN"


def run_id() -> str:
    return os.environ.setdefault(RUN_ENV, str(os.getpid()))


def start_run() -> str:
    """This session's id: a NEW one for every pytest session, inherited only by its own xdist
    workers (`PYTEST_XDIST_WORKER`). A pytest a test starts as a child is its own session:
    sharing its parent's id, it judged the folders the parent's other workers were using as
    left behind (the gate's browser shard, 2026-10-03, test_network_guard's child)."""
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        os.environ[RUN_ENV] = str(os.getpid())
    return run_id()


def session_prefix(kind: str) -> str:
    """The name a folder of this run's starts with (*kind*: browser or upload)."""
    return f"nmas-{kind}-{run_id()}-"


def session_prefixes() -> tuple:
    return (session_prefix("browser"), session_prefix("upload"))


def downloads_dir(env=None, home=None) -> str:
    """The person's download folder, as the desktop names it."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    if env.get("XDG_DOWNLOAD_DIR"):
        return env["XDG_DOWNLOAD_DIR"].replace("$HOME", home)
    try:
        with open(os.path.join(home, ".config", "user-dirs.dirs"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r'\s*XDG_DOWNLOAD_DIR="([^"]+)"', line)
                if m:
                    return m.group(1).replace("$HOME", home)
    except OSError:
        pass
    return os.path.join(home, "Downloads")


def session_parents(home=None) -> list:
    """Every folder `tests/browser.py` may make a session's folder in."""
    home = home or os.path.expanduser("~")
    return [os.path.join(home, "snap", "firefox", "common"), tempfile.gettempdir()]


def _entries(path, prefixes=None) -> list:
    try:
        names = os.listdir(path)
    except OSError:
        return None                        # absent: a folder that APPEARS is a change too
    return sorted(n for n in names if prefixes is None or n.startswith(prefixes))


def snapshot(downloads=None, parents=None) -> dict:
    downloads = downloads_dir() if downloads is None else downloads
    parents = session_parents() if parents is None else parents
    out = {("downloads", downloads): _entries(downloads)}
    for p in parents:
        out[("sessions", p)] = _entries(p, session_prefixes())
    return out


def new_entries(before: dict, after: dict) -> list:
    """Each path in *after* that was not in *before*."""
    found = []
    for key, names in after.items():
        was = before.get(key)
        if names is None:
            continue
        if was is None and key[0] == "downloads":
            found.append(key[1])               # the folder itself was made
            continue
        found += [os.path.join(key[1], n) for n in names if n not in (was or [])]
    return found


def judge(before: dict, after: dict, left_behind=()) -> str:
    """'' when the home is untouched, else the message that fails the run."""
    new = new_entries(before, after)
    left = [p for p in left_behind if p not in new]
    if not new and not left:
        return ""
    return ("the run left files outside its own temporary folders (C391, C392): "
            + "; ".join(new + left)
            + ". A browser session keeps its downloads and profile in its own folder "
              "(tests/browser.py). A file downloaded by hand during the run is named here too.")
