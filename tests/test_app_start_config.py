"""The app SDK's start-time config call, `mercury_app.start_config` (C2729; decision K9;
modules/apps/sdk/mercury_app/__init__.py): what an app reads at load from the file Mercury's
deploy staged beside its version.

Cases, each planted in a folder standing for /opt/ryu-apps:
- the SDK's path, suffix and size bound are the apply script's own (`config_path`,
  `CONFIG_SUFFIX`, `MAX_BYTES`), so the app reads the file the script checked;
- a staged object is read with its path and sha256;
- absent, unreadable, too large, not JSON, not an object: each `ok` false with its own words,
  never an exception;
- a name or version not of the script's shape opens nothing, even where a file sits at the
  path it would make;
- `start_config` is published and the app allowlist accepts it (an app may call it).
"""

import hashlib
import os
import sys

import pytest

from modules.apps import allowlist, channel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK_DIR = os.path.join(ROOT, "modules", "apps", "sdk")


@pytest.fixture()
def sdk(tmp_path, monkeypatch):
    """The SDK as an app imports it (its folder on the path), its APPS_ROOT this test's."""
    monkeypatch.syspath_prepend(SDK_DIR)
    sys.modules.pop("mercury_app", None)
    import mercury_app

    # raising=False: on a release without the call the test's own body fails, not its setup.
    monkeypatch.setattr(mercury_app, "APPS_ROOT", str(tmp_path), raising=False)
    yield mercury_app
    sys.modules.pop("mercury_app", None)


def stage(root, name, version, data: bytes):
    folder = root / name
    folder.mkdir(exist_ok=True)
    path = folder / f"{version}.config.json"
    path.write_bytes(data)
    return path


def test_the_sdk_reads_where_the_apply_script_checks(sdk):
    s = channel.script()
    assert (sdk.CONFIG_SUFFIX, sdk.MAX_BYTES) == (s.CONFIG_SUFFIX, s.MAX_BYTES)
    assert s.APPS_ROOT == "/opt/ryu-apps"
    assert sdk.config_path("switch_quirks", "1.0.0") == s.config_path(
        sdk.APPS_ROOT, "switch_quirks", "1.0.0")
    assert (sdk.NAME.pattern, sdk.VERSION.pattern) == (s.NAME.pattern, s.VERSION.pattern)


def test_the_sdks_default_root_is_the_apply_scripts():
    sys.modules.pop("mercury_app", None)
    sys.path.insert(0, SDK_DIR)
    try:
        import mercury_app

        assert mercury_app.APPS_ROOT == channel.script().APPS_ROOT
    finally:
        sys.path.remove(SDK_DIR)
        sys.modules.pop("mercury_app", None)


def test_a_staged_config_is_read_with_its_path_and_hash(sdk, tmp_path):
    text = channel.config_bytes({"switches": {"3": {"forward_table": 0, "punt_table": 0}}})
    path = stage(tmp_path, "fabric_forwarding", "0.2.0", text)
    got = sdk.start_config("fabric_forwarding", "0.2.0")
    assert got == {"ok": True, "error": "", "path": str(path),
                   "sha256": hashlib.sha256(text).hexdigest(),
                   "config": {"switches": {"3": {"forward_table": 0, "punt_table": 0}}}}


def test_an_absent_file_is_named_never_raised(sdk, tmp_path):
    got = sdk.start_config("switch_quirks", "1.0.0")
    path = str(tmp_path / "switch_quirks" / "1.0.0.config.json")
    assert got == {"ok": False, "config": None, "path": path, "sha256": "",
                   "error": f"no start-time config at {path}: the deploy staged none for "
                            "switch_quirks 1.0.0"}


def test_an_unreadable_file_says_why(sdk, tmp_path):
    # The suite runs as an unprivileged user (scripts/nmas-test, CI's runner), whom mode 0
    # refuses.
    path = stage(tmp_path, "switch_quirks", "1.0.0", b"{}\n")
    path.chmod(0)
    try:
        got = sdk.start_config("switch_quirks", "1.0.0")
    finally:
        path.chmod(0o600)
    assert got["ok"] is False and got["config"] is None
    assert got["error"] == f"the start-time config {path} cannot be read (Permission denied)"


@pytest.mark.parametrize("data, words", [
    (b"{" + b" " * (64 * 1024) + b"}", "is more than 65536 bytes, the apply script's bound"),
    (b"{not json", "is not JSON in UTF-8"),
    (b"\xff\xfe", "is not JSON in UTF-8"),
    (b"[1, 2]\n", "is a JSON list, not an object"),
])
def test_a_file_that_is_not_a_bounded_json_object_is_named(sdk, tmp_path, data, words):
    path = stage(tmp_path, "switch_quirks", "1.0.0", data)
    got = sdk.start_config("switch_quirks", "1.0.0")
    assert got["ok"] is False and got["config"] is None and got["path"] == str(path)
    assert got["error"].startswith(f"the start-time config {path} {words}"), got["error"]


@pytest.mark.parametrize("name, version", [
    ("../switch_quirks", "1.0.0"), ("switch_quirks", "../1.0.0"), ("Switch", "1.0.0"),
    ("switch_quirks\n", "1.0.0"), ("switch_quirks", "1.0.0\n"), (None, "1.0.0"),
    ("switch_quirks", 1),
])
def test_a_name_or_version_not_of_the_scripts_shape_opens_nothing(sdk, tmp_path, name,
                                                                  version):
    # A file where "switch_quirks/../1.0.0" would land, so a read of it would answer ok.
    (tmp_path / "1.0.0.config.json").write_bytes(b"{}\n")
    (tmp_path / "switch_quirks").mkdir()
    got = sdk.start_config(name, version)
    assert got["ok"] is False and got["config"] is None and got["path"] == ""
    assert "is not of the shape the apply script stages" in got["error"]
    assert "so no file was opened" in got["error"]


def test_start_config_is_published_and_an_app_may_call_it():
    assert "start_config" in allowlist.SDK_NAMES
    assert allowlist.name_problem("mercury_app", "start_config") == ""
    assert allowlist.name_problem("mercury_app", "read_file").startswith(
        "`mercury_app.read_file` is not among mercury_app's published names")
