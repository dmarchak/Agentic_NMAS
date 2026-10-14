"""scripts/nmas-ci-dispatch: the operator's Actions read-and-write token reaches curl only
through its standard input (`curl -K -`), never a command line; a file anyone else can read,
a missing one and a token GitHub refuses are each said plainly, naming the file; nothing the
script prints carries the token (the operator, 2026-10-14). curl is replaced by a recorder:
no test reaches GitHub."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTED = "PLANTED-dispatch-token-9q7"


def _load():
    path = os.path.join(ROOT, "scripts", "nmas-ci-dispatch")
    loader = importlib.machinery.SourceFileLoader("nmas_ci_dispatch", path)
    spec = importlib.util.spec_from_loader("nmas_ci_dispatch", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


D = _load()


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    folder = tmp_path / "nmas"
    folder.mkdir(mode=0o700)
    path = folder / "gh-dispatch-token"
    path.write_text(PLANTED + "\n")
    os.chmod(path, 0o600)
    monkeypatch.setenv("NMAS_DISPATCH_TOKEN_FILE", str(path))
    return path


class _Curl:
    """Records each curl call and answers as GitHub would: writes the body and headers to the
    files curl was told to (-o, -D) and prints the status (-w)."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, argv, input=None, capture_output=None, text=None):
        self.calls.append({"argv": list(argv), "input": input})
        status, body, headers = self.answers.pop(0)
        with open(argv[argv.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
        with open(argv[argv.index("-D") + 1], "w", encoding="utf-8") as fh:
            fh.write(headers)
        return subprocess.CompletedProcess(argv, 0, stdout=str(status), stderr="")


class TestTheTokenNeverReachesACommandLine:
    def test_it_is_in_curls_standard_input_and_in_no_argument(self, token_file):
        curl = _Curl([(204, "", "")])
        D.call("POST", "/repos/a/b/actions/workflows/w.yml/dispatches", {"ref": "main"},
               run=curl)
        (c,) = curl.calls
        assert not [a for a in c["argv"] if PLANTED in a], c["argv"]
        assert c["argv"][c["argv"].index("-K") + 1] == "-", "the config is read from stdin"
        assert f'header = "Authorization: Bearer {PLANTED}"' in c["input"]
        assert 'url = "https://api.github.com/repos/a/b/' in c["input"]

    def test_a_value_with_quotes_survives_the_config(self, token_file):
        """The JSON body is quoted for curl's config: its own quotes and backslashes escaped."""
        cfg = D.curl_config("POST", "https://api.github.com/x", "t",
                            {"inputs": {"functions": 'a "b" \\c'}})
        data = next(line for line in cfg.splitlines() if line.startswith("data = "))
        inner = data[len('data = "'):-1].replace('\\"', '"').replace("\\\\", "\\")
        assert json.loads(inner) == {"inputs": {"functions": 'a "b" \\c'}}

    def test_nothing_it_prints_carries_the_token(self, token_file, monkeypatch, capsys):
        curl = _Curl([(200, {"id": 7, "run_number": 9, "status": "completed",
                             "conclusion": "success", "event": "workflow_dispatch",
                             "head_sha": "abc", "html_url": "u"}, "")])
        monkeypatch.setattr(D.subprocess, "run", curl)
        monkeypatch.setattr(D, "_repo_slug", lambda: "a/b")
        assert D.main(["status", "7"]) == 0
        out = capsys.readouterr()
        assert PLANTED not in out.out + out.err and "run 7 #9: completed success" in out.out


class TestRefusalsAreSaidPlainly:
    def test_a_file_others_can_read_is_refused_naming_it(self, token_file):
        os.chmod(token_file, 0o640)
        with pytest.raises(D.Refused, match=r"can be read by others \(mode 640\)") as exc:
            D.read_token()
        assert str(token_file) in str(exc.value) and PLANTED not in str(exc.value)

    def test_a_missing_file_is_named(self, token_file):
        os.remove(token_file)
        with pytest.raises(D.Refused, match=f"no token file at {token_file}"):
            D.read_token()

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_token_github_refuses_is_said_with_its_file(self, token_file, monkeypatch, capsys,
                                                          status):
        monkeypatch.setattr(D.subprocess, "run", _Curl([(status, {"message": "Bad"}, "")]))
        monkeypatch.setattr(D, "_repo_slug", lambda: "a/b")
        assert D.main(["cancel", "7"]) == D.EXIT_TOKEN
        err = capsys.readouterr().err
        assert f"GitHub refused the token in {token_file} (HTTP {status})" in err
        assert "expired" in err and PLANTED not in err

    def test_the_expiry_is_said_when_near(self):
        now = D.datetime.datetime(2026, 10, 20, tzinfo=D.datetime.timezone.utc)
        near = "github-authentication-token-expiration: 2026-10-21 12:00:00 UTC\n"
        far = "github-authentication-token-expiration: 2026-11-21 12:00:00 UTC\n"
        assert "expires 2026-10-21 12:00 UTC (1 day(s) left)" in D.expiry_warning(near, now)
        assert D.expiry_warning(far, now) == ""


class TestADispatchFindsTheRunItMade:
    def test_the_newest_dispatch_run_after_the_request(self, token_file):
        later = (D.datetime.datetime.now(D.datetime.timezone.utc)
                 + D.datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = "2026-01-01T00:00:00Z"
        curl = _Curl([(204, "", ""),
                      (200, {"workflow_runs": [
                          {"id": 1, "event": "schedule", "created_at": later, "html_url": "x"},
                          {"id": 2, "event": "workflow_dispatch", "created_at": old,
                           "html_url": "y"}]}, ""),
                      (200, {"workflow_runs": [
                          {"id": 3, "event": "workflow_dispatch", "created_at": later,
                           "html_url": "z", "run_number": 5}]}, "")])
        out = D.dispatch("a/b", "w.yml", "main", {}, wait_start=True, run=curl,
                         sleep=lambda s: None)
        assert (out["id"], out["url"], out["run_number"]) == (3, "z", 5)
        assert json.loads(curl.calls[0]["input"].split("data = ", 1)[1].strip()[1:-1]
                          .replace('\\"', '"')) == {"ref": "main"}
