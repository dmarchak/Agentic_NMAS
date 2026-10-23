"""Settings › Installation › Console servers (O8 of out-of-band ZTP; routes/console_servers_v2.py,
templates/v2/_console_servers.html and _console_server_op.html; modules/nsot/console_rekey.py;
C1560).

- the tab: each port record with its NetBox port (one paged read of NetBox's console-server
  ports), its key's state by reference (never a value) and its host key; NetBox's ports with no
  record, each with Set up…; an unreadable NetBox said, never "none"; the region listens for
  `console_servers`, and its cards open outside it;
- a port's record: saved through the store's own validation (IPv4, IPv6 and a hostname), a
  refusal naming every field drawn with nothing written, the write recorded with who; Remove…
  says what stays;
- a console server's key: ONLY the public key, its fingerprint and the exact authorized_keys
  line drawn; no line of the private half reaches the page; an existing name refused unless
  Replace is ticked;
- C1560: a console server's refused host key names THIS page's Re-key…, never a device page's;
  the re-key's preview reads the key with no credential and shows both; its confirm is bound to
  both keys and keeps the new one, the old one in the record's history; a raw TCP console with
  no jump host has no key to re-key.
"""

import re
import socket
import types

import paramiko
import pytest

from tests.fake_netbox import FakeNetBox

BASE = "http://nb.invalid"
PERSON = "operator@example.invalid"
TAB = "/v2/settings/installation/console-servers"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules import config
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr("modules.credentials._FILE", str(data / "credential_profiles.json"))
    fake = FakeNetBox()
    cs = fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
    ports = [fake.seed("dcim/console-server-ports", {"device": cs["id"], "name": f"port {n}"})
             for n in (5, 6)]
    monkeypatch.setattr("modules.netbox_client._nb_ready", lambda: (True, "", fake, BASE))
    return types.SimpleNamespace(fake=fake, cs=cs, ports=ports, data=data)


@pytest.fixture
def client():
    import app as nmas
    return nmas.app.test_client()


@pytest.fixture
def person(monkeypatch):
    from modules import identity
    who = types.SimpleNamespace(actor=PERSON, kind="person", peer="192.0.2.5",
                                is_identified=True)
    monkeypatch.setattr(identity, "require", lambda *a, **k: (who, None))
    monkeypatch.setattr(identity, "request_actor", lambda: PERSON)
    return who


def _text(r) -> str:
    return r.get_data(as_text=True)


def _set(port_id, **record):
    from modules.nsot import console_servers
    got = console_servers.set_port(port_id, record, actor=PERSON)
    assert got["ok"], got


# ── The tab ────────────────────────────────────────────────────────────────────────────────

class TestTheTab:
    def test_it_draws_each_record_with_its_netbox_port_and_the_ports_with_none(self, lab,
                                                                                client):
        from modules import csp
        _set(lab.ports[0]["id"], driver="command_bridge", host="2001:db8::20", ssh_port=22,
             container="edge-a", credential_ref="console-bridge")
        r = client.get("/v2/settings/installation?tab=console")
        html = _text(r)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert '<a class="tab on" href="/v2/settings/installation?tab=console"' in html
        assert 'id="cs-op"' in html.split('id="console-servers"')[0], "cards open outside"
        assert f'hx-get="{TAB}"' in html and 'hx-trigger="nmas:console_servers from:body"' in html
        row = html.split(f'id="cs-port-{lab.ports[0]["id"]}"')[1].split("</tr>")[0]
        for words in ("cons-1", "port 5", "command_bridge", "2001:db8::20", "container edge-a",
                      "console-bridge", "no key stored", "kept on first contact"):
            assert words in row, words
        unset = html.split("In NetBox, with no record")[1]
        assert "port 6" in unset and "Set up…" in unset and "port 5" not in unset
        assert "Port %d added (command_bridge) by %s" % (lab.ports[0]["id"], PERSON) in html

    def test_an_unreadable_netbox_is_said_and_each_record_shown_by_its_id(self, lab, client,
                                                                          monkeypatch):
        _set(77, driver="raw_tcp", host="192.0.2.30", tcp_port=5000)
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "NetBox URL and API token are not configured",
                                     None, ""))
        html = _text(client.get(TAB))
        assert "NetBox's console-server ports could not be read:" in html
        assert "NetBox is not reachable: NetBox URL and API token are not configured" in html
        assert "not read" in html.split('id="cs-port-77"')[1].split("</tr>")[0]
        assert "In NetBox, with no record" not in html
        form = _text(client.get(f"{TAB}/port/form"))
        assert 'name="port_id" type="text" inputmode="numeric"' in form

    def test_the_store_unreadable_is_said(self, lab, client):
        from modules.nsot import console_servers
        with open(console_servers.path(), "w", encoding="utf-8") as fh:
            fh.write("{")
        html = _text(client.get(TAB))
        assert "The console-server store could not be read:" in html


# ── A port's record ────────────────────────────────────────────────────────────────────────

class TestAPortRecord:
    @pytest.mark.parametrize("host", ["192.0.2.40", "2001:db8::40", "cons-1.example.net"])
    def test_a_valid_record_is_saved_as_the_person(self, lab, client, person, host):
        from modules.nsot import console_servers
        pid = lab.ports[1]["id"]
        form = _text(client.get(f"{TAB}/port/form?port={pid}"))
        assert f'<option value="{pid}" selected>' in form
        r = client.post(f"{TAB}/port", data={"port_id": str(pid), "driver": "raw_tcp",
                                             "host": host, "tcp_port": "5001"})
        html = _text(r)
        assert r.status_code == 200, html
        assert f"Console-server port {pid} saved" in html and "5001" in html
        rec = console_servers.get_port(pid)["record"]
        assert rec["by"] == PERSON and rec["tcp_port"] == 5001
        assert rec["host"] == host

    def test_a_field_the_driver_does_not_hold_is_refused_naming_it(self, lab, client, person):
        from modules.nsot import console_servers
        pid = lab.ports[1]["id"]
        r = client.post(f"{TAB}/port", data={"port_id": str(pid), "driver": "raw_tcp",
                                             "host": "192.0.2.300", "tcp_port": "5001",
                                             "container": "edge-a"})
        html = _text(r)
        assert r.status_code == 409
        assert "field &#39;container&#39; is not held for the raw_tcp driver" in html
        assert "&#39;192.0.2.300&#39; is not an IPv4 or IPv6 address or a hostname" in html
        assert "Nothing was changed" in html
        assert 'value="192.0.2.300"' in html, "the form keeps what was typed"
        assert console_servers.get_port(pid)["state"] == "absent"

    def test_a_port_id_that_is_no_number_is_refused(self, lab, client, person):
        r = client.post(f"{TAB}/port", data={"port_id": "x", "driver": "raw_tcp",
                                             "host": "192.0.2.40", "tcp_port": "5001"})
        assert r.status_code == 409
        assert "a console-server port&#39;s NetBox id is a positive number, not &#39;x&#39;" \
            in _text(r)

    def test_remove_says_what_stays_and_forgets_the_record(self, lab, client, person):
        from modules.nsot import console_servers
        pid = lab.ports[0]["id"]
        _set(pid, driver="raw_tcp", host="192.0.2.30", tcp_port=5000)
        html = _text(client.get(f"{TAB}/port/{pid}/remove/form"))
        assert "What stays:" in html
        assert "NetBox's port and every cable to it, and the key" in html
        r = client.post(f"{TAB}/port/{pid}/remove")
        assert r.status_code == 200 and "record removed" in _text(r)
        assert console_servers.get_port(pid)["state"] == "absent"
        again = client.post(f"{TAB}/port/{pid}/remove")
        assert again.status_code == 409 and f"console-server port {pid} has no record" in \
            _text(again)


# ── A console server's key ─────────────────────────────────────────────────────────────────

class TestAKey:
    def _generate(self, client, **over):
        data = dict({"ref": "console-bridge", "username": "mercury",
                     "wrapper_path": "/usr/local/lib/nmas/nmas-console-bridge",
                     "allowlist_path": "/etc/nmas/console-allowlist"}, **over)
        return client.post(f"{TAB}/key", data=data)

    def test_only_the_public_half_and_its_line_are_drawn(self, lab, client, person):
        from modules import credentials
        form = _text(client.get(f"{TAB}/key/form"))
        assert 'value="/usr/local/lib/nmas/nmas-console-bridge"' in form
        r = self._generate(client)
        html = _text(r)
        assert r.status_code == 200, html
        stored = credentials.get_ssh_key("console-bridge")
        line = ('restrict,command="/usr/local/lib/nmas/nmas-console-bridge '
                '/etc/nmas/console-allowlist" ' + stored["public_key"])
        assert line.replace('"', "&#34;") in html or line in html
        body = [l for l in stored["private_key"].splitlines() if l and not l.startswith("-")]
        assert body and not any(l in html for l in body), "no line of the private half"
        assert "PRIVATE" not in html
        tab = _text(client.get(TAB))
        assert "console-bridge" in tab.split('id="h-cs-keys"')[1]
        assert "no port uses it yet" in tab

    def test_an_existing_name_is_refused_unless_replace_is_ticked(self, lab, client, person):
        from modules import credentials
        self._generate(client)
        first = credentials.get_ssh_key("console-bridge")["public_key"]
        r = self._generate(client)
        assert r.status_code == 409 and "Tick Replace to make a new one" in _text(r)
        assert credentials.get_ssh_key("console-bridge")["public_key"] == first
        assert 'name="replace" value="1"' in _text(r)
        r = self._generate(client, replace="1")
        assert r.status_code == 200
        assert credentials.get_ssh_key("console-bridge")["public_key"] != first

    def test_a_path_that_could_carry_a_command_is_refused(self, lab, client, person):
        r = self._generate(client, wrapper_path="/usr/bin/x; reboot")
        assert r.status_code == 409 and "Not generated: the wrapper path" in _text(r)


# ── A console server's host key (C1560) ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def two_keys():
    return [paramiko.RSAKey.generate(2048) for _ in range(2)]


class TestRekey:
    def _keys(self, lab, two_keys, monkeypatch, family=socket.AF_INET):
        """A console server's port record, its first key held, and a server answering with
        the second, read with no credential."""
        from modules import host_keys as HK
        host = "127.0.0.1" if family == socket.AF_INET else "::1"
        pid = lab.ports[0]["id"]
        _set(pid, driver="command_bridge", host=host, ssh_port=2222, container="edge-a",
             credential_ref="console-bridge")
        HK.check(host, two_keys[0], owner="test", port=2222)
        presented = HK.offered(two_keys[1])
        monkeypatch.setattr("modules.connection.read_host_key",
                            lambda h, port=22, owner="", timeout=None: dict(presented))
        return pid, host, presented

    def test_a_refused_console_server_key_names_this_page_never_a_device_page(self, lab,
                                                                             two_keys):
        from modules import host_keys as HK
        from modules.nsot.console_rekey import REMEDY
        HK.check("192.0.2.50", two_keys[0], port=22)
        with pytest.raises(HK.HostKeyRefused) as exc:
            HK.check("192.0.2.50", two_keys[1], port=22, remedy=REMEDY)
        words = str(exc.value)
        assert "Settings › Installation › Console servers (Re-key… on its port's row)" in words
        assert "re-key it on its page" not in words
        with pytest.raises(HK.HostKeyRefused) as exc:
            HK.check("192.0.2.50", two_keys[1], port=22)
        assert "re-key it on its page (Re-key…)" in str(exc.value), "a device keeps its own"

    def test_the_pinned_transport_passes_the_console_server_s_remedy(self, lab, two_keys,
                                                                     monkeypatch):
        """Through the real opener: the second key a loopback SSH server presents is refused
        with this page's words."""
        from modules import connection
        from modules import host_keys as HK
        from modules.nsot import console_keys
        from tests.console_fakes import SshServer
        key = console_keys.generate("console-bridge", username="mercury",
                                    wrapper_path="/usr/local/bin/bridge",
                                    allowlist_path="/etc/nmas/allow")
        username, pkey = console_keys.load("console-bridge")
        servers = [SshServer(k, user="mercury", client_public=key["public_key"])
                   for k in two_keys]
        try:
            first, second = servers
            HK.check(second.host, two_keys[0], port=second.port)      # held: the first key
            with pytest.raises(HK.HostKeyRefused) as exc:
                connection.open_pinned_transport(second.host, second.port, username=username,
                                                 pkey=pkey, owner="test", timeout=5)
            assert "Console servers (Re-key… on its port's row)" in str(exc.value)
            assert second.auth == [], "refused before the key was offered"
        finally:
            for s in servers:
                s.close()

    @pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6], ids=["ipv4", "ipv6"])
    def test_preview_then_confirm_keeps_the_new_key_and_the_old_in_history(
            self, lab, client, person, two_keys, monkeypatch, family):
        from modules import host_keys as HK
        pid, host, presented = self._keys(lab, two_keys, monkeypatch, family)
        held = HK.held(host)["fingerprint"]
        tab = _text(client.get(TAB))
        assert "Re-key…" in tab.split(f'id="cs-port-{pid}"')[1].split("</tr>")[0]
        r = client.post(f"{TAB}/port/{pid}/rekey/preview")
        html = _text(r)
        assert r.status_code == 200, html
        assert held in html and presented["fingerprint"] in html
        digest = re.search(r'name="hash" value="([0-9a-f]{16})"', html).group(1)
        r = client.post(f"{TAB}/port/{pid}/rekey", data={"hash": digest})
        html = _text(r)
        assert r.status_code == 200 and "kept" in html, html
        rec = HK.held(host)
        assert rec["fingerprint"] == presented["fingerprint"] and rec["kept_by"] == PERSON
        assert rec["history"][-1]["fingerprint"] == held

    def test_a_key_that_moved_since_the_preview_keeps_nothing(self, lab, client, person,
                                                              two_keys, monkeypatch):
        from modules import host_keys as HK
        pid, host, _presented = self._keys(lab, two_keys, monkeypatch)
        held = HK.held(host)["fingerprint"]
        r = client.post(f"{TAB}/port/{pid}/rekey", data={"hash": "0" * 16})
        assert r.status_code == 409 and "Nothing was kept; preview again" in _text(r)
        assert HK.held(host)["fingerprint"] == held

    def test_a_raw_console_with_no_jump_host_has_no_key_to_re_key(self, lab, client):
        pid = lab.ports[1]["id"]
        _set(pid, driver="raw_tcp", host="192.0.2.30", tcp_port=5000)
        r = client.post(f"{TAB}/port/{pid}/rekey/preview")
        assert r.status_code == 409
        assert "the raw_tcp driver with no jump host speaks no SSH" in _text(r)
        assert 'name="hash"' not in _text(r)
