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


class TestApprovalIsConsultedNotAssumed:
    """The blocker on the first real run of the loop.

    The editor reported *"template 'cisco_ios/base.j2' is not approved for
    this device"* on a device whose template had been approved the day
    before. It read as an approval that had revoked itself overnight -- the
    precise failure the scheme-2 correction was made to stop.

    It was not. `build_artifact()` takes `template_approved` as a plain
    argument defaulting to **False**, and
    `render_artifact.py` turns a False into that sentence. This route built
    artifacts directly and never called `approval.is_approved()`, so the
    message was produced **without consulting the approval store at all**.

    A caller that forgets the check does not get a missing feature. It gets a
    confident, wrong statement about something it never looked at.
    """

    def test_the_route_does_not_build_artifacts_directly(self):
        from tests.astcheck import calls_in

        from routes import templatize

        assert calls_in(templatize.preview_committed_edit,
                        "build_artifact") == 0, (
            "building directly defaults template_approved to False, which is "
            "reported as 'not approved' without asking")

    def test_it_uses_the_helper_that_resolves_approval(self):
        from tests.astcheck import calls_in

        from routes import templatize

        assert calls_in(templatize.preview_committed_edit, "artifact_for") >= 1

    def test_an_approved_template_is_not_reported_unapproved(self, world,
                                                              monkeypatch):
        """Behavioural, not only structural.

        Asserts the SPECIFIC reason is absent rather than that `deployable`
        is True: this fixture carries an unacknowledged `unmodeled` line, so
        it is legitimately not deployable for an unrelated reason. Keying on
        the summary flag would make the test depend on the fixture having no
        other blockers, which is a different claim than the one under test.
        """
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: True)
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text).get_json()
        assert not any("not approved" in r for r in body["blocking_reasons"]), \
            body["blocking_reasons"]

    def test_an_unapproved_template_still_blocks(self, world, monkeypatch):
        """The gate must still gate."""
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text).get_json()
        assert body["deployable"] is False
        assert any("not approved" in r for r in body["blocking_reasons"])

    def test_the_helper_is_shared_with_the_template_preview(self):
        """Two routes asking the same question must ask it the same way; the
        divergence is what produced this."""
        from tests.astcheck import calls_in

        from routes import templates

        assert calls_in(templates.preview, "artifact_for") >= 1



class TestApprovalIsNotKeyedOnThisDevicesIntent:
    """The correction to the correction.

    The first fix resolved approval by building the artifact, reading its
    parsed `host_vars`, and passing `{hostname: host_vars}` to
    `is_approved()` -- then building a second time. The docstring said the
    order was *forced*, "because `is_approved()` is keyed on the device's
    parsed host_vars".

    It is not, and saying so reinstates in prose the coupling scheme 2 exists
    to remove. `binding_fingerprint()` accepts `host_vars_by_device` and
    ignores it deliberately: under scheme 1 a successful deploy changed the
    device's capture, moved the hash, and revoked the approval **that had
    authorised it**. A comment asserting a dependency the code does not have
    is how that gets reintroduced by someone who believed the comment.

    So the verdict must not vary with this device's intent, and the helper
    must not pretend otherwise by passing a one-device stand-in for the bound
    set it does not have.
    """

    def test_the_verdict_does_not_vary_with_this_devices_intent(self, world,
                                                                monkeypatch):
        """Behavioural. Two very different documents, one verdict."""
        from routes.templates import artifact_for

        seen = []
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda *a, **kw: seen.append((a, kw)) or True)

        base = world["hostvars"].read_committed(world["repo"], "s4")
        other = dict(base, hostname="s4",
                     unmodeled=[{"line": "totally different", "children": [],
                                 "lineno": 1}])
        for host_vars in (base, other):
            artifact_for("s4", CONFIG, world["repo"], "cisco_ios",
                         "cisco_ios/base.j2", host_vars=host_vars)

        assert len(seen) == 2
        assert seen[0] == seen[1], (
            "the approval question changed because this device's intent did; "
            "that is scheme 1")

    def test_no_stand_in_for_the_bound_set_is_passed(self, world, monkeypatch):
        """A wrong value survives precisely because nothing reads it."""
        from routes.templates import artifact_for

        seen = []
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda *a, **kw: seen.append((a, kw)) or True)
        artifact_for("s4", CONFIG, world["repo"], "cisco_ios",
                     "cisco_ios/base.j2")

        args, kwargs = seen[0]
        passed = list(args[2:]) + list(kwargs.values())
        assert all(v is None for v in passed), (
            "the bound set is read from the repo; this caller does not have "
            "it and must not invent one: %r" % (passed,))

    def test_the_artifact_is_built_once(self):
        """The second build existed only to serve the false coupling."""
        from tests.astcheck import calls_in

        from routes import templates

        assert calls_in(templates.artifact_for, "build_artifact") == 1

class TestTheUnchangedDocumentSaysSo:
    """Opening the editor and pressing Check without typing reported "the
    document differs from what is committed" -- a claim about the document,
    made whenever the RENDER was unchanged."""

    def test_an_untouched_document_reports_no_change(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text).get_json()
        assert body["document_changed"] is False
        assert body["vs_intent_changed"] is False

    def test_a_changed_document_says_so(self, world):
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text.replace("uplink", "uplink to core")).get_json()
        assert body["document_changed"] is True

    def test_a_comment_only_change_is_document_changed_but_not_render_changed(
            self, world):
        """The state the old message described, which does exist -- it was
        just not the one being shown."""
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text + "\n# a trailing comment\n").get_json()
        assert body["document_changed"] is True
        assert body["vs_intent_changed"] is False

    def test_the_comparison_is_byte_for_byte(self, world):
        """Whitespace counts. The text-over-fields decision rests on the
        bytes surviving the round trip, so the check has to be on bytes."""
        text = open(os.path.join(world["repo"], "host_vars", "s4.yml")).read()
        body = _preview(world, text + "\n").get_json()
        assert body["document_changed"] is True

    def test_the_ui_has_three_branches(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "templates", "partials",
            "intent_editor.html")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        assert "d.document_changed" in source
        assert "byte-identical to what is committed" in source


class TestTheEditorReMeasuresWhenTheModalIsShown:
    """CodeMirror measures character and gutter widths at initialisation.
    Inside a modal that is still opening those come back zero, and the gutter
    is laid out on top of the text."""

    def _source(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "templates", "partials",
            "intent_editor.html")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_it_refreshes_on_shown(self):
        source = self._source()
        assert "shown.bs.modal" in source
        assert "_intentRefresh" in source

    def test_it_refreshes_after_the_document_loads(self):
        """Either can be the later of the two, so both trigger it."""
        source = self._source()
        assert source.count("_intentRefresh()") >= 2

    def test_refresh_is_guarded(self):
        source = self._source()
        body = source[source.index("function _intentRefresh"):]
        body = body[:body.index("}")]
        assert "if (_intentCM)" in body
