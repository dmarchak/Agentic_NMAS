"""Settings › Installation as C's document (Stage 5 step 2; the operator's GUI pick of 2026-11-25:
C): on Connections, one sentence from each connection's stored health, the same the cards
under it draw (`installation_settings.sentence`).

- The lead is the connection to act on (one that does not answer, or refuses its credential);
  the rest says every other connection's state. With nothing to act on, the states are the
  lead. A tab whose cards carry no connection has no sentence.
- On the page: Connections draws the sentence of the cards it draws; Access and identity draws
  none.
"""
import re
from html import unescape

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


def _card(title, state):
    return {"spec": {"title": title}, "health": {"state": state}}


def test_the_connection_to_act_on_leads_and_the_rest_follow():
    from modules import installation_settings as I
    got = I.sentence([_card("NetBox connection", "down"), _card("Proxmox", "not_configured")])
    assert got == {"lead": "NetBox connection does not answer.",
                   "rest": "Proxmox is not set up."}
    got = I.sentence([_card("NetBox connection", "refused"), _card("Proxmox", "down")])
    assert got == {"lead": "Proxmox does not answer and NetBox connection refuses its "
                           "credential.", "rest": ""}


def test_with_nothing_to_act_on_the_states_lead():
    from modules import installation_settings as I
    got = I.sentence([_card("NetBox connection", "up"), _card("Proxmox", "unread")])
    assert got == {"lead": "NetBox connection answers and Proxmox has not been read yet.",
                   "rest": ""}
    assert I.sentence([{"spec": {"title": "Server"}, "health": None}]) == {}


def test_connections_draws_the_sentence_of_its_own_cards_and_access_none(networks):  # noqa: F811
    import app as A
    from modules import installation_settings as I
    client = networks["client"]
    html = client.get("/v2/settings/installation?tab=connections").get_data(as_text=True)
    with A.app.test_request_context("/"):
        cards = [I.card(n) for n, s in I.CARDS.items()
                 if s["tab"] == "connections" and not s.get("template")]
    want = I.sentence(cards)
    assert want, "the fixture's connections have a state"
    m = re.search(r'<p class="doc-summary"><strong>(.*?)</strong>(?: (.*?))?</p>', html, re.S)
    assert m, "the sentence is drawn"
    assert (unescape(m.group(1)), unescape(m.group(2) or "")) == (want["lead"], want["rest"])
    assert html.index('class="doc-summary"') < html.index('aria-label="The installation\'s '
                                                          'settings"'), "above the tabs"
    other = client.get("/v2/settings/installation?tab=access").get_data(as_text=True)
    assert 'class="doc-summary"' not in other
