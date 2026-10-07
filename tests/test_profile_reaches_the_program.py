"""C565 (2026-10-07): a committed profile section reaches the device's program, or the plan says
why it does not. End to end, through the real Propose and the real /deploy/plan.

The operator walked P1 on the host: the management section was committed, yet r2's Plan a deploy
said "nothing to send" ("intent vs capture: no difference") and Monitoring > Apply said r2
already had everything. The network's template library held `_common.j2` as an older shipped
version (stale, measured by `templates_repo.seed_status`), which does not render the section's
lines: the data reached effective intent and the template dropped it, silently, while Propose
had said r2 inherits it. Now a plan names a section its template renders none of, with the
template's state, and never says "every line" in its place.

On test_profile_apply's lab (r2's real golden and intent, r6), with `syslog_host` configured so
Propose derives the management section, as on the host. The stale template is the shipped
`_common.j2` as it was before P1 (this repository's own history, the copy the host held).
"""

import os
import subprocess

import pytest

from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = {"ip ssh source-interface Loopback0", "ip tftp source-interface Loopback0"}
#: The last commit before P1 changed the shipped `_common.j2` (177b78e added the lines).
BEFORE_P1 = "97a4249"


def _propose_management(lab):  # noqa: F811
    from modules.nsot import profile, profile_propose as pp
    lab["settings"].update(syslog_host="192.0.2.10", syslog_source_interface="Loopback0")
    p = pp.propose("Lab")
    row = next(s for s in p["sections"] if s["section"] == "management")
    assert row["proposed"], row
    assert pp.apply("Lab", p["hash"], "op@example.invalid")["outcome"] == "committed"
    assert "management" in profile.read_committed(lab["repo"])["sections"]


def _plan(lab, **kw):  # noqa: F811
    body = lab["client"].post("/deploy/plan", json={"devices": ["r2"], "list_name": "Lab",
                                                    **kw}).get_json()
    (d,) = body["devices"]
    return body, d


def _stale_common(lab):  # noqa: F811
    old = subprocess.run(["git", "-C", ROOT, "show",
                          f"{BEFORE_P1}:modules/nsot/templates/_common.j2"],
                         capture_output=True, text=True)
    if old.returncode != 0:
        pytest.skip(f"no history for the shipped template here: {old.stderr.strip()}")
    assert "source_interfaces" not in old.stdout
    path = os.path.join(lab["repo"], "templates", "_common.j2")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(old.stdout)


class TestACommittedSectionReachesTheProgram:
    def test_plan_a_deploy_sends_the_sections_lines(self, lab):  # noqa: F811
        _propose_management(lab)
        _body, d = _plan(lab)
        assert LINES <= {c.strip() for c in d["commands"]}, d["commands"]
        assert "unrendered" not in d

    def test_apply_the_profile_sends_them_under_the_section(self, lab):  # noqa: F811
        _propose_management(lab)
        body, d = _plan(lab, scope="profile")
        assert LINES <= {c.strip() for c in d["commands"]}
        notes = [n["title"] for t in body["preview"]["targets"]
                 for n in t["program"].get("notes") or []]
        assert any(t.startswith("From the profile's management sources (TFTP and the SSH "
                                "client) section") for t in notes), notes


class TestATemplateThatCannotRenderItSaysSo:
    def test_the_plan_names_the_section_and_the_stale_template(self, lab):  # noqa: F811
        _propose_management(lab)
        _stale_common(lab)
        body, d = _plan(lab)
        assert not LINES & {c.strip() for c in d["commands"]}
        (u,) = d["unrendered"]
        assert u["section"] == "management"
        assert u["text"].startswith("Not sent: the profile's management sources (TFTP and the "
                                    "SSH client) section. r2's template")
        assert "templates/_common.j2 is an older shipped version, unedited" in u["text"]
        items = [i for i in body["preview"]["what_not"]["items"] if i["kind"] == "unrendered"]
        assert [i["text"] for i in items] == [u["text"]]

    def test_an_empty_program_never_claims_every_line(self, lab):  # noqa: F811
        _propose_management(lab)
        _stale_common(lab)
        body, d = _plan(lab, scope="profile")
        programs = [t["program"] for t in body["preview"]["targets"]]
        assert programs
        for p in programs:
            if not p.get("lines"):
                assert p["none"].startswith("Nothing will be sent: the device already has every "
                                            "line its template renders. Not every profile "
                                            "section is rendered"), p["none"]
        assert any(i["kind"] == "unrendered" for i in body["preview"]["what_not"]["items"])

    def test_a_current_template_names_nothing(self, lab):  # noqa: F811
        _propose_management(lab)
        _body, d = _plan(lab)
        assert "unrendered" not in d


class TestCoverageShowsTheSection:
    """C566, board C: Coverage's Mgmt sources column, measured from each committed golden; a
    device whose template drops the section reads "not rendered", linked to Templates, and is
    not offered for it; with the template current, the gap is offered and Coverage's Apply
    (the combined deploy) sends exactly the section's two lines."""

    def test_the_gap_is_offered_and_applied(self, lab, monkeypatch):  # noqa: F811
        from tests.test_coverage_grid import _box, _cell, _table
        _propose_management(lab)
        html = _table(lab, monkeypatch)
        cell = _cell(html, "r2", "Mgmt sources")
        assert 'data-state="gap"' in cell and "missing — the profile supplies it" in cell
        assert "management" in _box(html, "r2") or 'value="r2"' in _box(html, "r2")
        body, d = _plan(lab, scope="templates")
        assert LINES <= {c.strip() for c in d["commands"]}

    def test_a_template_that_drops_it_reads_not_rendered(self, lab, monkeypatch):  # noqa: F811
        import html as html_mod

        from tests.test_coverage_grid import _cell, _table
        _propose_management(lab)
        _stale_common(lab)
        html = _table(lab, monkeypatch)
        cell = html_mod.unescape(_cell(html, "r2", "Mgmt sources"))
        assert 'data-state="not_rendered"' in cell
        assert 'href="/v2/templates?list=Lab"' in cell
        assert "renders none of the profile's management sources section" in cell
        assert 'id="cov-legend-dropped"' in html

    def test_a_golden_holding_both_lines_is_configured(self, lab, monkeypatch):  # noqa: F811
        from modules.nsot.repo import GoldenItem, save_golden
        from tests.test_coverage_grid import _cell, _table
        _propose_management(lab)
        save_golden("Lab", [GoldenItem("r2", lab["captured"].replace(
            "\nend", "\nip ssh source-interface Loopback0\nip tftp source-interface Loopback0"
                     "\nend", 1), "203.0.113.12", platform="cisco_iosxe")],
                    source="capture", actor="t", baseline=False)
        cell = _cell(_table(lab, monkeypatch), "r2", "Mgmt sources")
        assert 'data-state="ok"' in cell
