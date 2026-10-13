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
        # The guarded producer (C729): never a key for a store something was sealed in.
        assert "read_or_create_fernet_key" in calls, f"{rel} {fn} creates the key itself"
        assert "open_secure" not in calls, f"{rel} {fn} writes a key file itself"
    # The session key, assigned at app.py's top level.
    tree = ast.parse(open(os.path.join(ROOT, "app.py"), encoding="utf-8").read())
    assigned = [n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(getattr(t, "attr", "") == "secret_key" for t in n.targets)]
    assert len(assigned) == 1 and isinstance(assigned[0], ast.Call) and \
        getattr(assigned[0].func, "id", "") == "read_or_create_key", \
        "app.py's session key is not created through read_or_create_key"


class TestNoKeyIsMadeForASealedStore:
    """C729 (the operator, 2026-10-13: "I'd rather the backup never holds both halves"): the key
    moves off the backed-up disk, so a store can come back without it. A new key then would
    open none of the old values, and an unopenable value reads as "": the store would look
    empty, not locked. The key is made only for a store nothing was sealed in."""

    def _make(self, data):
        from modules.config import key_creation_refusal, read_or_create_key
        path = data / "key.key"
        return path, lambda: read_or_create_key(str(path), Fernet.generate_key,
                                                refuse=key_creation_refusal)

    def test_a_fresh_store_gets_its_key(self, tmp_path):
        path, make = self._make(tmp_path)
        Fernet(make())
        assert path.exists()

    def test_sealed_settings_refuse_naming_the_store_and_the_count(self, tmp_path):
        import json
        import pytest
        from modules.config import KeyRefused
        (tmp_path / "user_settings.json").write_text(json.dumps(
            {"a": "enc:v1:gAAAA-one", "b": {"c": "enc:v1:gAAAA-two"}, "d": "plain"}))
        path, make = self._make(tmp_path)
        with pytest.raises(KeyRefused) as got:
            make()
        assert "2 encrypted value(s) in user_settings.json" in str(got.value), got.value
        assert "nmas-breakglass restore-key" in str(got.value)
        assert not path.exists() and not list(tmp_path.glob(".key-*"))   # nothing written

    def test_a_sealed_device_list_refuses(self, tmp_path):
        import pytest
        from modules.config import KeyRefused
        (tmp_path / "lists" / "default").mkdir(parents=True)
        (tmp_path / "lists" / "default" / "devices.csv").write_text(
            "hostname,ip,username,password,secret\nr1,192.0.2.1,u,gAAAA-token,\n")
        with pytest.raises(KeyRefused, match=r"1 encrypted value\(s\) in lists/default/devices"):
            self._make(tmp_path)[1]()

    def test_a_link_to_a_key_that_is_not_there_refuses_naming_its_target(self, tmp_path):
        """The key on its own disk, linked from data/: a disk that did not mount."""
        import pytest
        from modules.config import KeyRefused
        path, make = self._make(tmp_path)
        os.symlink(str(tmp_path / "keydisk" / "key.key"), str(path))
        with pytest.raises(KeyRefused, match="is a link to .*keydisk/key.key, which does not"):
            make()
        assert os.path.islink(path) and not (tmp_path / "keydisk").exists()

    def test_a_link_to_a_key_that_is_there_reads_it(self, tmp_path):
        path, make = self._make(tmp_path)
        (tmp_path / "keydisk").mkdir()
        key = Fernet.generate_key()
        (tmp_path / "keydisk" / "key.key").write_bytes(key)
        os.symlink(str(tmp_path / "keydisk" / "key.key"), str(path))
        assert make() == key

    def test_an_unreadable_store_refuses(self, tmp_path):
        import pytest
        from modules.config import KeyRefused
        (tmp_path / "credential_profiles.json").write_text("{not json")
        with pytest.raises(KeyRefused, match="credential_profiles.json could not be read"):
            self._make(tmp_path)[1]()
