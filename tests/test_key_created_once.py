"""The key file is created ONCE across processes (CONCURRENCY_AUDIT R30; 2026-10-04).

`key.key` opens every secret in the store. Both of its producers (`device.load_key()` at
import, `secrets_store._get_fernet()`) checked whether it existed and then created it with a
truncating write. On a fresh store, processes starting together each found no key, each wrote
its own, and the last writer won: whatever an earlier one had already encrypted could never be
opened again. A process reading mid-write saw a truncated key. Found by the gate on
2026-10-04: three processes importing `modules.device` on a fresh store, one dying on "Fernet
key must be 32 url-safe base64-encoded bytes".

Now one helper (`config.read_or_create_key`) writes the key whole to an owner-only temporary
file and links it into place, which fails when a key exists. Driven with real child processes
released together on a fresh folder, several rounds.
"""

import os
import stat
import subprocess
import sys
import time

from cryptography.fernet import Fernet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHILDREN = 8
ROUNDS = 6

CHILD = '''
import sys, time
sys.path.insert(0, {root!r})
from cryptography.fernet import Fernet
from modules.config import read_or_create_key
start = float(sys.argv[2])
while time.time() < start:
    pass
print(read_or_create_key(sys.argv[1], Fernet.generate_key).decode())
'''


def _race(folder) -> list:
    path = os.path.join(str(folder), "data", "key.key")
    start = repr(time.time() + 1.5)
    procs = [subprocess.Popen([sys.executable, "-c", CHILD.format(root=ROOT), path, start],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(CHILDREN)]
    keys = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err[-500:]
        keys.append(out.strip())
    return path, keys


def test_processes_starting_together_all_get_the_one_key_on_disk(tmp_path):
    for n in range(ROUNDS):
        path, keys = _race(tmp_path / f"round{n}")
        on_disk = open(path, encoding="ascii").read()
        assert set(keys) == {on_disk}, (
            f"round {n}: {len(set(keys))} different keys among {CHILDREN} processes")
        Fernet(on_disk.encode())                       # a whole, valid key
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert sorted(os.listdir(os.path.dirname(path))) == ["key.key"], \
            "a temporary key was left beside it"


def test_an_existing_key_is_read_never_replaced_and_its_mode_tightened(tmp_path):
    from modules.config import read_or_create_key

    path = tmp_path / "key.key"
    key = Fernet.generate_key()
    path.write_bytes(key)
    os.chmod(path, 0o644)
    assert read_or_create_key(str(path), Fernet.generate_key) == key
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_both_producers_go_through_the_one_helper():
    import ast

    for rel, fn in (("modules/device.py", "load_key"),
                    ("modules/secrets_store.py", "_get_fernet")):
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == fn)
        calls = {getattr(c.func, "id", getattr(c.func, "attr", ""))
                 for c in ast.walk(node) if isinstance(c, ast.Call)}
        assert "read_or_create_key" in calls, f"{rel} {fn} creates the key itself"
        assert "open_secure" not in calls, f"{rel} {fn} writes a key file itself"
    # The session key, assigned at app.py's top level.
    tree = ast.parse(open(os.path.join(ROOT, "app.py"), encoding="utf-8").read())
    assigned = [n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "attr", "") == "secret_key" for t in n.targets)]
    assert len(assigned) == 1 and isinstance(assigned[0], ast.Call) and \
        getattr(assigned[0].func, "id", "") == "read_or_create_key", \
        "app.py's session key is not created through read_or_create_key"
