"""The device page's Intent tab (NSOT_GUI_BRIEF 3.3; step 4), read-only:
the intent COMMITTED at HEAD, its last commit, and what the monitoring profile
adds on top or the device excludes (`device_page.intent_view`).

On test_profile_apply's lab: r2's REAL intent committed, and r6 in its real
shape; the profile committed by the real proposal. A working-tree edit nobody
committed is never drawn (C104); a device with none says so.
"""

import re

import pytest

from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)

R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R9 = {"hostname": "r9", "ip": "192.0.2.9", "device_type": "cisco_ios", "platform": "cisco_ios"}


@pytest.fixture
def page(lab, monkeypatch):
    from modules import device_page
    from modules.nsot import listref
    rows = {"r2": R2, "r9": R9}
    monkeypatch.setattr(device_page, "find_device",
                        lambda name: (listref.resolve("Lab"), dict(rows[name])))

    def get(name):
        r = lab["client"].get(f"/v2/device/{name}/intent")
        return r, r.get_data(as_text=True)
    return get


class TestTheIntentTab:
    def test_the_committed_document_and_its_last_commit(self, lab, page):
        from modules.nsot import hostvars
        r, html = page("r2")
        assert r.status_code == 200
        sha = hostvars.intent_change(lab["repo"], "r2")["sha"]
        assert f"<code>{sha[:10]}</code>" in html
        assert "hostname: r2" in html and "Read from the repository at HEAD" in html

    def test_a_working_edit_nobody_committed_is_never_drawn(self, lab, page):
        import os
        path = os.path.join(lab["repo"], "host_vars", "r2.yml")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("# HAND-EDIT-NOT-COMMITTED\n")
        _r, html = page("r2")
        assert "HAND-EDIT-NOT-COMMITTED" not in html

    def test_the_profile_it_inherits_is_named(self, page):
        _commit_proposal()
        _r, html = page("r2")
        assert re.search(r"Inherited from the network&#39;s monitoring profile: <strong>[^<]*snmp", html) \
            or re.search(r"Inherited from the network's monitoring profile: <strong>[^<]*snmp", html)

    def test_no_intent_says_why_it_matters(self, page):
        _r, html = page("r9")
        assert "r9 has no committed intent" in html

    def test_an_unreadable_intent_is_said(self, page, monkeypatch):
        def boom(repo, host):
            raise OSError("git show failed")
        monkeypatch.setattr("modules.nsot.hostvars.committed_at_head", boom)
        _r, html = page("r2")
        assert "its committed intent could not be read: git show failed" in html
        assert "Not the same as having no intent." in html

    def test_edit_opens_the_editor_in_place_and_the_fragment_is_strict(self, page):
        from modules import csp
        r, html = page("r2")
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        assert 'data-op="edit-intent"' in html and 'hx-get="/v2/device/r2/intent/edit"' in html
        assert "today's page</a>" not in html, "editing intent is on v2 (board H)"

    def test_the_deep_link_opens_the_editor_on_the_page(self, lab, page):
        """`?tab=intent&edit=1` (seeding's and the Templates refusal's link) lands in it."""
        html = lab["client"].get("/v2/device/r2?tab=intent&edit=1").get_data(as_text=True)
        assert "Editing r2's intent" in html and 'id="ie-text"' in html
        plain = lab["client"].get("/v2/device/r2?tab=intent").get_data(as_text=True)
        assert 'id="ie-text"' not in plain
