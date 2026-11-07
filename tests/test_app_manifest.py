"""The controller-app manifest (the SDN platform design r4, section 12, I-2; phase P1):
`modules/apps/manifest.py` loads `manifest.yml` and refuses each malformed field by name, and the
contract fixture (`tests/fixtures/apps/dns-blacklist/`) is the dns_blacklist app's manifest,
whose config schema declares the verdict service, the cache and the overrides (section 14).
Every refusal is planted; the verdict service's URL is checked with an IPv4 address, a bracketed
IPv6 address and a name."""

import copy
import os

import pytest
import yaml

from modules.apps import manifest as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "apps", "dns-blacklist")


def fixture_data() -> dict:
    with open(os.path.join(FIXTURE, M.MANIFEST), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def example_config() -> dict:
    with open(os.path.join(FIXTURE, "config.example.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def refused(data) -> str:
    with pytest.raises(M.ManifestError) as got:
        M.parse_manifest(yaml.safe_dump(data), "manifest.yml")
    return str(got.value)


# ── the contract fixture ─────────────────────────────────────────────────────────────────────

def test_the_dns_blacklist_manifest_is_valid():
    m = M.load_manifest(FIXTURE)
    assert (m.name, m.version, m.controllers, m.openflow_versions) == (
        "dns_blacklist", "0.1.0", {"ryu": ">=4.34"}, ("1.3",))
    assert {e.path for e in m.rest.endpoints} == {"/health", "/validate", "/policy"}
    assert m.owns_flows.classes == ("dns",)


def test_it_declares_its_one_network_destination_the_verdict_service():
    """C2635: the app reaches the network only through mercury_app.egress, to a destination
    its manifest declares; dns_blacklist's is its verdict service, whose address is the
    network's config at verdict_service.url."""
    m = M.load_manifest(FIXTURE)
    assert m.egress_names() == ("verdict_service",)
    assert (m.egress[0].from_config, m.egress[0].purpose) == (
        "verdict_service.url", "Asks the verdict service for each queried domain's verdict.")
    assert M.config_key_problem(m.config_schema, "verdict_service.url") == ""


def test_an_app_that_declares_no_destination_is_valid():
    data = fixture_data()
    del data["egress"]
    assert M.parse_manifest(yaml.safe_dump(data)).egress == ()


def test_its_config_schema_declares_the_verdict_service_the_cache_and_the_overrides():
    schema = M.load_manifest(FIXTURE).config_schema
    assert set(schema["required"]) == {"verdict_service", "cache", "overrides"}
    assert set(schema["properties"]["cache"]["required"]) == {"max_entries", "ttl_seconds"}
    assert set(schema["properties"]["overrides"]["properties"]) == {"allow", "block"}


def test_the_example_config_passes_its_schema():
    assert M.validate_config(M.load_manifest(FIXTURE), example_config()) == []


def test_a_verdict_service_that_does_not_answer_fails_open_unless_the_network_says_block():
    """The operator, 2026-11-06: `on_unavailable` defaults to allow, because DNS is a protected
    class with a must_reach invariant, and failing closed would break DNS for every host while
    the verdict service is down; block stays selectable per network."""
    manifest = M.load_manifest(FIXTURE)
    config = example_config()
    del config["verdict_service"]["on_unavailable"]
    assert M.validate_config(manifest, config) == [], "it may be left out"
    got = M.effective_config(manifest, config)
    assert got["verdict_service"]["on_unavailable"] == "allow"
    assert "on_unavailable" not in config["verdict_service"], "the caller's config is not changed"
    config["verdict_service"]["on_unavailable"] = "block"
    assert M.validate_config(manifest, config) == []
    assert M.effective_config(manifest, config)["verdict_service"]["on_unavailable"] == "block"


def test_defaults_fill_only_what_is_absent_at_each_declared_level():
    manifest = M.parse_manifest(yaml.safe_dump({
        **fixture_data(),
        "egress": [],                       # this schema declares no verdict service
        "config_schema": {"type": "object", "properties": {
            "a": {"type": "integer", "default": 1},
            "b": {"type": "object", "properties": {"c": {"type": "string", "default": "x"}}},
            "d": {"type": "string"}}}}))
    assert M.effective_config(manifest, {}) == {"a": 1}
    assert M.effective_config(manifest, {"a": 5, "b": {}}) == {"a": 5, "b": {"c": "x"}}
    assert M.effective_config(manifest, {"b": {"c": "y"}, "d": "z"}) == {
        "a": 1, "b": {"c": "y"}, "d": "z"}


@pytest.mark.parametrize("url", ["http://192.0.2.53:8053/verdict",
                                 "http://[2001:db8::53]:8053/verdict",
                                 "https://verdict.example.invalid/v1"],
                         ids=["ipv4", "ipv6", "name"])
def test_the_verdict_service_is_reached_by_either_address_family_or_a_name(url):
    config = example_config()
    config["verdict_service"]["url"] = url
    assert M.validate_config(M.load_manifest(FIXTURE), config) == []


@pytest.mark.parametrize("url", ["http://2001:db8::53:8053/verdict", "ftp://192.0.2.53/",
                                 "http://192.0.2.53:8053/verdict?q=1", "192.0.2.53"],
                         ids=["ipv6-unbracketed", "scheme", "query", "no-scheme"])
def test_a_verdict_service_url_not_of_that_shape_is_refused(url):
    config = example_config()
    config["verdict_service"]["url"] = url
    got = M.validate_config(M.load_manifest(FIXTURE), config)
    assert len(got) == 1 and got[0].startswith("verdict_service/url: ")


@pytest.mark.parametrize("path,value,where", [
    (("cache", "max_entries"), 0, "cache/max_entries"),
    (("cache", "ttl_seconds"), "300", "cache/ttl_seconds"),
    (("verdict_service", "timeout_seconds"), 0, "verdict_service/timeout_seconds"),
    (("verdict_service", "on_unavailable"), "retry", "verdict_service/on_unavailable"),
    (("overrides", "block"), ["Not A Domain"], "overrides/block/0"),
    (("overrides", "colour"), "red", "overrides"),
], ids=["cache-size", "cache-time", "timeout", "unavailable", "domain", "unknown"])
def test_a_config_outside_the_schema_is_refused_naming_where(path, value, where):
    config = example_config()
    config[path[0]][path[1]] = value
    got = M.validate_config(M.load_manifest(FIXTURE), config)
    assert got and got[0].startswith(f"{where}: ")


# ── each field refused by name ───────────────────────────────────────────────────────────────

def edited(change):
    data = fixture_data()
    change(data)
    return data


PLANTED = [
    ("name-hyphen", lambda d: d.update(name="dns-blacklist"), "name: 'dns-blacklist' refused"),
    ("name-long", lambda d: d.update(name="a" * 42), "does not match ^[a-z][a-z0-9_]{0,40}$"),
    ("version", lambda d: d.update(version="0.1"), "version: '0.1' refused"),
    ("summary", lambda d: d.update(summary="x" * 201), "summary is at most 200"),
    ("controllers-empty", lambda d: d.update(controllers={}), "at least one controller"),
    ("controller-kind", lambda d: d.update(controllers={"Ryu": ">=4.34"}),
     "a controller kind 'Ryu' does not match"),
    ("requirement", lambda d: d.update(controllers={"ryu": "4.34+"}),
     "ryu's requirement '4.34+' is not clauses"),
    ("of-number", lambda d: d.update(openflow_versions=[1.3]),
     "1.3 is a float: write each OpenFlow version quoted"),
    ("of-unknown", lambda d: d.update(openflow_versions=["2.0"]), "'2.0' is not one of 1.0"),
    ("of-twice", lambda d: d.update(openflow_versions=["1.3", "1.3"]), "'1.3' more than once"),
    ("of-empty", lambda d: d.update(openflow_versions=[]), "openflow_versions is a non-empty"),
    ("requires-name", lambda d: d.update(requires=["switch-quirks"]),
     "a required app's name 'switch-quirks' does not match"),
    ("requires-self", lambda d: d.update(requires=["dns_blacklist"]),
     "dns_blacklist requires itself"),
    ("schema-invalid", lambda d: d["config_schema"].update(type=5),
     "config_schema: {"),
    ("schema-invalid-said", lambda d: d["config_schema"].update(type=5),
     "not a JSON Schema at type: "),
    ("schema-not-object", lambda d: d.update(config_schema={"type": "array"}),
     "top-level type is 'object', not 'array'"),
    ("prefix", lambda d: d["rest"].update(prefix="dns_blacklist"),
     "rest.prefix: 'dns_blacklist' refused"),
    ("no-health", lambda d: d["rest"].update(endpoints=d["rest"]["endpoints"][1:]),
     "an app declares /health answering GET (Mercury's post-check reads it); /health here: "
     "absent"),
    ("health-post", lambda d: d["rest"]["endpoints"][0].update(methods=["POST"]),
     "/health here: ['POST']"),
    ("validate-get", lambda d: d["rest"]["endpoints"][1].update(methods=["GET"]),
     "/validate, when offered, answers POST, not ['GET']"),
    ("endpoint-twice", lambda d: d["rest"]["endpoints"].append(
        copy.deepcopy(d["rest"]["endpoints"][2])), "lists '/policy' more than once"),
    ("method", lambda d: d["rest"]["endpoints"][2].update(methods=["FETCH"]),
     "rest.endpoints.2.methods.0: 'FETCH' refused"),
    ("endpoint-path", lambda d: d["rest"]["endpoints"][2].update(path="policy"),
     "an endpoint's path 'policy' does not match"),
    ("cookie-outside-mask", lambda d: d["owns_flows"].update(cookie_prefix="0xd5000000000000ff"),
     "cookie_prefix 0xd5000000000000ff has bits outside cookie_mask 0xff00000000000000"),
    ("mask-zero", lambda d: d["owns_flows"].update(cookie_mask="0x0"),
     "cookie_mask 0x0 selects no bit"),
    ("cookie-hex", lambda d: d["owns_flows"].update(cookie_prefix="d5"),
     "a cookie 'd5' does not match"),
    ("class", lambda d: d["owns_flows"].update(classes=["DNS traffic"]),
     "a protected class 'DNS traffic' does not match"),
    ("egress-unknown-key", lambda d: d["egress"][0].update(from_config="verdict_service.host"),
     "egress 'verdict_service': from_config 'verdict_service.host' is not a key config_schema "
     "declares: verdict_service declares on_unavailable, timeout_seconds, url, not 'host'"),
    ("egress-unknown-top", lambda d: d["egress"][0].update(from_config="resolver.url"),
     "'resolver.url' is not a key config_schema declares: the config declares cache, "
     "overrides, verdict_service, not 'resolver'"),
    ("egress-not-a-string", lambda d: d["egress"][0].update(
        from_config="verdict_service.timeout_seconds"),
     "'verdict_service.timeout_seconds' carries an address, a string, and config_schema "
     "types it 'number'"),
    ("egress-object", lambda d: d["egress"][0].update(from_config="verdict_service"),
     "'verdict_service' carries an address, a string, and config_schema types it 'object'"),
    ("egress-key-shape", lambda d: d["egress"][0].update(from_config="verdict_service..url"),
     "a dotted config key 'verdict_service..url' does not match"),
    ("egress-twice", lambda d: d["egress"].append(copy.deepcopy(d["egress"][0])),
     "egress names lists 'verdict_service' more than once"),
    ("egress-name", lambda d: d["egress"][0].update(name="Verdict-Service"),
     "an egress destination's name 'Verdict-Service' does not match"),
    ("egress-purpose", lambda d: d["egress"][0].update(purpose=" "),
     "a purpose is one sentence, 1 to 200 characters"),
    ("egress-missing-key", lambda d: d["egress"][0].pop("from_config"),
     "egress.0.from_config: missing (a required field)"),
    ("test-parent", lambda d: d.update(tests=["../outside.py"]),
     "relative and without '..', not '../outside.py'"),
    ("test-absolute", lambda d: d.update(tests=["/tmp/x.py"]), "not '/tmp/x.py'"),
    ("unknown-field", lambda d: d.update(entrypoint="app.py"),
     "entrypoint: not a field of this contract (given 'app.py')"),
]


@pytest.mark.parametrize("change,said", [(c, s) for _i, c, s in PLANTED],
                         ids=[i for i, _c, _s in PLANTED])
def test_a_malformed_field_is_refused_by_name(change, said):
    text = refused(edited(change))
    assert text.startswith("manifest.yml refused: ") and said in text, text


@pytest.mark.parametrize("field", ["name", "version", "controllers", "openflow_versions",
                                   "config_schema", "rest"])
def test_a_required_field_missing_is_named(field):
    assert f"{field}: missing (a required field)" in refused(edited(lambda d: d.pop(field)))


def test_every_problem_is_named_not_only_the_first():
    text = refused(edited(lambda d: d.update(name="Bad", version="1", controllers={})))
    assert "name: 'Bad'" in text and "version: '1'" in text and "controllers: {}" in text


# ── the file ─────────────────────────────────────────────────────────────────────────────────

def test_a_key_given_twice_is_refused_naming_it_and_its_line():
    text = "name: dns_blacklist\nversion: 0.1.0\nname: other\n"
    with pytest.raises(M.ManifestError) as got:
        M.parse_manifest(text)
    assert "line 3" in str(got.value) and "the key 'name' is given twice" in str(got.value)


@pytest.mark.parametrize("text,said", [("- a\n- b\n", "(the whole): a mapping, not a list"),
                                       ("name: [unclosed\n", "not YAML a manifest can be read")],
                         ids=["list", "syntax"])
def test_a_file_that_is_not_one_mapping_is_refused(text, said):
    with pytest.raises(M.ManifestError, match=r"manifest\.yml refused: ") as got:
        M.parse_manifest(text)
    assert said in str(got.value)


def test_a_manifest_that_is_a_link_is_refused(tmp_path):
    with open(os.path.join(FIXTURE, M.MANIFEST), encoding="utf-8") as fh:
        (tmp_path / "real.yml").write_text(fh.read())
    (tmp_path / M.MANIFEST).symlink_to(tmp_path / "real.yml")
    with pytest.raises(M.ManifestError, match="is a symbolic link"):
        M.load_manifest(tmp_path)


def test_a_folder_without_a_manifest_is_refused(tmp_path):
    with pytest.raises(M.ManifestError, match="is not a file"):
        M.load_manifest(tmp_path)


def test_a_manifest_past_its_size_bound_is_refused_unread(tmp_path):
    (tmp_path / M.MANIFEST).write_text("#" * (M.MAX_BYTES + 1))
    with pytest.raises(M.ManifestError, match=f"is {M.MAX_BYTES + 1} bytes, more than"):
        M.load_manifest(tmp_path)
