"""Shared intent layers, the merge (board FC phase 1, PHASE8_PLAN 22.1 (a); C2283).

`modules/nsot/intent_layers.merge` alone, on the board's worked example (a lab account on a tag's
devices, the admin account on the network, the SNMP location a device overrides):

- **No layer** is the device's own document, unchanged, every leaf "this device".
- **Rank order:** network, site, role, tag, then the device: a later value wins; dicts merge;
  a keyed list merges entry by entry (a layer's `users[lab]` joins the device's `users[admin]`;
  the device's own entry with the same key replaces the layer's whole); an empty later value
  never replaces.
- **Provenance:** each leaf names the layer that supplied it.
- **Same rank, different values** (two tags) is a conflict naming both, never resolved; the same
  value is no conflict.
- **What a layer may carry:** `interfaces` and `routing` refused, a list no key names refused,
  an entry with no key or a repeated key refused.
"""

import copy

from modules.nsot import intent_layers as L

DEVICE = {"hostname": "edge1",
          "users": [{"name": "admin", "privilege": 15, "secret_ref": "user_admin_secret"}],
          "interfaces": [{"name": "GigabitEthernet2", "ip": "192.0.2.1/30"}],
          "snmp": {"settings": ["location rack 2, row b"]}}
NETWORK = ("network", "network default",
           {"users": [{"name": "admin", "privilege": 15, "secret_ref": "user_admin_secret"}],
            "ntp": {"servers": ["192.0.2.123"]}})
SITE = ("site", "site lab-a", {"snmp": {"settings": ["location lab-a"]}})
TAG = ("tag", "tag blind-lab",
       {"users": [{"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret",
                   "secret_kind": "secret"}]})


class TestTheMerge:
    def test_no_layer_is_the_device_s_own_document(self):
        got = L.merge([], copy.deepcopy(DEVICE))
        assert got["doc"] == DEVICE and got["conflicts"] == [] and got["problems"] == []
        assert set(got["from"].values()) == {L.DEVICE}

    def test_a_tag_s_account_joins_the_device_s_and_each_says_where_it_came_from(self):
        got = L.merge([TAG, NETWORK, SITE], copy.deepcopy(DEVICE))
        users = {u["name"]: u for u in got["doc"]["users"]}
        assert set(users) == {"admin", "lab"}, got["doc"]["users"]
        assert got["from"]["users[lab]"] == "tag blind-lab"
        assert got["from"]["users[admin]"] == L.DEVICE, "the device's own entry wins"
        assert got["from"]["ntp.servers"] == "network default"
        assert got["doc"]["ntp"] == {"servers": ["192.0.2.123"]}

    def test_the_device_overrides_a_site_s_value_by_its_key(self):
        got = L.merge([SITE], copy.deepcopy(DEVICE))
        assert got["doc"]["snmp"]["settings"] == ["location rack 2, row b"]
        assert got["from"]["snmp.settings[location]"] == L.DEVICE

    def test_a_later_rank_wins_whatever_the_order_given(self):
        role = ("role", "role edge-router", {"ntp": {"servers": ["192.0.2.124"]}})
        for order in ([NETWORK, role], [role, NETWORK]):
            got = L.merge(order, {"hostname": "edge1"})
            assert got["doc"]["ntp"]["servers"] == ["192.0.2.124"]
            assert got["from"]["ntp.servers"] == "role edge-router"

    def test_an_empty_later_value_never_replaces(self):
        got = L.merge([NETWORK], {"hostname": "edge1", "ntp": {"servers": []}})
        assert got["doc"]["ntp"]["servers"] == ["192.0.2.123"]
        assert got["from"]["ntp.servers"] == "network default"


class TestSameRank:
    def test_two_tags_setting_one_path_differently_are_a_conflict_naming_both(self):
        other = ("tag", "tag core", {"users": [{"name": "lab", "privilege": 1,
                                                "secret_ref": "user_lab_secret"}]})
        got = L.merge([TAG, other], {"hostname": "edge1"})
        (c,) = got["conflicts"]
        assert c["path"] == "users[lab]" and c["rank"] == "tag"
        assert [label for label, _v in c["layers"]] == ["tag blind-lab", "tag core"]

    def test_the_same_value_from_two_tags_is_no_conflict(self):
        same = ("tag", "tag core", copy.deepcopy(TAG[2]))
        assert L.merge([TAG, same], {"hostname": "edge1"})["conflicts"] == []

    def test_different_ranks_are_never_a_conflict(self):
        role = ("role", "role edge-router", {"ntp": {"servers": ["192.0.2.124"]}})
        assert L.merge([NETWORK, role], {"hostname": "edge1"})["conflicts"] == []


class TestWhatALayerMayCarry:
    def test_interfaces_and_routing_are_refused_naming_each(self):
        got = L.problems({"interfaces": [], "routing": {"ospf": []}})
        assert got == ["interfaces describes one device, so a layer cannot carry it",
                       "routing describes one device, so a layer cannot carry it"]

    def test_a_list_of_entries_no_key_names_is_refused_and_plain_values_are_one_value(self):
        got = L.problems({"ntp": {"servers": ["192.0.2.123"]},
                          "banners": [{"type": "motd", "text": "x"}]})
        assert got == ["banners is a list of entries no key names, so a layer cannot merge "
                       "it entry by entry"], got

    def test_an_entry_with_no_key_or_a_repeated_key_is_refused(self):
        got = L.problems({"users": [{"privilege": 15}, {"name": "lab"}, {"name": "lab"}]})
        assert got == ["users: an entry with no key (None)",
                       "users: an entry with a repeated key ('lab')"], got

    def test_a_layer_s_problems_are_returned_by_the_merge_with_its_label(self):
        got = L.merge([("network", "network default", {"interfaces": []})], {"hostname": "e"})
        assert got["problems"] == ["network default: interfaces describes one device, so a "
                                   "layer cannot carry it"]

    def test_every_list_the_key_table_names_is_a_list_the_intent_schema_has(self):
        # The table keys only what intent holds (hostvars.INTENT_SECTIONS), never a guess.
        from modules.nsot import hostvars
        schema = {p[:-2].replace("[].", ".") for p in hostvars.INTENT_SECTIONS
                  if p.endswith("[]")}
        assert set(L.KEYS) <= schema | {"snmp.settings"}, set(L.KEYS) - schema
