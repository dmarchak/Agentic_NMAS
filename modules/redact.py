"""modules/redact.py

Redaction at the **provider boundary**: the last thing that happens before a
payload leaves this process for a model API.

Why here, and not at the golden-config reader. The agent has a whole tool set,
and the readers are not the only source of secrets:

* ``show running-config`` over SSH returns the same SNMP communities and the
  same ``username … password`` lines as the stored golden;
* backups, drift diffs, `show tech`, and any free-form command a user asks the
  agent to run all carry them too;
* a future tool inherits the problem the day it is written.

Redacting at each reader is N places that must each remember. Redacting where
the request is built is one place that cannot be bypassed by adding a tool —
the same reasoning that put the deploy guards in ``prepare_for_deploy()``
rather than in each caller.

**This is not at-rest masking.** Golden configs stay verbatim on disk and in
git: masking them would make ``golden/`` depend on ``data/key.key``, which is
not in the repository, so a private remote would hold configs nobody could
restore a network from. See ``docs/NSOT_MULTINETWORK_AUDIT.md`` §E.

What it cannot do: it redacts values this installation **knows**. A password
typed into a chat message, or one on a device that was never extracted, is not
in the credential store and cannot be matched. Rotation is what makes an
unknown secret harmless; this makes a known one stop travelling.
"""

import logging
import re

log = logging.getLogger(__name__)

#: Below this length a value is too likely to occur in ordinary config text.
#: Redacting "RO" or "cisco" would corrupt the payload into uselessness while
#: protecting nothing an attacker could not guess. Matches
#: ``hostvars.MIN_CHECKABLE_SECRET``, which draws the line for the same reason.
MIN_REDACTABLE = 8

#: A token boundary in config text. Whole-token matching only: a secret that is
#: a substring of a longer token has not actually appeared.
_TOKEN_CHAR = r"[A-Za-z0-9_\-\.\$/]"

PLACEHOLDER = "<redacted:{label}>"


def _label_for(key: str) -> str:
    """``campus:r1:snmp_community_ro`` → ``snmp_community_ro``.

    The model is told a secret is *there* and what kind it is, which is what it
    needs to reason about the config. It is not told the value.
    """
    return key.rsplit(":", 1)[-1] or "secret"


def known_secret_values() -> dict:
    """``{value: label}`` for every secret this installation holds.

    **Every list**, not the active one: a payload is redacted for what it
    contains, and which network a secret belongs to does not change whether it
    should leave the process. Same reasoning as
    ``hostvars.assert_no_secret_values()`` — a guard narrowed by list fails
    open when the narrowing is wrong.
    """
    out = {}
    try:
        from modules.credentials import get_template_secret, list_template_secrets
        for entry in list_template_secrets():
            value = get_template_secret(entry["name"])
            if value and len(value) >= MIN_REDACTABLE:
                out[value] = _label_for(entry["name"])
    except Exception as exc:                  # noqa: BLE001
        log.error("redact: could not read template secrets (%s) — "
                  "payload will NOT be redacted for them", exc)

    # Device credentials never pass through the template-secret store, and
    # `show running-config` is not the only way they surface: a failed login
    # message or a connection error can echo one back.
    try:
        from modules.credentials import device_credential_values
        for value, label in device_credential_values().items():
            if value and len(value) >= MIN_REDACTABLE:
                out.setdefault(value, label)
    except Exception as exc:                  # noqa: BLE001
        log.debug("redact: device credentials unavailable (%s)", exc)
    return out


def _compile(values: dict):
    """One alternation, longest first, so a longer secret wins over a prefix."""
    if not values:
        return None, {}
    ordered = sorted(values, key=len, reverse=True)
    pattern = re.compile(
        f"(?<!{_TOKEN_CHAR})(" + "|".join(re.escape(v) for v in ordered)
        + f")(?!{_TOKEN_CHAR})")
    return pattern, values


def redact_text(text: str, values: dict = None) -> str:
    """Replace every known secret value in *text* with a labelled placeholder."""
    if not text:
        return text
    values = known_secret_values() if values is None else values
    pattern, table = _compile(values)
    if pattern is None:
        return text
    return pattern.sub(
        lambda m: PLACEHOLDER.format(label=table.get(m.group(1), "secret")), text)


def redact_payload(payload, values: dict = None):
    """Walk a request payload and redact every string in it.

    Structure-preserving: dicts, lists, tuples and strings. Anything else is
    returned unchanged, so a client object or a number passes through.

    The table is resolved **once** per call and threaded down, because a deep
    payload would otherwise decrypt the whole credential store per string.
    """
    values = known_secret_values() if values is None else values
    if not values:
        return payload

    def _walk(node):
        if isinstance(node, str):
            return redact_text(node, values)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(_walk(v) for v in node)
        return node

    return _walk(payload)


def contains_known_secret(payload) -> list:
    """Labels of any known secret present in *payload*. For tests and audits."""
    values = known_secret_values()
    found = []

    def _walk(node):
        if isinstance(node, str):
            for value, label in values.items():
                if re.search(f"(?<!{_TOKEN_CHAR})" + re.escape(value)
                             + f"(?!{_TOKEN_CHAR})", node):
                    found.append(label)
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(payload)
    return sorted(set(found))
