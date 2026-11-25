"""A short form of a text for a screen, marked when it is cut (C3041; CLAUDE.md: "keep the whole
record, then summarise"; "a view showing a subset says so"): the record keeps the whole text,
and the screen draws this. Four modules keep a private copy of the same shape (C4256)."""


def cut(text, most: int) -> str:
    """*text* with its runs of white space made one, at most *most* characters: whole when it
    fits, else its first ``most - 1`` and "…", so a cut is never silent."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"
