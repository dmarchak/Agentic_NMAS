"""Settings › a network › Network, the Code repository card (board docs/boards/code-repository.html;
the operator's decision 8 of 2026-11-08; routes/settings_v2.py `code_repo_*`).

Cases, each drawn from the real routes on a network made here, its code repository a git
repository made here:
- the Network tab draws the card: none set (the notice, Fetch now disabled with its reason);
- Save as a verified person sets it, answers Saved in place and declares ``code_repo``; a
  location carrying a user part is refused naming why, what was typed kept;
- Fetch now registers each app folder and the card says what (the commit, Registered), and
  every page hears ``code_repo``; a failed fetch answers 502 saying why;
- SDN › Apps' registry notice links to this card."""

import pytest

from modules import coderepo as R
from tests.test_coderepo import code, commit_app, git, lab  # noqa: F401 - the fixtures

NET = "Default"
URL = f"/v2/settings/network/{NET}"


@pytest.fixture
def client(lab, monkeypatch):  # noqa: F811 - the fixture, used
    import app as A

    heard = []
    monkeypatch.setattr("modules.invalidation.announce",
                        lambda keys, by, ok=True: heard.append((tuple(keys), by)))
    c = A.app.test_client()
    c.heard = heard
    return c


def test_the_network_tab_draws_the_card_with_nothing_set_and_fetch_does_nothing(client, lab):  # noqa: F811
    html = client.get(f"{URL}?tab=network").get_data(as_text=True)
    assert 'id="code-repo-card"' in html and ">none set<" in html
    assert f"{NET} has no code repository: SDN › Apps lists no app version" in html
    fetch = html.split('class="set-foot code-repo-fetch"')[1].split("</form>")[0]
    assert "disabled" in fetch and "Set a location and save it first" in fetch
    # Pressed anyway (a stale page): refused naming why, and nothing is fetched or recorded.
    r = client.post(f"{URL}/code-repository/fetch")
    assert r.status_code == 409 and "has no code repository set" in r.get_data(as_text=True)
    assert not (lab / R.RECORD).exists() and not (lab / R.COPY).exists()


def test_save_sets_it_in_place_declares_code_repo_and_the_card_redraws_on_it(client, code):  # noqa: F811
    r = client.post(f"{URL}/code-repository",
                    data={"location": str(code), "branch": "main", "loaded": "\n"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Saved" in html and f"{code}, branch main" in html
    assert "code_repo" in r.headers.get("X-NMAS-Invalidates", "")
    assert R.location(NET)["location"] == str(code)
    card = client.get(f"{URL}/code-repository").get_data(as_text=True)
    assert 'hx-trigger="nmas:code_repo from:body"' in card and f'value="{code}"' in card


def test_a_location_with_a_user_part_is_refused_keeping_what_was_typed(client):
    typed = "https://someone@code.example.invalid/x.git"
    r = client.post(f"{URL}/code-repository", data={"location": typed, "loaded": "\n"})
    html = r.get_data(as_text=True)
    assert r.status_code == 409 and "carries a user part" in html
    assert f'value="{typed}"' in html and R.location(NET)["state"] == "none"


def test_fetch_now_registers_and_says_what(client, code):  # noqa: F811
    R.set_location(NET, str(code), "", actor="op@example.invalid",
                   actor_verified="access-assertion")
    head = git(code, "rev-parse", "HEAD")
    r = client.post(f"{URL}/code-repository/fetch")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and f"Fetched commit <span class=\"mono\">{head[:7]}" in html
    assert "of_versions 1.0.0 registered" in html
    assert "1 version of 1 app, each a Draft until it is published" in html
    assert "code_repo" in r.headers.get("X-NMAS-Invalidates", "")
    assert client.heard == [(R.ANNOUNCE_KEYS, R.ANNOUNCER)]


def test_a_failed_fetch_answers_502_saying_why(client, tmp_path):
    R.set_location(NET, str(tmp_path / "missing.git"), "", actor="op@example.invalid",
                   actor_verified="access-assertion")
    r = client.post(f"{URL}/code-repository/fetch")
    html = r.get_data(as_text=True)
    assert r.status_code == 502 and "The fetch failed" in html and "git fetch of" in html
    last = R.card(NET)["last"]
    assert last["ok"] is False and "git fetch of" in last["error"]
