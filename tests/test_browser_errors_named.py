"""A WebDriver command's error is named, never only "HTTP Error 500" (C2127).

geckodriver answers every failed command (a script's TypeError, a stale element, a script
timeout) as an HTTP error whose JSON body names it; `tests/browser.Browser._call` used to let
urllib's bare "HTTP Error 500: Internal Server Error" through, so a flaky browser test's failure
in CI could not be told from the app's own 500 and was read as one. Here a script that throws in
a real Firefox must fail with WebDriver's error kind and the script's message in the exception,
still an `urllib.error.HTTPError` whose body reads (tests/test_credentials_v2.py reads it).
"""
import json
import urllib.error

import pytest

from tests import browser


def test_a_script_error_is_named_with_webdrivers_error_and_message():
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    with browser.Browser() as b:
        try:
            b.go("about:blank")
            with pytest.raises(urllib.error.HTTPError) as caught:
                b.js("return document.querySelector('#no-such-row').querySelector('.pack');")
            said = str(caught.value)
            assert "WebDriver javascript error" in said, said
            assert "null" in said or "TypeError" in said, said
            assert "/execute/sync" in said, said
            body = json.loads(caught.value.read())
            assert body["value"]["error"] == "javascript error"
        finally:
            b.go("about:blank")
