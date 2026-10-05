"""The product's name, in ONE place (NSOT_STAGE7_PLAN section 19; approved 2026-10-05).

"Mercury Network Automation Platform", "Mercury" for short. Every user-facing place that names
the product reads these, so a later rename is one change. Internal names (modules, scripts,
services, settings) stay `nmas` until Stage 10 renames them with their host steps.
"""

PRODUCT_NAME = "Mercury Network Automation Platform"
PRODUCT_SHORT = "Mercury"
PRODUCT_TAGLINE = "Network Automation Platform"


#: The one line under the name on the About page (board B, approved 2026-10-05).
PRODUCT_LINE = ("Intent and golden configurations in git, previewed, confirmed, deployed, "
                "verified and recorded.")
#: Where the name comes from (section 19), said on the About page.
NAME_ORIGIN = "The name is a nod to the first place the author worked as a network engineer."

#: The mark's two colours, fixed in both themes (the CSS tokens `--brand` and `--brand-hi`).
TEAL = "#1D9E75"
HIGHLIGHT = "#9FE1CB"
WHITE = "#FFFFFF"


def context() -> dict:
    """What a template reads: ``brand.short``, ``brand.name``, ``brand.tagline``, ``brand.line``,
    ``brand.origin``."""
    return {"brand": {"name": PRODUCT_NAME, "short": PRODUCT_SHORT, "tagline": PRODUCT_TAGLINE,
                      "line": PRODUCT_LINE, "origin": NAME_ORIGIN}}


# ---------------------------------------------------------------------------
# The mark's files (`static/img/brand/`), every one drawn here from the master geometry
# (NSOT_STAGE7_PLAN 19, the board approved 2026-10-05), so a change is made once.
# `tests/test_v2_brand.py` holds each file to what this draws; `scripts/nmas-brand-icons`
# writes them. The sidebar draws the master inline (`mercury_mark` in templates/v2/_macros.html)
# so its gap can take the theme's colour.
# ---------------------------------------------------------------------------

_ORBIT_FRONT = "M-72,0 A72 26 0 0 0 72,0"


def mark_parts(ink: str, gap: str, size: str = "master", hi: str = HIGHLIGHT) -> str:
    """The mark's shapes, centred at 0,0, in *ink* with its gap in *gap*. *size* is "master"
    (everything), "32" (no highlight, two side nodes) or "16" (no gap either)."""
    out = [f'<g transform="rotate(-20)"><ellipse rx="72" ry="26" fill="none" stroke="{ink}" '
           'stroke-width="5"/></g>',
           f'<circle r="26" fill="{ink}"/>']
    if size == "master":
        out.append(f'<path d="M-15.6,-9 A18 18 0 0 1 -4.7,-17.4" fill="none" stroke="{hi}" '
                   'stroke-width="4" stroke-linecap="round"/>')
    if size == "16":
        out.append(f'<g transform="rotate(-20)"><circle cx="-72" r="9" fill="{ink}"/>'
                   f'<circle cx="72" r="9" fill="{ink}"/></g>')
        return "".join(out)
    nodes = [("cx", "-72"), ("cx", "72")] + ([("cy", "26")] if size == "master" else [])
    out.append('<g transform="rotate(-20)">'
               f'<path d="{_ORBIT_FRONT}" fill="none" stroke="{gap}" stroke-width="12"/>'
               f'<path d="{_ORBIT_FRONT}" fill="none" stroke="{ink}" stroke-width="5"/>'
               + "".join(f'<circle {k}="{v}" r="9" fill="{ink}" stroke="{gap}" stroke-width="3"/>'
                         for k, v in nodes)
               + "</g>")
    return "".join(out)


def mark_svg(size: str = "master", gap: str = "#14202B") -> str:
    """The mark alone, on a background of colour *gap* (the 32 px one is the phone top bar's)."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-82 -42 164 84" role="img" '
            f'aria-label="{PRODUCT_SHORT}"><title>{PRODUCT_SHORT}</title>'
            + mark_parts(TEAL, gap, size) + "</svg>\n")


def square_svg(size: str = "master", radius: bool = True) -> str:
    """The square icon: the mark in white on teal, its gap in teal, the corners rounded 23 %
    (*radius* False draws them square, for a platform that rounds them itself)."""
    rx = ' rx="37.7"' if radius else ""
    hi = TEAL
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 164 164" role="img" '
            f'aria-label="{PRODUCT_SHORT}"><title>{PRODUCT_SHORT}</title>'
            f'<rect width="164" height="164"{rx} fill="{TEAL}"/>'
            '<g transform="translate(82.0 82.0) scale(0.8)">'
            + mark_parts(WHITE, TEAL, size, hi=hi) + "</g></svg>\n")


#: The files under static/img/brand/, each with what draws it.
FILES = {
    "mercury-mark.svg": lambda: mark_svg("master"),
    "mercury-mark-32.svg": lambda: mark_svg("32"),
    "mercury-icon.svg": lambda: square_svg("master"),
    "mercury-icon-32.svg": lambda: square_svg("32"),
    "favicon.svg": lambda: square_svg("16"),
    "mercury-icon-square.svg": lambda: square_svg("master", radius=False),
}
