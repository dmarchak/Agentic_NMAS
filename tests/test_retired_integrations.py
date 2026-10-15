"""A retired integration has no probe, no card and no reader (the operator, 2026-10-12).

Retiring the topology service at 7.8 removed its renderer and unit, and left its integration:
its health probe kept failing, and Needs attention drew a CRITICAL "Topology service is not
answering" for a service that was gone on purpose. A retired integration is named in
`modules.integrations.RETIRED`, with when; from then on:

- it is not in `REGISTRY`, which is what every health probe and status strip iterates
  (`all_statuses`), so nothing probes it and no row says it is down;
- it has no Settings card (`settings_page.INTEGRATIONS`), and no v2 card draws one of its keys
  (today's integrations script was scanned too, until it left at 7.8, 2026-10-15);
- its keys stay declared for one release, `retiring` in the scope table, so a rollback finds
  them, and nothing outside the declaring files reads one (found by parsing: a string
  constant equal to the key; Oxidized's test, tests/test_oxidized_settings_inert.py, is the
  same rule for its own keys).
"""

import ast
import os

import pytest

from modules import settings_page, settings_scope
from modules import integrations as I
from modules.settings_schema import DEFAULTS
from tests.test_oxidized_settings_inert import FLOOR, ROOT, python_files

#: The files that declare a retiring key, the only ones a read is excused in.
DECLARING = {"modules/settings_schema.py", "modules/settings_scope.py",
             "modules/secrets_store.py"}


def _keys(name: str) -> set:
    return {k for k in DEFAULTS if k.startswith(name + "_")}


@pytest.mark.parametrize("name", sorted(I.RETIRED))
def test_it_is_not_registered_so_nothing_probes_it(name, monkeypatch):
    assert name not in I.REGISTRY
    for cls in I.REGISTRY.values():
        monkeypatch.setattr(cls, "status", lambda self: {"ok": True, "state": "up"})
    probed = {s["name"] for s in I.all_statuses()}
    assert probed == set(I.REGISTRY) and name not in probed


@pytest.mark.parametrize("name", sorted(I.RETIRED))
def test_it_has_no_settings_card(name):
    """No v2 settings card draws it (today's Integrations script, scanned here until it left
    with today's Settings modal at 7.8, 2026-10-15): every key the network cards and the
    Installation cards draw, by their declarations."""
    from modules import installation_settings
    assert name not in settings_page.INTEGRATIONS
    drawn = {f["key"] for c in installation_settings.CARDS.values() for f in c["fields"]}
    drawn |= {k for g in settings_scope.network_groups() for k in settings_scope.group_keys(g)}
    assert len(drawn) >= 40, f"the scan of the v2 cards found {len(drawn)} fields"
    assert not drawn & _keys(name), drawn & _keys(name)


def test_the_topology_service_s_keys_are_retiring():
    keys = _keys("topology_service")
    assert keys == {"topology_service_url", "topology_service_type", "topology_service_token",
                    "topology_service_verify_tls"}
    assert {settings_scope.scope_of(k)[0] for k in keys} == {settings_scope.RETIRING}


def _reads(source: str, keys: set) -> list:
    return [(n.lineno, n.value) for n in ast.walk(ast.parse(source))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in keys]


def test_nothing_reads_the_topology_service_s_keys():
    files = python_files()
    assert len(files) >= FLOOR, len(files)
    keys = _keys("topology_service")
    found = []
    for f in files:
        if f in DECLARING:
            continue
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            found += [(f, line, key) for line, key in _reads(fh.read(), keys)]
    assert found == [], found


def test_the_scan_finds_a_planted_read():
    assert _reads('x = get_setting("topology_service_url")\n',
                  _keys("topology_service")) == [(1, "topology_service_url")]
    # Prose about a key, in a docstring or a comment, is not a read.
    assert _reads('"""topology_service_url is retired."""\n# "topology_service_url"\n',
                  _keys("topology_service")) == []
