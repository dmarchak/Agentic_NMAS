"""P.8 step 1: every setting declares its scope and group (NSOT_P8_DESIGN, section 2).

The resolver P.8 builds next reads this table, so a setting with no row would be read from the
wrong layer the day lists become networks. The population is every key the schema declares
(`settings_schema.DEFAULTS`), with a floor at the 143 measured on 2026-10-04; a row for a key
the schema does not hold is a ghost. Groups are checked against what must inherit together: a
connection with its credential (an integration inherits as a GROUP, never key by key).
"""

import pytest

from modules import settings_scope as S
from modules.settings_schema import DEFAULTS
from modules.secrets_store import SECRET_KEYS


def test_every_declared_setting_has_exactly_one_scope():
    assert len(DEFAULTS) >= 143, "the population shrank below its measured floor"
    missing = sorted(set(DEFAULTS) - set(S.SCOPES))
    ghosts = sorted(set(S.SCOPES) - set(DEFAULTS))
    assert missing == [], f"settings with no scope: {missing}"
    assert ghosts == [], f"scopes for settings the schema does not hold: {ghosts}"
    assert {s for s, _g in S.SCOPES.values()} <= {S.NETWORK, S.HOST, S.RETIRING, S.DEAD}


def test_a_credential_inherits_with_its_connection():
    """Every network-scoped secret sits in a group that also holds a URL or an address, so a
    list setting its own endpoint can never inherit Default's credential for it."""
    for key in SECRET_KEYS:
        scope, group = S.scope_of(key) if key in S.SCOPES else (None, None)
        if scope != S.NETWORK:
            continue
        keys = S.group_keys(group)
        assert any(k.endswith(("_url", "_endpoint")) for k in keys), (key, group, keys)


@pytest.mark.parametrize("key,scope", [
    ("grafana_fleet_dashboard_uid", S.NETWORK), ("grafana_device_dashboard_uid", S.NETWORK),
    ("netbox_url", S.HOST), ("netbox_token", S.HOST), ("platform_map", S.HOST),
    ("yang_push_script", S.HOST), ("promql_cpu", S.RETIRING), ("nsot_git_token", S.DEAD)])
def test_the_operators_decisions_are_the_table(key, scope):
    """2026-09-28 (the NetBox connection is global, its scope per list; the maps are global),
    2026-09-30 (the Grafana roles per network) and 2026-10-04 (yang_push_script global; the
    form-only keys to retire)."""
    assert S.scope_of(key)[0] == scope


def test_an_undeclared_key_is_named():
    with pytest.raises(KeyError, match="'no_such_key' has no scope"):
        S.scope_of("no_such_key")
