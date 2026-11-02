"""Source of Truth › Intent, a network's intent layers (board FC's FC2; PHASE8_PLAN 22.1 (8)(c);
C2283), read-only: `routes/intent_layers_v2.py` over `modules/intent_layers_page.py`.

On test_profile_apply's lab (r2 and r6, their real intent committed), with layers committed into
the same repository and the inventory's rows given their tags:

- **No layer** says so; an unknown network says so and reads nothing.
- **The layers** in merge order, each with the devices it reaches and its values; the chosen
  one's values, each with how many devices take it and who overrides it (r2's own domain over
  the network's); its file's commit; the secret references it names.
- **Two tags disagreeing** are listed above the layers with both values and the devices.
- **An unreadable inventory** counts no device and says why: no group from an earlier read.
- **Scale:** every device's intent in the fixed reads, never `read_committed` per device.
- The page is strict, the sidebar's Intent is current, and the region re-reads on
  `nmas:goldens`.
"""

import os
import subprocess

import pytest
import yaml

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

LAB_USER = {"users": [{"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret"}]}
ROWS = [{"hostname": "r2", "ip": "203.0.113.12", "platform": "cisco_iosxe",
         "_tags": ["blind-lab"]},
        {"hostname": "r6", "ip": "203.0.113.16", "platform": "cisco_iosxe", "_tags": []}]


def _commit_layer(repo, name, doc):
    path = os.path.join(repo, "layers", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(doc))
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for args in (("add", "--", f"layers/{name}"), ("commit", "-q", "-m", f"layer {name}")):
        subprocess.run(["git", "-C", repo, *args], check=True, env=env, capture_output=True)
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, text=True,
                          capture_output=True).stdout.strip()


@pytest.fixture
def page(lab, monkeypatch):
    rows = [dict(r) for r in ROWS]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(r) for r in rows])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")

    def get(query=""):
        r = lab["client"].get(f"/v2/intent?list=Lab{query}")
        return r, r.get_data(as_text=True)
    get.rows = rows
    return get


class TestNoLayer:
    def test_it_says_the_network_has_none(self, page):
        r, html = page()
        assert r.status_code == 200 and "data-layers-none" in html
        assert "Lab has no intent layers" in html

    def test_an_unknown_network_says_so(self, page, lab):
        r = lab["client"].get("/v2/intent?list=Nowhere")
        assert "Nowhere" in r.get_data(as_text=True) and "data-layers" not in \
            r.get_data(as_text=True), "a network that is not one is said, never another's layers"

    def test_the_page_is_strict_and_the_sidebar_item_current(self, page):
        from modules import csp
        r, html = page()
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert 'aria-current="page"><svg' in html.split("<span>Intent</span>")[0][-700:]
        assert 'hx-trigger="nmas:goldens from:body"' in html


class TestTheLayers:
    def test_each_in_merge_order_with_its_reach_and_values(self, lab, page):
        _commit_layer(lab["repo"], "tag-blind-lab.yml", LAB_USER)
        _commit_layer(lab["repo"], "network.yml", {"domain_name": "corp.example",
                                                   "ntp_servers": ["192.0.2.123"]})
        _r, html = page()
        net, tag = html.index('data-layer="network"'), html.index('data-layer="tag-blind-lab"')
        assert net < tag, "network before tag, the merge order"
        assert "2 devices · 2 values" in html[net:tag] and "1 device · 1 value" in html[tag:]

    def test_the_chosen_layer_names_who_overrides_each_value_and_its_commit(self, lab, page):
        sha = _commit_layer(lab["repo"], "network.yml", {"domain_name": "corp.example"})
        _r, html = page("&layer=network")
        assert 'data-chosen="network"' in html
        assert "<td>domain_name</td><td><code>corp.example</code></td>" in html, html
        own = html.split("<td>domain_name</td>")[1].split("</tr>")[0]
        assert "r2: this device" in own and "r6: this device" in own, own
        assert f"last changed by <code>{sha[:10]}</code>" in html

    def test_a_value_nobody_overrides_says_so(self, lab, page):
        _commit_layer(lab["repo"], "tag-blind-lab.yml", LAB_USER)
        _r, html = page("&layer=tag-blind-lab")
        row = html.split("<td>users › lab</td>")[1].split("</tr>")[0]
        assert "1 <span class=\"muted\">(none overrides it)</span>" in row, row
        assert "<code>user_lab_secret</code>" in html and "account lab, privilege 15" in html


class TestTwoTagsDisagreeing:
    def test_they_are_listed_with_both_values_and_the_devices(self, lab, page):
        page.rows[0]["_tags"] = ["blind-lab", "other"]
        _commit_layer(lab["repo"], "tag-blind-lab.yml", {"banner_motd": "a"})
        _commit_layer(lab["repo"], "tag-other.yml", {"banner_motd": "b"})
        _r, html = page()
        assert "data-layers-conflict" in html
        line = html.split("data-layers-conflict")[1].split("</li>")[0]
        assert "tag blind-lab says <code>a</code> and tag other says <code>b</code>" in line
        assert "· r2" in line, line


class TestAnUnreadableInventory:
    def test_no_device_is_counted_and_it_says_why(self, lab, page, monkeypatch):
        _commit_layer(lab["repo"], "network.yml", {"domain_name": "corp.example"})

        def down(list_name):
            raise ConnectionError("NetBox answered 503")
        monkeypatch.setattr("modules.nsot.restore._devices_of", down)
        _r, html = page()
        assert "data-inventory-error" in html and "NetBox answered 503" in html
        assert "0 devices · 1 value" in html


class TestScale:
    def test_no_device_s_intent_is_read_alone(self, lab, page, monkeypatch):
        _commit_layer(lab["repo"], "network.yml", {"domain_name": "corp.example"})

        def alone(*_a, **_k):
            raise AssertionError("a device's intent read alone: a read per device")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", alone)
        monkeypatch.setattr("modules.nsot.hostvars.committed_at_head", alone)
        r, html = page()
        assert r.status_code == 200 and "2 devices · 1 value" in html
