"""Deleting a list never removes it under a running operation (CONCURRENCY_AUDIT R38; 2026-10-04).

`delete_device_list` ran `shutil.rmtree` on the list's folder, and the route checked NetBox
records and credential dependents, never a device hold or a running drift run. A second
person's deploy, restore, capture or commit on that list then wrote into a repository and
stores that no longer existed, or half existed while the tree was being removed.

Now the delete refuses, naming each, while any device of the list is held or its drift run is
in progress, by any process. It checks again under the list's repository lock, which every
commit on the list takes, and removes the folder inside that lock. Driven with real child
processes on a temporary data folder: one holds a device or a drift run, another deletes.
"""

import ast
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETUP = '''
import sys, os
sys.path.insert(0, {root!r})
from modules import device
for name in ("Alpha", "Bravo"):
    ok, msg = device.create_device_list(name)
    assert ok, msg
slug = device._load_device_lists_config()["lists"]["Bravo"]
print(os.path.join(device.LISTS_DIR, slug))
'''

DELETE = '''
import json, sys
sys.path.insert(0, {root!r})
from modules import device
ok, msg = device.delete_device_list("Bravo")
print(json.dumps({{"ok": ok, "msg": msg,
                   "listed": "Bravo" in device._load_device_lists_config()["lists"]}}))
'''

HOLDER = '''
import sys
sys.path.insert(0, {root!r})
from modules.nsot import device_ops
device_ops.acquire("Bravo", "r9", "deploy", "operator@example.invalid")
print("held", flush=True)
sys.stdin.readline()
device_ops.release("Bravo", "r9")
'''

DRIFTER = '''
import sys
sys.path.insert(0, {root!r})
from modules import drift_check
with drift_check._OneRun(drift_check._run_lock_path("Bravo"), "test"):
    print("held", flush=True)
    sys.stdin.readline()
'''


@pytest.fixture
def world(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    env = dict(os.environ, NMAS_DATA_DIR=str(data))
    folder = _run(SETUP, env).strip()
    assert os.path.isdir(folder), folder
    return env, folder


def _run(script, env) -> str:
    out = subprocess.run([sys.executable, "-c", script.format(root=ROOT)], env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout


def _delete(env) -> dict:
    return json.loads(_run(DELETE, env))


def _holding(script, env):
    p = subprocess.Popen([sys.executable, "-c", script.format(root=ROOT)], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def _let_go(p):
    p.communicate("\n", timeout=30)
    assert p.returncode == 0


def test_a_held_device_refuses_the_delete_naming_it(world):
    env, folder = world
    p = _holding(HOLDER, env)
    try:
        got = _delete(env)
    finally:
        _let_go(p)
    assert got["ok"] is False, got
    assert "r9" in got["msg"] and "deploy" in got["msg"] and "Nothing was changed" in got["msg"]
    assert got["listed"] and os.path.isdir(folder)
    got = _delete(env)                                   # released: the delete goes ahead
    assert got["ok"] is True and not got["listed"], got
    assert not os.path.exists(folder)


def test_a_running_drift_run_refuses_the_delete(world):
    env, folder = world
    p = _holding(DRIFTER, env)
    try:
        got = _delete(env)
    finally:
        _let_go(p)
    assert got["ok"] is False and "drift run" in got["msg"], got
    assert os.path.isdir(folder)


def test_the_folder_is_removed_inside_the_lists_repository_lock():
    src = open(os.path.join(ROOT, "modules", "device.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "delete_device_list")
    withs = [w for w in ast.walk(fn) if isinstance(w, ast.With)
             and any("repo_lock" in ast.unparse(i.context_expr) for i in w.items)]
    # The folder leaves inside the lock: moved aside to lists_removed/ since 2026-10-10 (the
    # data survives), erased before that.
    assert any("shutil.move(list_dir" in ast.unparse(s) for w in withs for s in w.body), \
        "the folder is not moved aside inside the list's repository lock"
