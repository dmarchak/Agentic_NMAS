"""Board H-S (approved 2026-11-01; C235): the Intent tab's Secret references card and its
write-only Set value…, through the real app and routes on test_intent_editor's world (the
network `lab`, device s4), its intent given an account `lab` here and its own credential store.

- The card names each reference and its state, never a value, under the strict policy; the
  account Mercury signs in with offers no Set value….
- ``?set=<ref>`` opens the form for a reference the card lists and may set, and only those.
- A set as the verified person draws the reference, who and the commit in place; the value is
  in no response, and the card then reads it typed.
- A refusal draws the form again with the checks that failed, 400, nothing stored.
- A viewer who is not a verified person is offered no Set value… and is refused by the gate.
- The tab itself carries the card; the device page opens the form without script.
"""

from types import SimpleNamespace

import pytest

from modules import credentials
from modules.nsot import secret_refs as SR
from tests.test_intent_editor import world  # noqa: F401 (the fixture)

TYPED = "Lab-Not-Real-9"
INTENT = {"users": [{"name": "nmas", "privilege": 15, "secret_ref": "user_nmas_secret"},
                    {"name": "lab", "privilege": 15, "secret_ref": "user_lab_secret"}]}
DEV = {"hostname": "s4", "ip": "192.0.2.14", "platform": "cisco_ios",
       "device_type": "cisco_ios", "username": "nmas"}


@pytest.fixture
def sr(world, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr("routes.intent_v2._device_or_404",
                        lambda name: ((SimpleNamespace(name="lab"), DEV), None))
    monkeypatch.setattr(SR, "_intent", lambda list_name, host: INTENT)
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    return world


def _get(w, path):
    r = w["client"].get(path)
    return r, r.get_data(as_text=True)


def _set(w, **form):
    r = w["client"].post("/v2/device/s4/intent/secrets/set", data=form)
    return r, r.get_data(as_text=True)


def test_the_card_names_each_reference_and_offers_set_value_but_for_mercury_s_own(sr):
    from modules import csp
    r, html = _get(sr, "/v2/device/s4/intent/secrets")
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert "Secret references" in html and "user_lab_secret" in html
    assert "the account Mercury signs in with" in html and "changes by Rotate only" in html
    assert html.count('data-op="set-secret-value"') == 1        # lab's row only
    assert 'id="sr-form"' not in html
    assert "nmas:credentials from:body" in html.split(">", 1)[0]      # re-read at rest


@pytest.mark.parametrize("ref,opens", [("user_lab_secret", True), ("user_nmas_secret", False),
                                       ("user_ghost_secret", False)])
def test_set_opens_the_form_only_for_a_reference_it_may_set(sr, ref, opens):
    _r, html = _get(sr, f"/v2/device/s4/intent/secrets?set={ref}")
    assert ('id="sr-form"' in html) is opens
    if opens:
        assert f'name="ref" value="{ref}"' in html and 'type="password"' in html


def test_a_set_is_drawn_in_place_and_the_value_is_in_no_response(sr):
    r, html = _set(sr, ref="user_lab_secret", value=TYPED, again=TYPED,
                   reason="Blind runs: the temporary lab account")
    assert r.status_code == 200, html[:600]
    assert "data-sr-done" in html and "set by" in html and "Recorded in" in html
    assert TYPED not in html
    # The set's own announce (credentials) never redraws its result away.
    head = html.split(">", 1)[0]
    assert "hx-trigger" not in head and "hx-get" not in head
    assert credentials.template_secret_kind(
        credentials.template_secret_key("lab", "s4", "user_lab_secret")) == "plaintext"
    _r, after = _get(sr, "/v2/device/s4/intent/secrets")
    assert "typed, waiting for its deploy" in after and TYPED not in after


def test_a_refusal_draws_the_form_with_what_failed_and_stores_nothing(sr):
    r, html = _set(sr, ref="user_lab_secret", value=TYPED, again="Other-1", reason="why")
    assert r.status_code == 400
    assert 'id="sr-form"' in html and "data-sr-refused" in html and "the two match:" in html
    assert TYPED not in html and "Other-1" not in html
    assert credentials.template_secret_kind(
        credentials.template_secret_key("lab", "s4", "user_lab_secret")) == ""


def test_a_viewer_who_is_not_a_verified_person_is_offered_none_and_refused(sr, monkeypatch):
    from modules import identity
    monkeypatch.setattr(identity, "identify", lambda r: identity.Identity(peer="198.51.100.7"))
    _r, html = _get(sr, "/v2/device/s4/intent/secrets")
    assert 'data-op="set-secret-value"' not in html and "needs a verified person" in html
    r, _html = _set(sr, ref="user_lab_secret", value=TYPED, again=TYPED, reason="why")
    assert r.status_code in (401, 403)
    assert credentials.template_secret_kind(
        credentials.template_secret_key("lab", "s4", "user_lab_secret")) == ""


def test_the_intent_tab_carries_the_card_and_the_page_opens_the_form_without_script(
        sr, monkeypatch):
    ref = SimpleNamespace(name="lab", repo_dir=SR._repo("lab"))
    monkeypatch.setattr("routes.device_v2._device_or_404", lambda name: ((ref, DEV), None))
    _r, html = _get(sr, "/v2/device/s4/intent")
    assert 'id="intent-secrets"' in html and 'id="sr-form"' not in html
    _r, html = _get(sr, "/v2/device/s4?tab=intent&set_secret=user_lab_secret")
    assert 'id="sr-form"' in html
