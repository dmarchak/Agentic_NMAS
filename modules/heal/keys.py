"""A failure's key, shared by the heal loop and R1's one reader (`fixit.auto.pending`): its one
home, out of the fix-it path, so the heal loop's retry names no module of `modules.fixit`
(docs/HEAL_TO_INTENT.md section 12; the operator's ruling of 2026-11-23)."""


def key_of(kind: str, ident: str) -> str:
    """A failure's key: ``decision:<incident>``, ``held:<incident>``, ``act:<decision>``,
    ``tail:<decision>``, ``retry:<retry>`` or ``run:<run id>`` (the shape a background
    trigger's finding id takes: no underscore, no space)."""
    return f"{kind}:{ident}"
