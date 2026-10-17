"""The device-list registry across processes (CONCURRENCY_AUDIT R3, its store half; 2026-10-04).

R3: `device_lists.json` (the lists and the server-wide `current_list`) was truncated in place
with no lock. A read during a write saw a torn file, which `get_current_list_name()` maps to
"Default", so the next derived write landed in another list; two mutations at once erased
each other. Now each mutation (create, delete) holds the registry's lock across processes from
its read to its write, and the file is replaced atomically.

The switch left at 7.8 (2026-10-17, P7-26): the installation's active list is FROZEN, set by
nothing, and each person's network is their own choice (`network_choice`, the top bar's Network
▾). So the reader is now held beside a process creating and deleting networks, each a rewrite of
the whole registry, and must read the frozen list every time: a torn read answers "Default".

Driven with real child processes on a temporary data folder.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETUP = '''
import sys
sys.path.insert(0, {root!r})
from modules import device
for name in ("Alpha", "Bravo"):
    ok, msg = device.create_device_list(name)
    assert ok, msg
# The frozen list, as a host switched before the freeze holds it: nothing in the product sets it.
config = device._load_device_lists_config()
config["current_list"] = "Alpha"
device._save_device_lists_config(config)
'''

MUTATOR = '''
import sys
sys.path.insert(0, {root!r})
from modules import device
for i in range(60):
    ok, msg = device.create_device_list(f"Churn{{i}}")
    assert ok, msg
    ok, msg = device.delete_device_list(f"Churn{{i}}")
    assert ok, msg
print("rewrote", 2 * (i + 1))
'''

READER = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.config import get_current_list_name
seen, reads = set(), 0
deadline = time.time() + 60
while time.time() < deadline:
    seen.add(get_current_list_name())
    reads += 1
    if len(seen) > 1 or open(sys.argv[1]).read() == "done":
        break
print(",".join(sorted(seen)), reads)
'''

CREATOR = '''
import sys
sys.path.insert(0, {root!r})
from modules import device
who = sys.argv[1]
for i in range(8):
    ok, msg = device.create_device_list(f"{{who}}{{i}}")
    assert ok, msg
print("created", i + 1)
'''


def _run(tmp_path, body, *args, env):
    # ONE FILE PER CHILD (C527, CI #475): the three creators shared one script file, each start
    # rewriting it while an earlier child could still be reading it; a child that read it
    # truncated ran nothing and exited 0, and its lists were "lost".
    script = tmp_path / f"s{abs(hash(body)) % 10_000}-{len(list(tmp_path.glob('s*.py')))}.py"
    script.write_text(body.format(root=ROOT))
    return subprocess.Popen([sys.executable, str(script), *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _env(tmp_path):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    return dict(os.environ, NMAS_DATA_DIR=str(data))


def test_the_frozen_list_reads_whole_while_another_process_creates_and_deletes(tmp_path):
    env = _env(tmp_path)
    p = _run(tmp_path, SETUP, env=env)
    _o, err = p.communicate(timeout=60)
    assert p.returncode == 0, err[-500:]
    flag = tmp_path / "flag"
    flag.write_text("")
    reader = _run(tmp_path, READER, str(flag), env=env)
    mutator = _run(tmp_path, MUTATOR, env=env)
    out, err = mutator.communicate(timeout=120)
    assert mutator.returncode == 0, err[-500:]
    assert out.strip() == "rewrote 120", (out, err[-500:])    # it ran, all of it
    flag.write_text("done")
    out, err = reader.communicate(timeout=120)
    assert reader.returncode == 0, err[-500:]
    seen, reads = out.split()
    assert int(reads) > 100, f"the reader read {reads} times: too few to have met a write"
    assert seen == "Alpha", (
        f"the reader saw {seen}: a torn read answered as another list than the frozen one")


def test_three_processes_creating_lists_at_once_lose_none(tmp_path):
    env = _env(tmp_path)
    procs = [_run(tmp_path, CREATOR, who, env=env) for who in ("a", "b", "c")]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-500:]
        assert out.strip() == "created 8", (out, err[-500:])   # it ran, all of it
    check = subprocess.run([sys.executable, "-c", (
        f"import sys; sys.path.insert(0, {ROOT!r}); from modules import device; "
        "import json; print(json.dumps(sorted(device._load_device_lists_config()['lists'])))")],
        env=env, capture_output=True, text=True, timeout=60)
    names = set(json.loads(check.stdout))
    assert {f"{w}{i}" for w in "abc" for i in range(8)} <= names, sorted(names)
