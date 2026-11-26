"""Words a page says, shared: one home for joining names into a sentence (Stage 5's sentences,
2026-11-25: Settings, Needs attention, the device page and Devices each said "a, b and c" with
a helper of its own).
"""


def series(names, most: int = None) -> str:
    """"a", "a and b", "a, b and c". With *most*, past it the first *most* and "and N more",
    never "and 1 more": one more is named. An empty list is ""."""
    names = [str(n) for n in names]
    if not names:
        return ""
    if most is not None and len(names) > most + 1:
        return ", ".join(names[:most]) + f" and {len(names) - most} more"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
