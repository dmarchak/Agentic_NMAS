"""Reveal one golden version on v2 (decided 2026-10-05: revealing stays in the GUI, a person,
recorded; built 2026-10-10), on test_capture's lab (r2's REAL configuration committed as its
golden, `golden/r2/...` tagged).

- a golden row on the device's History offers Reveal r2's version…, posting the row's commit;
- a person sees the version unmasked, and the reveal is recorded BEFORE the text is drawn;
- a request that is no person draws nothing, and records nothing;
- a commit that is no hex, or one with no golden for the device, is refused naming it.
"""

import re
import subprocess

import pytest

from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def test_a_person_sees_the_version_and_it_is_recorded_first(lab, monkeypatch):  # noqa: F811
    from modules import reveal_audit
    from modules.redact import redact_text

    seen = []
    real = reveal_audit.record
    monkeypatch.setattr(reveal_audit, "record", lambda **k: seen.append(k) or real(**k))
    sha = _head(lab["repo"])
    r = lab["client"].post("/v2/device/r2/golden/reveal", data={"ref": sha})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:300]
    assert seen and seen[0]["what"] == "golden_config" and seen[0]["target"] == "r2"
    assert seen[0]["detail"] == sha
    assert "unmasked: revealed to test-person@example.invalid" in html
    masked = redact_text(lab["captured"])
    assert masked != lab["captured"], "the fixture holds no secret, so this proves nothing"
    secret_line = next(l for l, m in zip(lab["captured"].splitlines(), masked.splitlines())
                       if l != m)
    import html as H
    assert secret_line.strip() in H.unescape(html), "the reveal drew the masked text"


@pytest.mark.real_identity
def test_no_person_draws_nothing_and_records_nothing(lab, monkeypatch):  # noqa: F811
    from modules import reveal_audit
    monkeypatch.setattr(reveal_audit, "record", lambda **k: pytest.fail("recorded"))
    r = lab["client"].post("/v2/device/r2/golden/reveal", data={"ref": _head(lab["repo"])})
    assert r.status_code in (401, 403)
    assert "<pre" not in r.get_data(as_text=True)


@pytest.mark.parametrize("ref,code,words", [("not-a-sha", 400, "is not a commit"),
                                            ("0" * 40, 404, "has no golden at")])
def test_a_bad_commit_is_refused_naming_it(lab, ref, code, words):  # noqa: F811
    r = lab["client"].post("/v2/device/r2/golden/reveal", data={"ref": ref})
    assert r.status_code == code and words in r.get_data(as_text=True)


def test_a_golden_row_offers_the_reveal(lab):  # noqa: F811
    html = lab["client"].get("/v2/device/r2/history").get_data(as_text=True)
    m = re.search(r'hx-post="/v2/device/r2/golden/reveal[^"]*" hx-vals=\'\{&#34;ref&#34;: '
                  r'&#34;([0-9a-f]{40})&#34;\}\'', html) or \
        re.search(r'hx-post="/v2/device/r2/golden/reveal[^"]*" hx-vals=\'\{"ref": "([0-9a-f]{40})"\}\'',
                  html)
    assert m, "no golden row offers Reveal"
    assert "Reveal r2&#39;s version…" in html or "Reveal r2's version…" in html
