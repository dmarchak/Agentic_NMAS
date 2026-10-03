"""A device page's card names its ONE device: never the fleet's words (C408; the operator,
2026-10-04: restore said "1 of 1 device(s) you selected", Plan a deploy on r2 "Deploy to the
devices you tick… 1 of 1 can be deployed now, and for each…").

`fleet_words(html)` names every fleet phrase in a device card (the `id="device-op"` section),
by the class's shape, never a list of sentences: a count of devices, the plural `device(s)`,
"for each", "devices you tick". The suite's guard (`tests/conftest.py`) runs it on every card
`routes/device_v2.py` answers in any test, so the population is every card the suite draws.
"""

import html as html_mod
import re

FLEET = re.compile(r"devices you (?:tick|selected|chose)|\b\d+ of \d+ device\(s\)|"
                   r"\bfor each\b|\bdevice\(s\)", re.I)


def card_text(page: str) -> str:
    """The text of the device card in *page*, or "" when it holds none."""
    at = page.find('id="device-op"')
    if at < 0:
        return ""
    end = page.find("</section>", at)
    body = page[at:end if end > 0 else len(page)]
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", body))


def fleet_words(page: str) -> list:
    text = card_text(page)
    return [(m.group(0), " ".join(text[max(0, m.start() - 60):m.end() + 60].split()))
            for m in FLEET.finditer(text)]
