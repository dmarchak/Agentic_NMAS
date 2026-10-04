"""P.8 step 3: integration clients are built FOR a network (NSOT_P8_DESIGN, section 4).

Every client read the global store itself, so none could be given a list. Now each reads ONLY
through the base class's `_setting` and `_secret`, which resolve through `list_settings` for the
client's `list_name`, and through the global store for none. The shape is constrained, not the
members enumerated: a parse of `modules/integrations/` refuses any direct `get_setting` or
`get_secret` call outside the base class, so a client added later cannot read past its list.
"""

import ast
import json
import os

import pytest

from modules import config
from modules.integrations import REGISTRY, get_integration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, "modules", "integrations")


def test_no_client_reads_a_setting_past_its_list():
    found = []
    names = sorted(n for n in os.listdir(FOLDER) if n.endswith(".py"))
    assert len(names) >= 12, "the population shrank: the clients moved?"
    for name in names:
        if name in ("base.py", "__init__.py"):
            continue
        tree = ast.parse(open(os.path.join(FOLDER, name), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                called = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                owner = getattr(getattr(fn, "value", None), "id", "")
                if called in ("get_setting", "get_secret") and owner != "self":
                    found.append(f"{name}:{node.lineno} {called}")
    assert found == [], f"clients reading the global store directly: {found}"


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules.secrets_store import encrypt_value

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({
        "prometheus_url": "http://192.0.2.10:9090", "grafana_url": "http://192.0.2.10:3000",
        "grafana_token": encrypt_value("default-token")}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    return tmp_path


def test_a_client_for_a_list_reads_that_lists_values(store):
    from modules import list_settings

    list_settings.write("Branch", {"prometheus_url": "http://192.0.2.20:9090"})
    assert get_integration("prometheus", list_name="Branch").url == "http://192.0.2.20:9090"
    assert get_integration("prometheus").url == "http://192.0.2.10:9090"
    assert get_integration("prometheus", list_name="Default").url == "http://192.0.2.10:9090"
    assert get_integration("prometheus", list_name="Other").url == "http://192.0.2.10:9090"


def test_a_lists_own_grafana_never_carries_defaults_token(store):
    from modules import list_settings

    list_settings.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})
    g = get_integration("grafana", list_name="Branch")
    assert g.url == "http://192.0.2.20:3000"
    assert "Authorization" not in g._auth_headers(), "Default's token went to another Grafana"
    assert get_integration("grafana")._auth_headers()["Authorization"].endswith("default-token")
    assert g.get_config()["_secrets"]["grafana_token"] is False


def test_a_save_for_a_list_writes_that_lists_store_never_the_global_file(store):
    before = (store / "user_settings.json").read_text(encoding="utf-8")
    out = get_integration("kea", list_name="Branch").save_config(
        {"kea_url": "http://192.0.2.30:8000", "kea_username": "k", "kea_password": "p"})
    assert out["ok"] is True, out
    assert (store / "user_settings.json").read_text(encoding="utf-8") == before
    kea = get_integration("kea", list_name="Branch")
    assert kea.url == "http://192.0.2.30:8000" and kea._secret("kea_password") == "p"


def test_every_registered_client_takes_a_list():
    for name in REGISTRY:
        assert get_integration(name, list_name="Branch").list_name == "Branch", name
