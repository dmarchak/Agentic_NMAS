"""C4090 (the operator, 2026-11-23: "a read-only, masked reader for heal and fix-it records"):
`nmas-config-read --records <kind> --list <network>` prints each of the network's heal and
fix-it records' lines masked, found through the product's own paths, and names a record it
could not read; it writes nothing.

Kept apart from tests/test_claude_config_reads.py, which holds the config-read hook's own
guards (a guard path: scripts/nmas-guard-check); these test the reader's records mode alone.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER = os.path.join(ROOT, "scripts", "nmas-config-read")

#: A community line and its value: the value must never be printed.
COMMUNITY = ("snmp-server community Commntp9x RO", "Commntp9x")


class TestTheRecordsReadMasks:

    @pytest.fixture
    def data(self, tmp_path):
        from cryptography.fernet import Fernet
        # An installation's key, as every real store holds one (the masking reads the stored
        # secrets, and on a store with none it makes the key: C4218).
        (tmp_path / "key.key").write_bytes(Fernet.generate_key())
        net = tmp_path / "lists" / "lab"
        (net / "heal").mkdir(parents=True)
        (net / "fixit").mkdir()
        line = COMMUNITY[0]
        (net / "heal" / "incidents.json").write_text(
            json.dumps({"incidents": [{"id": "hi-1", "words": line}]}, indent=1), "utf-8")
        (net / "heal" / "decisions.jsonl").write_text(
            json.dumps({"id": "hd-1", "program": [line]}) + "\n", "utf-8")
        (net / "heal_steps.jsonl").write_text(json.dumps({"row": "act", "lines": [line]}) + "\n",
                                              "utf-8")
        (net / "fixit" / "hi-1.json").write_text(json.dumps({"lines": [line]}, indent=1), "utf-8")
        (net / "fixit" / "hi-2.json").write_text(json.dumps({"lines": ["ntp server 192.0.2.1"]}),
                                                 "utf-8")
        return tmp_path

    def _read(self, data, *args):
        with open(READER, encoding="utf-8") as fh:
            return subprocess.run([sys.executable, "-", "--checkout", ROOT, "--list", "Lab",
                                   *args], stdin=fh, capture_output=True, text=True,
                                  env=dict(os.environ, NMAS_DATA_DIR=str(data)))

    @pytest.mark.parametrize("kind,name", [("heal-incidents", "incidents.json"),
                                           ("heal-decisions", "decisions.jsonl"),
                                           ("heal-steps", "heal_steps.jsonl"),
                                           ("fixit", "hi-1.json")])
    def test_each_kind_reads_its_record_masked(self, data, kind, name):
        before = sorted(str(p) for p in data.rglob("*"))
        r = self._read(data, "--records", kind)
        assert r.returncode == 0, r.stderr
        assert COMMUNITY[1] not in r.stdout, r.stdout
        assert f"{name}: " in r.stdout and "<redacted:snmp_community>" in r.stdout, r.stdout
        assert sorted(str(p) for p in data.rglob("*")) == before, "it writes nothing"

    def test_one_incident_and_a_search(self, data):
        r = self._read(data, "--records", "fixit", "--incident", "hi-2", "--grep", "ntp")
        assert r.returncode == 0 and r.stdout.strip() == \
            'hi-2.json: {"lines": ["ntp server 192.0.2.1"]}', r.stdout

    def test_a_record_it_could_not_read_is_named(self, data):
        r = self._read(data, "--records", "fixit", "--incident", "hi-9")
        assert r.returncode == 1 and "could not read hi-9.json" in r.stderr, r.stderr
