"""Secrets compared by keyed hash: whether the values in two texts' masked positions are the
same, with no value and no hash leaving this module (C1792's design, the operator's,
2026-10-26; built first for C1693's Normalise proof, 2026-10-27; C924's baseline comparison
reuses it).

**What is compared is exactly what is masked.** Each line's values are the ones
`redact.redact_text` replaces in it, found by redaction's own patterns in redaction's own
order: a value in a secret's syntactic position (`redact._POSITIONAL`, a placeholder already
there left alone), then a value this installation holds, wherever it stands. A test holds the
two together: each line with its found values put back as placeholders is `redact_text`'s
output, byte for byte. So a masked line compared here is a line the masking hides, and a value
the masking does not hide is not one this claims to have compared.

**Pairing.** A masked line of one text is paired with the line of the other whose masked text
is the same (the first such line not yet paired, in order), so two texts that differ outside
their secrets still pair the lines they share. A masked line with no partner is listed apart
(``unpaired``): its masked text already differs, which a caller shows from the masked texts
themselves, and the keyed hash cannot say whether its value moved.

**The key.** HMAC-SHA256 under 32 bytes drawn from the operating system's random source once
per process (`secrets.token_bytes`) and held only in this process's memory: never written,
logged, shown or returned, and never stored beside a hash (no hash is stored or returned at
all; a caller gets counts and the lines that differ, named by line number and masked text).
The precedent is `records_db._TAG_KEY`, a random key per process for a password's hash.
Neither of the other two ways fits: a key derived from `data/key.key` would read the Fernet key
for a new purpose, and a key file is one more owner-only secret to create, back up and keep
current; both outlive the process, which buys nothing when no hash outlives the comparison
that made it. And a hash that escaped by mistake (a log line) means nothing outside the process
that made it: a 6-character SNMP community cannot be found from it by hashing guesses without
the key.

Nothing here reads a store but `redact.known_secret_values()` (when the caller gives no
*values*), and nothing is written.
"""

import hashlib
import hmac
import secrets

from modules import redact

#: The process's key: random, in memory only (see the module's docstring).
_KEY = secrets.token_bytes(32)


def _digest(value: str) -> bytes:
    """*value*'s keyed hash. Kept inside this module: never returned, logged or stored."""
    return hmac.new(_KEY, value.encode("utf-8"), hashlib.sha256).digest()


def masked_values(line: str, pattern=None, table=None) -> tuple:
    """``(masked, values)``: *line* as `redact.redact_text` masks it, and every value that
    masking replaced, in the order it replaced them. *pattern* and *table* are
    `redact._compile`'s for the known values (None: positional only)."""
    found = []

    def positional(label):
        def _replace(match):
            token = match.group(2)
            if redact._ALREADY.match(token):
                return match.group(0)
            found.append(token)
            return match.group(1) + redact.PLACEHOLDER.format(label=label) + match.group(3)
        return _replace

    text = line
    for label, compiled in redact._POSITIONAL:
        text = compiled.sub(positional(label), text)
    if pattern is not None:
        def by_value(match):
            # The pattern is built from the table's own keys, so every match is one of them.
            found.append(match.group(1))
            return redact.PLACEHOLDER.format(label=table[match.group(1)])
        text = pattern.sub(by_value, text)
    return text, found


def _masked_lines(text: str, pattern, table) -> list:
    """``[(masked, digests, line number)]`` for each line of *text* holding a masked value."""
    out = []
    for number, line in enumerate((text or "").splitlines(), 1):
        masked, values = masked_values(line, pattern, table)
        if values:
            out.append((masked, [_digest(v) for v in values], number))
    return out


def _same(a: list, b: list) -> bool:
    """Two lines' digests, every one equal, compared in constant time."""
    return len(a) == len(b) and all(hmac.compare_digest(x, y) for x, y in zip(a, b))


def compare(before: str, after: str, values: dict = None) -> dict:
    """Whether each masked line of *after* holds the same values as its partner in *before*.

    ``{"compared", "identical", "paired": [{"line", "masked"}], "differs": [{"line",
    "masked"}], "unpaired": [{"side", "line", "masked"}]}``: *compared* is the number of
    paired masked lines (each in *paired*, by its line in *after* and its masked text),
    *identical* those whose values are equal by keyed hash; each that differs is named by its
    line in *after* and its masked text, never its value; *unpaired* names a masked line with
    no partner by its side (``before`` or ``after``), line and masked text. *values* is the
    known-value table (`redact.known_secret_values()` when None), so both texts are masked by
    one table."""
    values = redact.known_secret_values() if values is None else values
    pattern, table = redact._compile(values)
    waiting = {}
    for masked, digests, number in _masked_lines(before, pattern, table):
        waiting.setdefault(masked, []).append((digests, number))
    compared, identical, paired, differs, unpaired = 0, 0, [], [], []
    for masked, digests, number in _masked_lines(after, pattern, table):
        queue = waiting.get(masked)
        if not queue:
            unpaired.append({"side": "after", "line": number, "masked": masked})
            continue
        theirs, _their_line = queue.pop(0)
        compared += 1
        paired.append({"line": number, "masked": masked})
        if _same(theirs, digests):
            identical += 1
        else:
            differs.append({"line": number, "masked": masked})
    for masked, queue in waiting.items():
        unpaired.extend({"side": "before", "line": number, "masked": masked}
                        for _digests, number in queue)
    unpaired.sort(key=lambda u: (u["side"], u["line"]))
    return {"compared": compared, "identical": identical, "paired": paired,
            "differs": differs, "unpaired": unpaired}
