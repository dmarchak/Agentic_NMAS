"""The spec card's format (the SDN platform design rev. 6, section 11a, item 1; T23's `ask:` case):
`modules/jobs/spec.py` reads `spec.yml` and refuses each malformed field by name, and refuses a
card holding an open question (`ask:`) naming where it sits, before any other field is judged.
The three fixture jobs' cards (tests/fixtures/jobs/) are the accepted cases."""

import os

import pytest
import yaml

from modules.jobs import spec as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "tests", "fixtures", "jobs")
FOLDERS = ("switch-links", "arp-guard", "tautology")


def card(**changes) -> dict:
    """A valid card as YAML would read it, with *changes* (None removes a field)."""
    data = {
        "kind": "job", "name": "switch-links",
        "summary": "Each switch with its link count, and which are busy.",
        "permission": "read",
        "scope": {"object_types": ["dcim.device"], "roles": ["openflow-switch"]},
        "inputs": {"busy": "int"}, "outputs": {"links": "table"},
        "examples": [
            {"name": "every switch is listed", "given": "the recorded switches",
             "when": "the job runs", "then": "each is a row", "fixture": "ryu_recorded"},
            {"name": "a busy switch is busy", "given": "a threshold of 2",
             "when": "a switch has 3 links", "then": "it is busy", "fixture": "netbox_export"},
        ],
    }
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def refusal(data) -> list:
    with pytest.raises(S.SpecError) as exc:
        S.parse_spec(yaml.safe_dump(data, sort_keys=False), "spec.yml")
    return exc.value.problems


def test_each_fixture_jobs_card_is_accepted():
    for folder in FOLDERS:
        got = S.load_spec(os.path.join(JOBS, folder))
        assert got.name == folder
        assert len(got.examples) >= S.MIN_EXAMPLES
        assert all(e.fixture in S.FIXTURES for e in got.examples)


def test_a_valid_card_reads_back_its_fields():
    got = S.parse_spec(yaml.safe_dump(card()))
    assert got.kind == "job" and got.permission == "read"
    assert got.scope.object_types == ("dcim.device",)
    assert got.inputs["busy"].type == "int"
    assert got.outputs["links"].type == "table"
    assert got.example_names() == ["every switch is listed", "a busy switch is busy"]


# ── open questions ───────────────────────────────────────────────────────────────────────────

def test_an_ask_as_a_mapping_is_refused_naming_its_field():
    problems = refusal(card(permission={"ask": "read or write?"}))
    assert problems == ["permission: an open question, 'read or write?': answer it before the "
                        "card is checked"]


def test_an_ask_as_a_string_is_refused_naming_its_field():
    problems = refusal(card(inputs={"busy": "ask: an int, or a list of thresholds?"}))
    assert len(problems) == 1
    assert problems[0].startswith("inputs.busy: an open question, 'ask: an int")


def test_an_ask_inside_an_example_names_its_place():
    data = card()
    data["examples"][1]["then"] = {"ask": "block or allow while the service is down?"}
    problems = refusal(data)
    assert problems == ["examples[1].then: an open question, 'block or allow while the service "
                        "is down?': answer it before the card is checked"]


def test_every_ask_is_named_and_nothing_else_is_judged_first():
    data = card(permission={"ask": "read or write?"}, scope={"ask": "which roles?"},
                summary="")
    problems = refusal(data)
    assert [p.split(":")[0] for p in problems] == ["permission", "scope"]


def test_a_word_beginning_ask_is_not_a_question():
    got = S.parse_spec(yaml.safe_dump(card(summary="Asks each switch for its links.")))
    assert got.summary.startswith("Asks")


# ── each field refused by name ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("changes, field, words", [
    ({"name": "switch_links"}, "(the whole)", "is not a job's name"),
    ({"kind": "app", "name": "dns-blacklist"}, "(the whole)", "is not an app's name"),
    ({"kind": "script"}, "kind", "refused"),
    ({"summary": ""}, "summary", "a summary is plain words"),
    ({"summary": "x" * 201}, "summary", "at most 200 characters, not 201"),
    ({"permission": "admin"}, "permission", "refused"),
    ({"scope": {"object_types": ["*"]}}, "scope.object_types", "does not match"),
    ({"scope": {"object_types": []}}, "(the whole)", "names at least one NetBox object type"),
    ({"inputs": {"busy": "number"}}, "inputs", "inputs.busy's type 'number' is not one of"),
    ({"inputs": {"Busy": "int"}}, "inputs", "does not match"),
    ({"inputs": {"busy": "list[table]"}}, "inputs", "is not one of"),
    ({"outputs": {"links": "HostRef"}}, "outputs", "outputs.links's type 'HostRef'"),
    ({"outputs": {"links": "list[str]"}}, "outputs", "is not one of"),
    ({"surprise": 1}, "surprise", "not a field of this contract"),
    ({"permission": None}, "permission", "missing"),
    ({"examples": None}, "examples", "missing"),
])
def test_a_malformed_field_is_refused_by_name(changes, field, words):
    problems = refusal(card(**changes))
    assert any(p.startswith(f"{field}:") and words in p for p in problems), problems


def test_an_app_card_takes_an_apps_name():
    got = S.parse_spec(yaml.safe_dump(card(kind="app", name="dns_blacklist")))
    assert got.kind == "app"


def test_an_input_may_be_a_list_of_an_input_type():
    got = S.parse_spec(yaml.safe_dump(card(inputs={"hosts": {"type": "list[HostRef]",
                                                             "description": "the hosts"}})))
    assert got.inputs["hosts"].type == "list[HostRef]"
    assert got.inputs["hosts"].description == "the hosts"


def test_fewer_than_two_examples_are_refused():
    data = card()
    data["examples"] = data["examples"][:1]
    problems = refusal(data)
    assert any(p.startswith("examples:") and "at least 2 acceptance examples, not 1" in p
               for p in problems), problems


def test_an_example_name_given_twice_is_refused():
    data = card()
    data["examples"][1]["name"] = data["examples"][0]["name"]
    problems = refusal(data)
    assert any("'every switch is listed' more than once" in p for p in problems), problems


@pytest.mark.parametrize("field, value, words", [
    ("fixture", "live_lab", "refused"),
    ("given", "", "an example's given is plain words"),
    ("then", " ", "an example's then is plain words"),
    ("name", "x" * 121, "at most 120 characters"),
])
def test_a_malformed_example_is_refused_naming_its_place(field, value, words):
    data = card()
    data["examples"][0][field] = value
    problems = refusal(data)
    assert any(p.startswith(f"examples.0.{field}:") and words in p for p in problems), problems


# ── the file itself ──────────────────────────────────────────────────────────────────────────

def test_a_key_given_twice_is_refused_naming_its_line():
    text = yaml.safe_dump(card(), sort_keys=False) + "name: another-name\n"
    with pytest.raises(S.SpecError) as exc:
        S.parse_spec(text)
    assert "the key 'name' is given twice" in exc.value.problems[0]
    assert exc.value.problems[0].startswith("line ")


def test_text_that_is_not_yaml_is_refused():
    with pytest.raises(S.SpecError) as exc:
        S.parse_spec("name: [unclosed\n")
    assert "not YAML a spec card can be read from" in exc.value.problems[0]


def test_a_card_that_is_not_a_mapping_is_refused():
    with pytest.raises(S.SpecError) as exc:
        S.parse_spec("- one\n- two\n")
    assert exc.value.problems == ["(the whole): a mapping, not a list"]


def test_a_folder_without_a_card_is_refused(tmp_path):
    with pytest.raises(S.SpecError) as exc:
        S.load_spec(tmp_path)
    assert "a job's folder holds its spec.yml" in exc.value.problems[0]


def test_a_card_that_is_a_link_is_refused(tmp_path):
    real = tmp_path / "real.yml"
    real.write_text(yaml.safe_dump(card()))
    (tmp_path / "spec.yml").symlink_to(real)
    with pytest.raises(S.SpecError) as exc:
        S.load_spec(tmp_path)
    assert exc.value.problems == ["is a symbolic link; a spec card is a regular file"]


def test_a_card_past_its_size_is_refused(tmp_path):
    (tmp_path / "spec.yml").write_text("#" * (S.MAX_BYTES + 1))
    with pytest.raises(S.SpecError) as exc:
        S.load_spec(tmp_path)
    assert exc.value.problems == [f"is {S.MAX_BYTES + 1} bytes, more than the {S.MAX_BYTES} a "
                                  "card may be"]
