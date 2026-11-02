"""A deploy preview names the intent layer each inherited line came from (board FC, PHASE8_PLAN
22.1 (6); C2283), through the REAL plan: r2's real config and committed intent
(`tests.test_capture.build_capture_lab`), layers committed into its repository, r2's inventory
row tagged, and `/deploy/plan` itself (`routes/deploy._split_profile`).

- **A tag layer's line** is its own group, naming the layer and the commit that last changed its
  file; never "from this edit", never the monitoring profile's.
- **Two layers setting one value:** the line is the later layer's, the first cumulative render
  that sends it.
- **A layer over the profile:** the layer's line is the layer's, and the profile, whose value the
  layer replaced, is given no line (before this, every inherited line was the profile's).
- The device card draws the group under its own heading.
"""

import os
import subprocess

import pytest
import yaml

from tests import deploy_core
from tests.test_monitoring_profile_plan import _intent, _profile_from, lab  # noqa: F401


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
def r2(lab, monkeypatch):
    """r2 holding no NTP server of its own (committed), its row tagged blind-lab."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    intent = _intent(lab["repo"])
    intent["ntp_servers"] = []
    hostvars.write_committed(lab["repo"], intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    monkeypatch.setattr("modules.nsot.profile._row_of",
                        lambda list_name, host: {"hostname": host, "_tags": ["blind-lab"]})
    return {"repo": lab["repo"], "intent": intent}


def _note():
    body = deploy_core.post_plan(json={"devices": ["r2"]}).get_json()
    notes = [n for t in body["preview"]["targets"]
             for n in (t.get("program") or {}).get("notes") or [] if "from_this_edit" in n]
    assert len(notes) == 1, body["preview"]["targets"]
    return notes[0], body


class TestALayersLine:
    def test_it_is_its_own_group_naming_the_layer_and_its_commit(self, r2):
        sha = _commit_layer(r2["repo"], "tag-blind-lab.yml", {"ntp_servers": ["192.0.2.123"]})
        n, _body = _note()
        assert n["from_layers"] == [{"label": "tag blind-lab", "sha": sha,
                                     "subject": "layer tag-blind-lab.yml",
                                     "lines": ["ntp server 192.0.2.123"]}], n
        assert not any("ntp server" in l for l in n["from_this_edit"] + n["pre_existing"]
                       + n["from_profile"]), n

    def test_two_layers_setting_one_value_give_the_line_to_the_later(self, r2):
        _commit_layer(r2["repo"], "network.yml", {"ntp_servers": ["192.0.2.123"]})
        _commit_layer(r2["repo"], "tag-blind-lab.yml", {"ntp_servers": ["192.0.2.124"]})
        n, _body = _note()
        assert [(g["label"], g["lines"]) for g in n["from_layers"]] == \
            [("tag blind-lab", ["ntp server 192.0.2.124"])], n


class TestALayerOverTheProfile:
    def test_the_layers_line_is_never_called_the_profiles(self, r2):
        from modules.nsot import profile
        assert profile.commit_profile(
            "Lab", _profile_from(r2["intent"], ntp={"ntp_servers": ["192.0.2.200"]}),
            "op@example.com", "NTP")["ok"]
        _commit_layer(r2["repo"], "tag-blind-lab.yml", {"ntp_servers": ["192.0.2.124"]})
        n, _body = _note()
        assert [g["lines"] for g in n["from_layers"]] == [["ntp server 192.0.2.124"]], n
        assert n["from_profile"] == [], "the profile's value was replaced, so it sends nothing"


def test_the_device_card_draws_the_layers_group(r2):
    import html as _html

    from tests.payload_render import render_deploy_card_v2

    sha = _commit_layer(r2["repo"], "tag-blind-lab.yml", {"ntp_servers": ["192.0.2.123"]})
    _n, plan = _note()
    out = _html.unescape(render_deploy_card_v2(plan, "r2"))
    assert 'data-attribution-group="layer" data-layer="tag blind-lab"' in out
    assert f"From the intent layer tag blind-lab (<code title=\"layer tag-blind-lab.yml\">" \
           f"{sha[:10]}</code>): <strong>1</strong> line(s)" in out
    group = out.split('data-attribution-group="layer"', 1)[1].split("From this edit", 1)[0]
    assert "ntp server 192.0.2.123" in group
