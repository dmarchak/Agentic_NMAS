"""C118: is a rollback block ENFORCED, and on what? Measured, not read.

s4 carried a block for four days (2026-09-23 to 09-27) through P.1's deploy
to s4, and nothing refused it. The operator's three hypotheses: (a) the plan
never reads the block; (b) it is keyed on the exact failed program, a replay
guard; (c) s4 was refused somewhere unnoticed. Each case below plants a block
with the real `record_rolled_back()` on r2's real config and committed intent,
and asks the real plan path (`routes.deploy._artifact_for`, which
`/deploy/plan` calls), then the route itself.
"""

import os

import pytest

from tests.test_capture import build_capture_lab


def _set_description(repo, iface, text):
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    intent = hostvars.read_committed(repo, "r2")
    for i in intent["interfaces"]:
        if i["name"] == iface:
            i["description"] = text
    hostvars.write_committed(repo, intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]


def _program(repo):
    import routes.deploy as rd

    (artifact, captured, _dev), err = rd._artifact_for("Lab", "r2")
    assert not err, err
    return artifact, rd._current_program(artifact, captured)


def _plant(repo, commands):
    from modules.nsot import hostvars

    sha = hostvars.intent_commits(repo, "r2", limit=1)[0]["sha"]
    hostvars.record_rolled_back(repo, "r2", sha, reason="C118 measurement",
                                commands=commands)


def _blocked(artifact):
    return artifact.rolled_back is not None and any(
        "rolled back" in r for r in artifact.blocking_reasons)


@pytest.fixture
def lab(monkeypatch, tmp_path):
    lab = build_capture_lab(monkeypatch, tmp_path)
    _set_description(lab["repo"], "GigabitEthernet2", "C118-FAILED-CHANGE")
    _artifact, failed = _program(lab["repo"])
    assert any("C118-FAILED-CHANGE" in c for c in failed), failed   # the case is reached
    _plant(lab["repo"], failed)
    return lab, failed


class TestTheBlockIsReadAndEnforced:
    def test_a_the_failed_program_is_refused(self, lab):
        """Rules out (a): the plan path reads the block and refuses."""
        repo = lab[0]["repo"]
        artifact, _ = _program(repo)
        assert _blocked(artifact) and not artifact.deployable, artifact.blocking_reasons

    def test_the_route_draws_the_refusal(self, lab):
        client = lab[0]["client"]
        body = client.post("/deploy/plan", json={"devices": ["r2"]}).get_json()
        text = str(body)
        assert "rolled back" in text, text[:600]

    def test_b_a_modified_program_still_containing_it_is_refused(self, lab):
        """Rules out (b): not a replay guard. An unrelated edit that adds its
        own line leaves the failed change inside the program, and the block
        stands."""
        repo, failed = lab[0]["repo"], lab[1]
        _set_description(repo, "GigabitEthernet3", "C118-UNRELATED-EDIT")
        artifact, program = _program(repo)
        assert program != failed and len(program) > len(failed)
        assert _blocked(artifact), program

    def test_the_block_lifts_only_when_the_failed_change_is_gone(self, lab):
        """The control: the failed line removed from intent, the block lifts."""
        from modules.nsot import hostvars

        repo = lab[0]["repo"]
        original = hostvars.committed_at(repo, "r2", hostvars.intent_commits(
            repo, "r2", limit=2)[1]["sha"])
        gi2 = next(i for i in original["interfaces"] if i["name"] == "GigabitEthernet2")
        _set_description(repo, "GigabitEthernet2", gi2.get("description") or "")
        _set_description(repo, "GigabitEthernet3", "C118-UNRELATED-EDIT")
        artifact, program = _program(repo)
        assert not any("C118-FAILED-CHANGE" in c for c in program)
        assert not _blocked(artifact)


class TestTheS4Shape:
    def test_c_a_block_whose_lines_are_never_proposed_blocks_nothing(self, monkeypatch,
                                                                      tmp_path):
        """s4's entry, verbatim: the lines of test_new_container_programs'
        fixture (`description x` on an interface), written into the live
        store by the suite before C32. No real s4 program ever contained
        them, so by the containment rule the block never applied: s4 was
        not refused because there was nothing of the failed change to
        refuse. A real change to the device is not blocked."""
        lab = build_capture_lab(monkeypatch, tmp_path)
        repo = lab["repo"]
        _plant(repo, ["interface GigabitEthernet0/1", " description x", "exit"])
        _set_description(repo, "GigabitEthernet2", "C118-REAL-CHANGE")
        artifact, program = _program(repo)
        assert any("C118-REAL-CHANGE" in c for c in program)
        assert not _blocked(artifact)
