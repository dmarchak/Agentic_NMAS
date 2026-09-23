"""Editing committed intent, from the interface.

Stage 3.1 measured that `/templatize` appeared **zero times** in the rendered
page. Twelve routes — extract, commit, read, **edit**, revert — reachable by
`curl` and nothing else, while "Deploy plan" *read* committed intent and had
a button. The interface could push a change toward a target it had no way to
set.

**Text, not fields.** A structured editor round-trips the document through
the model, so anything the field set does not cover — the `unmodeled:` block
above all — vanishes from the file without appearing in any diff. That is the
exact failure `unmodeled` was built to prevent. Text also means the bytes
reviewed in the diff are the bytes committed.

Honest is not usable on its own, which is what the other two requirements are
for: a line and column on every refusal, and the render diff before the
commit.
"""

import json
import os

import pytest

CONFIG = """hostname s4
!
interface GigabitEthernet0/1
 description uplink
 no switchport
!
end
"""


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A repo with one device, committed intent, and a golden capture."""
    from modules.nsot import hostvars, repo as _repo

    list_dir = tmp_path / "lab"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "golden"), exist_ok=True)

    # PATCH FIRST. `save_golden()` resolves its own path through
    # `get_list_data_dir()`, so calling it before the patch writes into the
    # REAL data directory -- which is how the first version of this fixture
    # put an s4.cfg into data/lists/lab/. The list name here is arbitrary;
    # had it been "default" it would have written into the live list.
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "n@l"}.get(key, default))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)

    _repo.init_repo(repo_dir)
    # COMMITTED, not merely written. `_captured_golden()` reads at HEAD --
    # the Stage 1.4 fix that stopped the preview serving the legacy store --
    # so a golden in the working tree is invisible to it. Writing the file
    # and skipping the commit made every render return "no captured config",
    # which is the route being right and the fixture being wrong.
    _repo.save_golden("lab", [_repo.GoldenItem("s4", CONFIG, "10.0.0.14")],
                      source="test", actor="test", allow_new=True)
    # Built by the PARSER, not by hand. `_apply_schema_defaults()` fills in
    # keys the templates require -- `services` among them -- so a
    # hand-written document renders with
    # `UndefinedError: 'dict object' has no attribute 'services'`. That was
    # the route reporting a real schema gap correctly and the fixture being
    # an unrealistic document.
    from modules.nsot.parsers import get_parser

    document = get_parser("cisco_ios").parse(CONFIG)
    document["hostname"] = "s4"
    document["unmodeled"] = [{"line": "some-construct nobody modelled",
                              "children": [], "lineno": 12}]
    hostvars.write_committed(repo_dir, document)

    import app as nmas

    return {"client": nmas.app.test_client(), "repo": repo_dir,
            "hostvars": hostvars}


def _preview(world, text):
    return world["client"].post("/templatize/committed/s4/preview",
                                json={"yaml": text})


class TestValidationRefusesWithLineAndColumn:
    """As the template editor does for Jinja."""

    def test_broken_yaml_gives_a_line(self, world):
        out = _preview(world, "hostname: s4\ninterfaces: [\n  bad\n")
        assert out.status_code == 400
        body = out.get_json()
        assert body["stage"] == "yaml"
        assert isinstance(body["line"], int) and body["line"] >= 1

    def test_broken_yaml_gives_a_column(self, world):
        out = _preview(world, "hostname: s4\n  bad: indent\n")
        body = out.get_json()
        assert body["stage"] == "yaml"
        assert body["column"] is not None

    def test_a_non_mapping_is_refused(self, world):
        body = _preview(world, "- just\n- a\n- list\n").get_json()
        assert body["stage"] == "schema"
        assert "mapping" in body["error"]

    def test_a_document_naming_another_device_is_refused(self, world):
        """How one device's intent lands in another's file."""
        body = _preview(world, "hostname: s1\ninterfaces: []\n").get_json()
        assert body["stage"] == "schema"
        assert "names its own device" in body["error"]

    def test_that_refusal_points_at_the_hostname_line(self, world):
        body = _preview(world, "interfaces: []\nhostname: s1\n").get_json()
        assert body["line"] == 2

    def test_a_valid_document_passes(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        out = _preview(world, text)
        assert out.status_code == 200
        assert out.get_json()["valid"] is True


class TestTheSecretGuardsApplyInTheEDITOR:
    """`write_committed_text()` refuses at commit; the editor must refuse
    before the operator has typed a summary and pressed the button."""

    def test_a_resolved_secret_is_refused_at_preview(self, world, monkeypatch):
        monkeypatch.setattr(
            "modules.nsot.hostvars.assert_no_secret_values",
            lambda text, host: (_ for _ in ()).throw(
                Exception("a resolved secret value appears in host_vars")))
        body = _preview(world, "hostname: s4\ninterfaces: []\n").get_json()
        assert body["stage"] == "secrets"
        assert "resolved secret" in body["error"]

    def test_non_printable_content_is_refused(self, world):
        body = _preview(world, "hostname: s4\ndescription: a—b\n").get_json()
        assert body["ok"] is False


class TestTheRenderDiffIsShownBeforeCommitting:
    def test_an_edit_reports_what_it_changes(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text.replace("uplink", "uplink to core")).get_json()
        assert body["ok"] is True
        assert body["vs_intent_changed"] is True
        assert "uplink to core" in body["vs_intent"]

    def test_an_unchanged_document_reports_no_change(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text).get_json()
        assert body["vs_intent_changed"] is False

    def test_it_also_reports_what_a_deploy_would_push(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text.replace("uplink", "uplink to core")).get_json()
        assert "vs_device" in body

    def test_nothing_is_written_by_a_preview(self, world):
        before = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        _preview(world, before.replace("uplink", "CHANGED"))
        after = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        assert after == before


class TestTextPreservesWhatAModelWouldDrop:
    """The decisive reason for text over fields."""

    def test_the_unmodeled_block_survives_a_round_trip(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        assert "unmodeled" in text
        edited = text.replace("uplink", "uplink to core")
        world["client"].post("/templatize/committed/s4",
                             json={"yaml": edited, "summary": "retitle uplink"})
        after = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        assert "some-construct nobody modelled" in after, (
            "the unmodeled block vanished -- the failure it was built to "
            "prevent")

    def test_the_committed_bytes_are_the_reviewed_bytes(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        edited = text.replace("uplink", "uplink to core")
        world["client"].post("/templatize/committed/s4",
                             json={"yaml": edited, "summary": "retitle"})
        after = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        assert after == edited, "the text was translated on the way through"


class TestTheLoopCloses:
    """Edit intent -> see the plan -> deploy. The acceptance item: after
    committing, the plan shows exactly that change and nothing else."""

    def test_a_commit_creates_one_commit_with_the_summary(self, world):
        import subprocess

        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        out = world["client"].post(
            "/templatize/committed/s4",
            json={"yaml": text.replace("uplink", "uplink to core"),
                  "summary": "retitle the uplink"})
        assert out.get_json()["ok"] is True
        subject = subprocess.run(
            ["git", "-C", world["repo"], "log", "-1", "--format=%s"],
            capture_output=True, text=True).stdout.strip()
        assert subject == "host_vars: s4 retitle the uplink"

    def test_a_summary_is_required(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        out = world["client"].post("/templatize/committed/s4",
                                   json={"yaml": text, "summary": "  "})
        assert out.status_code == 400
        assert "says nothing in a log" in out.get_json()["error"]

    def test_the_committed_edit_is_what_the_next_render_uses(self, world):
        """The loop's closing condition, checked on the artifact the deploy
        plan builds from rather than on the plan route, which needs an
        inventory this fixture does not have."""
        from modules.nsot import hostvars

        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        world["client"].post("/templatize/committed/s4",
                             json={"yaml": text.replace("uplink", "uplink to core"),
                                   "summary": "retitle"})
        committed = hostvars.read_committed(world["repo"], "s4")
        descriptions = [i.get("description") for i in committed["interfaces"]]
        assert descriptions == ["uplink to core"]


class TestItShipsWithItsEntryPoint:
    def test_the_device_row_has_an_edit_intent_button(self):
        import re

        import app as nmas
        from flask import render_template

        with nmas.app.test_request_context("/"):
            html = render_template("index.html", devices=[
                {"ip": "10.0.0.14", "hostname": "s4", "online": True},
                {"ip": "10.0.0.11", "hostname": "r1", "online": False}])
        hits = re.findall(r"nsotAction\('showIntentEditor', '([^']+)'", html)
        assert sorted(hits) == ["r1", "s4"]

    def test_commit_is_disabled_until_a_preview_passes(self):
        """A text editor is safe for someone who does not remember the schema
        only if the consequence is on screen before the commit."""
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "templates", "partials",
            "intent_editor.html")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        assert 'id="intentCommitBtn"' in source and "disabled" in source
        assert "_intentArm(true)" in source
        armed = source[source.index("_intentArm(true)"):]
        assert "previewIntentEdit" in source[:source.index("_intentArm(true)")]
