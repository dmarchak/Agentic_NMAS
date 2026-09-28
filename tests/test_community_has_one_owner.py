"""C139 / C141: the SNMP community has ONE owner, each device's own secret.

Measured on the host 2026-09-28: no list had a `collector_config.json`, so
`get_snmp_community()` returned its literal fallback, and `snmp_get`,
`snmp_walk` and `get_device_summary` defaulted to the same literal: the
fleet's real community, in a public repository. The code's default WAS the
configuration. Now NMAS reads the device's own secret (the one intent renders
from), per device, so the state between two devices' rotations is simply two
devices holding different values. No fallback, anywhere.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = "Lab"


@pytest.fixture
def two_devices(monkeypatch, tmp_path):
    """r1 still on the old value, s4 already rotated: the transitional state
    a per-device rotation IS."""
    from modules import collector_config, credentials, device

    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr(device, "get_device_lists",
                        lambda: [{"name": LIST, "filename": "lab"}])
    monkeypatch.setattr(device, "load_saved_devices", lambda path: [
        {"hostname": "r1", "ip": "192.0.2.11"}, {"hostname": "s4", "ip": "192.0.2.24"}])
    store = {credentials.template_secret_key(LIST, "r1", "snmp_community_ro"): "OLDCOMMUNITY1",
             credentials.template_secret_key(LIST, "s4", "snmp_community_ro"): "NEWCOMMUNITY2"}
    monkeypatch.setattr(credentials, "get_template_secret", lambda k: store.get(k, ""))
    return collector_config


class TestTheResolver:
    def test_each_device_gets_its_own_value(self, two_devices):
        cc = two_devices
        assert cc.device_community(LIST, "r1") == "OLDCOMMUNITY1"
        assert cc.device_community(LIST, "s4") == "NEWCOMMUNITY2"
        assert cc.community_for_address(LIST, "192.0.2.24") == ("s4", "NEWCOMMUNITY2")

    def test_a_device_with_no_secret_is_refused_never_defaulted(self, two_devices):
        cc = two_devices
        with pytest.raises(cc.NoCommunity) as exc:
            cc.device_community(LIST, "r9")
        assert "no default is ever used" in str(exc.value)

    def test_an_address_no_device_holds_is_refused(self, two_devices):
        cc = two_devices
        with pytest.raises(cc.NoCommunity) as exc:
            cc.community_for_address(LIST, "192.0.2.99")
        assert "Nothing was polled" in str(exc.value)


class TestTheCallers:
    def test_the_poll_route_uses_the_device_s_value_never_the_request_s(
            self, two_devices, monkeypatch):
        import app as A
        from modules import snmp_collector

        seen = []
        monkeypatch.setattr(snmp_collector, "snmp_get",
                            lambda host, oids, community, version=2, **k:
                            seen.append((host, community)) or [("sysName", "s4")])
        monkeypatch.setattr(A, "get_current_device_list", lambda: (LIST, "x"))
        r = A.app.test_client().post("/monitoring/snmp/poll", json={
            "device_ip": "192.0.2.24", "community": "TYPEDBYREQUEST"},
            headers={"Accept": "application/json"})
        assert seen == [("192.0.2.24", "NEWCOMMUNITY2")], (r.status_code, r.get_json())
        assert "NEWCOMMUNITY2" not in r.get_data(as_text=True)

    def test_the_form_refuses_a_community_by_naming_its_owner(self, monkeypatch, tmp_path):
        import app as A
        from modules import collector_config

        monkeypatch.setattr(collector_config, "_config_path",
                            lambda: str(tmp_path / "collector_config.json"))
        from modules import identity
        who = identity.Identity(actor="p@example.invalid", email="p@example.invalid",
                                kind="person", verified=True, outcome="ok",
                                peer="198.51.100.7", peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "identify", lambda _r: who)
        r = A.app.test_client().post("/monitoring/config", json={
            "snmp_community_ro": "TYPEDINTOFORM"}, headers={"Accept": "application/json"})
        assert r.status_code == 400 and "each device's own secret" in r.get_json()["error"]
        assert not (tmp_path / "collector_config.json").exists(), "nothing stored"

    def test_the_agent_tool_never_hands_the_model_the_value(self, two_devices, monkeypatch):
        """The success branch, which the leak sweep cannot reach (no test
        device answers SNMP): it printed `community=<value>` in prose, which
        positional redaction cannot see."""
        from modules import ai_assistant as ai
        from modules import snmp_collector

        monkeypatch.setattr(snmp_collector, "snmp_get",
                            lambda *a, **k: [("sysName", "s4")])
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: LIST)
        from tests import test_no_agent_tool_leaks_a_stored_secret as sweep
        monkeypatch.setitem(sweep.EXPLICIT, "snmp_poll",
                            {"device_ip": "192.0.2.24", "oids": ["sysName"]})
        tool = [t for t in ai.TOOLS if t.get("name") == "snmp_poll"]
        out = sweep.drive(tool)["snmp_poll"]
        assert "sysName" in out and "own community" in out, out
        assert "NEWCOMMUNITY2" not in out and "community=" not in out


class TestNoDefaultAnywhere:
    FILES = ("modules", "routes", "app.py")

    def _sources(self):
        for base in self.FILES:
            path = os.path.join(ROOT, base)
            if os.path.isfile(path):
                yield path
                continue
            for d, _dirs, files in os.walk(path):
                for f in files:
                    if f.endswith(".py"):
                        yield os.path.join(d, f)

    def test_no_parameter_named_community_has_a_default(self):
        found, scanned = [], 0
        for path in self._sources():
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scanned += 1
                    args = node.args.args + node.args.kwonlyargs
                    defaults = ([None] * (len(node.args.args) - len(node.args.defaults))
                                + list(node.args.defaults) + list(node.args.kw_defaults))
                    for a, dflt in zip(args, defaults):
                        if "community" in a.arg and dflt is not None:
                            found.append(f"{os.path.relpath(path, ROOT)}:{node.name}({a.arg})")
        assert scanned > 1000, scanned
        assert found == [], found

    def test_the_planted_default_is_found(self):
        """The control: the scan sees the shape it forbids."""
        tree = ast.parse('def snmp_get(host, oids, community="x"): pass')
        fn = tree.body[0]
        assert fn.args.args[2].arg == "community" and fn.args.defaults
