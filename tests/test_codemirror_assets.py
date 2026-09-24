"""Vendored front-end assets referenced by the template editor.

A misplaced CodeMirror mode file is not an error in CodeMirror: the editor
initialises with an unknown mode and renders plain text, which is
indistinguishable from the library being absent. That happened once during
development — the mode was referenced at the vendor root while it actually
lived under `mode/jinja2/`. These tests make the path a build-time fact rather
than something you notice by squinting at an editor.
"""

import os
import re

import pytest

from tests.js_source import read_shipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTIAL = os.path.join(ROOT, "templates", "partials", "template_editor.html")
VENDOR = os.path.join(ROOT, "static", "js", "vendor", "codemirror")


@pytest.fixture(scope="module")
def partial():
    return read_shipped(PARTIAL)


def _asset_paths(partial_text):
    """Static filenames referenced by url_for in the partial."""
    return re.findall(r"url_for\('static',\s*filename='([^']+)'\)", partial_text)


class TestAssetsExist:
    def test_every_referenced_asset_exists(self, partial):
        missing = []
        for rel in _asset_paths(partial):
            if not os.path.exists(os.path.join(ROOT, "static", rel)):
                missing.append(rel)
        assert missing == [], f"referenced but not present: {missing}"

    @pytest.mark.parametrize("name", [
        "codemirror.js", "codemirror.css", "mode/jinja2/jinja2.js"])
    def test_expected_files_are_vendored(self, name):
        path = os.path.join(VENDOR, name)
        assert os.path.exists(path), f"{name} is not vendored"
        assert os.path.getsize(path) > 1000, f"{name} looks like a stub"


class TestLoadOrder:
    def test_mode_loads_after_the_library(self, partial):
        """defineMode is called by the mode file; the library must exist first."""
        scripts = re.findall(r"<script src=\"\{\{ url_for\('static',\s*"
                             r"filename='([^']+)'\)", partial)
        cm = [i for i, s in enumerate(scripts) if s.endswith("codemirror.js")]
        mode = [i for i, s in enumerate(scripts) if "jinja2" in s]
        assert cm and mode, f"expected both scripts, found {scripts}"
        assert min(mode) > max(cm), "the jinja2 mode loads before CodeMirror"

    def test_no_cdn_references(self, partial):
        """Air-gapped requirement: nothing may be fetched from the internet."""
        assert "https://" not in re.sub(r"\{#.*?#\}", "", partial, flags=re.S) or \
            not re.search(r'src="https://|href="https://', partial), \
            "the partial references a remote asset"


class TestModeIsRegistered:
    def test_mode_file_defines_jinja2(self):
        with open(os.path.join(VENDOR, "mode", "jinja2", "jinja2.js"),
                  encoding="utf-8") as fh:
            source = fh.read()
        assert 'defineMode("jinja2"' in source

    def test_partial_checks_the_mode_explicitly(self, partial):
        """Because a missing mode fails silently, the UI must detect it."""
        assert "CodeMirror.modes.jinja2" in partial

    def test_library_is_the_expected_major_version(self):
        # The version assignment sits near the end of the bundle, so read it
        # all rather than guessing at a prefix length.
        with open(os.path.join(VENDOR, "codemirror.js"), encoding="utf-8") as fh:
            source = fh.read()
        match = re.search(r'CodeMirror\.version = "(\d+)\.', source)
        assert match and match.group(1) == "5", \
            "the jinja2 mode here targets CodeMirror 5"
