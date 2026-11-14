"""Which devices hold the read-only account, at which level, and what its last probe said: a
reader job (board R, Credentials › Profiles › Read-only account; provisional, operator review
pending).

**What it answers.** Per device of every network: the account its profiles give it, what its
committed intent says of it, what its committed golden holds (the device as last captured) and
its newest probe record (`modules/nsot/read_account.py`, `judge`). Never a password.

**Why a reader, and its cost.** The answer reads every device's committed intent and golden,
per-device work no page request does (CLAUDE.md, "No page load or badge poll waits on Grafana, Loki, NetBox, a device
or a computation"). Each cycle asks each
network's repository for its committed intent in two git calls (`neighbours.committed_intents`)
and one `git ls-tree HEAD golden/`, and reads a golden (`repo.committed_golden_for`) only when
its blob is new: a blob's text never changes, so its summary is kept by its sha, and a cycle in
which nothing was committed reads no golden. The probe folder is listed once and only each
device's newest record is read. Reads git, never a working file (C104).
"""

from modules import reader_job

NAME = "read-account-coverage"
INTERVAL_SECONDS = 300


def read(previous=None) -> dict:
    """The value (`read_account.read_coverage`), its golden summaries kept from the previous
    cycle by blob."""
    from modules.nsot import read_account

    if previous is None:
        got = reader_job.read_cached(NAME)
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    return read_account.read_coverage(previous)


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="which devices hold the read-only account, at which level, by their committed intent "
         "and golden, and what each one's newest probe record said (Credentials › Profiles)",
    endpoints=("each list's config repository: committed host_vars at HEAD, git ls-tree HEAD "
               "golden/, and each golden blob not summarised before",
               "the credential store's read-only account names (never a value)",
               "the read-only account probe's records (data/probes/read-account/)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the answer moves when intent or a golden is committed, the inventory or a "
                    "credential changes, which wake it at once (reader_wakes); a probe record "
                    "is written by the probe outside Mercury's operations, so five minutes keeps "
                    "a new record from waiting long; a cycle with no commit reads no golden"),
    read=read,
    invalidates=("read_account",),
    remedy="Read the error above: it names the network and what git answered",
    window="each network's repository at HEAD and the newest probe record per device, at the "
           "read",
))
