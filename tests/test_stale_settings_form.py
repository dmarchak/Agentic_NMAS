"""A stale Settings tab never reverts another person's decision (CONCURRENCY_AUDIT R17).

Today's Settings form sent every field as it was loaded. A tab opened before another person
turned NetBox writes off turned them back on when it saved an unrelated field. Today's forms (the
modal, every integration card, the general block) then sent only the fields the person changed,
with the values they loaded, and the server refused a changed field whose stored value had moved
since, naming both values. (The `.env` writer and its test left with the AI key it saved: C783.)

Those forms left with today's Settings modal at 7.8 (2026-10-15), and the property moved to their
v2 homes, which had resent every field as drawn (found by rebasing these tests): each card of
Settings › Installation (NetBox connection, Proxmox, Commit author, Server: the modal's NetBox
section and general block) and each network's integration cards (Settings › Default and a
network's own: the modal's integration cards). Each card sends what it drew (``loaded``); its
Save writes only what the person changed, under one hold of the settings lock, and refuses a
changed field another person moved since, naming both values, nothing saved. The incident's own
field, NetBox's master write switch, is on no Save at all on v2: the card turns it off only, and
an authorised NetBox confirm turns it on (tests/test_installation_settings.py).

Driven through the real routes on a temporary store, as each page sends its form."""

import json

from tests.test_settings_v2 import _card, _get, _save, loaded_of, networks  # noqa: F401
from tests.test_settings_v2 import L


def _stored(key):
    from modules.settings_schema import get_setting
    return get_setting(key)


def _install_card(n, name):
    _r, html = _get(n, f"/v2/settings/installation/card/{name}")
    return loaded_of(html)


def _install_save(n, name, data, loaded):
    import html as html_mod
    r = n["client"].post(f"/v2/settings/installation/card/{name}/save",
                         data=dict(data, loaded=loaded) if loaded is not None else data,
                         headers={"HX-Request": "true"})
    return r, html_mod.unescape(r.get_data(as_text=True))


NB = {"netbox_url": "https://192.0.2.30", "netbox_auth_scheme": "Bearer",
      "netbox_verify_tls": "on"}


class TestTheInstallationCards:
    """Today's modal's NetBox section and its general block, on Settings › Installation."""

    def test_a_field_this_person_did_not_change_never_reverts_anothers(self, networks):
        stale = _install_card(networks, "netbox")                  # this tab opens the card
        assert json.loads(stale)["netbox_verify_tls"] == "on"
        # Another person turns TLS verification off.
        r, _html = _install_save(networks, "netbox",
                                 {"netbox_url": "", "netbox_auth_scheme": "Bearer"},
                                 _install_card(networks, "netbox"))
        assert r.status_code == 200 and _stored("netbox_verify_tls") is False
        # This tab, opened before, saves a URL, its switch still drawn on.
        r, html = _install_save(networks, "netbox", NB, stale)
        assert r.status_code == 200 and "Saved" in html, html
        assert _stored("netbox_url") == "https://192.0.2.30"     # this person's change saved
        assert _stored("netbox_verify_tls") is False             # their decision stands

    def test_a_changed_field_another_person_moved_is_refused_naming_both(self, networks):
        stale = _install_card(networks, "netbox")
        assert _install_save(networks, "netbox", dict(NB, netbox_url="https://192.0.2.7"),
                             _install_card(networks, "netbox"))[0].status_code == 200
        r, html = _install_save(networks, "netbox", dict(NB, netbox_url="https://192.0.2.9"),
                                stale)
        assert r.status_code == 409, html
        assert ("netbox_url: not saved, because it changed after you opened Settings: it was "
                "'' when you opened it and is 'https://192.0.2.7' now") in html, html
        assert "Nothing was changed" in html
        assert _stored("netbox_url") == "https://192.0.2.7"

    def test_the_servers_bind_moved_since_is_refused(self, networks):
        """Today's general block's own case (flask_host), on the Server card."""
        stale = _install_card(networks, "server")
        assert _install_save(networks, "server", {"flask_host": "127.0.0.1", "flask_port": "5000"},
                             _install_card(networks, "server"))[0].status_code == 200
        r, html = _install_save(networks, "server",
                                {"flask_host": "192.0.2.5", "flask_port": "5000"}, stale)
        assert r.status_code == 409 and "flask_host: not saved" in html, html
        assert _stored("flask_host") == "127.0.0.1"

    def test_a_save_that_says_nothing_about_what_it_drew_is_refused(self, networks):
        before = _stored("netbox_url")
        for loaded in (None, "not json", "[]"):
            r, html = _install_save(networks, "netbox", dict(NB, netbox_url="https://192.0.2.9"),
                                    loaded)
            assert r.status_code == 409 and "did not say what it loaded" in html, loaded
        assert _stored("netbox_url") == before

    def test_the_card_sends_what_it_drew(self, networks):
        from modules import installation_settings as I
        _r, html = _get(networks, "/v2/settings/installation")
        for name in I.CARDS:
            drawn = _card(html, name)
            assert json.loads(loaded_of(drawn)) == I.card(name)["loaded"], name


class TestTheNetworkCards:
    """Today's modal's integration cards, on Settings › Default and a network's own."""

    def test_a_changed_field_another_person_moved_is_refused_naming_both(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Default/group/kea")
        stale = loaded_of(html)
        r, _h = _save(networks, "Default", "kea", {"kea_url": "http://192.0.2.7:8000"})
        assert r.status_code == 200 and _stored("kea_url") == "http://192.0.2.7:8000"
        r = networks["client"].post("/v2/settings/network/Default/group/kea/save",
                                    data={"kea_url": "http://192.0.2.9:8000", "loaded": stale})
        body = r.get_data(as_text=True)
        assert r.status_code == 409, body
        assert "kea_url: not saved, because it changed after you opened Settings" in body
        assert "http://192.0.2.7:8000" in body
        assert _stored("kea_url") == "http://192.0.2.7:8000"

    def test_a_field_this_person_did_not_change_never_reverts_anothers(self, networks):
        _r, html = _get(networks, "/v2/settings/network/Branch/group/grafana")
        stale = loaded_of(html)
        assert json.loads(stale)["grafana_verify_tls"] == "on"
        r, _h = _save(networks, "Branch", "grafana", {"grafana_verify_tls": "off"})
        assert r.status_code == 200 and L.resolve("Branch", "grafana_verify_tls")[0] is False
        r = networks["client"].post("/v2/settings/network/Branch/group/grafana/save", data={
            "grafana_url": "http://192.0.2.61:3000", "grafana_verify_tls": "on",
            "loaded": stale})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert L.resolve("Branch", "grafana_url")[0] == "http://192.0.2.61:3000"
        assert L.resolve("Branch", "grafana_verify_tls")[0] is False, "their decision stands"

    def test_a_card_save_without_what_it_drew_is_refused(self, networks):
        r = networks["client"].post("/v2/settings/network/Default/group/kea/save",
                                    data={"kea_url": "http://192.0.2.9:8000"})
        assert r.status_code == 409
        assert "did not say what it loaded" in r.get_data(as_text=True)
        assert _stored("kea_url") != "http://192.0.2.9:8000"
