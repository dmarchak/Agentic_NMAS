"""P.8 step 2: a network's settings, and the one resolver (NSOT_P8_DESIGN, sections 2 and 3).

The Default network's layer is the global settings file (decision 1: nothing copied). Another
list keeps its own `settings.json`; a network-scoped key resolves to the list's own value, else
Default's, except that an integration inherits as a GROUP: setting any key of a group makes the
group the list's own, and its other keys read their schema default, never Default's (a list's
own Grafana never receives Default's token). A declaration of "not applicable here" stops the
lookup. Host-wide keys are the global value for every list. Driven on a temporary store, with
real child processes for the concurrent writes.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from modules import config
from modules import list_settings as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary data folder whose global settings set Default's Grafana."""
    from modules.secrets_store import encrypt_value

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"grafana_url": "http://192.0.2.10:3000",
                                    "grafana_token": encrypt_value("default-token"),
                                    "flask_port": 5000}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    return tmp_path


class TestResolving:
    def test_default_is_the_global_file(self, store):
        assert L.resolve("Default", "grafana_url") == ("http://192.0.2.10:3000", L.SET_HERE)
        assert L.resolve("Default", "loki_url")[1] == L.UNSET_EVERYWHERE
        assert L.secret("Default", "grafana_token") == "default-token"

    def test_another_list_inherits_defaults_group(self, store):
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        assert L.secret("Branch", "grafana_token") == "default-token"

    def test_a_group_set_here_is_this_lists_own_and_never_gets_defaults_credential(self, store):
        assert L.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})["ok"] is True
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.20:3000", L.SET_HERE)
        value, origin = L.resolve("Branch", "grafana_token")
        assert origin == L.UNSET_HERE and value == ""
        assert L.secret("Branch", "grafana_token") == "", "Default's token went to another Grafana"
        # Another group is untouched: still inherited.
        assert L.resolve("Branch", "prometheus_url")[1] in (L.INHERITED, L.UNSET_EVERYWHERE)

    def test_a_secret_set_here_is_encrypted_at_rest_and_read_back(self, store):
        L.write("Branch", {"grafana_url": "http://192.0.2.20:3000", "grafana_token": "branch-t"})
        raw = (store / "lists" / "branch" / "settings.json").read_text(encoding="utf-8")
        assert "branch-t" not in raw
        assert L.secret("Branch", "grafana_token") == "branch-t"
        p = store / "lists" / "branch" / "settings.json"
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600

    def test_not_applicable_stops_the_lookup(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text(json.dumps({"values": {}, "not_applicable": {
            "grafana": {"by": "a@example.invalid", "why": "no Grafana"}}}), encoding="utf-8")
        assert L.resolve("Branch", "grafana_url") == (None, L.NOT_APPLICABLE)

    def test_a_host_key_is_the_global_value_for_every_list(self, store):
        assert L.resolve("Branch", "flask_port") == (5000, L.HOST)


class TestWriting:
    def test_a_host_key_is_refused_for_a_list(self, store):
        out = L.write("Branch", {"flask_port": 5001, "grafana_url": "http://192.0.2.20:3000"})
        assert out["ok"] is False and out["refused"] == ["flask_port"]
        assert not (store / "lists" / "branch" / "settings.json").exists()

    def test_defaults_write_goes_to_the_global_file(self, store):
        assert L.write("Default", {"loki_url": "http://192.0.2.10:3100"})["ok"] is True
        stored = json.loads((store / "user_settings.json").read_text(encoding="utf-8"))
        assert stored["loki_url"] == "http://192.0.2.10:3100"

    def test_an_unreadable_store_refuses_and_is_kept(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(L.ListSettingsUnreadable):
            L.resolve("Branch", "grafana_url")
        out = L.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})
        assert out["ok"] is False and "could not be read" in out["error"]
        assert (p / "settings.json").read_text(encoding="utf-8") == "{not json"


HOLDER = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.filestore import PathLock
with PathLock(sys.argv[1]):
    print("held", flush=True)
    time.sleep(2)
'''


def test_a_write_waits_while_another_process_holds_the_lists_store(store):
    """The store's read-modify-write holds its lock across processes: with the lock held
    elsewhere for 2 s, a write lands only after it is let go, and the holder's absence of a
    write cannot be overwritten by a stale copy. (A race test of two writers could not fail:
    the overlap a lost update needs is narrower than one write, so it is shown this way.)"""
    import time

    p = store / "lists" / "branch"
    p.mkdir(parents=True)
    holder = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=ROOT),
                               str(p / "settings.json")], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    started = time.time()
    assert L.write("Branch", {"deploy_max_workers": 3})["ok"] is True
    waited = time.time() - started
    holder.communicate(timeout=30)
    assert waited >= 1.5, f"the write landed after {waited:.2f} s while the lock was held"
