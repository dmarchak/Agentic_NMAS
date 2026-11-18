"""Masking keeps its compiled secret pattern by the exact table it was built from (16dc1ee8, the
overnight speed pass, 2026-11-17, C3914: an incident page called `redact_text` 1,120 times and
rebuilt the same alternation each time). The irreversible tier: what is held is that the cache
never masks with a stale table. The debt pass, 2026-11-18 (docs/FAST_LANE_DEBT.md's row for
16dc1ee8; the change's own hand check is docs/TIER_HAND_CHECK.md's of 2026-11-17).

Through the public mask (`redact.redact_text` with its table given, as `redact_payload` hands
it), on values in no positional slot, so only the value-based pass can mask them:
- **A rotated secret:** the same label with a new value of the same length (a cache keyed by
  size would hand back the old pattern) masks the new value and no longer the old.
- **Added and removed:** a value added is masked at once; removed, it is no longer masked.
- **The same table:** compiled once, its pattern handed back.
- **The bound:** at most `_COMPILED_KEPT` patterns kept, each later table still masked right.
"""
from modules import redact

OLD = "Alpha-Kestrel-4417"
NEW = "Bravo-Osprey-90210"          # the same length as OLD: a rotation keyed by size is caught
OTHER = "Charlie-Heron-55"


def masked(text: str, values: dict) -> str:
    return redact.redact_text(text, values)


def test_a_rotated_secret_is_masked_and_the_old_value_no_longer_matched():
    assert len(OLD) == len(NEW)
    before = {OLD: "the tacacs key"}
    after = {NEW: "the tacacs key"}
    assert OLD not in masked(f"sent {OLD} then", before)
    got = masked(f"sent {OLD} and {NEW}", after)
    assert NEW not in got and OLD in got, got
    assert redact.PLACEHOLDER.format(label="the tacacs key") in got


def test_a_value_added_is_masked_at_once_and_removed_is_not():
    one = {OLD: "the tacacs key"}
    two = {OLD: "the tacacs key", OTHER: "the snmp community"}
    assert OTHER in masked(f"{OLD} {OTHER}", one)
    got = masked(f"{OLD} {OTHER}", two)
    assert OLD not in got and OTHER not in got, got
    back = masked(f"{OLD} {OTHER}", one)
    assert OLD not in back and OTHER in back, back


def test_the_same_table_is_compiled_once():
    table = {OLD: "the tacacs key", OTHER: "the snmp community"}
    first, _ = redact._compile(dict(table))
    again, given = redact._compile(dict(table))
    assert again is first and given == table


def test_at_most_its_bound_is_kept_and_each_later_table_still_masks():
    redact._COMPILED.clear()
    for n in range(redact._COMPILED_KEPT * 2 + 1):
        value = f"Delta-Plover-{n:04d}"
        assert value not in masked(f"x {value} y", {value: "a key"}), n
        assert len(redact._COMPILED) <= redact._COMPILED_KEPT
