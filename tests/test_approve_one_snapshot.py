"""A template approval covers exactly what was validated (CONCURRENCY_AUDIT R12, 2026-10-04).

R12: `approve()` validated the template by rendering each bound device from disk, THEN
fingerprinted the closure from disk. An edit saved in that window made an approval whose
fingerprint was the edited closure, which no validation ran against, and the approval's save
overwrote the edit's revocation tombstone. Now the closure is fingerprinted before validation
and again under the record's lock just before the save; if it moved, nothing is approved, the
refusal names both fingerprints, and the edit's revocation stands.

On the real seeded library, validated through the real `validate_template`; the edit lands
while validation runs.
"""

import os

from modules.nsot import approval
from tests.test_approvals_record import REL, lab  # noqa: F401 (the fixture)
from tests.test_template_approval import _devices


def _edit_during_validation(monkeypatch, lab, also_revoke=False):  # noqa: F811
    real = approval.validate_template

    def validating(repo, rel_path, devices):
        got = real(repo, rel_path, devices)
        path = os.path.join(repo, "templates", rel_path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n{# an edit saved while the approval was being validated #}\n")
        if also_revoke:
            approval.revoke(repo, rel_path, reason="edited: approval withdrawn", actor="editor")
        return got
    monkeypatch.setattr(approval, "validate_template", validating)


def test_an_unchanged_template_is_approved(lab):  # noqa: F811
    got = approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
    assert got["ok"] is True, got


def test_an_edit_during_validation_approves_nothing_and_names_both(lab, monkeypatch):  # noqa: F811
    _edit_during_validation(monkeypatch, lab)
    got = approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
    assert got["ok"] is False
    assert "changed while it was being validated" in got["error"]
    assert "when validation began and is" in got["error"]
    assert not approval._load(lab).get(REL, {}).get("fingerprint") or \
        approval._load(lab)[REL].get("revoked")


def test_the_edits_revocation_stands(lab, monkeypatch):  # noqa: F811
    _edit_during_validation(monkeypatch, lab, also_revoke=True)
    approval.approve(lab, REL, _devices(["s1"]), actor="p@example.invalid")
    record = approval._load(lab)[REL]
    assert record.get("revoked") and record.get("reason") == "edited: approval withdrawn"
