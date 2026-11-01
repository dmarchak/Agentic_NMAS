"""C2239's boot-log evidence (the overnight brief of 2026-11-01, item 1, and queue item d of the
operator's answer): Re-key's preview names what the device logged about its own keys and SSH
since its key was kept (`rekey_op.key_log_words`), beside the restart recorded since, so the
person deciding whether the new key is the device's own reads the device's own account of it.
Still a person's decision: nothing here keeps a key.

On test_evidence_pack_neighbours.py's world (`near`): Loki's capture answered as Loki answers a
range, lines planted for r3. The key lines are r8's boot of 2026-10-30 as the B2 run's notes
record them (`%CRYPTO_ENGINE-5-KEY_ADDITION`, `%SSH-5-ENABLED`), moved to r3 and into the
window, its domain the documentation placeholder.
"""
import pytest

from modules.nsot import rekey_op
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack_context import ctx  # noqa: F401
from tests.test_evidence_pack_neighbours import _line, _t, near  # noqa: F401

KEY = ("%CRYPTO_ENGINE-5-KEY_ADDITION: A key named r3.example.net has been generated or "
       "imported by crypto config")
SSH = "%SSH-5-ENABLED: SSH 2.0 has been enabled"
NOW = _t("08:25:00")
SINCE = "2026-10-15T08:00:00Z"


def _words(near, planted):
    near.loki.planted = {"r3": [(hms, _line("r3", hms, msg)) for hms, msg in planted]}
    return rekey_op.key_log_words("Lab", "r3", SINCE, now=NOW, client=near.loki)


def test_the_device_s_key_lines_are_named_newest_first(near):
    got = _words(near, [("08:11:02", KEY), ("08:11:51", SSH),
                        ("08:12:00", "%LINK-3-UPDOWN: Interface Vlan1, changed state to up")])
    assert got.startswith("2 key or SSH lines in its log since the key was kept, the newest "
                          "first: 2026-10-15 08:11:51 UTC "), got
    assert got.index("SSH-5-ENABLED") < got.index("KEY_ADDITION")
    assert "UPDOWN" not in got


def test_none_logged_is_said(near):
    got = _words(near, [])
    assert got.startswith("its log holds no key or SSH line between "), got
    assert got.endswith("no key generated or imported was logged")


def test_another_device_s_line_is_not_its_own(near):
    near.loki.planted = {"r4": [("08:11:02", _line("r4", "08:11:02", KEY))]}
    got = rekey_op.key_log_words("Lab", "r3", SINCE, now=NOW, client=near.loki)
    assert got.startswith("its log holds no key or SSH line"), got


def test_a_log_that_cannot_be_read_says_why(near):
    class Down:
        def is_configured(self):
            return True

        def __getattr__(self, name):
            raise ConnectionError("Loki refused the connection")
    got = rekey_op.key_log_words("Lab", "r3", SINCE, now=NOW, client=Down())
    assert got.startswith("its log could not be read: "), got


@pytest.mark.parametrize("since", ["", "2026-10-01T00:00:00Z"])
def test_it_reads_at_most_a_day_back(near, since):
    """A key kept long ago (or when, unrecorded) is read back a day, never further."""
    near.loki.planted = {"r3": [("08:11:02", _line("r3", "08:11:02", KEY))]}
    got = rekey_op.key_log_words("Lab", "r3", since, now=NOW, client=near.loki)
    assert got.startswith("1 key or SSH line in its log"), got
