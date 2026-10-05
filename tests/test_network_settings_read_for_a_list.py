"""P.8 step 4: a network setting is read FOR a list (NSOT_P8_DESIGN, section 6).

Two lists are two networks (the operator, 2026-09-28), so a network-scoped setting has an
answer per list. Step 4 gives every read one of two shapes:

- **for a list it carries:** `list_settings.value(list_name, key)`. A write path carries its
  list (CLAUDE.md), so an empty one is refused with `NoListCarried`, never read as Default's;
- **the Default network's, said by name:** `list_settings.default_layer(key)`, only where one
  output serves every list until P.7 (the ZTP fragment, Oxidized's router.db, the Prometheus
  targets directory), where the read is paired with an integration client still built for no
  list (steps 5 and 8 move the pair together), or below any list on the path (C462).

The second shape is an exact inventory, parsed from the code: a new Default-layer read fails
here until it is listed with its reason, and each step that threads a list through lowers a
count. The inventory only shrinks.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_READERS = {"default_layer", "default_layer_secret"}

#: file -> (calls, why). Measured 2026-10-05 when step 4a landed.
INVENTORY = {
    "modules/config_read.py": (1, "the SSH layer's read bound: a device dict carries no list (C462)"),
    "modules/nsot/onboard.py": (1, "onboarding's device sessions hold no list (C462)"),
    "modules/device_page.py": (5, "paired with the Grafana client built for no list (step 8)"),
    "modules/panels.py": (2, "paired with the Grafana client built for no list (step 8)"),
    "modules/heartbeat_windows.py": (1, "paired with the Loki it measures from (step 5)"),
    "modules/readers/coverage_reporting.py": (1, "a reader of one global integration (step 5)"),
    "modules/readers/credential_health.py": (2, "a reader of one global integration (step 5)"),
    "routes/topology_view.py": (2, "paired with the topology client built for no list (step 8)"),
    "modules/netbox_client.py": (1, "the sync that asks carries no list down to here yet"),
    "modules/host_steps.py": (2, "one Oxidized helper on the host"),
    "modules/oxidized_fetch.py": (1, "one router.db names every list's devices (P.7)"),
    "modules/nsot/credential_rotation.py": (3, "one router.db and its helper on the host (P.7)"),
    "modules/prometheus_targets.py": (1, "one targets directory serves every list (P.7)"),
    "modules/nsot/ztp.py": (4, "one Kea fragment and responder serve every list (P.7)"),
    "modules/nsot/ztp_responder.py": (1, "one Kea fragment and responder serve every list (P.7)"),
}


def default_layer_calls(paths) -> dict:
    """``{relative path: calls}`` to the Default-layer readers, by PARSING: a call by name, by
    an alias bound in an import (`default_layer as get`), or as an attribute
    (`list_settings.default_layer`). A file that only mentions the name in prose counts 0."""
    out = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        aliases = set(DEFAULT_READERS)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "modules.list_settings":
                aliases.update(a.asname or a.name for a in node.names if a.name in DEFAULT_READERS)
        n = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                # A bare name may be an alias; an attribute only by its real name (a dict's
                # `.get` is not `default_layer as get`).
                if (isinstance(f, ast.Name) and f.id in aliases) or \
                        (isinstance(f, ast.Attribute) and f.attr in DEFAULT_READERS):
                    n += 1
        if n:
            out[os.path.relpath(path, ROOT)] = n
    return out


def _program_files():
    for top in ("modules", "routes"):
        for d, _subdirs, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith(".py") and not f == "list_settings.py":
                    yield os.path.join(d, f)


class TestTheDefaultLayerReadsAreAnExactInventory:
    def test_every_default_layer_read_is_listed_with_its_reason(self):
        found = default_layer_calls(_program_files())
        assert found == {k: n for k, (n, _why) in INVENTORY.items()}, (
            "a Default-layer read was added or removed. Added: carry the list instead, or list "
            "it here with why it must be Default's. Removed: lower its count (the inventory only "
            "shrinks).")

    def test_every_entry_says_why(self):
        assert all(len(why) > 20 for _n, why in INVENTORY.values())

    def test_the_scan_finds_something(self):
        """The floor: a parse that found nothing would satisfy an empty inventory."""
        assert sum(default_layer_calls(_program_files()).values()) >= 25

    def test_the_parse_sees_each_shape_and_ignores_prose(self, tmp_path):
        """The planted case: a call by name, by alias, as an attribute, and a docstring that
        only mentions it."""
        p = tmp_path / "planted.py"
        p.write_text(
            'def a():\n'
            '    """default_layer("x") in prose is not a call."""\n'
            '    from modules.list_settings import default_layer\n'
            '    return default_layer("x")\n'
            'def b():\n'
            '    from modules.list_settings import default_layer as get\n'
            '    return get("y")\n'
            'def c():\n'
            '    from modules import list_settings\n'
            '    return list_settings.default_layer_secret("z")\n', encoding="utf-8")
        assert list(default_layer_calls([str(p)]).values()) == [3]


class TestAMissingListIsRefused:
    def test_value_refuses_an_empty_list(self):
        from modules import list_settings as L
        with pytest.raises(L.NoListCarried):
            L.value("", "deploy_max_workers", 1)

    def test_the_refusal_is_not_a_value_error(self):
        """A reader's guard against a malformed VALUE (`except (TypeError, ValueError)`) must
        never swallow a missing list into a fallback: `max_workers` had exactly that guard."""
        from modules import list_settings as L
        assert not issubclass(L.NoListCarried, (ValueError, TypeError))

    def test_a_batch_with_no_list_is_refused(self):
        from modules.list_settings import NoListCarried
        from modules.nsot import deploy
        with pytest.raises(NoListCarried):
            deploy.max_workers("")
        with pytest.raises(NoListCarried):
            deploy.CircuitBreaker()

    def test_a_settle_window_with_no_list_is_refused(self):
        from modules.list_settings import NoListCarried
        from modules.nsot import convergence
        with pytest.raises(NoListCarried):
            convergence.window_for("ospf", "")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary data folder: the lists and the global (Default) settings file."""
    from modules import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    return tmp_path


@pytest.mark.usefixtures("store")
class TestEachNetworkReadsItsOwnValue:
    """The property itself, end to end through the real store: a second list's own value
    reaches the reads that carry it, and Default's stays Default's."""

    def test_the_batch_reads_its_own_networks_tuning(self):
        from modules import list_settings as L
        from modules.nsot import convergence, deploy

        assert L.write("Branch", {"deploy_max_workers": 3, "deploy_verify_failure_limit": 4,
                                  "verify_settle_windows": {"ospf": {"timeout": 99}}})["ok"]
        assert deploy.max_workers("Branch") == 3
        assert deploy.CircuitBreaker(list_name="Branch").limit == 4
        assert convergence.window_for("ospf", "Branch")["timeout"] == 99
        # The control: the Default network is untouched by Branch's values.
        assert deploy.max_workers("Default") == 1
        assert deploy.CircuitBreaker(list_name="Default").limit == 2
        assert convergence.window_for("ospf", "Default")["timeout"] != 99

    def test_onboarding_gives_a_device_its_own_networks_syslog_block(self):
        from modules import list_settings as L
        from modules.nsot import onboard

        assert L.write("Branch", {"syslog_host": "192.0.2.77"})["ok"]
        block, error = onboard.syslog_baseline("Branch")
        assert not error and block["hosts"] == ["192.0.2.77"], (block, error)
