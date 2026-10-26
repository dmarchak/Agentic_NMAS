"""What one request for a v2 page costs, per fleet size. Shared by `test_scale.py`.

Separate from the test module so the measurement is a function anybody can call: two
copies of a measurement is how they come to disagree. Until P7-19 (2026-10-15) it rendered
today's index (`/`), which goes at cutover; `scripts/nmas-scale-report` still measures that
page with its own copy (a finding of P7-19).

**Per-device work, measured as what moves with the fleet** (criterion 11, "no per-device
work per request"), for one request after a warm one:

- ``children``: processes started (`git` and anything else), counted at `subprocess.Popen`;
- ``opens``: files opened under the network's folder (a golden, intent, the manifest);
- ``loads``: reads of the inventory (`load_saved_devices`), counted by the caller's loader;
- ``connects``: socket connects (a device session, or any other), counted at the socket;
- ``calls``: function calls made by the REQUEST'S OWN THREAD (Python and builtin, each
  generator resumed counted again, as cProfile counted them), the CPU work no I/O count
  sees: a loop over the whole inventory to draw one device's page reads no file per device
  and still costs one pass per device (measured 2026-10-15 on the device page). Counted by
  `sys.setprofile`, which watches only the thread that sets it. Until 2026-10-25 this was
  `cProfile`'s total, and on Python 3.12 cProfile is built on `sys.monitoring`, which
  counts EVERY thread: measured in CI's interpreter, 102 calls alone and 171,444 beside one
  busy thread. A thread an earlier test in the worker left running (a job, a reader) was
  counted into whichever readings it overlapped, so the `/v2/` pin moved with test order
  (C875: +3.0, -3.3, -1.1, -1.0, -1.2);
- ``bytes``: the answer's size.

Nothing here writes into `data/lists/`: the caller's lab is under a temporary folder.
"""

import builtins
import collections
import os
import socket
import subprocess
import sys
import sysconfig
from unittest import mock


def golden_for(device: dict) -> str:
    """A small, parseable configuration for a fleet device: its hostname and a loopback."""
    _a, _b, c, d = device["ip"].split(".")
    return (f"hostname {device['hostname']}\n!\ninterface Loopback0\n"
            f" ip address 10.{int(c) - 100}.{d}.1 255.255.255.255\n!\nend\n")


def identity_for(device: dict) -> str:
    """A fleet device's manifest identity, in the shape the tool mints (a uuid), fixed and
    in REVERSE fleet order: the manifest is stored sorted by identity, and a lookup by name
    (`manifest.find_by_name`) passes over the entries before the one it finds, so the first
    device's entry, the device page's measured one, comes last and its page pays the whole
    pass (C855). A random uuid put it anywhere, so the measurement moved between runs."""
    return f"00000000-0000-4000-8000-{9999 - int(device['hostname'][-4:]):012d}"


def commit_goldens(list_name: str, devices: list) -> dict:
    """One commit of a golden for each device the fleet does not mark `no_golden`."""
    from modules.nsot.repo import GoldenItem, save_golden

    items = [GoldenItem(d["hostname"], golden_for(d), d["ip"], platform=d["platform"],
                        device_uid=identity_for(d))
             for d in devices if d.get("_scale_state") != "no_golden"]
    out = save_golden(list_name, items, source="onboarding", actor="t", allow_new=True,
                      baseline=False)
    assert out.get("ok"), out
    return out


#: The subprocess functions that wait for a child: each is counted as one call, never the
#: polling inside it (C1562).
WAITS = ("communicate", "wait")


def measure(client, path: str, list_dir: str, loads: dict) -> dict:
    """One request for *path*, after a warm one, and what it cost (the module docstring)."""
    client.get(path)                                   # warm: templates, caches
    counts = {"children": 0, "opens": 0, "connects": 0}
    loads["n"] = 0
    real_init, real_open = subprocess.Popen.__init__, builtins.open
    real_connect = socket.socket.connect
    prefix = os.path.realpath(list_dir) + os.sep

    def popen_init(self, *a, **k):
        counts["children"] += 1
        return real_init(self, *a, **k)

    def counting_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)) and \
                os.path.realpath(os.fspath(file)).startswith(prefix):
            counts["opens"] += 1
        return real_open(file, *a, **k)

    def connect(self, *a, **k):
        counts["connects"] += 1
        return real_connect(self, *a, **k)

    calls = {"n": 0}
    # C1562: the same count by function, so a count that moved names where (`profile_diff`).
    by_func = collections.Counter()
    # C1562's cause (measured 2026-10-26): a child's wait (`communicate`, `wait`) polls in a loop
    # whose length is how long the child takes, about 3,100 of /v2/'s calls for its 9 git
    # children, so the count measured wall-clock time. A wait is one call; its polling is not
    # counted (work, never wall-clock: CLAUDE.md, "Performance tests assert on work or growth").
    waiting = {"frame": None}

    def tally(frame, event, arg):
        if waiting["frame"] is not None:
            if event == "return" and frame is waiting["frame"]:
                waiting["frame"] = None
            return
        if event == "call":
            calls["n"] += 1
            by_func[(frame.f_code.co_filename, frame.f_code.co_name)] += 1
            if frame.f_code.co_name in WAITS and frame.f_code.co_filename == subprocess.__file__:
                waiting["frame"] = frame
        elif event == "c_call":
            calls["n"] += 1
            by_func[("<builtin>", getattr(arg, "__qualname__", repr(arg)))] += 1

    with mock.patch.object(subprocess.Popen, "__init__", popen_init), \
         mock.patch.object(builtins, "open", counting_open), \
         mock.patch.object(socket.socket, "connect", connect):
        before = sys.getprofile()
        sys.setprofile(tally)                         # this thread only (the docstring)
        try:
            r = client.get(path)
        finally:
            sys.setprofile(before)
    assert r.status_code == 200, (path, r.status_code)
    return dict(counts, loads=loads["n"], calls=calls["n"], bytes=len(r.get_data()),
                profile=by_func)


def profile_diff(small: dict, large: dict, top: int = 12) -> str:
    """The functions whose call counts differ most between two `measure` profiles, as
    ``file:function small→large (±n)``, largest difference first (C1562: the calls a count
    gained or lost, named)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep

    def where(key):
        path, name = key
        for cut in (root, "site-packages" + os.sep, sysconfig.get_paths()["stdlib"] + os.sep):
            if cut in path:
                path = path.split(cut, 1)[1]
        return f"{path}:{name}"
    moved = sorted(((small.get(k, 0) - large.get(k, 0), k) for k in set(small) | set(large)),
                   key=lambda d: (-abs(d[0]), where(d[1])))
    return "; ".join(f"{where(k)} {small.get(k, 0)}→{large.get(k, 0)} ({-d:+d})"
                     for d, k in moved[:top] if d)
