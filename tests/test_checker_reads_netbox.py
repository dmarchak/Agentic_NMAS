"""C95 (d): the secret-storage checker reads what NetBox HOLDS.

The import's masking was a second redactor that had never matched anything on
this fleet: true in the code, false in effect. So the verification of C95 (b)'s
re-import measures NetBox's config context, not the import's intent, with a
check that does not share a source with the redactor (its own slot pattern,
plus the positional redactor asked separately). Driven on the nine REAL fleet
configs: raw, as NetBox held them until (a), every device is a finding; through
the import's builders after (a), none is.
"""

import importlib.machinery
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


def _checker():
    return importlib.machinery.SourceFileLoader(
        "nmas_check_secret_storage",
        os.path.join(ROOT, "scripts", "nmas-check-secret-storage")).load_module()


def _fleet():
    for name in sorted(f for f in os.listdir(FLEET) if f.endswith(".cfg")):
        with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
            yield name[:-4], fh.read()


def test_the_config_context_as_netbox_held_it_is_found_on_every_device():
    """The positive control, from real data: what NetBox held before (a)."""
    import re

    chk = _checker()
    devices = []
    for name, cfg in _fleet():
        communities = [{"community": c, "permission": p} for c, p in
                       re.findall(r"^snmp-server community (\S+) (RO|RW)", cfg, re.M)]
        devices.append({"name": name, "local_context_data": {
            "running_config": cfg, "snmp": {"communities": communities}}})
    out = chk.scan_netbox_context(devices)
    assert out["read"] == 9
    assert sorted(f["device"] for f in out["findings"]) == sorted(n for n, _c in _fleet())
    kinds = {k for f in out["findings"] for k in f["slots"]}
    assert "snmp-server community" in kinds and any(k.startswith("username <name>") for k in kinds)
    printed = repr(out)
    for _name, cfg in _fleet():
        for value in re.findall(r"^snmp-server community (\S+)", cfg, re.M):
            assert f"'{value}'" not in printed, "the checker printed a value"


def test_what_the_import_writes_now_is_clean():
    from modules.netbox_client import (_build_config_context,
                                       _parse_routing_context_from_config)

    chk = _checker()
    devices = [{"name": n, "local_context_data": _build_config_context(
        n, "192.0.2.1", {}, [], [], [], cfg,
        routing_context=_parse_routing_context_from_config(cfg))} for n, cfg in _fleet()]
    out = chk.scan_netbox_context(devices)
    assert out["read"] == 9 and out["findings"] == []


def test_no_devices_is_not_clean(monkeypatch, capsys):
    """Zero devices read must never print a pass."""
    chk = _checker()

    class _R:
        ok, status_code = True, 200

        def json(self):
            return {"results": [], "next": None}

    class _S:
        def get(self, *a, **k):
            return _R()

    monkeypatch.setattr("modules.netbox_client._nb_ready", lambda: (True, "", _S(), "http://nb"))
    findings = chk.netbox_section()
    assert findings and "not clean" in findings[0]
    assert "UNPROVEN" in capsys.readouterr().out


def test_an_unreachable_netbox_is_unproven(monkeypatch, capsys):
    chk = _checker()
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (False, "not configured", None, ""))
    assert chk.netbox_section()
    assert "UNPROVEN" in capsys.readouterr().out
