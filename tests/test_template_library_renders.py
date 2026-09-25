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

import pytest

from tests.js_source import with_loaded_scripts

dukpy = pytest.importorskip("dukpy")

NAMES = ("_tEsc", "templateRowHtml", "approvalCellHtml", "saveToastText")


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
