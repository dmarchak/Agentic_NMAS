"""C139: a credential NetBox holds where no import reaches it.

`nmas-retire` keeps a device's NetBox record, so (b)'s re-import, which masked
every device a list claims, never reached r5 (measured 2026-09-28: three slot
kinds unmasked, its community the value eight managed devices carry now).
`nmas-netbox-mask-context` masks what NetBox HOLDS: the population is the
secret-storage checker's own scan, the authority is the modification record
(did NMAS write this context), and the result is read back with that scan.

Built on r5's REAL config (the sanitized fleet fixture) in the stored-context
shape the live NetBox holds (keys measured on the host).
"""

import importlib.machinery
import importlib.util
import os
import sys

import pytest

from tests.fake_netbox import FakeNetBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R5 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r5.cfg")).read()
COMMUNITY = next(l.split()[2] for l in R5.splitlines() if l.startswith("snmp-server community"))
KEYS = ["bgp", "ip_interfaces", "mgmt_ip", "model", "ntp_servers", "os_version",
        "platform", "running_config", "serial", "snmp", "vrfs"]


def _load(name):
    path = os.path.join(ROOT, "scripts", name)
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


MC = _load("nmas-netbox-mask-context")
SCAN = _load("nmas-check-secret-storage").scan_netbox_context


def _context(running=R5):
    ctx = {k: f"<{k}>" for k in KEYS}
    ctx["running_config"] = running
    ctx["snmp"] = {"communities": [{"community": COMMUNITY, "permission": "RO"}],
                   "location": "containerlab-rcn-lab1"}
    return ctx


def _device(i=9, name="r5", ctx=None):
    return {"id": i, "name": name, "local_context_data": ctx if ctx is not None else _context()}


def _record(obj_id=9, fields=("comments", "local_context_data")):
    return {"Default": {"dcim/devices": [{"id": obj_id, "name": "r5", "actor": "x",
                                          "at": "2026-09-25T06:17:34Z",
                                          "fields": {f: {} for f in fields}}]}}


class TestTheFixtureCanExhibitTheCase:
    def test_r5_as_netbox_holds_it_is_flagged(self):
        f = SCAN([_device()])["findings"]
        assert f and f[0]["slots"] and f[0]["communities"] == 1, f


class TestThePlan:
    def test_a_context_nmas_wrote_is_masked_to_what_the_import_writes(self):
        from modules.netbox_client import _sanitise_config

        todo, refused = MC.plan([_device()], _record(), SCAN)
        assert not refused and len(todo) == 1
        after = todo[0]["after"]
        # The import's own function, so the result is what an import writes.
        assert after["running_config"] == _sanitise_config(R5)
        assert after["snmp"]["communities"] == [{"permission": "RO"}]
        assert after["snmp"]["location"] == "containerlab-rcn-lab1"
        # Every other key untouched.
        assert {k: after[k] for k in KEYS if k not in ("running_config", "snmp")} == \
            {k: f"<{k}>" for k in KEYS if k not in ("running_config", "snmp")}
        # Judged by the checker's INDEPENDENT pattern, not the redactor.
        assert SCAN([_device(ctx=after)])["findings"] == []
        assert COMMUNITY not in str(after)
        assert todo[0]["lines"] >= 2 and todo[0]["wrote"] == "2026-09-25T06:17:34Z"

    def test_no_record_of_nmas_writing_it_is_refused_by_name(self):
        todo, refused = MC.plan([_device()], {}, SCAN)
        assert todo == [] and "somebody's data" in refused[0][2]

    def test_a_record_of_other_fields_is_not_authority(self):
        todo, refused = MC.plan([_device()], _record(fields=("status",)), SCAN)
        assert todo == [] and refused

    def test_another_device_s_record_is_not_authority(self):
        todo, refused = MC.plan([_device()], _record(obj_id=5), SCAN)
        assert todo == [] and refused

    def test_a_partly_masked_context_is_refused_not_masked_twice(self):
        from modules.netbox_client import _sanitise_config

        half = _sanitise_config(R5) + "\nsnmp-server community " + COMMUNITY + " RW\n"
        todo, refused = MC.plan([_device(ctx=_context(half))], _record(), SCAN)
        assert todo == [] and "partly masked" in refused[0][2]

    def test_a_clean_device_is_not_listed(self):
        from modules.netbox_client import masked_context

        todo, refused = MC.plan([_device(ctx=masked_context(_context()))], _record(), SCAN)
        assert todo == [] and refused == []


class TestTheCommand:
    @pytest.fixture
    def nb(self, monkeypatch):
        import modules.netbox_client as nbc
        from modules import netbox_guard

        nb = FakeNetBox()
        nb.seed("dcim/devices", _device())
        monkeypatch.setattr(nbc, "_nb_ready", lambda: (True, "", nb, "http://127.0.0.1:9"))
        monkeypatch.setattr(netbox_guard, "read_modified", lambda: (_record(), None))
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        return nb

    def _run(self, monkeypatch, capsys, *argv):
        monkeypatch.setattr(sys, "argv", ["nmas-netbox-mask-context", *argv])
        rc = MC.main()
        return rc, capsys.readouterr().out

    def test_the_dry_run_writes_nothing_and_names_what_it_would(self, nb, monkeypatch, capsys):
        rc, out = self._run(monkeypatch, capsys, "--device", "r5")
        assert rc == 0 and nb.patches == []
        assert "r5 (id 9)" in out and "would mask" in out and "DRY RUN" in out
        assert COMMUNITY not in out

    def test_apply_writes_reads_back_and_says_so(self, nb, monkeypatch, capsys):
        rc, out = self._run(monkeypatch, capsys, "--device", "r5", "--apply")
        assert rc == 0, out
        assert [p[0] for p in nb.patches] == ["dcim/devices"]
        assert "read back, NetBox holds no unmasked credential" in out
        assert COMMUNITY not in str(nb.store["dcim/devices"][0]["local_context_data"])

    def test_a_write_netbox_did_not_keep_is_named(self, nb, monkeypatch, capsys):
        # NetBox answers the PATCH and keeps the old context: the read-back is
        # what notices, never the 200.
        nb.patch = lambda url, json=None, timeout=None: type(
            "R", (), {"ok": True, "status_code": 200, "json": lambda s: _device(),
                      "raise_for_status": lambda s: None, "text": ""})()
        rc, out = self._run(monkeypatch, capsys, "--device", "r5", "--apply")
        assert rc == 1 and "STILL holds" in out

    def test_no_device_is_unproven_not_clean(self, nb, monkeypatch, capsys):
        rc, out = self._run(monkeypatch, capsys, "--device", "nosuch")
        assert rc == 2 and "UNPROVEN" in out
