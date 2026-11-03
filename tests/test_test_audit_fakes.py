"""The existing-test audit's tool (e), fakes (docs/TEST_AUDIT.md; `scripts/nmas-test-audit-fakes`),
run on its committed canary (`docs/test_audit/canary/fakes/`, its files stored as `<name>.txt` so
pytest never collects them, copied here into a temporary folder under their real names; the
list of files is git's, `tests.source_index.tracked()`).

The canary is a root of its own: a planted Widget API's recording
(`tests/fixtures/widget/answers.json`: a read, a widget that is not there, a create), a fake
module `tests/fake_widget.py` and a test file using two of its fakes.

- **Each plant has its state:** `FakeWidget` (typed by hand, answering as recorded) and
  `FakeWidgetDrifted` recorded; `FakeWidgetReplay` (it reads the recording) built from
  recording; `FakeGadget` (a service with no folder) no recording, naming the folder it looked
  for; `Answer`, the fake module's response class, recorded with no driver. A docstring naming
  the recording is not taken for reading it.
- **The comparison lists exactly what differs:** nothing for `FakeWidget`; for
  `FakeWidgetDrifted` the missing `tags` key and the `size` that became a string, and nothing
  else; each compared fake asked all three recorded requests.
- **The field-by-field rules**, on answers built here: a status, a content type, a fake that
  raises (named by its exception), a text body by its line count (never its text), a nested
  array's element key.
- **The output** carries its header, a state row per fake, its counts, and no address or email;
  a root with no `tests/` exits 2.
"""
import importlib.machinery
import importlib.util
import os
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANARY = os.path.join(ROOT, "docs", "test_audit", "canary", "fakes")
F = "tests/fake_widget.py"

#: Every fake in the canary and its state: the run's inventory must equal it.
EXPECTED_FAKE_STATES = {
    ("Answer", "recorded"),
    ("FakeWidget", "recorded"),
    ("FakeWidgetDrifted", "recorded"),
    ("FakeWidgetReplay", "built from recording"),
    ("FakeGadget", "no recording"),
}
#: Every differing field the canary's run lists: (fake, field, recorded, fake's).
EXPECTED_FAKE_DIFFERENCES = {
    ("FakeWidgetDrifted", "GET /widgets/1 body.tags", "array", "absent"),
    ("FakeWidgetDrifted", "GET /widgets/1 body.size", "integer", "string"),
}


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-test-audit-fakes")
    loader = importlib.machinery.SourceFileLoader("nmas_test_audit_fakes", path)
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("nmas_test_audit_fakes", loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def canary(tmp_path):
    """The committed canary under its real names, in a folder of its own."""
    from tests.source_index import tracked
    root = tmp_path / "te-canary"
    copied = 0
    for src in tracked(CANARY):
        f = os.path.basename(src)
        assert f.endswith(".txt"), f"every canary file is stored as .txt: {f}"
        dst = root / os.path.relpath(src, CANARY)[: -len(".txt")]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
    assert copied >= 3, "floor: the canary's three files are committed (git add them)"
    return str(root)


@pytest.fixture
def result(canary):
    return _tool().audit(canary)


def _by_name(result):
    return {f["name"]: f for f in result["fakes"]}


def test_every_plant_has_its_state(result):
    got = {(f["name"], f["state"]) for f in result["fakes"]}
    assert got == EXPECTED_FAKE_STATES, (
        f"missed: {sorted(EXPECTED_FAKE_STATES - got)}; unexpected: "
        f"{sorted(got - EXPECTED_FAKE_STATES)}")


def test_the_drifted_fake_lists_exactly_its_two_fields_and_the_matching_one_none(result):
    got = {(r[0], r[5], r[6], r[7]) for r in result["rows"] if r[4] == "differs"}
    assert got == EXPECTED_FAKE_DIFFERENCES, (
        f"missed: {sorted(EXPECTED_FAKE_DIFFERENCES - got)}; unexpected: "
        f"{sorted(got - EXPECTED_FAKE_DIFFERENCES)}")
    fakes = _by_name(result)
    for name in ("FakeWidget", "FakeWidgetDrifted"):
        assert fakes[name]["compared"].startswith("compared: 3 requests"), fakes[name]["compared"]
    assert fakes["FakeWidget"]["differing"] == []


def test_each_state_says_what_it_rests_on(result):
    fakes = _by_name(result)
    assert fakes["FakeWidgetReplay"]["reads"] == ["tests/fixtures/widget/answers.json"]
    assert fakes["FakeWidgetReplay"]["compared"] == "not compared: answers from the recording"
    assert fakes["FakeWidget"]["reads"] == [], "a docstring naming the recording is not a read"
    assert fakes["FakeWidget"]["recording"] == "1 file in tests/fixtures/widget"
    assert fakes["FakeGadget"]["recording"] == "looked: tests/fixtures/gadget"
    assert fakes["Answer"]["found_by"] == "fake module"
    assert fakes["Answer"]["compared"] == "not compared: no driver"
    assert fakes["FakeWidget"]["used_by"] == {"tests/test_widget_client.py"}


def _http(status=200, ctype="application/json", body="{}"):
    return {"status": status, "content_type": ctype, "body": body}


def _ex(recorded, fake, kind="http"):
    return {"recording": "r.json", "request": "GET /x", "kind": kind,
            "recorded": recorded, "fake": fake}


def test_the_field_rules_on_answers_built_here():
    tool = _tool()
    assert tool.compare(_ex(_http(), _http())) == []
    assert ("status", "404", "200") in tool.compare(_ex(_http(404), _http(200)))
    assert ("content type", "text/html; charset=UTF-8", "text/html") in tool.compare(
        _ex(_http(ctype="text/html; charset=UTF-8"), _http(ctype="text/html")))
    assert tool.compare(_ex(_http(), {"raised": "KeyError"})) == [
        ("answer", "status 200", "raised KeyError")]
    rows = tool.compare(_ex(_http(body='{"1": [{"a": 1}, {"b": "x"}]}'),
                            _http(body='{"1": [{"a": 1}]}')))
    assert rows == [("body.1[].b", "string", "absent")]
    text = tool.compare(_ex({"text": "line one\nline two\n"}, {"text": "other\n"}, "text"))
    assert text == [("text", "text, 2 lines", "text, 1 line, not the recorded text")]
    assert "line one" not in repr(text) and "other" not in repr(text)


def test_the_output_has_its_header_rows_counts_and_no_address(canary, tmp_path, capsys):
    tool = _tool()
    out = tmp_path / "raw.tsv"
    assert tool.main(["--root", canary, "--out", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "fake\tfile\tservice\trecording\tstate\tfield\trecorded\tfake"
    states = [ln.split("\t") for ln in lines[1:] if ln and not ln.startswith("#")]
    assert {(r[0], r[4]) for r in states if r[4] != "differs"} == EXPECTED_FAKE_STATES
    assert "# fakes\t5" in lines and "# differing-field rows\t2" in lines
    assert tool._cell("http://192.0.2.10:8080 by t@example.com") == "http://<address>:8080 by <email>"
    assert tool.main(["--root", str(tmp_path / "nothing-here")]) == 2
    assert "holds no tests/" in capsys.readouterr().err
