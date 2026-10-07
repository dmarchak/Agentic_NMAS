"""A stale Settings tab never reverts another person's decision (CONCURRENCY_AUDIT R17).

The Settings form sent every field as it was loaded. A tab opened before another person turned
NetBox writes off turned them back on when it saved an unrelated field. Now each settings form
(the modal, every integration card, the general block) sends only the fields the person
changed, with the values it loaded. Under the settings lock, a changed field whose stored value
moved since is refused, naming both values; the rest are saved. The `.env` write is locked and
replaced whole.

Driven through the real routes on a temporary settings file, and two real processes for
`.env`; the shipped clients are checked by lifting their functions."""

import os
import stat
import subprocess
import sys

import pytest

from tests.payload_render import lift, shipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app as nmas
    from modules import config

    path = tmp_path / "user_settings.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))
    return nmas.app.test_client()


def _stored(key):
    from modules.config import load_user_settings
    return load_user_settings().get(key)


class TestTheSettingsModal:
    def test_a_field_another_person_moved_is_refused_and_the_rest_saved(self, client):
        # The agent starts OFF (C497, 2026-10-07), so the other person turns it ON.
        stale = client.get("/settings").get_json()               # this tab opens Settings
        assert stale["background_agent_enabled"] is False
        assert client.post("/settings", json={                   # another person turns the agent on
            "background_agent_enabled": True,
            "loaded": client.get("/settings").get_json()}).status_code == 200
        r = client.post("/settings", json={"background_agent_enabled": False,
                                           "wf_read_first": False, "loaded": stale})
        body = r.get_json()
        assert r.status_code == 207 and body["status"] == "partial"
        assert any(e.startswith("background_agent_enabled: not saved, because it changed after "
                                "you opened Settings: it was False when you opened it and is "
                                "True now") for e in body["errors"]), body
        assert _stored("background_agent_enabled") is True       # their decision stands
        assert _stored("wf_read_first") is False                 # this person's change saved

    def test_a_field_this_person_did_not_change_is_never_sent_so_never_reverts(self, client):
        save = lift(SETTINGS_JS, "saveSettings")
        assert "if (loaded && k in loaded && loaded[k] === payload[k]) delete payload[k];" in save
        assert "payload.loaded = loaded;" in save
        assert "window._settingsLoaded = s;" in lift(SETTINGS_JS, "openSettingsModal")

    def test_a_save_that_says_nothing_about_what_it_loaded_is_refused(self, client):
        r = client.post("/settings", json={"wf_read_first": False})
        assert r.status_code == 400 and "did not say what it loaded" in r.get_json()["errors"][0]
        assert _stored("wf_read_first") is None

    def test_the_write_switch_alone_is_saved(self, client):
        """Sent alone (the other NetBox fields unchanged), it was dropped by a branch that
        waited for the URL beside it."""
        r = client.post("/settings", json={"netbox_allow_writes": True,
                                           "loaded": client.get("/settings").get_json()})
        assert r.status_code == 200, r.get_json()
        assert client.get("/settings").get_json()["netbox_allow_writes"] is True

    def test_the_general_blocks_answer_is_part_of_the_result(self):
        save = lift(SETTINGS_JS, "saveSettings")
        assert "Promise.all([fetch('/settings'" in save
        assert "concat(gen && gen.ok === false ? [gen.error] : [])" in save


class TestTheIntegrationCards:
    def _loaded(self, client):
        return client.get("/settings/integrations").get_json()["integrations"]["kea"]

    def test_a_field_another_person_moved_is_refused_naming_both(self, client):
        stale = self._loaded(client)
        assert client.post("/settings/integrations/kea", json={
            "kea_url": "http://192.0.2.7:8000", "loaded": self._loaded(client)}).get_json()["ok"]
        r = client.post("/settings/integrations/kea",
                        json={"kea_url": "http://192.0.2.9:8000", "loaded": stale})
        body = r.get_json()
        assert r.status_code == 409 and body["moved"] == ["kea_url"]
        assert "'http://192.0.2.7:8000' now" in body["error"]
        assert _stored("kea_url") == "http://192.0.2.7:8000"

    def test_an_unchanged_card_field_is_not_sent(self):
        js = shipped("partials__settings_integrations.1.js")
        save = lift(js, "saveIntegration")
        assert "JSON.stringify(loaded[k]) === JSON.stringify(changed[k])) delete changed[k];" in save
        assert "body: JSON.stringify({...changed, loaded})," in save
        assert "_intLoaded[name] = cfg;" in lift(js, "loadIntegrationSettings")

    def test_a_card_save_without_what_it_loaded_is_refused(self, client):
        r = client.post("/settings/integrations/kea", json={"kea_url": "http://192.0.2.9:8000"})
        assert r.status_code == 400 and "did not say what it loaded" in r.get_json()["error"]


class TestTheGeneralBlock:
    def test_a_field_another_person_moved_is_refused(self, client):
        stale = client.get("/settings/integrations/general").get_json()["settings"]
        fresh = client.get("/settings/integrations/general").get_json()["settings"]
        assert client.post("/settings/integrations/general",
                           json={"tftp_root": "/srv/a", "loaded": fresh}).get_json()["ok"]
        r = client.post("/settings/integrations/general",
                        json={"tftp_root": "/srv/b", "loaded": stale})
        assert r.status_code == 409 and r.get_json()["moved"] == ["tftp_root"]
        assert _stored("tftp_root") == "/srv/a"

    def test_the_block_sends_only_what_changed(self):
        js = shipped("partials__settings_integrations.1.js")
        save = lift(js, "saveGeneralIntegrationSettings")
        assert "payload.loaded = loaded;" in save
        assert "_intLoaded.general = d.settings;" in lift(js, "loadGeneralIntegrationSettings")


ENV_WRITER = '''
import sys
sys.path.insert(0, {root!r})
from modules.config import set_env_line
for i in range(60):
    set_env_line(sys.argv[1], sys.argv[2], str(i))
'''


class TestTheEnvFile:
    def test_two_processes_writing_different_keys_lose_neither(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("KEPT=1\n", encoding="utf-8")
        procs = [subprocess.Popen([sys.executable, "-c", ENV_WRITER.format(root=ROOT),
                                   str(path), name], stderr=subprocess.PIPE, text=True)
                 for name in ("A_KEY", "B_KEY")]
        for p in procs:
            _o, err = p.communicate(timeout=120)
            assert p.returncode == 0, err[-500:]
        lines = sorted(path.read_text(encoding="utf-8").splitlines())
        assert lines == ["A_KEY=59", "B_KEY=59", "KEPT=1"], lines
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

    def test_the_route_writes_through_it(self):
        from tests.astcheck import calls_in

        import app as nmas
        assert calls_in(nmas._save_settings, "set_env_line") == 1


SETTINGS_JS = None


def setup_module(_module):
    """The modal's script is inline in index.html: its <script> block, parsed out by tag."""
    global SETTINGS_JS
    with open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    blocks = html.split("<script>")
    SETTINGS_JS = next(b.split("</script>")[0] for b in blocks
                       if "window.saveSettings = function" in b)
