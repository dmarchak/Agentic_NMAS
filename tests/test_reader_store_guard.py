"""C1522: no test leaves a reader's stored value behind (the operator, 2026-10-21).

`test_v2_brand` failed in a gate and passed alone: `test_live_redraw_keeps_form` had left
`topology-graph` in the session's data directory, so a later test in its worker drew Mercury's
own map node, and its `<title>`, into a fragment that has none. tests/conftest.py's
`_no_test_leaves_a_reader_store` now puts back anything a test leaves under `readers/` and
fails that test naming each store (a silent reset would hide the next leaker); its module twin
does the same for a module's fixtures.

The control, run for real: a leaking test, in a child pytest under this suite's own conftest,
fails naming itself and `topology-graph.json`, and the test after it finds the store gone.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEAKER = '''
import json
import os


def test_writes_topology_graph_and_leaves_it():
    from modules import reader_job
    path = reader_job.store_path("topology-graph")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_attempt": {"at": "2026-10-21T19:00:00Z", "ok": True}}, fh)


def test_the_next_test_finds_no_topology_graph():
    from modules import reader_job
    assert not os.path.exists(reader_job.store_path("topology-graph"))


def test_one_that_keeps_its_store_in_its_own_folder_passes(reader_stores_in_tmp):
    from modules import reader_job
    path = reader_job.store_path("topology-graph")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{}")
    assert path.startswith(str(reader_stores_in_tmp))
'''


def test_a_leaking_test_fails_naming_itself_and_the_store(tmp_path):
    leaker = tmp_path / "test_c1522_leaker.py"
    leaker.write_text(LEAKER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "NMAS_DATA_DIR"}
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly",
         "-p", "tests.conftest", "--rootdir", ROOT, str(leaker)],
        cwd=ROOT, capture_output=True, text=True, timeout=180, env=env)
    text = out.stdout + out.stderr
    assert out.returncode != 0, text
    assert ("test_writes_topology_graph_and_leaves_it left reader store(s) behind" in text
            and "topology-graph.json. They are put back" in text), text
    assert "3 passed, 1 error" in text, text
