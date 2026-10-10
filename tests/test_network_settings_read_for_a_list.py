"""P.8 step 4: a network setting is read FOR a list (NSOT_P8_DESIGN, section 6).

Two lists are two networks (the operator, 2026-09-28), so a network-scoped setting has an
answer per list. Step 4 gives every read one of two shapes:

- **for a list it carries:** `list_settings.value(list_name, key)`. A write path carries its
  list (CLAUDE.md), so an empty one is refused with `NoListCarried`, never read as Default's;
- **the Default network's, said by name:** `list_settings.default_layer(key)`, only where one
  output serves every list until P.7 (the ZTP fragment, the Prometheus
  targets directory), where the read is paired with an integration client still built for no
  list (steps 5 and 8 move the pair together), or below any list on the path (C462).

The second shape is an exact inventory, parsed from the code: a new Default-layer read fails
here until it is listed with its reason, and each step that threads a list through lowers a
count. The inventory only shrinks.
"""

import ast
import os

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_READERS = {"default_layer", "default_layer_secret"}

#: file -> (calls, why). Measured 2026-10-05 when step 4a landed.
INVENTORY = {
    "modules/config_read.py": (1, "the SSH layer's read bound: a device dict carries no list (C462)"),
    "modules/nsot/onboard.py": (1, "onboarding's device sessions hold no list (C462)"),
    "modules/heartbeat_windows.py": (1, "paired with the Loki it measures from (step 5)"),
    "modules/readers/coverage_reporting.py": (1, "a reader of one global integration (step 5)"),
    "modules/readers/credential_health.py": (2, "a reader of one global integration (step 5)"),
    "routes/topology_view.py": (2, "paired with the topology client built for no list (step 8)"),
    "modules/netbox_client.py": (1, "the sync that asks carries no list down to here yet"),
    "modules/prometheus_targets.py": (1, "one targets directory serves every list (P.7)"),
    "modules/nsot/ztp.py": (4, "one Kea fragment and responder serve every list (P.7)"),
    "modules/nsot/ztp_responder.py": (1, "one Kea fragment and responder serve every list (P.7)"),
    "modules/attention.py": (1, "a declared expiry beside the Default network's clients (step 5)"),
    "modules/host_helpers.py": (1, "one topology renderer on the host"),
    "modules/monitoring_coverage.py": (2, "rows() answers every list from one read (step 5)"),
    "routes/settings_integrations.py": (3, "the general Settings form writes the global file, "
                                           "the Default network's layer (step 7)"),
}

#: file -> (calls, why): a global reader called with a COMPUTED key, which a parse cannot judge.
#: Each is read by hand and holds only host-wide (or dead) keys, or is the Default layer by
#: construction. Measured 2026-10-05 (step 4b); only shrinks.
COMPUTED = {
    "modules/identity.py": (1, "its `_setting` wrapper: cf_access_* and identity keys, host-wide"),
    "modules/integrations/base.py": (2, "a client built for no list reads the global file, the "
                                        "Default network's layer; tests inject through these names"),
    "modules/readers/credential_health.py": (1, "a loop over (`proxmox_url`,): host-wide"),
    "modules/installation_settings.py": (4, "the Installation cards' field keys (`CARDS`, boards "
                                            "F3 and F4): netbox_connection, proxmox, git_author, "
                                            "web_server and ai; and the Access and identity "
                                            "tab's ACCESS_CARD_KEYS and SERVICE_CARD_KEYS, the "
                                            "identity group's: every one host-wide"),
    "modules/records_db.py": (1, "`backend(store)`: records_store_<store> for each of STORES "
                                 "(receipts), the records_db group's: host-wide"),
}


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _in_scope(node):
    """The nodes of *node*'s own scope, never descending into a nested function."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, _FUNCTIONS):
            stack.extend(ast.iter_child_nodes(n))


def reader_calls(tree, readers: dict) -> list:
    """Every call to one of *readers* (``{name: its module}``) in *tree*: by its own name, as an
    attribute, or by an alias an import binds. An alias holds in the scope that imports it
    (the module, or one function and what it nests), never module-wide: `get` imported as a
    reader in one function is another function's own `get` elsewhere. A bare name may be an
    alias; an attribute counts only by its real name (a dict's `.get` is no reader)."""
    found = []

    def scope(node, inherited):
        names = set(inherited)
        for n in _in_scope(node):
            if isinstance(n, ast.ImportFrom):
                names.update(a.asname or a.name for a in n.names
                             if readers.get(a.name) == n.module)
        for n in _in_scope(node):
            if isinstance(n, _FUNCTIONS):
                scope(n, names)
            elif isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Name) and f.id in names) or \
                        (isinstance(f, ast.Attribute) and f.attr in readers):
                    found.append(n)

    scope(tree, set(readers))
    return found


def _parse(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def default_layer_calls(paths) -> dict:
    """``{relative path: calls}`` to the Default-layer readers, by PARSING (`reader_calls`). A
    file that only mentions the name in prose counts 0."""
    readers = {name: "modules.list_settings" for name in DEFAULT_READERS}
    out = {}
    for path in paths:
        n = len(reader_calls(_parse(path), readers))
        if n:
            out[os.path.relpath(path, ROOT)] = n
    return out


def _program_files():
    for path in tracked("modules", "routes", suffix=".py"):
        if not os.path.basename(path) == "list_settings.py":
            yield path


#: The global readers. Called with a NETWORK key, they answer the global file, which is only
#: the Default network's layer: for another list it is the wrong network's value.
GLOBAL_READERS = {"get_setting": "modules.settings_schema", "get_secret": "modules.secrets_store"}
#: The settings machinery itself: the resolver, the schema and the secrets store, whose reads
#: ARE the layers.
MACHINERY = {"modules/list_settings.py", "modules/settings_schema.py",
             "modules/secrets_store.py", "modules/settings_scope.py"}


def settings_reads(paths) -> tuple:
    """``(literal, computed)`` over *paths*, by PARSING: ``literal`` lists each
    ``file:line key`` where a global reader is called with a NETWORK key written as a string;
    ``computed`` is ``{file: calls}`` whose key is not a string literal (a variable, a loop, a
    wrapper's parameter), which a parse cannot judge and so each is listed by hand. A global
    reader is matched by name, by an import alias, or as an attribute."""
    from modules.settings_scope import NETWORK, SCOPES

    network = {k for k, (scope, _g) in SCOPES.items() if scope == NETWORK}
    literal, computed = [], {}
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        if rel in MACHINERY:
            continue
        for node in reader_calls(_parse(path), GLOBAL_READERS):
            if not node.args:
                continue
            key = node.args[0]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value in network:
                    literal.append(f"{rel}:{node.lineno} {key.value}")
            else:
                computed[rel] = computed.get(rel, 0) + 1
    return literal, computed


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
        assert sum(default_layer_calls(_program_files()).values()) >= 20   # 22 after Phase 3

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


class TestNoNetworkKeyIsReadPastItsList:
    """Step 4b: the global readers never answer a network key outside the settings machinery.
    Refused by PARSING rather than at run time: 84 test seams inject settings by patching
    `get_setting`, and a run-time refusal would cut every one of them while seeing nothing a
    parse cannot (2026-10-05)."""

    def test_no_global_reader_is_given_a_network_key(self):
        literal, _computed = settings_reads(_program_files())
        assert literal == [], (
            "a network key read through the global file answers Default's value for every "
            "list: read it with list_settings.value(list, key), or default_layer(key) listed "
            "with its reason")

    def test_every_computed_key_read_is_listed(self):
        _literal, computed = settings_reads(_program_files())
        assert computed == {k: n for k, (n, _why) in COMPUTED.items()}, (
            "a global reader with a computed key was added or removed: read it by hand, and "
            "list it with the keys it can be given, or lower its count")

    def test_the_scan_sees_each_shape(self, tmp_path):
        """The planted case: a literal network key by name, by alias and as an attribute; a
        host key (allowed); a computed key; and an alias imported in another function, which
        is that function's alone."""
        p = tmp_path / "planted.py"
        p.write_text(
            'def a():\n'
            '    from modules.settings_schema import get_setting\n'
            '    get_setting("grafana_url")\n'
            '    get_setting("flask_port")\n'
            'def b():\n'
            '    from modules.settings_schema import get_setting as get\n'
            '    get("loki_url")\n'
            'def c(get):\n'
            '    get("prometheus_url")\n'
            'def d(key):\n'
            '    from modules import secrets_store\n'
            '    secrets_store.get_secret("grafana_token")\n'
            '    secrets_store.get_secret(key)\n', encoding="utf-8")
        literal, computed = settings_reads([str(p)])
        assert sorted(x.split(" ")[1] for x in literal) == ["grafana_token", "grafana_url", "loki_url"]
        assert list(computed.values()) == [1]


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
