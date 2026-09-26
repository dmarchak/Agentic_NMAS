"""P.3 step 11 (register B14): a login credential is stored ONCE.

Every device stored its login password twice, as `password` and as `secret`.
No device has an enable secret, and Netmiko sends `secret` only when a device
asks for one, so the copy did nothing, and it is what made the terminal's
unconditional send of it look harmless (B13). A credential stored twice is a
credential that leaks twice.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "Pw-SINGLE-COPY-7c1e9a"
ENABLE = "En-DISTINCT-4b2d8f"


class TestTheConnectionFallsBack:
    @pytest.mark.parametrize("secret", [None, ""])
    def test_no_stored_secret_means_the_password(self, secret):
        from modules.connection import connection_params
        p = connection_params({"device_type": "cisco_ios", "ip": "192.0.2.1", "username": "u"},
                              password=PASSWORD, secret=secret)
        assert p["secret"] == PASSWORD

    def test_a_real_enable_secret_is_used(self):
        """Control: the fallback is for an EMPTY secret only."""
        from modules.connection import connection_params
        p = connection_params({"device_type": "cisco_ios", "ip": "192.0.2.1", "username": "u"},
                              password=PASSWORD, secret=ENABLE)
        assert p["secret"] == ENABLE


class TestRotationStoresOneCopy:
    def test_the_csv_row_gets_no_copy(self, tmp_path, monkeypatch):
        from modules.device import decrypt_field
        from modules.nsot import credential_rotation as cr
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        wrote = []
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: [{"hostname": "r2", "ip": "203.0.113.2",
                                        "password": "old", "secret": "old"}])
        monkeypatch.setattr("modules.device.write_devices_csv",
                            lambda rows, path: wrote.append(rows))
        monkeypatch.setattr(cr, "_csv_path_for", lambda ln: str(tmp_path / "d.csv"))
        cr._commit("Lab", str(tmp_path), "r2", {"ip": "203.0.113.2", "hostname": "r2"},
                   "admin", 15, PASSWORD, "", "", "t")
        row = next(r for r in wrote[0] if r["hostname"] == "r2")
        assert decrypt_field(row["password"]) == PASSWORD
        assert decrypt_field(row["secret"]) == "", "a second copy of the password"


class TestBreakGlassSaysWhatIsTrue:
    def _summary(self, secret):
        from modules import breakglass
        payload = {"devices": [{"hostname": "s1", "ip": "192.0.2.21",
                                "password": PASSWORD, "secret": secret}]}
        return breakglass.describe(payload)["devices"][0]

    def test_a_copy_of_the_password_is_not_an_enable_secret(self):
        assert self._summary(PASSWORD)["has_enable_secret"] is False

    def test_a_distinct_one_is(self):
        assert self._summary(ENABLE)["has_enable_secret"] is True


# ---------------------------------------------------------------------------
# The one-time rewrite of what is already stored
# ---------------------------------------------------------------------------

def _load_script():
    path = os.path.join(ROOT, "scripts", "nmas-credential-dedupe")
    loader = importlib.machinery.SourceFileLoader("nmas_credential_dedupe", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from modules import credentials
    from modules.device import fernet, write_devices_csv
    from modules.secrets_store import encrypt_value
    lists = tmp_path / "lists"
    (lists / "lab").mkdir(parents=True)
    monkeypatch.setattr("modules.config.LISTS_DIR", str(lists))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    enc = lambda v: fernet.encrypt(v.encode()).decode()
    csv_path = str(lists / "lab" / "devices.csv")
    write_devices_csv([
        {"hostname": "s1", "ip": "192.0.2.21", "device_type": "cisco_ios", "username": "admin",
         "password": enc(PASSWORD), "secret": enc(PASSWORD), "role": ""},
        {"hostname": "r9", "ip": "192.0.2.29", "device_type": "cisco_ios", "username": "admin",
         "password": enc(PASSWORD), "secret": enc(ENABLE), "role": ""},
    ], csv_path)
    store = tmp_path / "credential_profiles.json"
    store.write_text(json.dumps({"profiles": {}, "device_overrides": {
        "192.0.2.40": {"username": "admin", "password": encrypt_value(PASSWORD),
                       "secret": encrypt_value(PASSWORD)}}}))
    monkeypatch.setattr(credentials, "_FILE", str(store))
    return {"csv": csv_path, "store": store}


def _run(monkeypatch, *argv):
    mod = _load_script()
    monkeypatch.setattr(sys, "argv", ["nmas-credential-dedupe", *argv])
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = mod.main()
    return code, buf.getvalue()


def _secrets(csv_path):
    from modules.device import decrypt_field, load_saved_devices
    return {r["hostname"]: decrypt_field(r["secret"]) for r in load_saved_devices(csv_path)}


class TestTheRewrite:
    def test_a_dry_run_changes_nothing(self, stores, monkeypatch):
        before_csv, before_store = open(stores["csv"]).read(), stores["store"].read_text()
        code, out = _run(monkeypatch)
        assert code == 0 and "would be emptied" in out
        assert open(stores["csv"]).read() == before_csv
        assert stores["store"].read_text() == before_store

    def test_apply_empties_the_copies_and_keeps_a_real_enable_secret(self, stores, monkeypatch):
        from modules.secrets_store import decrypt_value
        code, out = _run(monkeypatch, "--apply")
        assert code == 0, out
        assert _secrets(stores["csv"]) == {"s1": "", "r9": ENABLE}
        data = json.loads(stores["store"].read_text())
        assert data["device_overrides"]["192.0.2.40"]["secret"] == ""
        assert decrypt_value(data["device_overrides"]["192.0.2.40"]["password"]) == PASSWORD

    def test_it_prints_no_value(self, stores, monkeypatch):
        _code, out = _run(monkeypatch, "--apply")
        assert PASSWORD not in out and ENABLE not in out
        assert "s1" in out and "r9" in out

    def test_an_unparseable_store_is_refused_and_left_as_it_was(self, stores, monkeypatch):
        """The store's loader reads an unreadable file as EMPTY; saving that
        would erase every credential."""
        stores["store"].write_text("{not json")
        code, out = _run(monkeypatch, "--apply")
        assert code == 1 and "REFUSED" in out
        assert stores["store"].read_text() == "{not json"
