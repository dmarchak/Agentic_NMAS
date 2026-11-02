"""The render's chain reads the network's intent layers (board FC phase 1 (b); PHASE8_PLAN 22.1
(3); C2283).

`profile.effective_for`, the one chain every reader that renders or compares calls, merges the
committed layers a device takes (`intent_layers.for_device`) under the device's own intent,
before the profile. On a real git repository:

- **No layer** (no `layers/` folder, or no repository at all) is the intent unchanged, and the
  inventory is not read for it: today's render, byte for byte.
- **A committed tag layer** reaches only the devices whose row names the tag; a site and a role
  layer the same by their slugs.
- **Only what is committed** is read: a layer file in the working tree alone is not.
- **A conflict or a file that is not a layer** refuses by name, as a `ProfileRefused`, which
  every caller of the chain already refuses by.
"""

import os
import subprocess

import pytest
import yaml

from modules.nsot import intent_layers as L
from modules.nsot import profile as P

INTENT = {"hostname": "edge1",
          "users": [{"name": "admin", "privilege": 15, "secret_ref": "user_admin_secret"}]}
LAB = {"users": [{"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret",
                  "secret_kind": "secret"}]}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid"))


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "config_repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "README").write_text("x\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "first")
    return r


def _commit(repo, rel, doc):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"add {rel}")


def _effective(repo, monkeypatch, row):
    asked = []
    monkeypatch.setattr(P, "_row_of", lambda list_name, host: asked.append(host) or row)
    monkeypatch.setattr(P, "read_for", lambda list_name, repo_: {"doc": None})
    got = P.effective_for(str(repo), "Lab", "edge1", dict(INTENT), "cisco_iosxe", role="router")
    return got, asked


class TestNoLayer:
    def test_no_layers_folder_is_the_intent_unchanged_and_reads_no_inventory(self, repo,
                                                                             monkeypatch):
        got, asked = _effective(repo, monkeypatch, {"_tags": ["blind-lab"]})
        assert got == INTENT and asked == [], "no inventory read for a network with no layer"

    def test_no_repository_at_all_is_the_intent_unchanged(self, tmp_path, monkeypatch):
        got, asked = _effective(tmp_path / "nowhere", monkeypatch, {})
        assert got == INTENT and asked == []


class TestATagLayer:
    def test_it_reaches_a_device_its_row_tags_and_not_another(self, repo, monkeypatch):
        _commit(repo, "layers/tag-blind-lab.yml", LAB)
        tagged, _ = _effective(repo, monkeypatch, {"_tags": ["blind-lab"]})
        assert {u["name"] for u in tagged["users"]} == {"admin", "lab"}, tagged
        other, asked = _effective(repo, monkeypatch, {"_tags": ["core"]})
        assert other == INTENT and asked == ["edge1"]

    def test_a_site_and_a_role_layer_by_their_slugs(self, repo, monkeypatch):
        _commit(repo, "layers/site-lab-a.yml", {"ntp": {"servers": ["192.0.2.123"]}})
        _commit(repo, "layers/role-edge-router.yml", {"ntp": {"servers": ["192.0.2.124"]}})
        got, _ = _effective(repo, monkeypatch, {"_site": "lab-a", "_role_slug": "edge-router"})
        assert got["ntp"]["servers"] == ["192.0.2.124"], "the role outranks the site"
        got, _ = _effective(repo, monkeypatch, {"_site": "lab-a"})
        assert got["ntp"]["servers"] == ["192.0.2.123"]

    def test_only_what_is_committed_is_read(self, repo, monkeypatch):
        (repo / "layers").mkdir()
        (repo / "layers" / "network.yml").write_text(yaml.safe_dump(LAB))   # not committed
        got, _ = _effective(repo, monkeypatch, {})
        assert got == INTENT


class TestRefusals:
    def test_two_tags_that_disagree_refuse_naming_both(self, repo, monkeypatch):
        _commit(repo, "layers/tag-blind-lab.yml", LAB)
        _commit(repo, "layers/tag-core.yml",
                {"users": [{"name": "lab", "privilege": 1, "secret_ref": "user_lab_secret"}]})
        with pytest.raises(P.ProfileRefused) as got:
            _effective(repo, monkeypatch, {"_tags": ["blind-lab", "core"]})
        assert isinstance(got.value, L.LayersRefused)
        assert "users[lab]: tag blind-lab says" in str(got.value)
        assert "tag core says" in str(got.value)

    def test_a_file_that_is_not_a_layer_refuses_naming_it(self, repo, monkeypatch):
        _commit(repo, "layers/notes.yml", {"x": 1})
        with pytest.raises(L.LayersRefused, match="layers/notes.yml is not a layer's name"):
            _effective(repo, monkeypatch, {})

    def test_a_layer_carrying_interfaces_refuses(self, repo, monkeypatch):
        _commit(repo, "layers/network.yml", {"interfaces": [{"name": "Gi1"}]})
        with pytest.raises(L.LayersRefused, match="network: interfaces describes one device"):
            _effective(repo, monkeypatch, {})
