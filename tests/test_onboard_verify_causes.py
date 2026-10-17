"""C1151: a pending device's Verify… refusal draws each likely cause in words.

`modules/nsot/onboard.verify_device` returns its causes as `{cause, why, where, command}` (most
worth checking first, each with what settles it), and `routes/onboard.verify_preview_of` passes
them on as they are. v2's pending card drew `c.text` when a cause had one and the cause ITSELF
otherwise, so a real refusal printed each cause as a Python mapping ("{'cause': 'the
management interface', 'why': …}"). The test that held the card mocked causes as `{"text": …}`,
a shape the core never returns. Today's wizard drew them in words (its
`onboardVerifyRefusalHtml`) until it left at 7.8 (2026-10-17, P7-25).
"""

import html as html_mod
import re


def _refused(monkeypatch, causes):
    import app as nmas
    from routes import onboard

    monkeypatch.setattr(onboard, "verify_preview_of", lambda name, data, req: (
        {"ok": False, "error": "r7 did not answer at 192.0.2.7", "causes": causes}, 409))
    r = nmas.app.test_client().post("/v2/onboard/r7/verify/preview",
                                    data={"list_name": "probe"})
    assert r.status_code == 409, r.status_code
    return r.get_data(as_text=True)


class TestTheVerifyRefusalDrawsItsCauses:
    REAL = [{"cause": "the management interface is shut", "why": "nothing answers on 22",
             "where": "the device's console", "command": "show ip interface brief"},
            {"cause": "the <credential> was rotated", "why": "", "where": "", "command": ""}]

    def test_a_real_cause_is_drawn_in_words_with_what_settles_it(self, monkeypatch):
        page = _refused(monkeypatch, self.REAL)
        text = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", "", page)).split())
        assert "{'cause'" not in text and "'why':" not in text, text[-1200:]
        assert ("the management interface is shut: nothing answers on 22. Settled by "
                "show ip interface brief (the device's console)") in text, text[-1200:]
        assert "Not verified: r7 did not answer at 192.0.2.7" in text

    def test_a_cause_with_nothing_more_is_its_words_alone_and_escaped(self, monkeypatch):
        page = _refused(monkeypatch, self.REAL)
        assert "<li>the &lt;credential&gt; was rotated</li>" in page, page[-1200:]

    def test_a_cause_given_as_text_is_still_drawn(self, monkeypatch):
        """The control: the shape the card already drew keeps drawing."""
        page = _refused(monkeypatch, [{"text": "it has not booted"}])
        assert "<li>it has not booted</li>" in page
