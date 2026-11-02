"""The device's Intent tab says where each value comes from (board FC3; PHASE8_PLAN 22.1 (6) and
(8)(c); C2283): the committed intent layers it takes, each with the commit that last changed
its file, the values a layer supplies, and each of the device's own values that overrides a
layer's (`intent_layers.provenance`, drawn by `device_page.intent_view`).

On test_profile_apply's lab (r2's real intent committed), with layers committed into the same
repository:

- **No layer:** the tab is today's, and the inventory is not read for it.
- **A tag layer r2's row names** supplies `users › lab`, From "tag blind-lab", its commit on
  the page; a tag r2 does not carry adds nothing.
- **r2's own value over a layer's** says "this device (overrides network: …)".
- **Two tags disagreeing** say the layers cannot be merged, naming the path, never a table.
"""

import os
import subprocess

import pytest
import yaml

from tests.test_device_intent_v2 import R2, page  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

LAB_USER = {"users": [{"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret"}]}


def _commit_layer(repo, name, doc):
    path = os.path.join(repo, "layers", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml.safe_dump(doc))
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    subprocess.run(["git", "-C", repo, "add", "--", f"layers/{name}"], check=True, env=env,
                   capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", f"layer {name}"], check=True,
                   env=env, capture_output=True)
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, text=True,
                          capture_output=True).stdout.strip()


@pytest.fixture
def row(monkeypatch):
    """r2's inventory row as the layers read it; every read counted."""
    from modules.nsot import profile
    got = {"row": dict(R2, _tags=["blind-lab"], _site="lab-a"), "asked": 0}

    def row_of(list_name, host):
        got["asked"] += 1
        return dict(got["row"])
    monkeypatch.setattr(profile, "_row_of", row_of)
    return got


class TestNoLayer:
    def test_the_tab_is_todays_and_reads_no_inventory(self, page, row):
        r, html = page("r2")
        assert r.status_code == 200
        assert "data-intent-layers" not in html and "Last changed by <code>" in html
        assert row["asked"] == 0, "a network with no layer reads no inventory for its Intent tab"


class TestATagLayer:
    def test_its_value_says_where_it_came_from_with_the_layer_commit(self, lab, page, row):
        sha = _commit_layer(lab["repo"], "tag-blind-lab.yml", LAB_USER)
        _r, html = page("r2")
        assert "data-intent-layers" in html
        assert f"<strong title=\"layers/tag-blind-lab.yml, last changed by {sha[:10]}" in html
        assert f"tag blind-lab</strong> <code>{sha[:10]}</code>" in html, "the layer commit drawn"
        assert '<tr data-from="tag blind-lab"><td>users › lab</td>' in html, html
        assert "privilege 15 · secret_ref user_lab_secret" in html
        assert "r2&#39;s own document last changed by" in html \
            or "r2's own document last changed by" in html

    def test_a_tag_the_device_does_not_carry_adds_nothing(self, lab, page, row):
        _commit_layer(lab["repo"], "tag-other.yml", LAB_USER)
        _r, html = page("r2")
        assert "data-intent-layers" not in html and "users › lab" not in html


class TestTheDevicesOwnOverALayer:
    def test_it_names_the_layer_and_the_value_it_overrides(self, lab, page, row):
        _commit_layer(lab["repo"], "network.yml", {"domain_name": "corp.example"})
        _r, html = page("r2")
        assert '<tr data-from="this device"><td>domain_name</td><td><code>example.com</code>' \
            in html, html
        assert "(overrides network: <code>corp.example</code>)" in html


class TestTwoTagsDisagreeing:
    def test_the_tab_says_they_cannot_be_merged_naming_the_path(self, lab, page, row):
        row["row"]["_tags"] = ["blind-lab", "other"]
        _commit_layer(lab["repo"], "tag-blind-lab.yml", {"domain_name": "a.example"})
        _commit_layer(lab["repo"], "tag-other.yml", {"domain_name": "b.example"})
        _r, html = page("r2")
        assert "data-layers-error" in html and "cannot be merged" in html
        assert "domain_name" in html and "intent-from" not in html
