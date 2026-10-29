"""C2059 (2026-10-29): a commit message in a list's repository is masked before git sees it.

A person's typed line becomes a commit's subject ("Why, in one line" on the Intent tab, every
intent editor summary, a template's message), and the repository is pushed to its remote, whose
history is never rewritten. `repo.commit`, the one function every commit in a list's repository
passes (tests/test_every_commit_publishes.py), masks the message with `redact.redact_text`: a
secret in its position, and any stored credential's value, never reach the commit object; an
address (IPv4 and IPv6), a device's name and the trailers are kept. Each test reads the commit
back from git (`git cat-file commit HEAD`, the object that is pushed).
"""

import logging
import os
import subprocess

import pytest

from tests.test_intent_editor import world  # noqa: F401 (the fixture)

#: Planted secrets, each typed into a summary in its own secret position. The last three are
#: read only by the egress shapes, a summary following `host_vars: <device> ` (no line start
#: for `enable secret`'s rule to anchor on, and a hash or a key with no carrier).
POSITIONAL = (
    ("username admin secret Pl4ntedUserSecret", "Pl4ntedUserSecret"),
    ("snmp-server community Pl4ntedComm RO", "Pl4ntedComm"),
    ("neighbor 2001:db8::1 password Pl4ntedBgpV6", "Pl4ntedBgpV6"),
    ("neighbor 192.0.2.1 password Pl4ntedBgpV4", "Pl4ntedBgpV4"),
    ("archive path ftp://nmasprobe:Pl4ntedUrlPw@192.0.2.50/x", "Pl4ntedUrlPw"),
    ("enable secret 0 Pl4ntedEnableTyped", "Pl4ntedEnableTyped"),
    ("the old hash $9$Pl4ntedSalt$Pl4ntedHashBody", "Pl4ntedHashBody"),
    ("peer key 1 md5 Pl4ntedPeerKey", "Pl4ntedPeerKey"),
)


def _raw_commit(repo: str) -> str:
    return subprocess.run(["git", "-C", repo, "cat-file", "commit", "HEAD"],
                          capture_output=True, text=True, check=True).stdout


def _subject(repo: str) -> str:
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _edit(world, summary: str) -> dict:  # noqa: F811 (the fixture's name)
    """The Intent tab's Commit with a changed document and *summary* as its line."""
    from modules.nsot import intent_edit
    path = os.path.join(world["repo"], "host_vars", "s4.yml")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stamp = str(len(_raw_commit(world["repo"])))
    out = intent_edit.commit("lab", "s4", text.replace("uplink", f"uplink {stamp}", 1), summary,
                             intent_edit.open_doc("lab", "s4")["base"], "test")
    assert out["ok"] is True and out["changed"], out
    return out


@pytest.fixture
def stored(tmp_path, monkeypatch):
    """A credential store holding one value, read by the mask (the store's file in tmp)."""
    from modules import credentials, redact
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr(credentials, "device_credential_values", dict)
    redact.invalidate_cache()
    credentials.set_template_secret("lab:s4:snmp_community_ro", "Kn0wnStoredValue",
                                    list_name="lab")
    redact.invalidate_cache()
    yield "Kn0wnStoredValue"
    redact.invalidate_cache()


class TestATypedLineIsCommittedMasked:
    @pytest.mark.parametrize("typed,secret", POSITIONAL, ids=[s for _t, s in POSITIONAL])
    def test_a_secret_typed_in_its_position_never_reaches_the_commit(self, world, typed, secret):
        _edit(world, f"why: {typed}")
        raw = _raw_commit(world["repo"])
        assert secret not in raw, f"{secret} reached the commit object"
        assert "<redacted:" in _subject(world["repo"])

    def test_a_stored_value_typed_in_prose_never_reaches_the_commit(self, world, stored):
        _edit(world, f"the old community was {stored}, rotated")
        raw = _raw_commit(world["repo"])
        assert stored not in raw
        assert _subject(world["repo"]) == (
            "host_vars: s4 the old community was <redacted:snmp_community_ro>, rotated")

    def test_addresses_and_names_survive_unmasked(self, world):
        typed = "move s4's uplink from 192.0.2.14 to 2001:db8::14/64 and fe80::1"
        _edit(world, typed)
        assert _subject(world["repo"]) == f"host_vars: s4 {typed}"

    def test_the_trailers_are_kept(self, world):
        _edit(world, "username admin secret Pl4ntedUserSecret")
        trailers = subprocess.run(
            ["git", "-C", world["repo"], "log", "-1", "--format=%(trailers:only,unfold)"],
            capture_output=True, text=True, check=True).stdout
        assert "Actor: test" in trailers and "Source: intent-edit" in trailers, trailers

    def test_a_subject_ending_in_a_secret_word_keeps_the_next_line(self, world):
        """The egress shapes read a space run after `secret`; over the whole message a subject
        ending in the word took the `Source:` trailer's key (the rotation's own subject,
        tests/test_config_check.py's `test_a_scheduled_rotation_commits_…`)."""
        _edit(world, "rotated to a device-generated type-9 secret")
        msg = subprocess.run(["git", "-C", world["repo"], "log", "-1", "--format=%B"],
                             capture_output=True, text=True, check=True).stdout
        assert msg.startswith("host_vars: s4 rotated to a device-generated type-9 secret\n"), msg
        assert "\nSource: intent-edit" in msg and "<redacted:" not in msg, msg

    def test_the_masking_is_logged_without_the_value(self, world, caplog):
        with caplog.at_level(logging.WARNING, logger="modules.nsot.repo"):
            _edit(world, "username admin secret Pl4ntedUserSecret")
        said = [r.getMessage() for r in caplog.records if r.name == "modules.nsot.repo"]
        assert any("committed masked" in m for m in said), said
        assert not any("Pl4ntedUserSecret" in m for m in said)

    def test_a_line_with_nothing_to_mask_is_committed_as_typed(self, world, caplog):
        with caplog.at_level(logging.WARNING, logger="modules.nsot.repo"):
            _edit(world, "retitle the uplink")
        assert _subject(world["repo"]) == "host_vars: s4 retitle the uplink"
        assert not any("committed masked" in r.getMessage() for r in caplog.records)


class TestEveryCommitPathIsMasked:
    """The mask is in `repo.commit`, so a path other than the Intent tab cannot skip it."""

    def test_a_template_message_is_masked(self, world):
        from modules.nsot import repo as _repo
        path = os.path.join(world["repo"], "templates", "cisco_ios", "note.j2")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("! a note\n")
        out = _repo.save_templates("lab", ["cisco_ios/note.j2"], actor="test",
                                   message="template: key-string 7 Pl4ntedKeyString7 noted")
        assert out["ok"], out
        assert "Pl4ntedKeyString7" not in _raw_commit(world["repo"])

    def test_a_direct_commit_is_masked(self, world):
        from modules.nsot import repo as _repo
        with _repo.repo_lock(world["repo"]):
            rc, sha, err = _repo.commit(world["repo"], "empty: enable secret 0 Pl4ntedEnable",
                                        allow_empty=True, publish_now=False)
        assert rc == 0 and sha, err
        assert "Pl4ntedEnable" not in _raw_commit(world["repo"])
        assert _subject(world["repo"]) == "empty: enable secret 0 <redacted:egress_password>"

    def test_a_typed_reason_in_the_body_is_masked_and_the_other_trailers_kept(self, world):
        """A decline's or a retirement's reason is a trailer a person typed (`Reason:`)."""
        from modules.nsot import repo as _repo
        message = ("host_vars: s4 retired\n\nReason: its key 7 Pl4ntedReasonKey leaked\n"
                   "Actor: test\nSource: retire\n")
        with _repo.repo_lock(world["repo"]):
            rc, sha, err = _repo.commit(world["repo"], message, allow_empty=True,
                                        publish_now=False)
        assert rc == 0 and sha, err
        raw = _raw_commit(world["repo"])
        assert "Pl4ntedReasonKey" not in raw
        assert "\nActor: test\nSource: retire\n" in raw, raw
