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

WHAT FAILS THE RUN, AND WHAT IS ONLY NAMED (C519, the operator, 2026-10-06: two gate runs were
refused over the person's own activity, a `.deb` downloaded and LibreOffice's lock beside an
open document). A file in a shared folder carries no record of its writer, so attribution is by
ROUTE: the suite reaches the download folder by two routes only, and each is closed apart from
this watch. A browser session saves into its own folder (`tests/browser.py`; proven each run by
test_credentials_v2's export, which waits for its file THERE), and no code outside this guard
and `tests/browser.py` names the download folder (`test_home_untouched`'s scan, which fails a
planted one). So:
- this run's own session folders, new or left behind, FAIL the run (their names carry the run's
  id, so they are the run's by construction);
- a new file in the download folder is NAMED in the run's summary and does not fail it: neither
  route could have written it, so it is the person's;
- a desktop program's transient file (`TRANSIENT`: an office lock, a browser's partial download,
  an editor's swap or backup) is not even named: it is never a finished file anything writes.
"""
import os
import re
import tempfile

#: This run's id, set by the process that starts the run and inherited by its xdist workers:
#: the gate runs three shards AT ONCE, so a shard must judge only its own sessions' folders.
RUN_ENV = "NMAS_TEST_RUN"


def run_id() -> str:
    return os.environ.setdefault(RUN_ENV, str(os.getpid()))


def start_run(is_worker: bool) -> str:
    """This session's id: a NEW one for every pytest session, inherited only by its own xdist
    workers. *is_worker* comes from the session's config (`workerinput`), never from the
    environment: a pytest a test starts inherits `PYTEST_XDIST_WORKER` from the worker that
    started it, took itself for a worker and kept its parent's id, and so judged the folders
    the parent's other workers were using as left behind (C395, twice: test_network_guard's
    child, then test_harness_isolation's, 2026-10-03)."""
    if not is_worker:
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


#: Files a desktop program makes beside a person's work and removes again (C519), by name: an
#: office suite's lock beside an open document, a browser's download in progress, an editor's
#: swap, lock, autosave or backup, GLib's atomic-write temporary. Never a finished file.
TRANSIENT = (
    re.compile(r"\.~lock\..*#"),                       # LibreOffice
    re.compile(r".+\.(part|crdownload|download)"),     # Firefox, Chromium, Safari-style partials
    re.compile(r"\..+\.sw[a-p]"),                      # vim
    re.compile(r"\.#.+|#.+#"),                         # emacs
    re.compile(r".+~"),                                # an editor's backup
    re.compile(r"\.goutputstream-.+"),                 # GLib
)


def is_transient(name: str) -> bool:
    return any(p.fullmatch(name) for p in TRANSIENT)


def new_entries(before: dict, after: dict, kind: str = "") -> list:
    """Each path in *after* that was not in *before* (only *kind*'s folders, when given)."""
    found = []
    for key, names in after.items():
        if kind and key[0] != kind:
            continue
        was = before.get(key)
        if names is None:
            continue
        if was is None and key[0] == "downloads":
            found.append(key[1])               # the folder itself was made
            continue
        found += [os.path.join(key[1], n) for n in names if n not in (was or [])]
    return found


def judge(before: dict, after: dict, left_behind=()) -> str:
    """'' when the run left nothing of its own, else the message that fails the run: this run's
    session folders, new or left behind (C391, C392). The download folder is `noted`, never
    judged here (C519)."""
    new = new_entries(before, after, "sessions")
    left = [p for p in left_behind if p not in new]
    if not new and not left:
        return ""
    return ("the run left files outside its own temporary folders (C391, C392): "
            + "; ".join(new + left)
            + ". A browser session keeps its downloads and profile in its own folder "
              "(tests/browser.py).")


def noted(before: dict, after: dict) -> str:
    """'' or the line naming what appeared in the person's download folder during the run, not
    counting a desktop program's transient files. Named, never failing the run (C519): the
    suite reaches that folder by no route (the module's docstring)."""
    new = [p for p in new_entries(before, after, "downloads")
           if not is_transient(os.path.basename(p))]
    if not new:
        return ""
    return ("NOTE: new in the download folder during the run, and not the suite's (its browser "
            "sessions save in their own folders, and no code names this one): " + "; ".join(new))
