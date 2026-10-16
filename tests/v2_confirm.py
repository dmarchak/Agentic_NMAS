"""The batch confirm as a v2 page sends it (C850, the one confirm pattern).

The batch Apply, Coverage's Deploy missing and History's Re-apply draw their confirm as an
htmx button whose `hx-vals` carry the body the preview built from the hashes it shows, each
structured field (the order, the hashes, the removals and reasons) as JSON in its own form
field. These read that body from the page, post it exactly as the button does, and read the
job the answer draws, so a test confirms what the page offers and nothing typed from memory.
"""

import html
import json
import re

#: The confirm body's structured fields, sent as JSON in a form field each
#: (routes.v2.CONFIRM_JSON_FIELDS).
STRUCTURED = ("order", "confirmations", "command_hashes", "remove", "authorise")


def button(page_html: str, button_id: str = "apply-confirm"):
    """The confirm button's start tag, or None when the page draws none."""
    m = re.search(r'<button\b[^>]*\bid="%s"[^>]*>' % re.escape(button_id), page_html, re.S)
    return m.group(0) if m else None


def confirm_body(page_html: str, button_id: str = "apply-confirm"):
    """The body the page's confirm posts: its `hx-vals`, each structured field decoded. None
    when the page draws no confirm."""
    tag = button(page_html, button_id)
    if tag is None:
        return None
    m = re.search(r"hx-vals='([^']*)'", tag)
    assert m, f"the confirm carries its body: {tag}"
    vals = json.loads(html.unescape(m.group(1)))
    return {k: (json.loads(v) if k in STRUCTURED and isinstance(v, str) else v)
            for k, v in vals.items()}


def post_confirm(client, url: str, body: dict):
    """Post *body* as the button does: each structured field as JSON, the rest as text, as an
    htmx request."""
    data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in body.items()}
    return client.post(url, data=data, headers={"HX-Request": "true"})


def job_of(response) -> str:
    """The job the confirm's answer draws (the card's `data-job`), or "" when none."""
    m = re.search(r'id="apply-job" data-job="([^"]*)"', response.get_data(as_text=True))
    return m.group(1) if m else ""


def job_url(job: str) -> str:
    return f"/v2/monitoring/apply/job/{job}"
