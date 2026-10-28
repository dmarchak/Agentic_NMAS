"""The gateway: Mercury's one way to a model (PHASE8_PLAN 13.2, AI_ANTHROPIC_PLAN 3.1).

`ask(feature, prompt, schema, parts, ...)` returns ``{"ok": True, "output": <the validated
StrictModel>, "call_id", "cost_usd"}`` or ``{"ok": False, "error": <kind>, "detail", "call_id"}``,
and every call, sent or refused, is one `ai_calls` row. In order, before anything is sent:

0. **The call names its trigger** (PHASE8_PLAN 18.3 rule 1, `triggers.check`): a person's
   press, an evaluation run, or a background job on a finding; none, or one out of shape, is
   refused (`trigger`) before anything is read. The row records it.
1. **Hosted AI is allowed** on this installation: the admin's setting `ai_hosted`, with who,
   when and the recorded reason (PHASE8_PLAN 13.1, 15.8). Off by default. **A background
   call's feature is on for its network** (rule 2, `background.admit`): off by default, else
   refused (`feature_off`).
2. **A key is set** (`anthropic_api_key`, in the secrets store, typed by a person). **The
   provider's workspace usage limit is not held** (C2084, `provider_limit`): once the provider
   refused a call because the workspace reached its usage limit, every later call is refused
   here (`workspace_limit`), in the same words, without asking the provider, until the moment
   it named (or `provider_limit.RECHECK_S` when it named none); a person's press of the AI
   card's Test (`connection_check`, `provider_limit.rechecks`) still asks, and any answer
   clears the hold.
3. **The task** is one `profiles.TASKS` pins: its model, its prompt bound and its answer
   bound (the operator's ruling of 2026-10-25: pinned per task, never chosen at run time).
   **The prompt** is a registered, versioned file; **the schema** a registered StrictModel.
4. **Masked for egress**: first **what a person typed or pasted** (C1845, PHASE8_PLAN 18.1
   A1 (b)): the task's typed parts (`TYPED_PARTS`; a task naming none is refused,
   `typed_undeclared`) masked by position and by known value (`mask_typed`), and what was
   masked said back in words, never the value (`typed_said`: on the result and the row as
   ``typed_masked``; a question with nothing to mask is sent as typed, and nothing is said).
   Then the request built (the prompt as the system text, each part as delimited data, never
   as instructions), then `redact.egress_payload` over all of it; a known stored secret still
   present refuses the call (`unmasked_secret`), naming its label.
5. **The prompt's length** (C1898): the provider's count of the masked request (`Counter`,
   `anthropic_adapter.count_tokens`), or, when the count is not had, the fallback
   over-estimate from its size (`CHARS_PER_TOKEN`, calibrated against the recorded calls),
   the row saying which (``prompt_count``); under the task's bound, which is always under its
   model's long tier (Haiku 5.5 over 100,000 tokens pays every rate 5x); over it the call is
   refused (`prompt_too_long`), both numbers and how the prompt was measured named.
6. **The caps**, judged by the worst case (that count as cache writes, plus all of
   `max_tokens`, at the pinned model's prices): the task's per-call cap (its pinned model's
   worst case at its bounds, `profiles.cap_per_call`), and the day's spend so far plus what
   calls in flight have reserved plus this call against the installation's day cap, unless
   an admin chose no cap (`day_cap` None, said in every cap refusal). A refusal names every
   operand. A background call's feature's own day and month caps on its network after it
   (rule 4, `background.over_cap`: `feature_cap`, naming which). **Reserved atomically**
   (C2039, `reservations`): the spend read, the caps judged and the worst case reserved under
   one lock across threads and processes, so calls at once can never pass a cap together;
   the reservation settled once the call's row, with its actual cost, is recorded.

**One press, one provider request** (C1854): from the caps on, a call runs through
`presses.once`: a press whose key was already seen, or whose request is already in flight (the
same feature, network, subject, prompt, model, access scope and masked body), gets that call's
result (`from_row`) and sends nothing, the join its own row (verdict ``joined``, cost 0).

Then the adapter sends it; a refusal, a `max_tokens` stop, an answer that is not the schema,
and each provider failure are each their own kind, never a parser's crash (13.5).
"""
import json
import logging
import re

from pydantic import ValidationError

from modules.ai import (anthropic_adapter, background, calls, profiles, prompts, provider_limit,
                        schemas, triggers)

log = logging.getLogger(__name__)

#: Characters per token the FALLBACK estimate assumes, when the provider's count is not had
#: (C1898: an error, a timeout, rate-limited, or no count asked): deliberately high, so the
#: estimate is over the real input, never under. Calibrated 2026-10-28 against the recorded
#: calls' real input (input plus cache read plus cache write tokens): 10,395 sent calls, their
#: characters ``len(json.dumps(request, ensure_ascii=False))``; the fewest characters a token
#: any of them had was 1.956 (an sdn_classify call on Haiku, 49,318 characters and 25,210
#: tokens), so 1.8 is over every recorded call, by 8.7% at the tightest; median over by 1.44x
#: (tests/test_ai_token_count.py reads a sample, `CALIBRATION` the whole set's numbers). The
#: earlier 3.0 was UNDER every one of them (0.65 to 0.89 of the real). The recorded usage
#: replaces either once the call is answered.
CHARS_PER_TOKEN = 1.8
#: The calibration's numbers, whole (the dataset is a report's, not the repository's: numbers
#: only, ~/Documents/nmas-reports/overnight/2026-10-28-calibration-calls.tsv on the laptop).
CALIBRATION = {"calls": 10395, "fewest_chars_per_token": 1.9563,
               "tightest": {"feature": "sdn_classify", "model": "claude-haiku-5-5",
                            "chars": 49318, "real_input": 25210},
               "read": "2026-10-28"}

#: The default the schema seeds (modules/settings_schema.py): a day's spend for the
#: installation. PHASE8_PLAN 7 caps a month at $50 globally; $1.50 a day is under that. A
#: call's cap is its task's (`profiles.cap_per_call`).
DEFAULT_CAP_PER_DAY = 1.50


# ── What a person typed or pasted (C1845; PHASE8_PLAN 18.1 A1 prerequisite (b)) ─────────────

#: The parts of each task's data that hold what a person typed or pasted, by the part's name.
#: Every task `profiles.TASKS` pins is named here, with its typed parts or none: `ask` refuses a
#: task not named (`typed_undeclared`) before anything is built, so no new feature reaches a
#: model without saying which of its data a person wrote (tests/test_ai_typed_text.py holds this
#: to the pins, and every field the routes into the gateway read to it). Mercury's own data
#: (an evidence pack, a detection, the network's slice: PHASE8_PLAN 15.11's classes) is no
#: typed part: it passes the request's own mask once, unchanged by this one.
TYPED_PARTS = {
    "nl_query": ("question",),        # Ask in words, both builders: the question as typed
    "intent_patch": ("sentence",),    # Change it in words: the sentence, its quoted text
                                      # already held back as placeholders (intent_words)
    "explain": (),                    # an evidence pack: Mercury's own data
    "sdn_classify": (),               # a detection's pack: Mercury's own data
    "connection_check": (),           # a word Mercury chose
}

#: What each mask's label is, in a person's words: the label is the redact rule's
#: (`redact._POSITIONAL`, `redact._EGRESS`); a label not here is a value Mercury holds, masked by
#: value (its label the store's name for it, never shown to the person).
MASK_WORDS = {
    "snmp_community": "an SNMP community",
    "user_password": "a user's password",
    "enable_secret": "an enable secret",
    "key_string": "a key string",
    "pre_shared_key": "a pre-shared key",
    "shared_key": "a TACACS or RADIUS key",
    "server_host_key": "a TACACS or RADIUS server's key",
    "dynamic_author_key": "a RADIUS dynamic-authorization client's key",
    "pac_key": "a RADIUS PAC key",
    "config_key": "the password-encryption master key",
    "nhrp_authentication": "an NHRP authentication string",
    "ikev2_pre_share_key": "an IKEv2 pre-shared key",
    "ospf_virtual_link_key": "an OSPF virtual link's key",
    "ospfv3_ipsec_encryption_key": "an OSPFv3 IPsec encryption key",
    "ospfv3_ipsec_authentication_key": "an OSPFv3 IPsec authentication key",
    "server_block_key": "a server block's key",
    "ospf_key": "an OSPF authentication key",
    "neighbor_password": "a neighbor's password",
    "snmp_user_auth": "an SNMPv3 user's authentication password",
    "snmp_user_priv": "an SNMPv3 user's privacy password",
    "isakmp_key": "an IKE (ISAKMP) key",
    "server_key": "a server's or group's key",
    "fhrp_authentication": "an HSRP, VRRP or GLBP authentication string",
    "ntp_key": "an NTP authentication key",
    "line_password": "a line password",
    "http_client_password": "an HTTP client password",
    "ppp_password": "a PPP password",
    "url_userinfo": "a URL's user and password",
    "sealed": "an encrypted secret",
    "egress_password": "a password or secret",
    "egress_key": "an authentication key",
    "egress_snmp_auth": "an SNMPv3 authentication key",
    "egress_snmp_priv": "an SNMPv3 privacy key",
    "egress_hash": "a password hash",
}
#: A value masked because Mercury holds it (`redact.known_secret_values`).
BY_VALUE_WORDS = "a credential Mercury holds"

_MASK = re.compile(r"<redacted:([^<>\s]*)>")


def _new_masks(before: str, after: str) -> list:
    """The labels of the masks *after* holds that *before* did not, in their order (a mask a
    person typed themselves is not one this made)."""
    held = {}
    for label in _MASK.findall(before):
        held[label] = held.get(label, 0) + 1
    out = []
    for label in _MASK.findall(after):
        if held.get(label):
            held[label] -= 1
        else:
            out.append(label)
    return out


def mask_typed(parts: dict, names, values: dict) -> dict:
    """``{"parts", "masked"}``: *parts* with each typed part (*names*) masked as it leaves the
    host (`redact.redact_egress`: by position, by the egress shapes and by the known values
    *values*), every other part the very object given; and what was masked, per part and line,
    ``[{"part", "line", "lines", "labels"}]``, never a value. A typed part absent, or holding
    nothing to mask, is left as it is."""
    from modules import redact

    out, found = dict(parts), []
    for name in names:
        text = parts.get(name)
        if not isinstance(text, str) or not text:
            continue
        masked = redact.redact_egress(text, values)
        if masked == text:
            continue
        out[name] = masked
        before, after = text.split("\n"), masked.split("\n")
        if len(before) != len(after):
            # A held value spanning lines: said for the text whole.
            before, after = [text], [masked]
        for n, (b, a) in enumerate(zip(before, after), 1):
            if a != b:
                found.append({"part": name, "line": n, "lines": len(after),
                              "labels": _new_masks(b, a) or ["secret"]})
    return {"parts": out, "masked": found}


def _listed(words: list) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def typed_said(masked: list) -> dict:
    """What `mask_typed` masked, for the person who typed it (shown on the screen that sent it)
    and the call's row: ``{"values", "lines", "said"}``, the words naming each mask's kind and,
    for text of more than one line, its line; never a value. ``{}`` when nothing was masked."""
    if not masked:
        return {}
    def kinds(labels):
        return [MASK_WORDS.get(label, BY_VALUE_WORDS) for label in labels]
    count = sum(len(m["labels"]) for m in masked)
    parts = sorted({m["part"] for m in masked})
    where = f" in the {_listed(parts)}" if len(parts) > 1 else ""
    if any(m["lines"] > 1 for m in masked):
        n = len(masked)
        said = (f"{n} line{'s' if n > 1 else ''} {'were' if n > 1 else 'was'} masked before "
                f"sending{where}: " + "; ".join(
                    f"{_listed(kinds(m['labels']))} on line {m['line']}"
                    + (f" of the {m['part']}" if where else "") for m in masked))
    else:
        said = (f"{count} value{'s' if count > 1 else ''} {'were' if count > 1 else 'was'} "
                f"masked before sending{where}: "
                + _listed([w for m in masked for w in kinds(m["labels"])]))
    return {"values": count, "lines": [m["line"] for m in masked], "said": said}


def hosted_allowed() -> dict:
    """``{"allowed": bool, "why": str, "by", "at", "reason"}`` from the admin's setting."""
    from modules.settings_schema import get_setting
    got = get_setting("ai_hosted") or {}
    if not isinstance(got, dict) or not got.get("reason") or not got.get("by"):
        return {"allowed": False, "why": "hosted AI is off: an admin allows it in Settings, "
                "with a recorded reason (PHASE8_PLAN 15.8)", "by": "", "at": "", "reason": ""}
    # `by` and `reason` are there (the guard above); only `at` may be absent.
    return {"allowed": True, "why": "", "by": got["by"], "at": got.get("at", ""),
            "reason": got["reason"]}


#: Said in a cap's refusal while no day cap is set: what the person chose, and what stands.
NO_DAY_CAP_WORDS = ("no day cap is set (an admin chose no cap: Mercury does not stop AI "
                    "spend; the provider's own limit is the backstop)")


def day_cap():
    """The installation's day cap in US dollars, or None: **no cap**, an admin's explicit
    choice (the key stored as null, behind a typed confirmation on the AI card; the operator,
    2026-10-27). A key never set reads as the schema's default; a stored value that is not a
    number (a hand-edited file) as the gateway's, the same one, never as no cap."""
    from modules.settings_schema import get_setting

    # The schema declares the key's default, and the default is named here too, so a key never
    # set is never read as None: None here is only a stored null.
    raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_CAP_PER_DAY


def caps(feature: str) -> dict:
    """The task's per-call cap (derived from its pin) and the installation's day cap
    (`day_cap`: None is no cap)."""
    return {"per_call": profiles.cap_per_call(feature), "per_day": day_cap()}


def _api_key() -> str:
    from modules.secrets_store import get_secret
    return get_secret("anthropic_api_key") or ""


def _delimited(tag: str, parts: dict) -> str:
    return "\n\n".join(f'<{tag} name="{name}">\n{parts[name]}\n</{tag}>' for name in sorted(parts))


def build_request(prompt: dict, schema_model, parts: dict, pin: dict, context: dict = None,
                  profile: dict = None) -> dict:
    """The Messages API body. **The stable prefix, cached** (the operator, 2026-10-25): the
    prompt, then the *context* (what every call of a feature shares, as 8.1's builder
    vocabulary), as system blocks, the last marked `cache_control` (the 5-minute TTL). **The
    call's own parts, uncached**: each as data, delimited by its name, in one user turn (a
    question, an evidence pack). The answer's schema in `output_config.format`. Nothing
    volatile (a time, an id) is ever in the system blocks: any byte that moves there misses
    the cache for everything after it. **The request's settings are the task's *pin*'s**
    (its file, `profiles.load_pins`): its model and `max_tokens`; its `thinking` off sent in
    the model's own form (*profile*'s `thinking_off`), adaptive sending none; its
    `temperature` sent when it names one, null sending none. `ask` checks the pin's settings
    against the model before this is built."""
    system = [{"type": "text", "text": prompt["text"]}]
    if context:
        system.append({"type": "text", "text": _delimited("context", context)})
    system[-1]["cache_control"] = {"type": "ephemeral"}
    body = {
        "model": pin["model"],
        "max_tokens": int(pin["max_tokens"]),
        "system": system,
        "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],
        "output_config": {"format": {"type": "json_schema",
                                     "schema": schemas.schema_for(schema_model)}},
    }
    if pin.get("thinking") == "off":
        body["thinking"] = dict((profile or {})["thinking_off"])
    if pin.get("temperature") is not None:
        body["temperature"] = pin["temperature"]
    return body


def tokens_of_chars(chars: int) -> int:
    """The fallback estimate of a request of *chars* characters, in tokens (`CHARS_PER_TOKEN`:
    calibrated to be over the real input)."""
    return int(chars / CHARS_PER_TOKEN) + 1


def prompt_tokens(body: dict) -> int:
    """The request's prompt, in tokens, by the fallback estimate from its size (an
    over-estimate: `CHARS_PER_TOKEN`). The provider's count, when it answers, replaces it
    (`Counter`)."""
    return tokens_of_chars(len(json.dumps(body, ensure_ascii=False)))


def worst_case_usd(model: str, body: dict, tokens: int = None) -> float:
    """The call's cost if nothing is read from the cache: the whole input (*tokens*, the
    provider's count or the fallback estimate; the estimate when not given) priced as a cache
    write (the dearer of the two), plus all of `max_tokens` (every body `build_request` makes
    carries it)."""
    return profiles.cost_usd(model, 0, int(body["max_tokens"]),
                             cache_write_tokens=prompt_tokens(body) if tokens is None
                             else int(tokens))


# ── The provider's token count (C1898) ──────────────────────────────────────────────────────

#: The most counts one `Counter` asks (a press's context-budget selection, or a call): past
#: it the fallback estimate is used, said. A selection that drops one piece at a time could
#: otherwise ask once per piece.
MAX_COUNTS = 8
#: A candidate request is skipped without a count when this press's measured tokens per
#: character puts it more than this fraction over the budget (`Counter.measure`).
SKIP_MARGIN = 0.05


class Counter:
    """A request's prompt in tokens, by the provider's count (`anthropic_adapter.count_tokens`)
    where it answers, else the fallback estimate (`prompt_tokens`), saying which: ``{"tokens",
    "how": "counted" | "estimated" | "scaled", "why", ...}``.

    It counts only the masked request (`redact.egress_payload`; a stored secret still in it is
    never sent, not even to be counted), with the same key as the send, never logged, and only
    when *allowed* (the call's own gates passed: `counter`). The same request is counted once
    (by digest). *count* replaces the adapter's count (tests)."""

    def __init__(self, model: str, key: str = "", *, allowed: bool = True, why_not: str = "",
                 count=None):
        self.model, self._key, self.allowed, self.why_not = model, key, allowed, why_not
        self._count = count
        self._seen = {}
        self.asked = 0
        #: The most tokens a character this counter's counts measured (None before one).
        self.ratio = None

    def measure(self, body: dict, budget: int = None, *, masked: bool = False) -> dict:
        """*body*'s prompt in tokens. With *budget* (a selector's): a request the fallback
        estimate already puts within it is not counted (the estimate is over the real), and
        one this counter's measured ratio puts over it by more than `SKIP_MARGIN` is not
        either (``scaled``: a selector's skip, never what a call is judged on). *masked*: the
        body is already masked (the gateway's own)."""
        import hashlib

        from modules import redact

        if not masked:
            body = redact.egress_payload(body)
        chars = len(json.dumps(body, ensure_ascii=False))
        est = tokens_of_chars(chars)

        def estimated(why):
            return {"tokens": est, "how": "estimated", "why": why,
                    "chars_per_token": CHARS_PER_TOKEN}

        if budget is not None and est <= budget:
            return estimated("the fallback over-estimate is within the bound, so no count "
                             "was asked")
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=True)
                                .encode("utf-8")).hexdigest()
        if digest in self._seen:
            return dict(self._seen[digest])
        if not self.allowed:
            return estimated(self.why_not)
        if budget is not None and self.ratio is not None \
                and chars * self.ratio > budget * (1 + SKIP_MARGIN):
            return {"tokens": int(chars * self.ratio) + 1, "how": "scaled",
                    "why": f"over the bound {budget} by this press's measured "
                           f"{self.ratio:.4f} tokens a character; not counted"}
        if redact.contains_known_secret(body):
            return estimated("a stored secret is still in the request after masking, so it "
                             "was not sent to be counted")
        if self.asked >= MAX_COUNTS:
            return estimated(f"this press asked {MAX_COUNTS} counts already; the fallback "
                             "over-estimate is used")
        self.asked += 1
        try:
            got = (self._count or anthropic_adapter.count_tokens)(body, self._key)
        except Exception as exc:                        # noqa: BLE001 (said, never a crash)
            kind = getattr(exc, "kind", type(exc).__name__)
            out = estimated(f"the provider's count failed ({kind}: {exc}); the fallback "
                            "over-estimate is used")
        else:
            out = {"tokens": int(got.tokens), "how": "counted", "why": "",
                   "latency_s": round(float(got.latency_s), 3)}
            self.ratio = max(self.ratio or 0.0, got.tokens / max(chars, 1))
        self._seen[digest] = out
        return dict(out)


def counter(feature: str, *, actor: str, trigger: dict = None, count=None) -> Counter:
    """A press's `Counter` for a context-budget selector (`nl_query.select_context`,
    `explain.budgeted`), run before `ask`: it counts only where the call itself would get as
    far as being sent (its trigger, hosted AI allowed, a background feature on, a key, a
    pinned task); otherwise it estimates, saying why, and sends nothing. `ask` asks its own
    gates again whatever this said."""
    pin = profiles.TASKS.get(feature) or {}
    named = triggers.check(trigger, actor, feature)
    why = "" if named["ok"] else named["why"]
    if not why and not hosted_allowed()["allowed"]:
        why = hosted_allowed()["why"]
    if not why and named["trigger"]["kind"] == triggers.BACKGROUND:
        why = background.admit(named["trigger"])
    key = "" if why else _api_key()
    if not why and not key:
        why = "no Anthropic API key is set"
    if not why and not provider_limit.rechecks(feature, named["trigger"]["kind"]):
        hold = provider_limit.holding()
        if hold:
            why = provider_limit.said(hold)["words"]
            key = ""
    if not why and not pin:
        why = f"{feature!r} is not a task profiles.TASKS pins"
    return Counter(pin.get("model", ""), key, allowed=not why,
                   why_not=f"not counted: {why}" if why else "", count=count)


def _limit_fields(hold: dict) -> dict:
    """What a call's row keeps of the provider's workspace limit (C2084): when it was met, the
    moment the provider named (or None), when Mercury asks again, and the provider's words."""
    return {"limit": {"since": hold["since"], "until": hold.get("until"),
                      "recheck_at": hold["recheck_at"], "provider": hold.get("said") or "",
                      "call_id": hold.get("call_id") or ""}}


def _text_of(reply_body: dict) -> str:
    return "".join(b.get("text", "") for b in reply_body.get("content") or []
                   if b.get("type") == "text")


def ask(feature: str, prompt: tuple, schema_model, parts: dict, *, actor: str,
        trigger: dict = None, context: dict = None, send=None, today: str = None,
        thinking: str = None, subject: dict = None, network: str = "", count=None) -> dict:
    """One schema-bound call of the task *feature* (the module's docstring has the order): its
    model and bounds are its pin in `profiles.TASKS`, never an argument. *context* is the
    stable prefix every call of the task shares, cached; *parts* the call's own data,
    uncached. *send* replaces the adapter (tests); *today* the UTC day the caps count.
    *thinking* (one of `profiles.THINKING`) replaces the task's for this call alone, as a
    measurement of both asks; by default the task's pin, "adaptive" when it names none. The
    row records which was sent. *subject* is what the call is about, written with it (15.14:
    the device, the alert or the query, ``{"kind", "id", "devices"}``), on every row, sent or
    refused. *trigger* is what started the call (`triggers`); a call without one is refused.
    *network* is the network the call is about (a list's folder name; "" for the
    installation's own, the connection check): with the subject, the prompt, the model and
    the requester's access scope, what makes two presses one request (C1854). *count*
    replaces the adapter's token count (tests), as *send* its send."""
    call_id = calls.new_id()
    pin = profiles.TASKS.get(feature) or {}
    model = pin.get("model", "")
    # No verdict here: every path that records the row sets its own (a refusal's kind,
    # `_answered`'s, or "ok").
    row = {"id": call_id, "feature": feature, "actor": actor, "model": model,
           "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,
           "subject": dict(subject or {})}
    # What was masked of the person's own words, once masked (C1845): on every result from
    # there on, as on the row.
    told = {}

    def refuse(kind, detail, **extra):
        out = calls.record(dict(row, verdict=kind, detail=detail, **extra))
        log.info("ai: %s refused for %s: %s", feature, kind, detail)
        return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,
                "recorded": out.get("recorded", False), **told}

    named = triggers.check(trigger, actor, feature)
    row["trigger"] = named["trigger"]
    if not named["ok"]:
        return refuse("trigger", named["why"])
    hosted = hosted_allowed()
    if not hosted["allowed"]:
        return refuse("ai_off", hosted["why"])
    if named["trigger"]["kind"] == triggers.BACKGROUND:
        off = background.admit(named["trigger"])
        if off:
            return refuse("feature_off", off)
    key = _api_key()
    if not key:
        return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")
    # The provider's workspace usage limit, held from its refusal (C2084): refused here, in the
    # same words, without asking the provider, but for the AI card's Test (the re-check).
    if not provider_limit.rechecks(feature, named["trigger"]["kind"]):
        hold = provider_limit.holding()
        if hold:
            return refuse(provider_limit.KIND, provider_limit.said(hold)["words"],
                          **_limit_fields(hold))
    if not pin:
        return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "
                      f"{', '.join(sorted(profiles.TASKS))}")
    if feature not in TYPED_PARTS:
        return refuse("typed_undeclared", f"{feature!r} names no typed parts in "
                      "gateway.TYPED_PARTS: which of its data a person typed is not known, so "
                      "it could not be masked and said; nothing was sent")
    max_tokens = int(pin["max_tokens"])
    try:
        profile = profiles.profile(model)
    except KeyError as exc:
        return refuse("unknown_model", str(exc))
    if profile["provider"] != profiles.ANTHROPIC:
        return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")
    # The request's settings are the pin file's; a measurement's *thinking* replaces its one.
    asked = dict(pin, thinking=thinking) if thinking is not None else pin
    mode = asked["thinking"]                    # every pin names it (profiles.PIN_KEYS)
    row["thinking"] = mode
    if mode not in profiles.THINKING:
        return refuse("thinking", f"thinking {mode!r} is not one of "
                      f"{', '.join(profiles.THINKING)}; nothing was sent")
    if mode == "off" and not profile.get("thinking_off"):
        return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "
                      "nothing was sent")
    temperature = asked["temperature"]
    if temperature is not None and temperature not in profile.get("temperatures", ()):
        return refuse("temperature", f"the pin's temperature {temperature!r} is not one "
                      f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "
                      "was sent")
    ident = getattr(schema_model, "__ai_schema__", None)
    if ident is None or schemas.REGISTRY.get(ident) is not schema_model:
        return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "
                      "registered AI schema")
    row["schema"] = f"{ident[0]}.v{ident[1]}"
    try:
        prompt_file = prompts.load(*prompt)
    except prompts.PromptError as exc:
        return refuse("prompt", str(exc))
    row["prompt_sha256"] = prompt_file["sha256"]

    from modules import redact
    values = redact.known_secret_values()
    # What a person typed, masked here, once, for every entry point (C1845), and what was
    # masked said to them; then the whole request masked as it leaves.
    typed = mask_typed(parts, TYPED_PARTS[feature], values)
    said = typed_said(typed["masked"])
    if said:
        row["typed_masked"] = said
        told["typed_masked"] = said
    body = redact.egress_payload(build_request(prompt_file, schema_model, typed["parts"], asked,
                                               context=context, profile=profile), values)
    leaked = redact.contains_known_secret(body)
    if leaked:
        return refuse("unmasked_secret", "a stored secret is still in the request after "
                      f"masking ({', '.join(leaked)}); nothing was sent")
    row["request"] = body

    # The prompt's size (C1898): the provider's count of the masked request, every gate above
    # passed; the fallback over-estimate when the count is not had, said. Both on the row.
    measured = Counter(model, key, count=count).measure(body, masked=True)
    est = measured["tokens"]
    row["prompt_tokens"] = est
    row["prompt_count"] = {k: v for k, v in measured.items() if k != "tokens"}
    how = ("counted by the provider" if measured["how"] == "counted" else
           f"by the fallback estimate, {CHARS_PER_TOKEN} characters a token "
           f"({measured['why']})")
    if est > pin["max_prompt_tokens"]:
        long_at = profile.get("long_prompt_tokens")
        return refuse("prompt_too_long", f"this prompt is {est} tokens ({how}), over the "
                      f"task's bound of {pin['max_prompt_tokens']}"
                      + (f" ({model} charges every rate at its long tier over {long_at})"
                         if long_at else "") + "; nothing was sent")

    # One press, one provider request (C1854): the caps, the send and the record run once per
    # press key and once per identical request in flight; a press that joins one gets that
    # call's result, rebuilt from its row (modules/ai/presses.py).
    def spend():
        return _capped_send(feature, row, body, model, max_tokens, schema_model, key,
                            send=send, today=today, refuse=refuse, tokens=est)

    # The request's identity beside its body (presses.IDENTITY): everything that changes the
    # answer or who may see it, named here where each is known.
    from modules import identity
    from modules.ai import presses
    about = {"network": network or "", "subject": row["subject"], "prompt": row["prompt"],
             "model": model, "scope": identity.access_scope()}
    got = presses.once(feature, body, about=about, actor=actor, make=spend, refuse=refuse,
                       rebuild=lambda kept, why: _joined(row, kept, schema_model, why,
                                                         about["scope"]),
                       wait_s=press_wait_s())
    return dict(got, **told) if told else got


#: Added to the adapter's worst case for a press's wait: the caps' read and the record's write
#: around the send (an allowance, not measured).
PRESS_MARGIN_S = 15.0


def send_bound_s() -> float:
    """One call's longest time in the adapter: each attempt's connect and read bounds, every
    retry and the longest wait between them, 65 s x 3 + 20 s x 2 = 235 s (from
    anthropic_adapter.TIMEOUT, MAX_RETRIES and MAX_WAIT_S). Derived from the adapter's bounds,
    not measured: no live call has been measured near them."""
    a = anthropic_adapter
    return (a.TIMEOUT[0] + a.TIMEOUT[1]) * (a.MAX_RETRIES + 1) + a.MAX_WAIT_S * a.MAX_RETRIES


def press_wait_s() -> float:
    """How long a press waits on an identical call in flight (`presses.once`): one call's
    longest time in the adapter (`send_bound_s`, 235 s), and `PRESS_MARGIN_S`."""
    return send_bound_s() + PRESS_MARGIN_S


#: A reservation's life over one call's longest time in the adapter (CLAUDE.md: a bound is
#: about 2.5x the time it covers).
RESERVATION_FACTOR = 2.5


def reservation_ttl_s() -> float:
    """How long a call's reservation against the caps lives unsettled (C2039,
    `reservations`): `RESERVATION_FACTOR` times one call's longest time in the adapter
    (`send_bound_s`, 235 s, derived from the adapter's bounds, not measured), 587.5 s. A live
    call is settled long before; only a process that died leaves one to expire. Its cost: a
    dead process's worst case is held against the caps for at most this long."""
    return RESERVATION_FACTOR * send_bound_s()


def from_row(row: dict, schema_model) -> dict:
    """A recorded call's result as `ask` returned it (a joined press's, C1854): its output
    validated again by its schema, as JSON as the answer was (a strict schema takes an enum's
    value only from JSON), or its refusal's kind and words."""
    out = {"call_id": row.get("id", ""), "cost_usd": float(row.get("cost_usd") or 0.0)}
    if row.get("verdict") == "ok":
        return dict(out, ok=True, output=schema_model.model_validate_json(
            json.dumps(row.get("output") or {})))
    return dict(out, ok=False, error=row.get("verdict") or "unknown",
                detail=row.get("detail") or "")


def _joined(row: dict, kept: dict, schema_model, why: str, scope: str) -> dict:
    """A press that joined the call *kept* (C1854): its own row in the record of AI calls,
    attributed to its actor (this press's *row*, without a request: none was sent), verdict
    ``joined``, cost 0, ``joined`` the call's id and *why*, its access *scope*; and the call's
    result (`from_row`), ``recorded`` whether this row was kept."""
    own = {k: v for k, v in row.items() if k != "request"}
    out = calls.record(dict(own, verdict=calls.JOINED, cost_usd=0.0, joined=kept["id"],
                            scope=scope, detail=f"joined call {kept['id']}: {why}"))
    return dict(from_row(kept, schema_model), recorded=out.get("recorded", False))


def _capped_send(feature, row, body, model, max_tokens, schema_model, key, *, send, today,
                 refuse, tokens=None) -> dict:
    """The part of `ask` that spends: the caps judged by the worst case (*tokens*, the
    prompt's count or estimate, as cache writes, and all of `max_tokens`), reserved against
    them atomically across threads and processes (C2039, `reservations`), the send, and the
    answer checked and recorded (the module's docstring, items 6 on); the reservation settled
    once the row is recorded, whatever the outcome."""
    from modules.ai import reservations

    cap = caps(feature)
    # No day cap (an admin's choice) is said in every cap refusal, so nobody reads one as the
    # day cap's.
    uncapped = "" if cap["per_day"] is not None else f"; {NO_DAY_CAP_WORDS}"
    worst = worst_case_usd(model, body, tokens)
    if worst > cap["per_call"]:
        return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "
                      f"{feature} task's per-call cap ${cap['per_call']:.4f}{uncapped}",
                      worst_usd=worst)
    # The cap's day: its midnight the stated boundary's (calls.today; UTC by default), from a
    # clock asked for UTC by name (never a local time read by default).
    day = today or calls.today()
    trig = row["trigger"]
    is_background = trig["kind"] == triggers.BACKGROUND

    def judge(held):
        """Inside the reservations' lock: the spend read, then every cap against the spend,
        what is in flight and this call (None allows it)."""
        spent = calls.spent_usd(day)
        if spent["state"] == "unreadable":
            return {"kind": "over_cap", "why": "the record of AI calls cannot be read, so "
                    f"today's spend is unknown ({spent['error']}){uncapped}; nothing was sent"}
        flying = reservations.in_flight(held)
        if cap["per_day"] is not None and spent["usd"] + flying["usd"] + worst > cap["per_day"]:
            return {"kind": "over_cap", "worst_usd": worst, "why": (
                f"today's spend ${spent['usd']:.4f} plus ${flying['usd']:.4f} reserved by "
                f"{flying['calls']} call(s) in flight plus this call's worst case "
                f"${worst:.4f} is over the day cap ${cap['per_day']:.4f}")}
        if is_background:
            over = background.over_cap(trig, worst, day, reserved=reservations.in_flight(
                held, feature=trig["feature"], network=trig["network"]))
            if over:
                return {"kind": over["kind"], "why": over["why"], "cap_kind": over["cap"],
                        "worst_usd": worst}
        return None

    ttl = reservation_ttl_s()
    # A background call's reservation names its background feature and network (what its own
    # caps count, `reservations.in_flight`); a person's or an evaluation's, its task.
    held = reservations.reserve(row["id"], worst, judge=judge, ttl_s=ttl,
                                feature=trig["feature"] if is_background else feature,
                                network=trig["network"] if is_background else "",
                                background=is_background, day=day)
    if not held["ok"]:
        said = dict(held["refusal"])
        return refuse(said.pop("kind"), said.pop("why"), **said)
    recorded = False
    try:
        sent_at = provider_limit.clock()
        try:
            reply = (send or anthropic_adapter.send)(body, key)
        except anthropic_adapter.WorkspaceLimit as exc:
            # The workspace's usage limit (C2084): held, so every later call is refused here
            # without asking the provider, and said in the words every screen uses.
            hold = provider_limit.record(exc, call_id=row["id"], feature=feature)
            out = refuse(exc.kind, provider_limit.said(hold)["words"], attempts=exc.attempts,
                         ratelimit=exc.headers, **_limit_fields(hold))
        except anthropic_adapter.AdapterError as exc:
            out = refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)
        else:
            out = _received(row, reply, model, max_tokens, schema_model)
            # The provider answered, so its workspace limit (if one was held from before this
            # call was sent) no longer holds (C2084).
            provider_limit.clear(sent_at, call_id=row["id"])
        recorded = bool(out.get("recorded"))
        return out
    except BaseException as exc:
        # Not one of the adapter's kinds, nor an answer the gateway reads: whether the provider
        # billed it is unknown, so its worst case is what the record counts.
        got = calls.record(dict(row, verdict="exception", cost_usd=worst, worst_usd=worst,
                                detail=f"the call raised {type(exc).__name__} after it was "
                                       "reserved; whether the provider billed it is unknown, "
                                       f"so its worst case ${worst:.4f} is counted"))
        recorded = bool(got.get("recorded"))
        raise
    finally:
        # Settled once its row is in the record: until then the reservation is what counts
        # it. A row that could not be recorded leaves the reservation to its expiry.
        if recorded:
            reservations.settle(row["id"], ttl)


def _received(row, reply, model, max_tokens, schema_model) -> dict:
    """The provider's answer checked and recorded (`_capped_send`'s, once sent)."""
    from modules import redact

    usage = reply.body.get("usage") or {}
    tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                   "cache_read_input_tokens",
                                                   "cache_creation_input_tokens")}
    cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],
                             cache_write_tokens=tokens["cache_creation_input_tokens"],
                             cache_read_tokens=tokens["cache_read_input_tokens"])
    charged = profiles.prices_for(model, tokens["input_tokens"]
                                  + tokens["cache_creation_input_tokens"]
                                  + tokens["cache_read_input_tokens"])
    text = _text_of(reply.body)
    sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,
                latency_s=round(reply.latency_s, 3),
                attempts=reply.attempts, ratelimit=reply.headers,
                stop_reason=reply.body.get("stop_reason", ""),
                response=redact.redact_egress(text))
    stop = reply.body.get("stop_reason")
    if stop == "refusal":
        details = reply.body.get("stop_details") or {}
        return _answered(sent, "refusal", "the model declined "
                         f"(category {details.get('category') or 'none given'})")
    if stop == "max_tokens":
        return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")
    try:
        output = schema_model.model_validate_json(text)
    except ValidationError as exc:
        # A ValidationError Pydantic raises always holds an error, each with its loc and msg.
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "the answer"
        return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "
                         f"{first['msg']}")
    out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))
    return {"ok": True, "output": output, "call_id": row["id"], "cost_usd": cost,
            "recorded": out.get("recorded", False)}


def _answered(row, kind, detail):
    out = calls.record(dict(row, verdict=kind, detail=detail))
    return {"ok": False, "error": kind, "detail": detail, "call_id": row["id"],
            "cost_usd": row["cost_usd"], "recorded": out.get("recorded", False)}
