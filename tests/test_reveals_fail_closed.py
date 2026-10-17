"""Every reveal writes its record FIRST and shows nothing unrecorded (C841; the operator's
decision 2026-10-15, as the log line's reveal does, C818).

The reveal record (`modules/reveal_audit.py`) never raises: `record` answers ``recorded:
False`` when it could not write. Each reveal reads that answer and, when the record was not
written, answers 503 naming why, with nothing unmasked in the answer:

- the golden version on v2 (`device_v2.golden_reveal`);
- the bootstrap config, today's GET and v2's POST (`onboard.bootstrap_reveal`, the one core);
- the golden version and diff behind ``?reveal=1`` (`outbound.config_text`), masked text only.

The planted failure is the real one: the record's file cannot be opened for append (a folder
stands where the file goes), so `record` itself fails, as an unwritable store does. The other
reveals already read the answer and are held by their own tests: the log line
(tests/test_log_reveal.py), the break-glass export (tests/test_breakglass_export.py,
``record_reveal``) and the ZTP responder (tests/test_ztp_responder.py).
"""

import html as H
import subprocess

import pytest

from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)
from tests.test_onboard_abandon import _onboard, repo  # noqa: F401 (the fixture)

#: The bootstrap config's planted credential (in no capture).
BOOT_SECRET = "Pl4ntedB00tCred"
#: What a revealed answer says to every cache (C840; modules/outbound.py).
NO_STORE = "no-store, no-transform"


@pytest.fixture
def unwritable(tmp_path, monkeypatch):
    """The reveal record cannot be written: a folder where its file goes."""
    from modules import reveal_audit
    where = tmp_path / "reveal_audit.jsonl"
    where.mkdir()
    monkeypatch.setattr(reveal_audit, "_path", lambda: str(where))
    assert reveal_audit.record(actor="probe", kind="person", what="probe",
                               target="probe")["recorded"] is False, "the planted failure fails"
    return where


@pytest.fixture
def writable(tmp_path, monkeypatch):
    from modules import reveal_audit
    where = tmp_path / "reveal_audit.jsonl"
    monkeypatch.setattr(reveal_audit, "_path", lambda: str(where))
    return where


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _secret_line(lab):
    from modules.redact import redact_text
    masked = redact_text(lab["captured"])
    assert masked != lab["captured"], "the fixture holds no secret, so this proves nothing"
    return next(l for l, m in zip(lab["captured"].splitlines(), masked.splitlines())
                if l != m).strip()


class TestTheGoldenVersionOnV2:
    def test_unrecorded_it_shows_nothing_and_answers_503_naming_why(self, lab,  # noqa: F811
                                                                     unwritable):
        r = lab["client"].post("/v2/device/r2/golden/reveal", data={"ref": _head(lab["repo"])})
        page = H.unescape(r.get_data(as_text=True))
        assert _secret_line(lab) not in page, "a golden version was revealed unrecorded"
        assert r.status_code == 503, (r.status_code, page[:300])
        assert "the reveal could not be recorded, so nothing is shown" in page
        assert "<pre" not in page

    def test_recorded_it_shows_the_version(self, lab, writable):  # noqa: F811
        """The control's other half: the same request, the record writable, reveals."""
        r = lab["client"].post("/v2/device/r2/golden/reveal", data={"ref": _head(lab["repo"])})
        assert r.status_code == 200
        assert _secret_line(lab) in H.unescape(r.get_data(as_text=True))
        assert r.headers.get("Cache-Control") == NO_STORE, "a revealed golden may be kept (C840)"
        assert '"list": "Lab"' in writable.read_text(), "the reveal names its network (C837)"


class TestTheGoldenBehindRevealOne:
    @pytest.mark.parametrize("path", ["/golden/version/r2?reveal=1&list_name=Lab&ref={sha}",
                                      "/golden/diff/r2?reveal=1&list_name=Lab&a={sha}~1"
                                      "&b={sha}"])
    def test_unrecorded_it_answers_masked_and_503(self, lab, unwritable, path):  # noqa: F811
        sha = _head(lab["repo"])
        r = lab["client"].get(path.format(sha=sha))
        body = r.get_json()
        assert _secret_line(lab) not in r.get_data(as_text=True), \
            "a configuration was revealed unrecorded"
        assert r.status_code == 503, (r.status_code, body)
        assert body["masked"] is True and body["ok"] is False
        assert "could not be recorded, so it is not shown unmasked" in body["error"]

    def test_recorded_it_reveals(self, lab, writable):  # noqa: F811
        sha = _head(lab["repo"])
        r = lab["client"].get(f"/golden/version/r2?reveal=1&list_name=Lab&ref={sha}")
        assert r.status_code == 200 and r.get_json()["masked"] is False
        assert _secret_line(lab) in r.get_json()["config"]
        assert r.headers.get("Cache-Control") == NO_STORE


@pytest.fixture
def pending(repo, monkeypatch):  # noqa: F811
    """bp1 pending in the list `probe`; its bootstrap config as the onboarding core renders
    it, standing in for the render (the reveal's record is what is under test)."""
    _onboard(repo)
    monkeypatch.setattr("modules.nsot.onboard.bootstrap_artifact", lambda repo_dir, host: {
        "ok": True, "hostname": host,
        "config": f"hostname {host}\nusername nmas privilege 15 secret 0 {BOOT_SECRET}\nend\n"})
    import app as A
    return A.app.test_client()


class TestTheBootstrapConfig:
    def test_v2_unrecorded_shows_nothing_and_answers_503(self, pending, unwritable):
        r = pending.post("/v2/onboard/bp1/bootstrap", data={"list_name": "probe"})
        page = r.get_data(as_text=True)
        assert BOOT_SECRET not in page, "a bootstrap config was revealed unrecorded"
        assert r.status_code == 503, (r.status_code, page[:300])
        assert "the reveal could not be recorded, so nothing is shown" in H.unescape(page)

    # Today's reveal (GET /onboard/bootstrap/<host>) and its two assertions left with today's
    # pending banner at 7.8 (2026-10-17, P7-25); v2's, above and below, call the same core.

    def test_recorded_it_reveals(self, pending, writable):
        r = pending.post("/v2/onboard/bp1/bootstrap", data={"list_name": "probe"})
        assert r.status_code == 200 and BOOT_SECRET in r.get_data(as_text=True)
        assert r.headers.get("Cache-Control") == NO_STORE, "a revealed bootstrap may be kept"
        assert "reveals" in r.headers.get("X-NMAS-Invalidates", ""), "History is not told"
        assert BOOT_SECRET not in writable.read_text(), "the record holds the value"
        assert '"list": "probe"' in writable.read_text()
