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
import threading
import time

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

#: **Positional** redaction: the token that occupies a secret's syntactic slot,
#: whatever its length and whether or not this installation has ever seen it.
#:
#: Value-based redaction alone was measured against the live fleet and covered
#: almost nothing: 14 of 18 stored secrets fall under the 8-character floor —
#: every SNMP community (6 chars) and every plaintext router password (7). The
#: floor cannot simply be lowered, because redacting a 6-character string
#: wherever it appears would corrupt ordinary config text. Position is the
#: discriminator the length never was: ``community X RO`` tells you X is a
#: secret no matter what X is.
#:
#: It also covers what the store has never seen — a device not yet onboarded,
#: a list not yet extracted, a password typed into chat — which value-based
#: redaction cannot reach by construction.
#:
#: The captured value, shared by every pattern below so the rule is stated once.
#:
#: A value cannot begin with these. Found in a real log line:
#:
#:     show running-config | include snmp-server community [in /home/…:2613]
#:
#: An operator *searching* for the community — no value present — and the token
#: the pattern ate was the log formatter's own ``[in``. Masking it corrupted
#: the line without protecting anything. A config keyword named with nothing
#: after it is a mention, not a setting, and the next token belongs to someone
#: else.
_VALUE = r"((?![\[\]|<>(){}])\S+)"

#: Each entry captures (prefix, secret, suffix); only the middle is replaced.
_POSITIONAL = (
    ("snmp_community", re.compile(
        r"(?i)\b(snmp-server\s+community\s+)" + _VALUE + r"()")),
    ("snmp_community", re.compile(
        r"(?i)\b(snmp-server\s+host\s+\S+(?:\s+version\s+\S+)?\s+)" + _VALUE + r"()")),
    # `privilege N` and `algorithm-type X` are both optional, may appear in
    # either order, and either may be absent. The first version allowed only
    # `privilege N`, so
    #     username admin privilege 15 algorithm-type scrypt secret <pw>
    # — the exact line the credential rotation sends — matched nothing and the
    # live password would have reached the log in clear. Caught by a test that
    # generates a password and asserts the redactor can mask it, before any
    # device was touched.
    ("user_password", re.compile(
        r"(?i)\b(username\s+\S+"
        r"(?:\s+(?:privilege\s+\d+|algorithm-type\s+\S+))*"
        r"\s+(?:password|secret)\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    ("enable_secret", re.compile(
        r"(?i)^(\s*enable\s+(?:password|secret)\s+(?:\d+\s+)?)" + _VALUE + r"()",
        re.M)),
    ("key_string", re.compile(
        r"(?i)\b(key-string\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    ("pre_shared_key", re.compile(
        r"(?i)\b(pre-shared-key\s+(?:address\s+\S+\s+)?(?:key\s+)?)" + _VALUE + r"()")),
    ("shared_key", re.compile(
        r"(?i)\b((?:tacacs-server|radius-server)\s+key\s+(?:\d+\s+)?)" + _VALUE + r"()")),
    ("line_password", re.compile(
        r"(?i)^(\s*password\s+(?:\d+\s+)?)" + _VALUE + r"()", re.M)),
    ("ppp_password", re.compile(
        r"(?i)\b(ppp\s+(?:chap|pap)\s+(?:password|sent-username\s+\S+\s+password)\s+(?:\d+\s+)?)" + _VALUE + r"()")),
)

#: Already redacted, or a marker — replacing these again would nest markers.
_ALREADY = re.compile(r"^<(?:redacted|missing-secret)[:>]")


def redact_positional(text: str) -> str:
    """Mask whatever occupies a secret position, regardless of length.

    Structure-preserving: ``snmp-server community`` and the trailing ``RO`` both
    survive, so the model still sees what the line *is*. Idempotent — a token
    that is already a placeholder is left alone.
    """
    if not text:
        return text

    def _sub(label):
        def _replace(match):
            token = match.group(2)
            if _ALREADY.match(token):
                return match.group(0)
            return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)
        return _replace

    for label, pattern in _POSITIONAL:
        text = pattern.sub(_sub(label), text)
    return text


def _label_for(key: str) -> str:
    """``campus:r1:snmp_community_ro`` → ``snmp_community_ro``.

    The model is told a secret is *there* and what kind it is, which is what it
    needs to reason about the config. It is not told the value.
    """
    return key.rsplit(":", 1)[-1] or "secret"


_cache = {"values": None, "at": 0.0}
_cache_lock = threading.Lock()

#: Seconds a built table is reused. Short enough that a rotation or a new
#: extraction is picked up promptly; long enough that a burst of log records
#: does not decrypt the credential store once per line.
CACHE_TTL = 30.0


def invalidate_cache() -> None:
    """Drop the cached table — call after writing a secret."""
    with _cache_lock:
        _cache["values"] = None
        _cache["at"] = 0.0


def known_secret_values() -> dict:
    """``{value: label}`` for every secret this installation holds. Cached.

    **Every list**, not the active one: a payload is redacted for what it
    contains, and which network a secret belongs to does not change whether it
    should leave the process. Same reasoning as
    ``hostvars.assert_no_secret_values()`` — a guard narrowed by list fails
    open when the narrowing is wrong.
    """
    with _cache_lock:
        if (_cache["values"] is not None
                and time.monotonic() - _cache["at"] < CACHE_TTL):
            return _cache["values"]

    out = {}
    try:
        from modules.credentials import get_template_secret, list_template_secrets
        for entry in list_template_secrets():
            value = get_template_secret(entry["name"])
            if value and len(value) >= MIN_REDACTABLE:
                out[value] = _label_for(entry["name"])
    except Exception as exc:                  # noqa: BLE001
        # Counted, not just logged. An unreadable credential store means
        # secrets are NOT being redacted, and the filter never raises — so
        # without this, health() reports "healthy" while the table is empty.
        _note_failure(exc)
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

    with _cache_lock:
        _cache["values"] = out
        _cache["at"] = time.monotonic()
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
    """Redact *text* both ways: by known value, and by syntactic position.

    The two are complementary and neither subsumes the other. Value-based
    catches a secret wherever it appears — in prose, a diff, an error message —
    but only if this installation holds it and it clears the length floor.
    Positional catches anything in a secret's slot, including secrets never
    extracted and secrets too short to match safely, but only where the
    surrounding syntax is recognised.

    Positional runs first so that value-based cannot re-wrap a placeholder.
    """
    if not text:
        return text
    text = redact_positional(text)

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


# ---------------------------------------------------------------------------
# The log boundary
# ---------------------------------------------------------------------------

class RedactingFilter(logging.Filter):
    """Redact secrets from log records. Attach to the **handler**, not a logger.

    The app log is the third place secrets leave the process, after the model
    API and the HTTP API. It is also the easiest to forget, because nobody
    writes ``log.info(password)`` on purpose — it arrives inside a config dump,
    an exception message, a Netmiko echo, or a diff.

    Attached to the root handler, so it covers every module's own
    ``logging.getLogger(__name__)`` without each having to remember — the same
    reasoning that put redaction at the provider boundary rather than at each
    reader.

    **Fails open, deliberately.** If redaction raises, the record is written
    unredacted rather than dropped. A log that silently loses entries is a
    worse failure than one that occasionally keeps something it should not:
    the first destroys the record of what happened, and this is the file an
    operator reaches for when something has already gone wrong.

    Failing open only stays defensible while the failure is *visible*, so it is
    counted in module state and surfaced by :func:`health` — a one-time log
    line announcing that the log is unreliable is a note written in the medium
    that just became unreliable.
    """

    #: Re-entry guard. The filter calls `known_secret_values()`, which logs on
    #: failure — and that record re-enters the filter, which calls it again.
    #: Unbounded recursion that can hang the process, not merely the tests it
    #: was first seen in. Thread-local because handlers are shared across
    #: threads and a module-level flag would make one thread's redaction
    #: silently skip another's record.
    _local = threading.local()

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(RedactingFilter._local, "active", False):
            # A record emitted from inside redaction — typically a credential
            # store failure. Skip the VALUE lookup, which is what would recurse,
            # but still redact POSITIONALLY: positional needs no store, and the
            # exception text that brought us here can quote a config line or a
            # ciphertext verbatim. The diagnostic survives, and it survives
            # masked.
            try:
                message = record.getMessage()
                cleaned = redact_positional(message)
                if cleaned != message:
                    record.msg = cleaned
                    record.args = ()
                if record.exc_info or record.exc_text:
                    record.exc_text = redact_positional(
                        record.exc_text
                        or logging.Formatter().formatException(record.exc_info))
                    record.exc_info = None
            except Exception:                 # noqa: BLE001
                pass                          # never lose the diagnostic
            return True
        RedactingFilter._local.active = True
        try:
            values = known_secret_values()
            # Format once here so args are interpolated; a secret is far more
            # often in an arg than in the format string.
            message = record.getMessage()
            cleaned = redact_text(message, values)
            if cleaned != message:
                record.msg = cleaned
                record.args = ()
            if record.exc_info:
                # An exception's text can quote a config line verbatim.
                record.exc_text = redact_text(
                    record.exc_text or logging.Formatter().formatException(
                        record.exc_info), values)
                record.exc_info = None
        except Exception as exc:              # noqa: BLE001
            _note_failure(exc)
        finally:
            RedactingFilter._local.active = False
        return True


# ---------------------------------------------------------------------------
# Failure visibility
# ---------------------------------------------------------------------------

#: Redaction fails open, so the only thing standing between that and a silent
#: leak is somebody noticing. Kept as state rather than only a log line,
#: because a log line saying "the log is unreliable" is written in the medium
#: that just became unreliable.
_failures = {"count": 0, "first_at": "", "last_at": "", "last_error": ""}
_failure_lock = threading.Lock()


def _note_failure(exc: Exception) -> None:
    with _failure_lock:
        first = _failures["count"] == 0
        _failures["count"] += 1
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _failures["last_at"] = stamp
        _failures["last_error"] = type(exc).__name__
        if first:
            _failures["first_at"] = stamp
    if first:
        logging.getLogger(__name__).error(
            "redact: log redaction FAILED (%s) — records are being written "
            "UNREDACTED. See redaction health in /identity/status.",
            type(exc).__name__)


def health() -> dict:
    """Is outbound redaction working? For diagnostics and health badges."""
    with _failure_lock:
        failures = dict(_failures)
    handlers = _handler_coverage()
    probe = canary_report()
    return {
        # The canary is the authority: it asks whether a record reaching each
        # handler comes out masked, rather than whether a filter is attached.
        "healthy": (failures["count"] == 0 and handlers["unprotected"] == 0
                    and probe["leaking"] == 0),
        "canary_handlers_checked": probe["handlers"],
        "canary_leaking": probe["leaking"],
        "canary_leaking_detail": probe["leaking_detail"],
        "redaction_failures": failures["count"],
        "first_failure_at": failures["first_at"],
        "last_failure_at": failures["last_at"],
        "last_error": failures["last_error"],
        "log_handlers_total": handlers["total"],
        "log_handlers_unprotected": handlers["unprotected"],
        "unprotected_handler_types": handlers["types"],
    }


def reset_health() -> None:
    """For tests. Never called by the app."""
    with _failure_lock:
        _failures.update({"count": 0, "first_at": "", "last_at": "",
                          "last_error": ""})


# ---------------------------------------------------------------------------
# Handler coverage
# ---------------------------------------------------------------------------

def _all_handlers() -> list:
    """Every handler attached anywhere, root and named loggers alike."""
    seen, out = set(), []
    loggers = [logging.getLogger()]
    manager = logging.getLogger().manager
    loggers += [lg for lg in manager.loggerDict.values()
                if isinstance(lg, logging.Logger)]
    for logger in loggers:
        for handler in getattr(logger, "handlers", []):
            if id(handler) not in seen:
                seen.add(id(handler))
                out.append(handler)
    return out


def _handler_coverage() -> dict:
    handlers = _all_handlers()
    unprotected = [h for h in handlers
                   if not any(isinstance(f, RedactingFilter) for f in h.filters)]
    return {"total": len(handlers), "unprotected": len(unprotected),
            "types": sorted({type(h).__name__ for h in unprotected})}


#: A line shaped exactly like a secret-bearing config line, with a value that
#: is not a secret anywhere. Pushed through a handler's own filter chain to ask
#: the only question that matters: *does a record reaching THIS handler come out
#: masked?* Inspecting `handler.filters` answers a weaker question — a filter
#: can be present and disabled, shadowed by an earlier filter returning False,
#: or installed on a handler that was later replaced.
#: One line per secret SHAPE, each with its own token so a failure names which
#: shape leaked rather than only that something did.
#:
#: The `algorithm-type` line is here because its absence was a live gap: the
#: pattern allowed `username X [privilege N] secret <v>` but not an
#: `algorithm-type` clause between them, so the exact line the credential
#: rotation sends matched nothing. A canary that only ever tested the shapes we
#: already handled would not have found it, and will not find the next one —
#: so every shape the tool itself EMITS belongs here.
CANARY_LINES = (
    ("snmp_community", "snmp-server community CanaryTokenA1 RO"),
    ("user_password", "username admin privilege 15 password CanaryTokenB2"),
    ("user_secret_algo",
     "username admin privilege 15 algorithm-type scrypt secret CanaryTokenC3"),
    ("enable_secret", "enable secret 9 CanaryTokenD4"),
)
CANARY_TOKENS = {label: line.split()[-1] if label != "snmp_community"
                 else "CanaryTokenA1"
                 for label, line in CANARY_LINES}

#: Kept for callers that want a single representative line.
CANARY_LINE = CANARY_LINES[0][1]
CANARY_TOKEN = "CanaryTokenA1"


def canary(handler) -> dict:
    """Would a secret-bearing record survive *handler*'s filters unmasked?

    Runs the handler's real filter chain over a synthetic record. Never emits:
    the record is built and filtered, not handled, so nothing is written
    anywhere and no canary line appears in any log.
    """
    record = logging.LogRecord(
        name="redact.canary", level=logging.INFO, pathname=__file__, lineno=0,
        msg="\n".join(line for _label, line in CANARY_LINES),
        args=(), exc_info=None)
    try:
        for f in list(handler.filters):
            result = f.filter(record) if hasattr(f, "filter") else f(record)
            if result is False:
                # Dropped before reaching the formatter — nothing to leak here.
                return {"ok": True, "dropped": True,
                        "handler": type(handler).__name__}
        message = record.getMessage()
        leaked = sorted(label for label, token in CANARY_TOKENS.items()
                        if token in message)
        return {"ok": not leaked, "dropped": False,
                "handler": type(handler).__name__,
                "leaked_shapes": leaked,
                "target": _handler_target(handler)}
    except Exception as exc:                  # noqa: BLE001
        return {"ok": False, "dropped": False, "handler": type(handler).__name__,
                "error": type(exc).__name__}


def _handler_target(handler) -> str:
    """Where a handler writes, for a report an operator can act on."""
    for attr in ("baseFilename", "stream"):
        value = getattr(handler, attr, None)
        if isinstance(value, str):
            return value
        name = getattr(value, "name", "")
        if name:
            return str(name)
    return ""


def canary_report() -> dict:
    """Run the canary through every handler. This replaces grepping the log."""
    results = [canary(h) for h in _all_handlers()]
    leaking = [r for r in results if not r["ok"]]
    return {"handlers": len(results), "leaking": len(leaking),
            "leaking_detail": leaking, "results": results}


def install_log_redaction(handler) -> bool:
    """Attach :class:`RedactingFilter` to *handler*. Idempotent."""
    if any(isinstance(f, RedactingFilter) for f in handler.filters):
        return False
    handler.addFilter(RedactingFilter())
    return True


def redact_all_handlers() -> int:
    """Install on **every** handler attached anywhere. Returns how many gained it.

    A filter on the root *logger* would not do: a record emitted by a child
    logger is passed to ancestor **handlers** without ancestor logger filters
    being consulted. Handler filters are the only ones every record must pass.

    And one handler is not enough either. The file handler is created only when
    ``app.debug`` is false; a StreamHandler to stdout — which under systemd is
    the journal — would otherwise carry unredacted records to exactly the place
    an operator greps first.
    """
    return sum(1 for handler in _all_handlers() if install_log_redaction(handler))


_guard_installed = False


def guard_new_handlers() -> bool:
    """Make handlers added *later* inherit the filter. Idempotent.

    Coverage established once at startup decays: a library that calls
    ``addHandler`` after boot, a lazily-imported module, a handler swapped at
    runtime. Rather than documenting "remember to re-run redact_all_handlers",
    the capability is bounded at the point where a handler is attached — the
    same move as ``resolve_identity`` losing the ability to mint.
    """
    global _guard_installed
    if _guard_installed:
        return False

    original = logging.Logger.addHandler

    def addHandler(self, hdlr):                # noqa: N802 - matches stdlib
        try:
            install_log_redaction(hdlr)
        except Exception:                      # noqa: BLE001
            pass                               # never break logging setup
        return original(self, hdlr)

    logging.Logger.addHandler = addHandler
    _guard_installed = True
    return True
