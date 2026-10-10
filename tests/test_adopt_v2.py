"""Devices › Adopt a device… on v2 (7.4's board G, built 2026-10-10), on test_capture's lab.

`adopt.plan` and `adopt.apply` are replaced at their edge (each has its own tests,
tests/test_adopt_apply.py and tests/test_adopt_account.py); through the real routes and template:

- Devices offers Adopt a device…, its how-link beside it; the form's password fields are
  password fields and draw no value;
- the preview passes the typed login to the plan and draws every gate by name, the program, what
  a save makes permanent and what it does not do, and never draws the typed password back; the
  confirm carries the fingerprint and every field but the password, which it asks for again;
- a plan with a reason it cannot be adopted draws every reason and offers no confirm;
- the confirm without the fingerprint or the password typed again starts nothing; a request
  that is no person starts nothing;
- the confirm starts the apply as a job, as the verified person, with the fingerprint and the
  password typed again; the running card draws the stepper and its poll carries no password;
  the result draws each step, and a stop names its reason and what remains.
"""

import re

import pytest

from modules.nsot import adopt
from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)

TYPED = "Typed-Once-7731"
FORM = {"list_name": "Lab", "hostname": "r9", "mgmt_ip": "192.0.2.29",
        "platform": "cisco-ios-xe", "role": "router", "supplied_username": "owner",
        "supplied_password": TYPED}
FP = "f" * 64


def _plan(**over):
    p = {"device": "r9", "list": "Lab", "gates": [
        {"name": "role", "state": "pass", "detail": "recorded as a router"},
        {"name": "local_login", "state": "pass", "detail": "a local account logs in over SSH"}],
        "blocking": [], "resume": False,
        "program": ["username nmas privilege 15 secret 9 <redacted>"],
        "not_doing": list(adopt.NOT_DOING), "fingerprint": FP,
        "persist": {"sentence": "Saving makes 1 running line permanent."}, "netbox": {},
        "rw_kept": [], "_device": {"password": TYPED}}
    p.update(over)
    return p


@pytest.fixture
def planned(monkeypatch):
    seen = []
    monkeypatch.setattr(adopt, "plan", lambda *a, **k: seen.append((a, k)) or _plan())
    return seen


def test_devices_offers_adopt_with_its_how_link(lab):  # noqa: F811
    html = lab["client"].get("/v2/devices?list=Lab").get_data(as_text=True)
    m = re.search(r'<a class="btn" data-op="adopt" href="/v2/adopt/new\?list=Lab"[^>]*>'
                  r'Adopt a device…</a>\{?', html)
    assert m, "Devices offers no Adopt a device…"
    assert 'id="adopt-card"' in html


def test_the_form_draws_password_fields_with_no_value(lab):  # noqa: F811
    html = lab["client"].get("/v2/adopt/new?list=Lab").get_data(as_text=True)
    for name in ("supplied_password", "supplied_enable"):
        tag = re.search(rf'<input[^>]*name="{name}"[^>]*>', html).group(0)
        assert 'type="password"' in tag and "value=" not in tag, tag


def test_the_preview_draws_the_plan_and_never_the_password(lab, planned):  # noqa: F811
    r = lab["client"].post("/v2/adopt/preview", data=FORM)
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:400]
    (args, kw), = planned
    assert args == ("Lab", "r9") and kw["supplied_password"] == TYPED
    assert kw["platform"] == "cisco_iosxe" and kw["role"] == "router"
    assert TYPED not in html, "the typed password was drawn back"
    for words in ("role", "recorded as a router", "local_login",
                  "username nmas privilege 15 secret", "Saving makes 1 running line",
                  "No intent is committed"):
        assert words in html, words
    confirm = re.search(r'<form[^>]*action="/v2/adopt/confirm".*?</form>', html, re.S).group(0)
    assert f'name="fingerprint" value="{FP}"' in confirm
    assert 'name="mgmt_ip" value="192.0.2.29"' in confirm
    pw = re.search(r'<input[^>]*name="supplied_password"[^>]*>', confirm).group(0)
    assert 'type="password"' in pw and "value=" not in pw, pw
    assert "Adopt r9" in confirm


def test_a_blocked_plan_draws_every_reason_and_offers_no_confirm(lab, monkeypatch):  # noqa: F811
    gates = [{"name": "role", "state": "fail", "detail": "no role was given"},
             {"name": "credential", "state": "fail", "detail": "the login was refused"}]
    monkeypatch.setattr(adopt, "plan", lambda *a, **k: _plan(
        gates=gates, blocking=[g["detail"] for g in gates], fingerprint=""))
    html = lab["client"].post("/v2/adopt/preview", data=FORM).get_data(as_text=True)
    assert "2 reasons it cannot be adopted" in html
    assert "no role was given" in html and "the login was refused" in html
    assert "/v2/adopt/confirm" not in html


def test_a_preview_naming_no_network_is_refused(lab, planned):  # noqa: F811
    r = lab["client"].post("/v2/adopt/preview", data=dict(FORM, list_name=""))
    assert r.status_code == 400 and "no network was named" in r.get_data(as_text=True)
    assert not planned


@pytest.mark.parametrize("drop", ["fingerprint", "supplied_password"])
def test_a_confirm_without_the_fingerprint_or_the_password_starts_nothing(lab, monkeypatch,  # noqa: F811
                                                                          drop):
    from modules.nsot import capture_job
    monkeypatch.setattr(capture_job, "start", lambda *a, **k: pytest.fail("started"))
    body = {k: v for k, v in dict(FORM, fingerprint=FP).items() if k != drop}
    r = lab["client"].post("/v2/adopt/confirm", data=body)
    assert r.status_code == 400 and "typed again" in r.get_data(as_text=True)


@pytest.mark.real_identity
def test_no_person_starts_nothing(lab, monkeypatch):  # noqa: F811
    from modules.nsot import capture_job
    monkeypatch.setattr(capture_job, "start", lambda *a, **k: pytest.fail("started"))
    r = lab["client"].post("/v2/adopt/confirm", data=dict(FORM, fingerprint=FP))
    assert r.status_code in (401, 403)


def _run(lab, monkeypatch, result):  # noqa: F811
    from modules.nsot import capture_job
    seen = []
    monkeypatch.setattr(adopt, "apply", lambda *a, **k: seen.append((a, k)) or dict(result))
    html = lab["client"].post("/v2/adopt/confirm", data=dict(FORM, fingerprint=FP,
                                                                reason="brought in from the "
                                                                       "old team")) \
        .get_data(as_text=True)
    m = re.search(r'hx-get="(/v2/adopt/job/([0-9a-f]+)[^"]*)"', html)
    assert m, html[:600]
    assert TYPED not in html and "supplied_password" not in m.group(1)
    assert "Adoption progress" in html and "Add the tool&#39;s account" in html
    assert capture_job.wait(m.group(2), 30)
    card = lab["client"].get(m.group(1).replace("&amp;", "&")).get_data(as_text=True)
    return seen, card


def test_the_confirm_runs_the_apply_as_the_person_and_draws_the_result(lab, monkeypatch):  # noqa: F811
    steps = [{"step": s, "ok": True, "detail": ""} for s in adopt.APPLY_STEPS]
    seen, card = _run(lab, monkeypatch, {"ok": True, "steps": steps, "remaining": [],
                                         "reason": ""})
    (args, kw), = seen
    assert args == ("Lab", "r9")
    assert kw["confirmed_fingerprint"] == FP and kw["supplied_password"] == TYPED
    assert kw["actor"] == "test-person@example.invalid"
    assert kw["reason"] == "brought in from the old team"
    assert "r9 is adopted" in card and "Open r9's page" in card
    assert card.count("done") >= len(adopt.APPLY_STEPS)
    # Board G (v32) ends there: the seed with its fidelity and one commit, then the export.
    seed = card.index('href="/v2/device/r9?list=Lab&amp;op=seed">Seed r9\'s intent…</a>')
    export = re.search(r'href="(/v2/credentials[^"]*)">Export the break-glass record…', card)
    assert export, "no export offered"
    assert "list=Lab" in export.group(1) and "open=export" in export.group(1), export.group(1)
    assert seed < export.start(), "the seed comes first, then the export"


def test_a_stop_offers_neither_the_seed_nor_the_export(lab, monkeypatch):  # noqa: F811
    _seen, card = _run(lab, monkeypatch, {"ok": False, "steps": [], "remaining": [],
                                          "reason": "the device moved"})
    assert "op=seed" not in card and "open=export" not in card


def test_a_stop_names_its_reason_and_what_remains(lab, monkeypatch):  # noqa: F811
    steps = [{"step": "confirm", "ok": True, "detail": ""},
             {"step": "account", "ok": False, "detail": "the device refused the new account"}]
    _seen, card = _run(lab, monkeypatch, {
        "ok": False, "steps": steps, "reason": "the device refused the new account",
        "remaining": [{"step": "golden", "why": "the account was not added"}]})
    assert "r9 is NOT adopted: the device refused the new account" in card
    assert "Still to finish" in card and "the account was not added" in card
    assert "resumes where it stopped" in card


def test_the_stepper_is_adopt_s_declared_steps(lab):  # noqa: F811
    from modules import device_actions
    rows = device_actions.job_steps("adopt", "Lab", "r9")
    assert len(rows) == len(adopt.STEPPER) == len(adopt.APPLY_STEPS)
    assert [s[0] for s in adopt.STEPPER] == list(adopt.APPLY_STEPS)
