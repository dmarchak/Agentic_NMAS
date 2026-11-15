"""NetBox's prefix read for the DHCP reservation plan's subnet lookup (modules/ai/netbox_reads.py;
`plan_engine.netbox_prefix_found`, B1): read only, a fixed field list, bounded, outside the AI's
read loop (the operator, 2026-11-14, C3719; tests/test_ai_read_loop_never_reaches_netbox.py).

NetBox is tests/netbox_fake.py's `FakeNetBox` (NetBox 4's list shape; any method but GET fails
the test).

- **No write is reachable:** the module's syntax tree holds no call of a write method (post,
  patch, put, delete, request), no NetBox write helper and no write verb; a planted one is
  found.
- **A fixed field list:** custom fields, comments and contacts never leave; a known person's
  name in a field that is read is their label.
- **Bounded:** one page; a count past it is said ("20 shown of 57").
- **An absence is a fact;** NetBox not configured, or not answering, is said, never read as
  nothing found. IPv6 beside IPv4; an argument not of its shape is refused before anything is
  asked.
"""
import ast
import os

import pytest

from modules.ai import netbox_reads as NR
from tests.netbox_fake import NETBOX, FakeNetBox, netbox  # noqa: F401 (the fixture)

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules",
                      "ai", "netbox_reads.py")
WRITE_METHODS = {"post", "patch", "put", "delete", "request", "send"}
WRITE_HELPERS = {"_nb_post", "_nb_patch", "_nb_delete", "_nb_put", "_ensure_tag",
                 "add_journal_entry"}
WRITE_VERBS = {"POST", "PATCH", "PUT", "DELETE"}
PREFIXES = "/api/ipam/prefixes/"


def writes_in(source: str) -> list:
    """Every write reachable in *source*, by its syntax tree: a call of a write method, a
    NetBox write helper named (imported or called), a write verb as a string."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in WRITE_METHODS:
            found.append(f"line {node.lineno}: .{node.func.attr}(")
        if isinstance(node, ast.ImportFrom):
            found += [f"line {node.lineno}: imports {a.name}" for a in node.names
                      if a.name in WRITE_HELPERS]
        if isinstance(node, ast.Name) and node.id in WRITE_HELPERS:
            found.append(f"line {node.lineno}: names {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in WRITE_HELPERS:
            found.append(f"line {node.lineno}: names {node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and \
                node.value.upper() in WRITE_VERBS:
            found.append(f"line {node.lineno}: the verb {node.value!r}")
    return found


class TestNoWriteIsReachable:
    def test_the_module_holds_no_write(self):
        with open(SOURCE, encoding="utf-8") as fh:
            source = fh.read()
        assert "session.get(" in source, "the floor: the scan reads the module's one GET"
        assert writes_in(source) == []

    @pytest.mark.parametrize("planted", [
        "session.post(url, json={})",
        "from modules.netbox_client import _nb_patch",
        "s.delete(url)",
        "requests.request('DELETE', url)",
        "method = 'PATCH'",
    ])
    def test_a_planted_write_is_found(self, planted):
        assert writes_in(f"def f(session, url, s, requests):\n    {planted}\n"), planted

    def test_its_one_read_is_the_plans_prefix_read(self):
        assert set(NR.KINDS) == {"netbox_prefixes"}
        assert NR.KINDS["netbox_prefixes"].path == PREFIXES


class TestTheRead:
    def test_a_prefix_containing_an_address_ipv4_and_ipv6(self, netbox):  # noqa: F811
        v4 = NR.read("netbox_prefixes", {"contains": "192.0.2.50"})
        v6 = NR.read("netbox_prefixes", {"contains": "2001:db8:50::50"})
        assert [r["prefix"] for r in v4["rows"]] == ["192.0.2.0/24"]
        assert [r["prefix"] for r in v6["rows"]] == ["2001:db8:50::/64"]
        assert v4["said"] == "1 prefix found" and v4["source"] == \
            "NetBox › IPAM › Prefixes (GET /api/ipam/prefixes/)"
        assert netbox.sent == [
            ("GET", PREFIXES, {"contains": "192.0.2.50", "limit": NR.PAGE}),
            ("GET", PREFIXES, {"contains": "2001:db8:50::50", "limit": NR.PAGE})]

    def test_an_absent_prefix_is_a_fact_ipv4_and_ipv6(self, netbox):  # noqa: F811
        for address in ("198.51.100.7", "2001:db8:99::7"):
            got = NR.read("netbox_prefixes", {"contains": address})
            assert (got["state"], got["count"], got["rows"]) == ("ok", 0, [])
            assert got["said"] == f"no NetBox prefix contains {address}"

    def test_only_the_fixed_fields_are_read(self, netbox):  # noqa: F811
        got = NR.read("netbox_prefixes", {"contains": "192.0.2.9"})
        (row,) = got["rows"]
        assert set(row) == {"prefix", "status", "vrf", "role", "vlan", "site", "description"}
        assert "planted" not in repr(got), "no custom field or comment"

    @pytest.mark.parametrize("contains", ["192.0.2.77", "2001:db8:50::77"])
    def test_no_email_or_contact_name_is_read(self, monkeypatch, contains):
        """The operator, 2026-11-14 (Part A's gate): no email and no person's name, a stable
        label only. Contacts, tenants, comments, custom fields and journal entries are never
        read (the fixed fields); a known person's name or email in a field that is read (the
        description) becomes their label."""
        from modules import display_names

        email, name = "jane.doe@example.org", "Jane Doe"
        display_names.set_name(email, name, by=email, actor_verified="access")
        planted = {"id": 77, "prefix": "192.0.2.0/24" if "." in contains else "2001:db8:50::/64",
                   "status": {"value": "active"},
                   "description": f"printers: ask {name} or {email}",
                   "tenant": {"name": "Doe Printing"}, "contacts": [{"name": name}],
                   "comments": f"call {name}", "custom_fields": {"owner": email},
                   "journal_entries": [{"comments": f"{name} moved it"}]}
        nb = FakeNetBox({PREFIXES: [planted]})
        monkeypatch.setattr(NR, "_ready", lambda: (True, "", nb, "http://netbox.invalid"))
        got = NR.read("netbox_prefixes", {"contains": contains})
        assert got["rows"], got
        read = repr(got)
        assert "Doe Printing" not in read, "a tenant, comment or custom field was read"
        assert name not in read and email not in read, read
        assert display_names.label(email) in read, "the population: the description was read"

    def test_one_page_and_the_rest_is_said(self, monkeypatch):
        many = {PREFIXES: [{"prefix": "198.51.100.0/24", "description": f"copy {n}"}
                           for n in range(NR.PAGE)]}
        nb = FakeNetBox(many, count={PREFIXES: 57})
        monkeypatch.setattr(NR, "_ready", lambda: (True, "", nb, "http://netbox.invalid"))
        got = NR.read("netbox_prefixes", {"prefix": "198.51.100.0/24"})
        assert (got["shown"], got["count"], got["truncated"]) == (NR.PAGE, 57, True)
        assert got["said"].startswith(f"{NR.PAGE} shown of 57 prefixes: the rest were not read")

    @pytest.mark.parametrize("args, words", [
        ({}, "needs one of contains or prefix"),
        ({"contains": "192.0.2.0/24&limit=1000"}, "is not one IPv4 or IPv6 address"),
        ({"prefix": "2001:db8::1"}, "is not one IPv4 or IPv6 prefix"),
        ({"device": "r2"}, "takes no argument 'device'"),
    ])
    def test_a_read_not_of_its_shape_is_not_asked(self, netbox, args, words):  # noqa: F811
        got = NR.read("netbox_prefixes", args)
        assert got["state"] == "refused" and words in got["why"], got["why"]
        assert netbox.sent == []

    def test_not_configured_and_not_answering_are_said(self, monkeypatch):
        monkeypatch.setattr(NR, "_ready", lambda: (False, "NetBox URL and API token are not "
                                                          "configured", None, ""))
        got = NR.read("netbox_prefixes", {"contains": "192.0.2.50"})
        assert got["state"] == "unconfigured" and "not configured" in got["said"]
        nb = FakeNetBox(NETBOX, down=True)
        monkeypatch.setattr(NR, "_ready", lambda: (True, "", nb, "http://netbox.invalid"))
        got = NR.read("netbox_prefixes", {"contains": "2001:db8:50::50"})
        assert (got["state"], got["said"]) == (
            "failed", "not read: NetBox did not answer (ConnectionError)")
