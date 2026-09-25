"""An UPDATE is a write with no provenance, and this is what makes it answerable.

Provenance protects an OBJECT (the `nmas-managed` tag, the created-id record);
a cascade travels a RELATIONSHIP (`netbox_cascade`); and an **update travels
neither**. Measured on 2026-09-24: `_ensure_ip_address()` PATCHed
`assigned_object_id` and moved one address object between six devices for
weeks, and every defence there was reported nothing, because the object never
disappeared.

So this file pins four separate things, and the middle two are the ones that
make the mechanism worth having rather than merely present:

1. a PATCH records the **before** as well as the after — *"NMAS set it to 60"*
   is a fact, *"NMAS moved it from 44 to 60"* is the finding;
2. recording a modification **never** makes the object removable — the record
   is a second file for exactly that reason;
3. the census **states which claim it is making**, because `PASS` has always
   meant *"no object was created or destroyed"* and was read as *"nothing
   changed"*;
4. a zero is distinguishable from an unrecorded zero, so a recorder that is
   not running cannot read as an assurance that nothing happened.
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import stat
import sys
import ast

import pytest

from modules import netbox_guard


@pytest.fixture
def record(tmp_path, monkeypatch):
    """Point both provenance records at a temp dir."""
    monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE",
                        str(tmp_path / "netbox_modified.json"))
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                        str(tmp_path / "netbox_created_ids.json"))
    return tmp_path


def _census():
    loader = importlib.machinery.SourceFileLoader(
        "census_under_test", "scripts/nmas-netbox-census")
    spec = importlib.util.spec_from_loader("census_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. The before is the point


class TestTheBeforeIsRecorded:
    def test_a_change_records_before_and_after(self, record):
        fields = netbox_guard.changed_fields(
            {"assigned_object_id": 44}, {"assigned_object_id": 60})
        assert fields == {"assigned_object_id": {"before": 44, "after": 60}}

        netbox_guard.record_modified("default", "ipam/ip-addresses", 41, fields,
                                     name="10.0.0.15/24")
        got = netbox_guard.modified_since()
        assert got["count"] == 1
        entry = got["entries"][0]
        assert entry["fields"]["assigned_object_id"]["before"] == 44
        assert entry["fields"]["assigned_object_id"]["after"] == 60
        assert entry["endpoint"] == "ipam/ip-addresses"
        assert entry["id"] == 41

    def test_netboxs_nested_form_is_not_a_change(self):
        """A GET returns {"region": {"id": 5, ...}}; a PATCH sends 5.

        Without normalising, every field of every PATCH looks changed, the log
        records a modification on every no-op sync, and it stops meaning
        anything — the shape that makes a checker get switched off.
        """
        assert netbox_guard.changed_fields(
            {"region": {"id": 5, "name": "lab", "url": "http://x"}},
            {"region": 5}) == {}

    def test_nothing_changed_records_nothing(self, record):
        netbox_guard.record_modified("default", "dcim/sites", 7, {})
        assert netbox_guard.modified_since()["count"] == 0

    def test_an_unreadable_before_records_unknown_not_nothing(self, record):
        """`None` means the object could not be read. Recording nothing would
        make 'what changed is unknown' indistinguishable from 'nothing did'."""
        assert netbox_guard.changed_fields(None, {"region": 9}) is None
        netbox_guard.record_modified("default", "dcim/sites", 7, None)
        got = netbox_guard.modified_since()
        assert got["count"] == 1
        assert got["unknown_before"] == 1
        assert got["entries"][0]["before_unknown"] is True

    def test_a_field_netbox_did_not_return_is_unknown_not_null(self, record):
        """Absent from the response and genuinely null are different facts, and
        null is a real before-value."""
        fields = netbox_guard.changed_fields({}, {"comments": "x"})
        assert fields["comments"]["before"] == netbox_guard.UNKNOWN_BEFORE

        fields = netbox_guard.changed_fields({"comments": None}, {"comments": "x"})
        assert fields["comments"]["before"] is None

    def test_a_long_value_becomes_a_summary_not_its_contents(self):
        fields = netbox_guard.changed_fields({"comments": "a"}, {"comments": "b" * 900})
        after = fields["comments"]["after"]
        assert after["summarised"] is True
        assert after["bytes"] > 900 and len(after["sha256"]) == 12


class TestSizeIsMeasuredNotTyped:
    """The recorder's own first run found this, which is the point.

    Capping strings and not structures let `local_context_data` -- a dict
    holding a device's whole running config -- through untouched: 113,767
    bytes from ONE sync of ten devices. *Bulk is not evidence*, and a record
    that costs 113 KB a sync is one somebody turns off.
    """

    def test_a_large_dict_is_summarised(self):
        big = {"config": "hostname r2\n" * 900}
        got = netbox_guard.record_value(big)
        assert got["summarised"] is True and got["bytes"] > 10_000
        assert "hostname" not in json.dumps(got)

    def test_a_large_list_is_summarised(self):
        got = netbox_guard.record_value(["line"] * 400)
        assert got["summarised"] is True

    def test_one_sync_shaped_change_stays_small(self):
        """The regression in the units it was found in."""
        before = {"config": "hostname r2\n" * 900}
        after = {"config": "hostname r2\n" * 950}
        fields = netbox_guard.changed_fields({"local_context_data": before},
                                             {"local_context_data": after})
        assert len(json.dumps(fields)) < 400

    def test_the_hash_is_of_the_raw_value_so_a_rotation_is_visible(self):
        """Hashing the MASKED form would make a credential rotation
        hash-identical to no change at all -- the one movement most worth
        noticing, made invisible by the masking meant to protect it."""
        pad = "interface Gi1\n" * 40
        one = netbox_guard.record_value(
            {"c": pad + "username admin secret 9 $9$AAAAAAAAAAAAAA"})
        two = netbox_guard.record_value(
            {"c": pad + "username admin secret 9 $9$BBBBBBBBBBBBBB"})
        assert one["summarised"] and two["summarised"]
        assert one["sha256"] != two["sha256"]

    def test_a_summary_is_never_re_wrapped(self):
        once = netbox_guard.record_value({"config": "x" * 900})
        assert netbox_guard.record_value(once) == once


class TestNothingRecordedCarriesACredential:
    """The fix for a provenance gap created a new place a credential lived.

    `nmas-check-secret-storage` did not know about the file either -- which
    is verbatim its own warning, *a secret in a store this script does not
    know about is not reported at all*, arriving in a store created after the
    warning was written.
    """

    def test_a_credential_line_is_masked_before_it_is_written(self, record):
        fields = netbox_guard.changed_fields(
            {"description": "old"},
            {"description": "username admin privilege 15 password 0 sekrit99"})
        netbox_guard.record_modified("default", "dcim/devices", 3, fields)

        raw = open(netbox_guard._MODIFIED_FILE, encoding="utf-8").read()
        assert "sekrit99" not in raw
        assert "redacted" in raw

    def test_masking_is_positional_so_an_unknown_devices_secret_is_covered(self):
        """Value matching would need the store to have seen it. Positional
        masking covers a device NMAS was never told about."""
        got = netbox_guard.record_value("snmp-server community s3cr3tpub RW")
        assert "s3cr3tpub" not in got

    def test_redaction_failure_records_a_marker_not_the_value(self, monkeypatch):
        """FAILS CLOSED, opposite to the log filter.

        A log that loses entries is the worse failure in the file an operator
        reaches for when something has gone wrong. Nobody diagnoses an outage
        from this record, so a dropped value costs a detail and a leaked one
        costs a credential.
        """
        import modules.redact as redact_mod

        def boom(*a, **k):
            raise RuntimeError("credential store unreadable")

        monkeypatch.setattr(redact_mod, "redact_text", boom)
        got = netbox_guard.record_value("username admin password 0 hunter2")
        assert "hunter2" not in got
        assert "not recorded" in got

    def test_the_checker_scans_this_file(self):
        src = open("scripts/nmas-check-secret-storage", encoding="utf-8").read()
        assert "netbox_modified.json" in src
        assert "redact_positional" in src

    def test_the_checker_actually_finds_a_planted_secret(self, tmp_path):
        """The positive control. A scan that can only report 'clean' is
        indistinguishable from one that cannot run."""
        census = importlib.machinery.SourceFileLoader(
            "chk", "scripts/nmas-check-secret-storage")
        spec = importlib.util.spec_from_loader("chk", census)
        mod = importlib.util.module_from_spec(spec)
        census.exec_module(mod)

        clean = tmp_path / "clean.json"
        clean.write_text('{"default": {"dcim/sites": [{"id": 5}]}}')
        assert mod._holds_a_secret(str(clean)) == (False, "")

        dirty = tmp_path / "dirty.json"
        dirty.write_text('{"a": "username admin privilege 15 password 0 hunter2"}')
        found, _ = mod._holds_a_secret(str(dirty))
        assert found is True

        missing, why = mod._holds_a_secret(str(tmp_path / "nope.json"))
        assert missing is None and why


class TestSanitisingWhatIsAlreadyOnDisk:
    """Fixing the writer does nothing about what is already written, and
    *a tightened mode does not undo exposure* applies to a record too."""

    def _oversized(self, record):
        netbox_guard.record_modified(
            "default", "dcim/devices", 3,
            {"local_context_data": {
                "before": {"config": "hostname r2\n" * 900},
                "after": {"config": "hostname r2\n" * 950}}})

    def test_it_shrinks_the_record_and_keeps_the_finding(self, record):
        self._oversized(record)
        before_bytes = os.path.getsize(netbox_guard._MODIFIED_FILE)

        got = netbox_guard.sanitise_modified()
        assert got["ok"] and got["rewritten"] == 1
        assert os.path.getsize(netbox_guard._MODIFIED_FILE) < before_bytes / 10

        entry = netbox_guard.modified_since()["entries"][0]
        pair = entry["fields"]["local_context_data"]
        assert pair["before"]["summarised"] and pair["after"]["summarised"]
        assert pair["before"]["sha256"] != pair["after"]["sha256"]
        assert entry["endpoint"] == "dcim/devices" and entry["id"] == 3

    def test_a_planted_credential_is_gone_afterwards(self, record):
        netbox_guard.record_modified(
            "default", "dcim/devices", 3,
            {"description": {"before": "old",
                             "after": "username admin password 0 sekrit99"}})
        assert "sekrit99" in open(netbox_guard._MODIFIED_FILE, encoding="utf-8").read()

        netbox_guard.sanitise_modified()
        assert "sekrit99" not in open(netbox_guard._MODIFIED_FILE,
                                      encoding="utf-8").read()

    def test_it_tightens_the_mode_even_with_nothing_to_rewrite(self, record):
        """The checker names --sanitise as the remedy for a loose mode, so
        --sanitise has to BE one. Measured before the fix: 0664 in, 0664 out,
        reporting success -- a named remedy that runs and changes nothing,
        one step worse than advice that is merely incomplete."""
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        os.chmod(netbox_guard._MODIFIED_FILE, 0o664)

        got = netbox_guard.sanitise_modified()
        assert got["rewritten"] == 0
        assert got["mode"] == "0o600"
        assert stat.S_IMODE(
            os.stat(netbox_guard._MODIFIED_FILE).st_mode) == 0o600

    def test_it_is_idempotent(self, record):
        self._oversized(record)
        netbox_guard.sanitise_modified()
        second = netbox_guard.sanitise_modified()
        assert second["rewritten"] == 0

    def test_an_unreadable_record_is_unproven_not_clean(self, record):
        with open(netbox_guard._MODIFIED_FILE, "w", encoding="utf-8") as fh:
            fh.write("{ truncated")
        got = netbox_guard.sanitise_modified()
        assert got["ok"] is False and got["reason"]

    def test_the_script_runs_and_never_prints_a_value(self, record):
        import subprocess
        netbox_guard.record_modified(
            "default", "dcim/devices", 3,
            {"description": {"before": "a", "after": "b"}})
        out = subprocess.run(
            [sys.executable, "scripts/nmas-netbox-modified", "--sanitise"],
            capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr


class TestTheRecordIsOwnerOnly:
    def test_it_is_created_0600(self, record):
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        mode = stat.S_IMODE(os.stat(netbox_guard._MODIFIED_FILE).st_mode)
        assert mode == 0o600, oct(mode)

    def test_a_loose_mode_self_heals_on_the_next_write(self, record):
        """os.replace swaps in the temp file's inode, so the 0600 it was
        created with becomes the record's mode — a file written before this
        existed does not stay group-readable for ever."""
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        os.chmod(netbox_guard._MODIFIED_FILE, 0o664)
        netbox_guard.record_modified(
            "default", "dcim/sites", 8, {"region": {"before": 1, "after": 3}})
        assert stat.S_IMODE(os.stat(netbox_guard._MODIFIED_FILE).st_mode) == 0o600


# ---------------------------------------------------------------------------
# 2. An update must never confer ownership


class TestAnUpdateConfersNoOwnership:
    def test_a_modified_object_is_not_removable(self, record):
        """THE reason this is a separate file.

        Removal requires `tagged AND recorded`. Putting an update in the
        created-id record would mark a human's object as NMAS's own and make
        it deletable — the ownership claim an update must not make.
        """
        netbox_guard.record_modified(
            "default", "dcim/sites", 7,
            {"region": {"before": 1, "after": 2}}, name="curated-site")

        assert netbox_guard.was_created_by_nmas("default", "dcim/sites", 7) is False
        assert netbox_guard.get_created("default") == {}

    def test_the_two_records_are_different_files(self):
        assert netbox_guard._MODIFIED_FILE != netbox_guard._CREATED_IDS_FILE

    def test_forgetting_created_does_not_erase_the_modification_history(self, record):
        """Deleting a list drops its created-id record. What NMAS *did* to
        objects it does not own outlives that, or the trail is erasable by
        the routine action that follows every probe."""
        netbox_guard.record_created("default", "dcim/sites", 7, "s")
        netbox_guard.record_modified("default", "dcim/sites", 9,
                                     {"region": {"before": 1, "after": 2}})
        netbox_guard.forget_created("default")

        assert netbox_guard.get_created("default") == {}
        assert netbox_guard.modified_since()["count"] == 1


# ---------------------------------------------------------------------------
# 3. Four states, and a zero that cannot pose as an assurance


class TestAZeroCannotPoseAsAnAssurance:
    def test_no_record_at_all_is_not_none(self, record):
        got = netbox_guard.modified_since()
        assert got["count"] == 0 and got["exists"] is False

        status, lines = _census()._modification_report()
        assert status == "no-record"
        assert "NO RECORD EXISTS" in lines[0]
        assert "not as 'none'" in " ".join(lines)

    def test_a_real_zero_says_so_with_its_denominator(self, record):
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        status, lines = _census()._modification_report(since="2999-01-01T00:00:00Z")
        assert status == "none"
        # The total is what proves the recorder runs and found nothing here.
        assert "out of 1 recorded in total" in lines[0]

    def test_unreadable_is_weaker_than_none(self, record):
        with open(netbox_guard._MODIFIED_FILE, "w", encoding="utf-8") as fh:
            fh.write("{ truncated")
        got = netbox_guard.modified_since()
        assert got["ok"] is False and got["scope"] == "unknown"

        status, lines = _census()._modification_report()
        assert status == "unknown"
        assert "weaker than 'none'" in " ".join(lines)

    def test_an_unscoped_count_says_it_could_not_be_scoped(self, record):
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        status, lines = _census()._modification_report(since="")
        assert status == "some"
        assert "could not be scoped" in lines[0]

    def test_the_four_statuses_are_distinct(self):
        c = _census()
        assert len({c.MODS_NONE, c.MODS_SOME,
                    c.MODS_UNKNOWN, c.MODS_NO_RECORD}) == 4


# ---------------------------------------------------------------------------
# 4. The census states which claim it makes


class TestTheCensusStatesItsClaim:
    def test_the_census_cannot_see_a_moved_address(self):
        """The measurement this whole file exists for, pinned so the docs stay
        true. Identity is `id:display`, and moving an address between
        interfaces changes neither."""
        c = _census()
        before = {"id": 41, "display": "10.0.0.15/24", "assigned_object_id": 100}
        after = {**before, "assigned_object_id": 200}
        assert c._identity(before) == c._identity(after)

        b = {"types": {"ip-addresses": {"total": 1, "objects": [c._identity(before)],
                                        "tagged_objects": []}}}
        a = {"types": {"ip-addresses": {"total": 1, "objects": [c._identity(after)],
                                       "tagged_objects": []}}}
        assert c.compare(b, a) == []

    def test_pass_says_what_it_does_and_does_not_claim(self):
        src = open("scripts/nmas-netbox-census", encoding="utf-8").read()
        assert "no object was created or destroyed" in src
        assert "does NOT say nothing changed" in src.replace("\n", " ") or \
               "It does NOT say nothing changed" in src

    def test_the_headline_is_chosen_from_a_status_not_from_its_own_prose(self):
        """Matching the printed sentence to decide the headline is the
        'pattern that can appear in English' error, and it also read UNKNOWN
        as a modification. The mapping must be keyed on the constants."""
        src = open("scripts/nmas-netbox-census", encoding="utf-8").read()
        head = src.split("head = {")[1].split("}[mod_status]")[0]
        for const in ("MODS_SOME", "MODS_UNKNOWN", "MODS_NO_RECORD", "MODS_NONE"):
            assert const in head
        assert "startswith" not in head

    def test_unknown_is_never_reported_as_modifications_existing(self):
        src = open("scripts/nmas-netbox-census", encoding="utf-8").read()
        head = src.split("head = {")[1].split("}[mod_status]")[0]
        for line in head.splitlines():
            if "MODS_UNKNOWN" in line or "MODS_NO_RECORD" in line:
                assert "UNKNOWN" in line


# ---------------------------------------------------------------------------
# 5. Still exactly three write paths


class TestTheWriteSurfaceIsStillThree:
    def test_every_http_write_is_inside_a_chokepoint(self):
        """A fourth write path would be outside the gate AND outside this
        record. Floor on the count, so a regex matching nothing cannot pass.
        """
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        verbs = re.findall(r"session\.(post|patch|put|delete)\(", src)
        assert len(verbs) >= 3, f"found {verbs} — the scan matched too little"
        assert sorted(verbs) == ["delete", "patch", "post"], verbs

        tree = ast.parse(src)
        enclosing = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr in ("post", "patch", "put", "delete")
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "session"):
                    enclosing.append(node.name)
        assert sorted(enclosing) == ["_nb_delete", "_nb_patch", "_nb_post"], enclosing

    def test_patch_reads_the_before_state_itself(self):
        """Not from an argument. An optional `before=` is how a caller bypasses
        this by omission, and there are eleven call sites."""
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        body = src.split("def _nb_patch(")[1].split("\ndef ")[0]
        assert "_nb_get_by_id(" in body
        assert "record_modified(" in body

        sig = body.split(")")[0]
        assert "before" not in sig, "the before-state must not be a parameter"

    def test_the_chokepoint_records_the_move_end_to_end(self, record,
                                                        monkeypatch):
        """THE INCIDENT, driven through the real chokepoint.

        `_ensure_ip_address()` PATCHing `assigned_object_id` is what moved one
        address between six devices. Everything above tests a piece; this is
        the piece assembled — a PATCH goes in, and the record afterwards says
        *moved from 44 to 60*, which is the sentence nobody could read for
        weeks.
        """
        from modules import netbox_client

        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)

        class Sess:
            def get(self, url, params=None, timeout=None):
                return _Resp({"id": 41, "display": "10.0.0.15/24",
                              "assigned_object_id": 44})

            def patch(self, url, json=None, timeout=None):
                return _Resp({"id": 41, "display": "10.0.0.15/24",
                              **(json or {})})

        with netbox_guard.for_list("default", actor="dustin@example.com"):
            netbox_client._nb_patch(Sess(), "http://nb",
                                    "ipam/ip-addresses/41/",
                                    {"assigned_object_id": 60})

        got = netbox_guard.modified_since()
        assert got["count"] == 1
        e = got["entries"][0]
        assert e["endpoint"] == "ipam/ip-addresses" and e["id"] == 41
        assert e["fields"]["assigned_object_id"] == {"before": 44, "after": 60}
        assert e["actor"] == "dustin@example.com"
        assert e["name"] == "10.0.0.15/24"

    def test_an_unattributed_write_says_so_rather_than_blank(self, record,
                                                             monkeypatch):
        """An empty actor reads as 'nobody'; the truth is 'this write carried
        no identity'."""
        netbox_guard.record_modified("default", "dcim/sites", 7,
                                     {"region": {"before": 1, "after": 2}})
        assert netbox_guard.modified_since()["entries"][0]["actor"] == "unattributed"

    def test_a_dry_run_records_nothing(self, record):
        """A preview must leave no trail — it changed nothing.

        Driven through the real chokepoint with a session whose verbs all
        raise: a dry run must reach neither the network nor the record.
        """
        from modules import netbox_client
        from modules.netbox_guard import dry_run

        class Exploding:
            def _boom(self, *a, **k):
                raise AssertionError("a dry run reached the network")
            get = patch = post = delete = _boom

        with dry_run():
            out = netbox_client._nb_patch(Exploding(), "http://nb",
                                          "dcim/sites/5/", {"region": 9})

        assert out["_dry_run"] is True
        assert netbox_guard.modified_since()["count"] == 0
        assert not os.path.exists(netbox_guard._MODIFIED_FILE)


# ---------------------------------------------------------------------------
# 6. _ensure_site stops editing objects it does not own


class _Resp:
    def __init__(self, payload, ok=True):
        self._p, self.ok, self.status_code = payload, ok, 200 if ok else 500

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise AssertionError("unexpected HTTP failure in the stub")


class _SiteSession:
    """Answers the get-or-create, and records any PATCH it is asked for."""

    def __init__(self, site):
        self.site = site
        self.patched = []

    def get(self, url, params=None, timeout=None):
        if "/dcim/sites/" in url and (params or {}).get("slug"):
            return _Resp({"results": [self.site], "count": 1})
        return _Resp({"results": [self.site], "count": 1})

    def patch(self, url, json=None, timeout=None):
        self.patched.append((url, json))
        return _Resp({**self.site, **(json or {})})


@pytest.fixture
def writes_on(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)


class TestEnsureSiteDoesNotEditWhatItDoesNotOwn:
    def _run(self, site, monkeypatch, record):
        from modules import netbox_client

        sess = _SiteSession(site)
        monkeypatch.setattr(netbox_client, "_nb_get_by_id",
                            lambda *a, **k: dict(site))
        notes = []
        with netbox_guard.for_list("default"):
            netbox_client._ensure_site(sess, "http://nb", "default", 99,
                                       notes=notes)
        return sess, notes

    def test_a_foreign_site_is_left_alone_and_reported(self, monkeypatch,
                                                       record, writes_on):
        """Removal REFUSES to touch an object NMAS did not create, so moving
        one silently is the same tool being inconsistent about ownership in
        the direction that matters."""
        site = {"id": 5, "name": "default", "slug": "default",
                "region": {"id": 1}, "tags": []}
        sess, notes = self._run(site, monkeypatch, record)

        assert sess.patched == [], "a human's site was re-parented"
        assert notes and "did not create it" in notes[0]
        assert "Move it in NetBox" in notes[0]

    def test_its_own_site_is_still_re_parented(self, monkeypatch, record,
                                              writes_on):
        """The positive anchor: a refusal that refused everything would pass
        the test above and quietly break the importer's own invariant."""
        site = {"id": 5, "name": "default", "slug": "default",
                "region": {"id": 1},
                "tags": [{"slug": netbox_guard.MANAGED_TAG_SLUG}]}
        sess, notes = self._run(site, monkeypatch, record)

        assert len(sess.patched) == 1
        assert sess.patched[0][1] == {"region": 99}
        assert notes == []

    def test_the_created_record_also_establishes_ownership(self, monkeypatch,
                                                          record, writes_on):
        """A site NMAS created whose tag was removed by hand is still its own
        if the record says so — tagged OR recorded, deliberately not the
        conjunction removal uses, because the blast radii differ."""
        netbox_guard.record_created("default", "dcim/sites", 5, "default")
        site = {"id": 5, "name": "default", "slug": "default",
                "region": {"id": 1}, "tags": []}
        sess, notes = self._run(site, monkeypatch, record)
        assert len(sess.patched) == 1

    def test_a_site_already_in_the_right_region_is_never_patched(
            self, monkeypatch, record, writes_on):
        site = {"id": 5, "name": "default", "slug": "default",
                "region": {"id": 99}, "tags": []}
        sess, notes = self._run(site, monkeypatch, record)
        assert sess.patched == [] and notes == []

    def test_the_sync_surfaces_the_notes(self):
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        assert '"notes":      provisioning_notes,' in src
        assert "notes=provisioning_notes" in src


# ---------------------------------------------------------------------------
# 7. Neither record is written by truncating in place


class TestNeitherRecordIsTruncatedInPlace:
    def test_both_go_through_the_atomic_writer(self):
        src = open("modules/netbox_guard.py", encoding="utf-8").read()
        assert "os.replace(tmp, path)" in src
        # No open-for-write on either record outside the atomic writer.
        body = src.split("def _write_json_atomic(")[1].split("\ndef ")[0]
        others = [ln for ln in src.splitlines()
                  if '"w"' in ln and ln.strip() not in body]
        assert others == [], others

    def test_a_write_leaves_no_temp_file_behind(self, record):
        netbox_guard.record_modified(
            "default", "dcim/sites", 7, {"region": {"before": 1, "after": 2}})
        assert os.path.exists(netbox_guard._MODIFIED_FILE)
        assert not os.path.exists(netbox_guard._MODIFIED_FILE + ".tmp")
        with open(netbox_guard._MODIFIED_FILE, encoding="utf-8") as fh:
            json.load(fh)


# ---------------------------------------------------------------------------
# 8. A ping result is observed state and must not reach the source of truth


class TestStatusIsNotWrittenByTheSync:
    """The rule already existed and this escaped it.

    `_scan_device` was deleted because *importing observed state into the
    source of truth is the wrong direction*. A ping result is observed state.
    A 140-line SSH scanner went under that rule while three words on a call
    site doing the same thing survived — because a rule gets applied to things
    that have names.
    """

    def test_status_is_not_in_the_update_allowlist(self):
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        body = src.split("update = {k: v for k, v in payload.items()")[1]
        allowlist = body.split("}")[0]
        assert '"status"' not in allowlist, allowlist
        # Floor: the allowlist is still a real allowlist, not emptied.
        for kept in ("name", "serial", "comments", "local_context_data"):
            assert f'"{kept}"' in allowlist

    def test_the_sync_no_longer_derives_status_from_the_ping_cache(self):
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.strip().startswith("#"))
        assert '"active" if (status_cache' not in code
        assert "else \"offline\"" not in code

    def test_the_ping_cache_still_gates_live_sessions(self):
        """The positive anchor. `status_cache` has a legitimate use — not
        opening an SSH session to a device that is down — and removing that
        too would be the fix overshooting into a different defect."""
        src = open("modules/netbox_client.py", encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.strip().startswith("#"))
        assert "(status_cache or {}).get(r[\"ip\"], False)" in code

    def test_a_created_device_is_still_active(self):
        """Create keeps it: onboarding reached the device before the record
        existed, so `active` is a lifecycle claim that has been earned."""
        import inspect
        from modules import netbox_client

        sig = inspect.signature(netbox_client._upsert_device)
        assert sig.parameters["status"].default == "active"

    def test_the_source_filter_no_longer_defaults_to_active(self):
        """The other half of the self-sealing loop. With status frozen at
        whatever it was at creation, filtering on it selects for an accident
        of onboarding."""
        from modules.inventory.source_config import DEFAULT_CONFIG

        assert DEFAULT_CONFIG["filters"]["status"] == ""
        # Floor: the other filters still exist, so this did not pass by the
        # filters dict having been emptied.
        assert set(DEFAULT_CONFIG["filters"]) == {"site", "role", "tag", "status"}

    def test_the_docstring_example_does_not_read_as_the_default(self):
        """A docstring example that contradicts DEFAULT_CONFIG is the
        manifest.py slug example again — confident prose beside correct code.
        """
        src = open("modules/inventory/source_config.py", encoding="utf-8").read()
        doc = src.split('"""')[1]
        assert '"status": "active"' not in doc
