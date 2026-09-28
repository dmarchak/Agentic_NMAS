"""C79 and C140 (2026-09-28, the operator's decision (a)): one authorisation
mechanism, every authorised line with the person's stated reason.

C79: a restore may not ADD a secret the device does not hold. After a
rotation the old value is a DIFFERENT line, so it lands beside the new one
and every other guard passes it; the first community rotation (C139) is what
fills the class. "Secret position" has one definition, the positional
redactor's.

C140: the dangerous-line authorisation recorded which lines and who, never
why. Now a reason is required for both classes, its minimum is shape (never
quality), it is drawn as testimony, and how often a line was authorised on a
device before is shown with it.

Built on r2's REAL config (the sanitized fleet fixture).
"""

import json
import os
import re

import pytest

from modules.nsot import authorisation
from modules.nsot.deploy import RestoreTarget

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")).read()
COMMUNITY_LINE = next(l for l in R2.splitlines() if l.startswith("snmp-server community"))
OLD_VALUE = COMMUNITY_LINE.split()[2]
#: The device after a community rotation: the same line with a new value.
ROTATED = R2.replace(COMMUNITY_LINE, COMMUNITY_LINE.replace(OLD_VALUE, "ROTATEDVALUE9"))
MASKED = "snmp-server community <redacted:snmp_community> RO"
REASON = "restoring the pre-rotation community on purpose"


def _target(ref_config=R2, device_config=ROTATED, authorised=()):
    return RestoreTarget(device="r2", platform="cisco_iosxe", target_config=ref_config,
                         captured=device_config, ref="baseline/x",
                         authorised=tuple(authorised))


def _check(target, name="no secret re-added"):
    return next((st, dt) for n, st, dt in target.checks if n == name)


def test_the_fixture_can_exhibit_the_case():
    assert COMMUNITY_LINE in R2 and COMMUNITY_LINE not in ROTATED
    assert "snmp-server community ROTATEDVALUE9 RO" in ROTATED


class TestARestoreMayNotAddASecret:
    def test_the_old_community_after_a_rotation_is_refused_by_its_masked_line(self):
        t = _target()
        assert t.reintroduced_secrets == [MASKED]
        state, detail = _check(t)
        assert state == "fail" and not t.deployable
        assert MASKED in detail and OLD_VALUE not in detail, "named masked, never by value"
        assert "authorise each exact line with your reason" in detail

    def test_authorised_with_a_reason_it_passes_and_says_so(self):
        t = _target(authorised=authorisation.valid_keys([{"line": MASKED, "reason": REASON}]))
        state, detail = _check(t)
        assert state == "pass" and "authorised with a stated reason" in detail
        assert t.deployable

    def test_an_authorisation_without_a_reason_is_not_honoured(self):
        """The target's check runs on every path that prepares a restore, so
        a reason-less authorisation must not pass it where no hash is compared."""
        t = _target(authorised=authorisation.valid_keys([MASKED]))
        assert _check(t)[0] == "fail" and not t.deployable

    def test_the_apply_refuses_it_before_anything_connects(self):
        from modules.nsot.deploy import DeployRefused, prepare_restore
        with pytest.raises(DeployRefused):
            prepare_restore(_target())

    def test_an_account_added_back_is_refused_too(self):
        """C79's first shape: the ref has an account the device lacks."""
        line = next(l for l in R2.splitlines() if l.startswith("username "))
        renamed = R2.replace(line, line.replace("username admin", "username operator", 1))
        t = _target(ref_config=R2, device_config=renamed)
        assert any(k.startswith("username admin") for k in t.reintroduced_secrets), \
            t.reintroduced_secrets
        assert _check(t)[0] == "fail"

    def test_a_rewritten_account_is_c75_s_refusal_and_not_counted_twice(self):
        line = next(l for l in R2.splitlines() if l.startswith("username "))
        value = line.split()[-1]
        changed = R2.replace(line, line[: -len(value)] + "DIFFERENTPW1")
        t = _target(ref_config=R2, device_config=changed)
        assert not any(k.startswith("username") for k in t.reintroduced_secrets)
        assert _check(t, "credential unchanged")[0] == "fail"

    def test_a_restore_to_what_the_device_holds_adds_no_secret(self):
        """The control: nothing to add, nothing flagged."""
        t = _target(ref_config=R2, device_config=R2)
        assert t.reintroduced_secrets == [] and _check(t)[0] == "pass"

    def test_secret_position_has_one_definition(self):
        """The redactor's: a line it would change is a secret line, and no
        second list exists in the mechanism."""
        src = open(os.path.join(ROOT, "modules", "nsot", "authorisation.py")).read()
        assert "redact_positional" in src
        assert not re.search(r"snmp-server|username|key-string", src.split('"""', 2)[2]), \
            "a second list of secret forms"


class TestTheRouteAndTheHash:
    def test_the_restore_program_needs_the_authorisation_and_folds_its_reason(self, monkeypatch):
        from tests.test_p3_restore_is_guarded import _preview_for

        auth = {"line": MASKED, "reason": REASON}
        plain_out = _preview_for(monkeypatch, [_target()])
        plain = plain_out["devices"][0]
        authed = _preview_for(monkeypatch, [_target()], body={
            "ref": "HEAD", "authorise": {"r2": [auth]}})["devices"][0]
        # Awaiting an authorisation, NOT blocked: the program is shown with the
        # line to authorise, and the device cannot be confirmed until it is.
        assert plain["secret_readded"] == [MASKED] and plain["authorisation_ok"] is False
        assert any("<redacted:snmp_community>" in c for c in plain["commands"])
        t = plain_out["preview"]["what"]["targets"][0]
        assert t["state"] == "not_authorised" and t["selectable"] is False
        assert authed["deployable"] is True and authed["authorisation_ok"] is True
        other = _preview_for(monkeypatch, [_target()], body={
            "ref": "HEAD", "authorise": {"r2": [dict(auth, reason="a different stated reason")]}})
        assert other["devices"][0]["command_hash"] != authed["command_hash"], \
            "the reason is part of what was confirmed"
        assert OLD_VALUE not in json.dumps([plain, authed])


class TestTheAggregate:
    """The same line authorised on the same device again and again is a
    pattern worth seeing (the operator, from 8.8's written override)."""

    @pytest.fixture
    def store(self, monkeypatch, tmp_path):
        from modules.nsot import receipts
        path = tmp_path / "receipts.jsonl"
        monkeypatch.setattr(receipts, "path_for", lambda list_name: str(path))
        return path

    def _row(self, at, auth, device="s4", sent=True, outcome="deployed"):
        return {"at": at, "device": device, "actor": "p@example.invalid", "sent": sent,
                "outcome": outcome, "authorised": auth}

    def test_prior_authorisations_count_what_was_sent_and_name_the_last_reason(self, store):
        from modules.nsot import receipts
        rows = [self._row("2026-09-01", ["shutdown"]),                       # before reasons
                self._row("2026-09-02", [{"line": "shutdown", "reason": "port no longer used"}]),
                self._row("2026-09-03", [{"line": "shutdown", "reason": "lab rebuild tonight"}],
                          sent=False, outcome="refused"),                   # not counted
                self._row("2026-09-04", [{"line": "shutdown", "reason": "x y z"}], device="s3")]
        store.write_text("".join(json.dumps(r) + "\n" for r in rows))
        got = receipts.prior_authorisations("Lab", "s4", ["shutdown"])
        assert got["state"] == "ok"
        assert got["lines"]["shutdown"] == {"count": 2, "last_at": "2026-09-02",
                                            "last_actor": "p@example.invalid",
                                            "last_reason": "port no longer used"}

    def test_an_unreadable_record_is_said_never_read_as_never_authorised(self, store):
        from modules.nsot import receipts
        store.write_text("{not json\n")
        assert receipts.prior_authorisations("Lab", "s4")["state"] == "unreadable"

    def test_the_plan_carries_it_and_the_shipped_renderer_draws_it(self, store, monkeypatch):
        from modules.nsot import receipts
        from tests import payload_providers as P
        from tests.payload_render import render_preview

        store.write_text(json.dumps(self._row(
            "2026-09-02", [{"line": "shutdown", "reason": "port no longer used"}])) + "\n")
        plan = P.deploy_plan(monkeypatch)
        d = plan["devices"][0]
        assert d["prior_authorised"]["lines"]["shutdown"]["count"] == 1
        html = render_preview(plan["preview"])
        assert "authorised on this device 1 time(s) before" in html
        assert 'stated reason: "port no longer used"' in html.replace("&quot;", '"')
        assert receipts  # the record the plan read


class TestTheReceiptKeepsTheReason:
    def test_the_row_stores_each_line_with_its_reason_masked(self):
        from modules.nsot.receipts import _authorised_record
        rec = _authorised_record([{"line": "shutdown", "reason": "port no longer used"},
                                  {"line": MASKED, "reason": "old community " + OLD_VALUE
                                   + " kept for the monitor"}])
        assert rec[0] == {"line": "shutdown", "reason": "port no longer used"}
        assert rec[1]["line"] == MASKED

    def test_the_result_draws_it_as_testimony(self):
        import dukpy
        from tests.js_source import read_shipped

        src = read_shipped("static/js/nmas_preview_confirm.js")
        m = re.search(r"function sentHtml\(t, r\) \{", src)
        assert m, "sentHtml"
        html = dukpy.evaljs(src + "\n" + """
            previewConfirmResultHtml({action: 'deploy', level: 'success',
              parts: ['happened','did_not','sent','checks','record','not_watched'],
              happened: {summary: 's', targets: [{name: 's4', outcome: 'deployed', words: 'deployed'}]},
              did_not: {items: [], none: 'nothing'},
              targets: [{name: 's4', sent: {lines: ['shutdown'], program_hash: 'abc',
                 matches: true, match_words: 'm', none: '', actor: 'p@example.invalid',
                 authorised: [{line: 'shutdown', reason: 'port unused'}, 'reload']},
                 checks: {ran: false, why: 'w'}, rollback: {}}],
              record: {statement: 'r'}, not_watched: 'n'})""")
        assert 'authorised by p@example.invalid: <code>shutdown</code>, stated reason: ' in html
        assert "no reason recorded (authorised before reasons were required)" in html
