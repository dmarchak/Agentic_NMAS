"""C529 step 5, the subnet move's plan (`modules/dhcp_subnets.py`), on the host's own Kea main
files as captured 2026-10-11 (tests/fixtures/kea/kea-dhcp4.conf and kea-dhcp6.conf, after step
2: each subnet already takes its reservations from Mercury's file).

- the subnet array moves VERBATIM into Mercury's file (comments, layout and the reservation
  includes kept), and Kea's file keeps one include in its place, nothing else changed;
- a file already moved reads as done; a "shared-networks" key, a subnet key found other than
  once, or a value that is not an array is refused by name;
- a key named inside a comment or a string is not the key.
(That Kea 2.4.1 resolves the include inside an included file was measured on the host's own
kea-dhcp4 and kea-dhcp6 -t before this was relied on: docs/OPEN_FINDINGS.md, C529.)
"""

import json
import os
import re

import pytest

from modules import dhcp_subnets as S

KEA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "kea")


def _main(name):
    with open(os.path.join(KEA, name), encoding="utf-8") as fh:
        return fh.read()


def _strip(text):
    """The text as JSON: comments and include directives removed (enough to read the shape)."""
    text = re.sub(r"<\?include \"[^\"]+\"\?>", "[]", text)
    return re.sub(r"(?m)^\s*(//|#).*$", "", text)


@pytest.mark.parametrize("family, name, key, ids", [
    ("IPv4", "kea-dhcp4.conf", "subnet4", [10, 20, 255]),
    ("IPv6", "kea-dhcp6.conf", "subnet6", [10, 20, 30]),
])
def test_the_array_moves_verbatim_and_one_include_takes_its_place(family, name, key, ids):
    main = f"/etc/kea/{name}"
    text = _main(name)
    p = S.move_plan(text, main, family)
    assert p["state"] == "move" and p["refused"] == ""
    assert p["file"] == f"/etc/kea/nmas/subnets{family[-1]}.json"
    moved = p["subnets_text"].rstrip("\n")
    assert moved in text, "verbatim"
    assert moved.startswith("[") and moved.endswith("]")
    assert [s["id"] for s in json.loads(_strip(moved))] == ids
    assert moved.count("<?include") == len(ids), "every subnet's reservation include kept"
    assert p["candidate"] == text.replace(moved, f'<?include "{p["file"]}"?>')
    assert f'"{key}": <?include "{p["file"]}"?>' in p["candidate"]
    again = S.move_plan(p["candidate"], main, family)
    assert again["state"] == "done", "a file already moved is left alone"


def test_the_ipv6_file_s_comments_stay_in_kea_s_file():
    text = _main("kea-dhcp6.conf")
    p = S.move_plan(text, "/etc/kea/kea-dhcp6.conf", "IPv6")
    head = text.split('"subnet6"')[0]
    assert head.count("//") >= 10 and p["candidate"].startswith(head)


def test_shared_networks_are_refused():
    text = _main("kea-dhcp4.conf").replace('"subnet4": [', '"shared-networks": [], "subnet4": [')
    p = S.move_plan(text, "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "refused" and '"shared-networks"' in p["refused"]


def test_a_key_in_a_comment_or_a_string_is_not_the_key():
    text = _main("kea-dhcp4.conf")
    noisy = text.replace('"subnet4": [',
                         '// "subnet4": [ in a comment\n"comment": "\\"subnet4\\": [",\n'
                         '"subnet4": [', 1)
    p = S.move_plan(noisy, "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "move", p["refused"]


@pytest.mark.parametrize("change, words", [
    (lambda t: t.replace('"subnet4": [', '"subnet4": [], "x": { "subnet4": [', 1) + "}",
     "found 2 times"),
    (lambda t: t.replace('"subnet4": [', '"subnet4": { "a": [', 1), "is not an array"),
], ids=["twice", "not-an-array"])
def test_what_is_not_one_array_is_refused_by_name(change, words):
    p = S.move_plan(change(_main("kea-dhcp4.conf")), "/etc/kea/kea-dhcp4.conf", "IPv4")
    assert p["state"] == "refused" and words in p["refused"]


# --- the host step's proof: before and after, compared ----------------------------------------

def _tool():
    import importlib.machinery
    import importlib.util
    path = os.path.join(os.path.dirname(KEA), "..", "..", "scripts", "nmas-kea-subnet-files")
    loader = importlib.machinery.SourceFileLoader("nmas_kea_subnet_files", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _snapshot():
    """A snapshot from the lab's own Kea answers (tests/fixtures/kea/), as the tool takes one."""
    def load(name):
        with open(os.path.join(KEA, name), encoding="utf-8") as fh:
            return json.load(fh)

    class FakeKea:
        def command(self, cmd, services):
            svc = services[0]
            name = {"config-get": f"{svc}-config-get.json",
                    "lease4-get-all": "dhcp4-lease4-get-all.json",
                    "lease6-get-all": "dhcp6-lease6-get-all.json"}[cmd]
            return {"ok": True, "result": load(name)}
    return _tool().snapshot(FakeKea())


def test_a_snapshot_holds_both_families_leases_and_configuration():
    snap = _snapshot()
    assert set(snap) == {"IPv4", "IPv6"}
    assert snap["IPv4"]["leases"] and snap["IPv6"]["leases"]
    assert "hash" not in snap["IPv4"]["config"] and snap["IPv4"]["config"]["subnet4"]


def test_equal_snapshots_compare_equal_and_any_move_is_named():
    tool = _tool()
    before = _snapshot()
    assert tool.compare(before, json.loads(json.dumps(before))) == []
    after = json.loads(json.dumps(before))
    after["IPv4"]["leases"].pop()
    after["IPv6"]["config"]["valid-lifetime"] = 1
    moved = tool.compare(before, after)
    assert any("IPv4: 1 leases before and not after" in m for m in moved), moved
    assert any("IPv6: Kea's configuration key 'valid-lifetime' differs" in m for m in moved)


def test_the_update_page_s_check_reads_done_only_when_both_families_moved(tmp_path, monkeypatch):
    from modules import host_steps
    files = {}
    for family, name in (("IPv4", "kea-dhcp4.conf"), ("IPv6", "kea-dhcp6.conf")):
        files[family] = tmp_path / name
        files[family].write_text(_main(name))
    monkeypatch.setattr("modules.dhcp_reservations.main_config",
                        lambda list_name, family: str(files[family]))
    got = host_steps.check_kea_subnet_files()
    assert got["state"] == "not_done" and "IPv4" in got["detail"] and "IPv6" in got["detail"]
    for family in files:
        p = S.move_plan(files[family].read_text(), str(files[family]), family)
        files[family].write_text(p["candidate"])
    assert host_steps.check_kea_subnet_files()["state"] == "done"
