"""Two ZTP onboardings at once lose no Kea reservation (CONCURRENCY_AUDIT R22; 2026-10-04).

`write_reservations` read the fragment, built a candidate, tested, replaced, reloaded and read
back, with no lock. The later replace dropped the earlier device's reservation; if the earlier
run's read-back came first it reported success, and its device later got no address. A failed
reload restored `previous_text` over another writer's fragment.

Now the whole write, from the read to the read-back, holds one lock across processes, kept
in the app's data folder (never beside the fragment, under /etc/kea). Driven with two real
processes, each writing 15 reservations one at a time against the fake Kea of
`test_ztp_reservations`, reading the fragment as the one shared server does.
"""

import json
import os
import subprocess
import sys

from tests.test_ztp_reservations import site  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WRITER = '''
import sys
sys.path.insert(0, {root!r})
from tests.test_ztp_reservations import FakeKea, _accepting_test, _entry
from modules.nsot import ztp

class SharedKea(FakeKea):
    """One server for every process: its running reservations are the fragment as last
    reloaded, which under the writers' lock is the file."""
    def command(self, command, service=None):
        if command == "config-get":
            self._load()
        return super().command(command, service)

fragment, main, who = sys.argv[1], sys.argv[2], int(sys.argv[3])
failed = []
for i in range(15):
    mac = f"aa:bb:cc:00:{{who:02x}}:{{i:02x}}"
    entry = _entry(mac=mac, addr=f"192.0.2.{{100 + who * 20 + i}}", host=f"z{{who}}-{{i}}")
    out = ztp.write_reservations([entry], kea=SharedKea(fragment), fragment=fragment,
                                 main_config=main, run_test=_accepting_test)
    if not out["ok"]:
        failed.append(out["error"])
print(len(failed), failed[:1])
'''


def test_two_onboardings_at_once_lose_no_reservation(site):  # noqa: F811
    fragment, main = site
    procs = [subprocess.Popen([sys.executable, "-c", WRITER.format(root=ROOT), fragment, main,
                               str(who)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, cwd=ROOT)
             for who in (1, 2)]
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err[-800:]
        assert out.startswith("0 "), f"a writer reported failures: {out.strip()}"
    with open(fragment, encoding="utf-8") as fh:
        macs = {r["hw-address"] for r in json.load(fh)}
    want = {f"aa:bb:cc:00:{who:02x}:{i:02x}" for who in (1, 2) for i in range(15)}
    assert want <= macs, f"lost {len(want - macs)} reservation(s)"


def test_the_lock_is_in_the_apps_data_never_beside_the_fragment(site):  # noqa: F811
    from modules import config
    from modules.nsot import ztp

    lock = ztp.fragment_lock(site[0])
    assert lock.path().startswith(os.path.abspath(config.DATA_DIR))
    assert os.path.dirname(lock.path()) != os.path.dirname(site[0])
