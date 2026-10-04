"""The device-list registry across processes (CONCURRENCY_AUDIT R3, its store half; 2026-10-04).

R3: `device_lists.json` (the lists and the server-wide `current_list`) was truncated in place
with no lock. A read during a write saw a torn file, which `get_current_list_name()` maps to
"Default", so the next derived write landed in another list; two mutations at once erased
each other. Now each mutation (switch, create, delete, rename) holds the registry's lock
across processes from its read to its write, and the file is replaced atomically.

Not this half: the active list being per session (each person's own), which reaches v1 routes
and their JavaScript and is a decision recorded on R3.

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
device.set_current_device_list("Alpha")
'''

SWITCHER = '''
import sys
sys.path.insert(0, {root!r})
from modules import device
for i in range(400):
    device.set_current_device_list("Alpha" if i % 2 else "Bravo")
'''

READER = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.config import get_current_list_name
seen = set()
deadline = time.time() + 60
while time.time() < deadline:
    seen.add(get_current_list_name())
    if len(seen) > 2 or open(sys.argv[1]).read() == "done":
        break
print(",".join(sorted(seen)))
'''

CREATOR = '''
import sys
sys.path.insert(0, {root!r})
from modules import device
who = sys.argv[1]
for i in range(8):
    ok, msg = device.create_device_list(f"{{who}}{{i}}")
    assert ok, msg
'''


def _run(tmp_path, body, *args, env):
    script = tmp_path / f"s{abs(hash(body)) % 10_000}.py"
    script.write_text(body.format(root=ROOT))
    return subprocess.Popen([sys.executable, str(script), *args], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _env(tmp_path):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    return dict(os.environ, NMAS_DATA_DIR=str(data))


def test_a_reader_never_sees_a_torn_registry_while_another_process_switches(tmp_path):
    env = _env(tmp_path)
    p = _run(tmp_path, SETUP, env=env)
    _o, err = p.communicate(timeout=60)
    assert p.returncode == 0, err[-500:]
    flag = tmp_path / "flag"
    flag.write_text("")
    reader = _run(tmp_path, READER, str(flag), env=env)
    switcher = _run(tmp_path, SWITCHER, env=env)
    _o, err = switcher.communicate(timeout=120)
    assert switcher.returncode == 0, err[-500:]
    flag.write_text("done")
    out, err = reader.communicate(timeout=120)
    assert reader.returncode == 0, err[-500:]
    assert set(out.strip().split(",")) <= {"Alpha", "Bravo"}, (
        f"the reader saw {out.strip()}: a torn read answered as another list")


def test_three_processes_creating_lists_at_once_lose_none(tmp_path):
    env = _env(tmp_path)
    procs = [_run(tmp_path, CREATOR, who, env=env) for who in ("a", "b", "c")]
    for p in procs:
        _o, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-500:]
    check = subprocess.run([sys.executable, "-c", (
        f"import sys; sys.path.insert(0, {ROOT!r}); from modules import device; "
        "import json; print(json.dumps(sorted(device._load_device_lists_config()['lists'])))")],
        env=env, capture_output=True, text=True, timeout=60)
    names = set(json.loads(check.stdout))
    assert {f"{w}{i}" for w in "abc" for i in range(8)} <= names, sorted(names)
