"""A saved fix is one object, every older kind read as one, and it belongs to the network it
was saved on (3a659d6b and 4816fadb, the operator, 2026-11-16, C3849; `modules/nsot/
saved_plans.py` `as_fix`, `fixes`, `scripts`, `actions`). The debt pass, 2026-11-18
(docs/FAST_LANE_DEBT.md's row for C3849 piece 1 and the network rule).

- **Each old kind read as a fix:** an old ``script`` is its network's, never shared, out of
  the catalog, its match kept; an old ``action`` is the network its run was on, never shared,
  in the catalog, with no match and no mode; a ``fix`` keeps its own network and sharing. The
  stored entry is never rewritten (`as_fix` reads a copy).
- **Whose it is:** a network may use its own fixes and the shared ones; another network's
  unshared fix is not its; only its own matched fixes are offered and fired (`scripts`); a
  deleted one is none of them.
The store is written as its file, under a temporary data folder; no device.
"""
import json
import os

import pytest

from modules.nsot import saved_plans as S

ENTRIES = {
    "sp-script": {"kind": "script", "name": "BPDU recovery", "network": "Lab",
                  "match": {"condition": "err_disabled"}, "mode": "auto", "template": {}},
    "sp-action": {"kind": "action", "name": "Bounce interface", "from_run": {"network": "Lab"},
                  "match": {"condition": "down"}, "mode": "auto", "template": {}},
    "sp-own": {"kind": "fix", "name": "Clear the session", "network": "Lab", "shared": False,
               "match": {}, "template": {}},
    "sp-shared": {"kind": "fix", "name": "Re-add the receiver", "network": "Other",
                  "shared": True, "match": {}, "template": {}},
    "sp-gone": {"kind": "script", "name": "Old recovery", "network": "Lab", "retired": True,
                "match": {"condition": "err_disabled"}, "mode": "auto", "template": {}},
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    S._READ.clear()
    path = os.path.join(str(tmp_path), S.STORE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"plans": ENTRIES}, fh)
    return path


class TestEachOldKind:
    def test_an_old_script_is_its_networks_never_shared_out_of_the_catalog(self):
        f = S.as_fix(dict(ENTRIES["sp-script"]))
        assert (f["kind"], f["saved_as"], f["network"], f["shared"], f["catalog"]) == (
            S.FIX, "script", "Lab", False, False)
        assert f["match"] == {"condition": "err_disabled"} and f["how"] == "automatic"

    def test_an_old_action_is_its_runs_network_in_the_catalog_with_no_match(self):
        f = S.as_fix(dict(ENTRIES["sp-action"]))
        assert (f["saved_as"], f["network"], f["shared"], f["catalog"]) == (
            "action", "Lab", False, True)
        assert (f["match"], f["fills"], f["mode"], f["how"]) == ({}, {}, "", "manual")

    def test_a_fix_keeps_its_own_network_and_sharing_and_the_entry_is_not_rewritten(self):
        e = dict(ENTRIES["sp-shared"])
        f = S.as_fix(e)
        assert (f["saved_as"], f["network"], f["shared"], f["catalog"]) == (
            "fix", "Other", True, True)
        assert e == ENTRIES["sp-shared"], "a copy read, the entry unchanged"
        assert f["version"] == 1


class TestWhoseItIs:
    def test_a_network_uses_its_own_and_the_shared_ones(self, store):
        assert sorted(S.fixes("Lab")) == ["sp-action", "sp-own", "sp-script", "sp-shared"]
        assert sorted(S.fixes("Other")) == ["sp-shared"], "another network's unshared: not its"
        assert sorted(S.actions("Other")) == ["sp-shared"]

    def test_only_its_own_matched_fixes_are_offered_and_fired_and_never_a_deleted_one(
            self, store):
        assert sorted(S.scripts("Lab")) == ["sp-script"], "an old action carries no match"
        assert S.scripts("Other") == {}
        assert "sp-gone" not in S.fixes() and "sp-gone" in S.fixes(deleted=True)
