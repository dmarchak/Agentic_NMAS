"""The Template library panel, EXECUTED (OPEN_FINDINGS D3).

Three things the panel got wrong while every payload was right:
`_common.j2` could never be listed (any `_`-prefixed file was filtered out,
so the shared macros were editable only from a shell); a withdrawn
approval's REASON was carried and drawn nowhere (`changes` won); and the save
message said "approval revoked" whatever the route returned.

The renderers are lifted from the RENDERED page, not a copy, and run in
duktape against the payloads the routes return.
"""

import json
import os

import pytest

from tests.js_source import with_loaded_scripts

dukpy = pytest.importorskip("dukpy")

NAMES = ("_tEsc", "templateRowHtml", "approvalEvidenceText", "approvalCellHtml", "saveToastText")


@pytest.fixture(scope="module")
def js():
    import app as nmas

    page = with_loaded_scripts(
        nmas.app.test_client().get("/").get_data(as_text=True))
    out = []
    for name in NAMES:
        start = page.index(f"function {name}(")
        depth, i, seen = 0, page.index("{", start), False
        while i < len(page):
            if page[i] == "{":
                depth, seen = depth + 1, True
            elif page[i] == "}":
                depth -= 1
                if seen and depth == 0:
                    break
            i += 1
        out.append(page[start:i + 1])
    return "\n".join(out)


def _call(js, fn, payload):
    return dukpy.evaljs(js + f"\n{fn}({json.dumps(payload)});")


class TestTheSharedFileIsListed:
    SHARED = {"path": "_common.j2", "size": 9000, "bound_devices": [],
              "shared": True,
              "imported_by": ["cisco_ios/base.j2", "cisco_iosxe/base.j2"]}

    def test_it_has_a_row_with_edit_and_what_editing_revokes(self, js):
        html = _call(js, "templateRowHtml", self.SHARED)
        assert "_common.j2" in html and "openTemplate('_common.j2')" in html
        assert "cisco_ios/base.j2" in html and "cisco_iosxe/base.j2" in html
        assert "revokes" in html

    def test_it_offers_no_approval_of_its_own(self, js):
        html = _call(js, "templateRowHtml", self.SHARED)
        assert "approveTemplate" not in html and "validateTemplate" not in html

    def test_a_platform_template_keeps_its_actions(self, js):
        """Floor: the shared branch did not swallow the ordinary one."""
        html = _call(js, "templateRowHtml", {
            "path": "cisco_ios/base.j2", "size": 1, "bound_devices": ["s1"]})
        assert "approveTemplate('cisco_ios/base.j2')" in html
        assert "appr_cisco_ios_base_j2" in html


class TestTheWithdrawalReasonIsDrawn:
    REVOKED = {"approved": False, "revoked": True,
               "reason": "REVOKED: '_common.j2' was edited, and this "
                         "template imports it",
               "changes": ["re-approval must validate against every bound "
                           "device before this template can deploy again"]}

    def test_reason_and_changes_both_appear(self, js):
        html = _call(js, "approvalCellHtml", self.REVOKED)
        assert "_common.j2&#39; was edited" in html
        assert "re-approval must validate" in html
        assert html.index("REVOKED") < html.index("re-approval")

    def test_approved_still_renders_approved(self, js):
        html = _call(js, "approvalCellHtml",
                     {"approved": True, "approved_at": "2026-09-25T17:55"})
        assert "bg-success" in html and "not approved" not in html


class TestTheSaveMessageSaysWhatHappened:
    def test_a_save_that_withdrew_names_what(self, js):
        text = _call(js, "saveToastText", {
            "commit": "d1057dc0abc", "approval_revoked": True,
            "revoked": ["cisco_ios/base.j2", "cisco_iosxe/base.j2"]})
        assert text.startswith("Saved and committed d1057dc0")
        assert "cisco_ios/base.j2, cisco_iosxe/base.j2" in text

    def test_a_save_that_withdrew_nothing_does_not_claim_it(self, js):
        text = _call(js, "saveToastText", {
            "commit": "abc", "approval_revoked": False, "revoked": []})
        assert "no approval was affected" in text
        assert "withdrawn" not in text and "revoked" not in text


def test_the_listing_route_marks_shared_files(tmp_path, monkeypatch):
    """The server half: `_common.j2` is listed, flagged shared, with the
    templates that import it -- computed from the import closure, not a
    constant."""
    import app as nmas
    from modules.nsot import repo as _repo, templates_repo

    list_dir = tmp_path / "lab"
    repo_dir = str(list_dir / "config_repo")
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    # The list must EXIST: a read naming a list that does not is refused
    # (register C51). Patching the accessor alone left `lab` nowhere.
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    monkeypatch.setattr("routes.templates._seed_and_commit",
                        lambda n, r: None)
    _repo.init_repo(repo_dir)
    templates_repo.seed_templates(repo_dir)
    body = nmas.app.test_client().get(
        "/templates?list_name=lab").get_json()
    by_path = {t["path"]: t for t in body["templates"]}
    assert by_path["_common.j2"]["shared"] is True
    assert sorted(by_path["_common.j2"]["imported_by"]) == [
        "cisco_ios/base.j2", "cisco_iosxe/base.j2"]
    assert "shared" not in by_path["cisco_ios/base.j2"]
    assert all("approved" not in t for t in body["templates"]), \
        "approval is answered by /templates/approval/<path> only"


class TestTheBadgeSaysWhatItCoversAndWhatItDoesNot:
    """P.5, the operator's addition, executed against the ROUTE's real payload
    (never a hand-built one: a renderer test fed by hand passed while a real
    payload's shape differed, P.3 step 4)."""

    def _payload(self, tmp_path, monkeypatch):
        import app as nmas
        from modules.nsot import approval, manifest, templates_repo
        from routes import templates as troutes
        from tests.js_source import read_shipped

        repo = str(tmp_path / "config_repo")
        os.makedirs(repo)
        templates_repo.seed_templates(repo)
        fleet = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")
        for n in ("s1", "s2"):
            manifest.upsert_device(repo, f"uid:{n}", n, f"203.0.113.2{n[1]}", platform="cisco-ios")
        devices = [{"device": n, "platform": "cisco_ios",
                    "running_config": read_shipped(os.path.join(fleet, f"{n}.cfg"))} for n in ("s1", "s2")]
        devices[1]["running_config"] += "\nsome construct no template models 42\n"
        approval.approve(repo, "cisco_ios/base.j2", devices, actor="operator@example.invalid")
        from tests.test_template_approval import _commit_approvals
        _commit_approvals(repo)          # the gate counts a COMMITTED approval (R13)
        monkeypatch.setattr(troutes, "_active_list", lambda *a: "Lab")
        monkeypatch.setattr(troutes, "_repo_for", lambda *_a: repo)
        monkeypatch.setattr(troutes, "_captured_golden", lambda *a, **k: (None, None))
        return nmas.app.test_client().get("/templates/approval/cisco_ios/base.j2").get_json()

    def test_an_approved_badge_draws_both_sentences_and_the_evidence(self, js, tmp_path, monkeypatch):
        payload = self._payload(tmp_path, monkeypatch)
        assert payload["approved"] is True, payload
        html = _call(js, "approvalCellHtml", payload)
        assert "covers the template itself" in html
        assert "blocked there alone" in html
        assert "validated on 1 of 2 bound device(s)" in html and "s2 did not round-trip" in html
        assert "operator@example.invalid" in html

    def test_the_footnote_no_longer_states_the_scheme_2_rule(self):
        from tests.js_source import read_shipped
        src = read_shipped(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        "static", "js", "gen", "partials__template_editor.1.js"))
        assert "binding a new" not in src and "<strong>every</strong> device bound" not in src
        assert "<strong>at least one</strong> to round-trip" in src
