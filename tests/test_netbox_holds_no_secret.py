"""C95 (a): what the NetBox import writes into `local_context_data` is masked
on the way IN.

Measured on the host 2026-09-28 (R2a, on a copy of `data/`): every device's
`running_config` carried 2 credential-slot lines unmasked and the structured
`snmp.communities` carried the community in plaintext, because the import's
`_sanitise_config` was a second redactor whose username pattern did not match
the fleet's `username admin privilege 15 secret 9 ...` and which had no
community pattern at all. And the import's whole remaining device-level work
was writing that field (the operator's reading of R2a: nine of nine device
updates "change local_context_data").

Driven through the import's own builders over the nine REAL fleet configs.
The check of "masked" is independent of the code under test: a value in a
credential slot is read with its own pattern here, and must be a mask.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")

#: A credential slot and its value, read independently of `redact.py`.
SLOT = re.compile(r"^\s*(username \S+ (?:privilege \d+ )?(?:secret|password)(?: \d)?|"
                  r"snmp-server community|"
                  r"snmp-server host \S+(?: (?:informs|traps))?(?: version \S+)?|"
                  r"enable (?:secret|password)(?: \d)?|"
                  r"key-string(?: \d)?)\s+(\S+)", re.M)


def _fleet():
    names = sorted(f for f in os.listdir(FLEET) if f.endswith(".cfg"))
    assert len(names) >= 9, names
    for name in names:
        with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
            yield name, fh.read()


def _context(config):
    from modules.netbox_client import (_build_config_context,
                                       _parse_routing_context_from_config)

    return _build_config_context("x", "192.0.2.1", {}, [], [], [], config,
                                 routing_context=_parse_routing_context_from_config(config))


def test_the_fleet_has_credential_slots_to_mask():
    """The floor: a fleet with nothing in a slot would pass everything below."""
    slots = sum(len(SLOT.findall(cfg)) for _n, cfg in _fleet())
    assert slots >= 18, slots


@pytest.mark.parametrize("name,config", list(_fleet()))
def test_no_credential_slot_value_reaches_netbox(name, config):
    rc = _context(config)["running_config"]
    values = [m.group(2) for m in SLOT.finditer(rc)]
    assert values, f"{name}: the slot lines vanished; masking must keep the line"
    assert all(v.startswith("<redacted") for v in values), (name, len(values))


@pytest.mark.parametrize("name,config", list(_fleet()))
def test_the_structured_community_carries_no_value(name, config):
    communities = ((_context(config).get("snmp") or {}).get("communities")) or []
    real = re.findall(r"^snmp-server community (\S+)", config, re.M)
    assert len(communities) == len(real), "what a community grants is still recorded"
    for c in communities:
        assert set(c) == {"permission"}, c
    # Checked in the STRUCTURED field only: the fleet's community `public` is
    # also an ordinary word in an interface description ("simulated public"),
    # deliberately left alone, and the running config's community line is
    # covered slot by slot above. A whole-context substring search matched
    # the description (a pattern that can appear in English needs an anchor).
    snmp = str(_context(config).get("snmp") or {})
    for value in real:
        assert value not in snmp, f"{name}: a community value reached the structured field"
