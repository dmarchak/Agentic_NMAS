"""`scripts/nmas-ci-log` reads CI with the operator's Actions-read token
(2026-10-01) and never lets the token go anywhere but GitHub's API.

No network: every request goes to a recording opener. The token is planted
built by concatenation, so no file here holds one.
"""
import datetime
import io
import os
import urllib.error
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CL = SourceFileLoader("ci_log", str(ROOT / "scripts" / "nmas-ci-log")).load_module()
TOKEN = "github" + "_pat_" + "11AAAAAAA0" + "t" * 72


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    d = tmp_path / "nmas"
    d.mkdir(mode=0o700)
    f = d / "github-actions-read.token"
    f.write_text(TOKEN + "\n")
    f.chmod(0o600)
    monkeypatch.setenv("NMAS_CI_TOKEN_FILE", str(f))
    return f


class TestTheTokenFile:
    def test_owner_only_is_read(self, token_file):
        assert CL.read_token() == TOKEN

    def test_a_file_others_can_read_is_refused(self, token_file):
        token_file.chmod(0o644)
        with pytest.raises(CL.TokenRefused, match="mode 0644"):
            CL.read_token()

    def test_a_directory_others_can_enter_is_refused(self, token_file):
        token_file.parent.chmod(0o755)
        try:
            with pytest.raises(CL.TokenRefused, match="directory is mode 0755"):
                CL.read_token()
        finally:
            token_file.parent.chmod(0o700)

    def test_a_symlink_or_an_absent_file_is_refused(self, token_file, tmp_path, monkeypatch):
        link = token_file.parent / "link.token"
        link.symlink_to(token_file)
        monkeypatch.setenv("NMAS_CI_TOKEN_FILE", str(link))
        with pytest.raises(CL.TokenRefused, match="not a regular file"):
            CL.read_token()
        monkeypatch.setenv("NMAS_CI_TOKEN_FILE", str(tmp_path / "none"))
        with pytest.raises(CL.TokenRefused, match="no token file"):
            CL.read_token()


class _Resp:
    def __init__(self, body=b"{}", headers=None, status=200):
        self.status, self._body, self.headers = status, body, headers or {}

    def read(self):
        return self._body


class _Opener:
    """Records every request; answers from a script of responses."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def open(self, req, timeout=None):
        self.seen.append((req.full_url, dict(req.header_items())))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def _redirect(to):
    return urllib.error.HTTPError("https://api.github.com/x", 302, "Found",
                                  {"Location": to}, io.BytesIO(b""))


class TestTheTokenGoesOnlyToTheApi:
    def test_the_api_request_carries_it_in_the_header(self):
        op = _Opener(_Resp(b'{"workflow_runs": []}'))
        CL.get("/repos/x/actions/runs", TOKEN, opener=op)
        (url, headers), = op.seen
        assert url.startswith("https://api.github.com/")
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in url

    def test_a_redirect_to_the_log_store_is_asked_WITHOUT_it(self):
        """Python's redirect handler forwards Authorization; the script's does not."""
        op = _Opener(_redirect("https://logs.example.invalid/blob?sig=1"), _Resp(b"log text"))
        got = CL.get("/repos/x/actions/jobs/1/logs", TOKEN, opener=op)
        assert got.body == b"log text"
        (_u1, h1), (u2, h2) = op.seen
        assert "Authorization" in h1 and u2.startswith("https://logs.example.invalid/")
        assert "Authorization" not in h2 and TOKEN not in str(h2)

    def test_a_redirect_off_https_is_refused(self):
        op = _Opener(_redirect("http://logs.example.invalid/blob"))
        with pytest.raises(RuntimeError, match="non-https"):
            CL.get("/x", TOKEN, opener=op)
        assert len(op.seen) == 1

    def test_an_error_never_carries_the_token(self):
        err = urllib.error.HTTPError("https://api.github.com/x", 401, "Bad credentials",
                                     {}, io.BytesIO(b""))
        with pytest.raises(RuntimeError) as exc:
            CL.get("/x", TOKEN, opener=_Opener(err))
        assert "401" in str(exc.value) and TOKEN not in str(exc.value)

    def test_the_default_opener_does_not_follow_redirects(self):
        handlers = [type(h).__name__ for h in CL._opener().handlers]
        assert "_NoRedirect" in handlers and "HTTPRedirectHandler" not in handlers


class TestTheExpiryIsSaidBeforeItLapses:
    NOW = datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)
    H = "github-authentication-token-expiration"

    def test_fewer_than_two_weeks_left_warns(self):
        w = CL.expiry_warning({self.H: "2026-10-10 00:00:00 UTC"}, now=self.NOW)
        assert "expires 2026-10-10 (9 day(s) left)" in w and "new one" in w

    def test_more_left_says_nothing(self):
        assert CL.expiry_warning({self.H: "2026-12-30 00:00:00 UTC"}, now=self.NOW) == ""

    def test_an_unparseable_expiry_is_said(self):
        assert "cannot parse" in CL.expiry_warning({self.H: "soon"}, now=self.NOW)


class TestTheCommandNeverPrintsIt:
    def test_runs_and_a_failure_print_no_token(self, token_file, monkeypatch, capsys):
        body = (b'{"workflow_runs": [{"id": 7, "run_number": 245, "head_sha": "9fd781b0",'
                b' "status": "completed", "conclusion": "failure", "created_at": "t"}]}')
        monkeypatch.setattr(CL, "_opener", lambda: _Opener(_Resp(body, {
            "github-authentication-token-expiration": "2026-10-05 00:00:00 UTC"})))
        assert CL.main(["runs"]) == 0
        out = capsys.readouterr()
        assert "#245 9fd781b" in out.out and "WARNING" in out.err
        assert TOKEN not in out.out + out.err

    def test_a_refused_file_exits_1_naming_why(self, token_file, capsys):
        token_file.chmod(0o640)
        assert CL.main(["runs"]) == CL.EXIT_TOKEN
        err = capsys.readouterr().err
        assert "mode 0640" in err and TOKEN not in err


class TestTimes:
    """`times` (C614, the operator, 2026-10-09): each completed run's job minutes and each job's
    slowest run, a job past TRIGGER_MINUTES said."""

    @staticmethod
    def _job(name, start, end):
        return (f'{{"name": "{name}", "started_at": "2026-10-09T19:{start}Z",'
                f' "completed_at": "2026-10-09T19:{end}Z"}}')

    def test_minutes_are_completed_less_started_and_unknown_is_none(self):
        assert CL.job_minutes({"started_at": "2026-10-09T19:00:00Z",
                               "completed_at": "2026-10-09T19:10:30Z"}) == 10.5
        assert CL.job_minutes({"started_at": "2026-10-09T19:00:00Z",
                               "completed_at": None}) is None

    def test_the_slowest_run_of_each_job_and_the_trigger(self, token_file, monkeypatch, capsys):
        runs = (b'{"workflow_runs": ['
                b'{"id": 2, "run_number": 562, "head_sha": "aaaaaaa1", "status": "completed",'
                b' "created_at": "t2"},'
                b'{"id": 1, "run_number": 561, "head_sha": "bbbbbbb2", "status": "completed",'
                b' "created_at": "t1"},'
                b'{"id": 3, "run_number": 563, "head_sha": "ccccccc3", "status": "in_progress",'
                b' "created_at": "t3"}]}')
        second = ('{"jobs": [' + self._job("tests (browser)", "00:00", "10:30") + ", "
                  + self._job("tests (a)", "00:00", "05:00") + "]}").encode()
        first = ('{"jobs": [' + self._job("tests (browser)", "00:00", "08:00") + ", "
                 + self._job("tests (a)", "00:00", "06:00") + "]}").encode()
        op = _Opener(_Resp(runs), _Resp(second), _Resp(first))
        monkeypatch.setattr(CL, "_opener", lambda: op)
        assert CL.main(["times"]) == 0
        out = capsys.readouterr().out
        assert "#562 aaaaaaa t2: tests (browser) 10.5; tests (a) 5.0" in out
        assert "slowest of 2 completed runs" in out           # the run in progress left out
        assert "  tests (browser): 10.5 in #562  PAST THE TRIGGER" in out
        assert "  tests (a): 6.0 in #561\n" in out
        assert len(op.seen) == 3


def test_the_failing_lines_are_what_a_reader_needs():
    log = ("2026-10-01T02:57:39.2Z ............\n"
           "2026-10-01T02:57:39.2Z E       AssertionError: a different status\n"
           "2026-10-01T02:57:39.2Z FAILED tests/test_x.py::T::t - AssertionError\n"
           "2026-10-01T02:57:39.2Z all good here\n")
    got = CL.failing_lines(log)
    assert got == ["E       AssertionError: a different status",
                   "FAILED tests/test_x.py::T::t - AssertionError"]
