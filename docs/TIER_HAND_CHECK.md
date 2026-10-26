# The irreversible tier's hand checks

The tier's proof for Allow during the Phase 8 sprint (the operator's ruling of 2026-10-25,
PHASE8_PLAN 15.12, docs/TESTING.md "The deploy bar"; it expires Sat 31 Oct, and Stage 10
restores the run bar). Each check is a dated section. Each section records:
- every mutant of each function, applied by hand;
- the test that killed each mutant;
- the canary's outcome.

## 2026-10-25: #64's 15 functions, at cfa0822b

**Why by hand.** Tier run #64 measured nothing (C1696), and its continuation, #66, measured
nothing either (C1697): a family of tests fails in mutmut's copy. The other 13 tier functions
were proved by run #65 (tier-63b, on 0163f124): 523 mutants run, 523 killed.

**The method.** It was applied to each function in a clean checkout of cfa0822b, one function
at a time. A second checkout held the other module group, so a module mutated in one checkout
never stood beside a judgement in the other.
1. **The baseline:** the aimed tests pass on the file as committed. Otherwise nothing is judged.
2. **The canary:** the function's body is replaced by a `raise`, and the tests must kill it.
   A canary that survives voids the function's result: it means the tests do not reach the
   function.
3. **Every mutant** mutmut 3.8.0 generates from the committed file (`write_all_mutants_to_file`,
   the same generator the workflow runs) is put in the function's place, one at a time. The
   tests are then run with `-x` in CI's interpreter (Python 3.12.3), confined to loopback by
   `scripts/nmas-test`. A mutant is killed when the run fails, and the first failing test is
   named. A run past 600 s counts as killed by its timeout; none did.
4. **The file is restored** from its copy and compared byte for byte. The checkout is clean by
   `git status` at the end.

This counts more mutants than a workflow run. The workflow never mutates a logging call's
arguments; this check mutates everything mutmut generates.

**The aimed tests.**
- The 14 functions in `modules/ai/`: tests/test_ai_gateway_ask.py, tests/test_ai_gateway.py,
  tests/test_ai_gateway_parts.py, tests/test_ai_profiles.py, tests/test_ai_card.py and
  tests/test_ai_nl_cases.py.
- `redact.redact_positional`: tests/test_sealed_values_masked.py,
  tests/test_provider_redaction.py, tests/test_unmodeled_secrets.py,
  tests/test_reveal_and_log_redaction.py, tests/test_url_userinfo_masked.py and
  tests/test_redact_egress.py.

**The harness shown able to fail, before the check** (the same checkouts and the same code):

| control | function | judged by | result |
|---|---|---|---|
| survivors reported | `gateway.prompt_tokens` | only tests/test_ai_profiles.py | 2 of 4 survived, named |
| survivors reported | `profiles.table` | only tests/test_ai_gateway.py | 24 of 57 survived, named |
| a void reported | `profiles.prices_age_days` | only tests/test_redact_egress.py | the canary survived, so the function's result was void |

The harness and its renderer are scratch tooling, not committed. C1697's fix restores the
workflow as the proof after the sprint.

**The result.**

| function | mutants | killed | survived | canary | baseline | file restored |
|---|---|---|---|---|---|---|
| `modules.ai.gateway.caps` | 11 | 11 | 0 | killed | passed | identical |
| `modules.ai.gateway.prompt_tokens` | 4 | 4 | 0 | killed | passed | identical |
| `modules.ai.gateway.worst_case_usd` | 13 | 13 | 0 | killed | passed | identical |
| `modules.ai.gateway.build_request` | 66 | 66 | 0 | killed | passed | identical |
| `modules.ai.gateway.ask` | 485 | 485 | 0 | killed | passed | identical |
| `modules.ai.profiles.profile` | 4 | 4 | 0 | killed | passed | identical |
| `modules.ai.profiles.task` | 4 | 4 | 0 | killed | passed | identical |
| `modules.ai.profiles.prices_for` | 33 | 33 | 0 | killed | passed | identical |
| `modules.ai.profiles.cost_usd` | 26 | 26 | 0 | killed | passed | identical |
| `modules.ai.profiles.cap_per_call` | 17 | 17 | 0 | killed | passed | identical |
| `modules.ai.profiles.cases_off_pin` | 51 | 51 | 0 | killed | passed | identical |
| `modules.ai.profiles.prices_age_days` | 7 | 7 | 0 | killed | passed | identical |
| `modules.ai.profiles.table` | 57 | 57 | 0 | killed | passed | identical |
| `modules.ai.connection.check` | 60 | 60 | 0 | killed | passed | identical |
| `modules.redact.redact_positional` | 20 | 20 | 0 | killed | passed | identical |
| **all 15** | **858** | **858** | **0** | | | |

### `modules.ai.gateway.caps`

- Baseline: the tests passed on the committed file (3.6 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 11, killed 11, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- per_day = float(get_setting("ai_cap_usd_per_day"))`<br>`+ per_day = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 2 | `- per_day = float(get_setting("ai_cap_usd_per_day"))`<br>`+ per_day = float(None)` | killed | `tests/test_ai_gateway.py::test_the_day_cap_counts_what_today_spent` |
| 3 | `- per_day = float(get_setting("ai_cap_usd_per_day"))`<br>`+ per_day = float(get_setting(None))` | killed | `tests/test_ai_gateway.py::test_the_day_cap_counts_what_today_spent` |
| 4 | `- per_day = float(get_setting("ai_cap_usd_per_day"))`<br>`+ per_day = float(get_setting("XXai_cap_usd_per_dayXX"))` | killed | `tests/test_ai_gateway.py::test_the_day_cap_counts_what_today_spent` |
| 5 | `- per_day = float(get_setting("ai_cap_usd_per_day"))`<br>`+ per_day = float(get_setting("AI_CAP_USD_PER_DAY"))` | killed | `tests/test_ai_gateway.py::test_the_day_cap_counts_what_today_spent` |
| 6 | `- per_day = DEFAULT_CAP_PER_DAY`<br>`+ per_day = None` | killed | `tests/test_ai_gateway_parts.py::test_the_day_cap_is_the_stored_number_else_its_declared_default[stored3-1.5]` |
| 7 | `- return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}`<br>`+ return {"XXper_callXX": profiles.cap_per_call(feature), "per_day": per_day}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 8 | `- return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}`<br>`+ return {"PER_CALL": profiles.cap_per_call(feature), "per_day": per_day}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 9 | `- return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}`<br>`+ return {"per_call": profiles.cap_per_call(None), "per_day": per_day}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 10 | `- return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}`<br>`+ return {"per_call": profiles.cap_per_call(feature), "XXper_dayXX": per_day}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 11 | `- return {"per_call": profiles.cap_per_call(feature), "per_day": per_day}`<br>`+ return {"per_call": profiles.cap_per_call(feature), "PER_DAY": per_day}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |

### `modules.ai.gateway.prompt_tokens`

- Baseline: the tests passed on the committed file (3.5 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier`.
- Mutants: 4, killed 4, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1`<br>`+ return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) - 1` | killed | `tests/test_ai_gateway.py::test_the_worst_case_assumes_no_cache_hit` |
| 2 | `- return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1`<br>`+ return int(None) + 1` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 3 | `- return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1`<br>`+ return int(len(json.dumps(body, ensure_ascii=False)) * CHARS_PER_TOKEN) + 1` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 4 | `- return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 1`<br>`+ return int(len(json.dumps(body, ensure_ascii=False)) / CHARS_PER_TOKEN) + 2` | killed | `tests/test_ai_gateway.py::test_the_worst_case_assumes_no_cache_hit` |

### `modules.ai.gateway.worst_case_usd`

- Baseline: the tests passed on the committed file (3.5 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 13, killed 13, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(None, 0, int(body["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 2 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, None, int(body["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 3 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, 0, None,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 4 | `- cache_write_tokens=prompt_tokens(body))`<br>`+ cache_write_tokens=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 5 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(0, int(body["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 6 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, int(body["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 7 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`- cache_write_tokens=prompt_tokens(body))`<br>`+ return profiles.cost_usd(model, 0, cache_write_tokens=prompt_tokens(body))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 8 | `- cache_write_tokens=prompt_tokens(body))`<br>`+ )` | killed | `tests/test_ai_gateway.py::test_the_worst_case_assumes_no_cache_hit` |
| 9 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, 1, int(body["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 10 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, 0, int(None),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 11 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, 0, int(body["XXmax_tokensXX"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 12 | `- return profiles.cost_usd(model, 0, int(body["max_tokens"]),`<br>`+ return profiles.cost_usd(model, 0, int(body["MAX_TOKENS"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 13 | `- cache_write_tokens=prompt_tokens(body))`<br>`+ cache_write_tokens=prompt_tokens(None))` | killed | `tests/test_ai_gateway.py::test_the_worst_case_assumes_no_cache_hit` |

### `modules.ai.gateway.build_request`

- Baseline: the tests passed on the committed file (3.9 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept`.
- Mutants: 66, killed 66, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = None` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 2 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"XXtypeXX": "text", "text": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 3 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"TYPE": "text", "text": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 4 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "XXtextXX", "text": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 5 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "TEXT", "text": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 6 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "text", "XXtextXX": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 7 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "text", "TEXT": prompt["text"]}]` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 8 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "text", "text": prompt["XXtextXX"]}]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 9 | `- system = [{"type": "text", "text": prompt["text"]}]`<br>`+ system = [{"type": "text", "text": prompt["TEXT"]}]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 10 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append(None)` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 11 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"XXtypeXX": "text", "text": _delimited("context", context)})` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 12 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"TYPE": "text", "text": _delimited("context", context)})` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 13 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "XXtextXX", "text": _delimited("context", context)})` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 14 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "TEXT", "text": _delimited("context", context)})` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 15 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "XXtextXX": _delimited("context", context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 16 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "TEXT": _delimited("context", context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 17 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited(None, context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 18 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited("context", None)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 19 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited(context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 20 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited("context", )})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 21 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited("XXcontextXX", context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 22 | `- system.append({"type": "text", "text": _delimited("context", context)})`<br>`+ system.append({"type": "text", "text": _delimited("CONTEXT", context)})` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 23 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["cache_control"] = None` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 24 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[+1]["cache_control"] = {"type": "ephemeral"}` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 25 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-2]["cache_control"] = {"type": "ephemeral"}` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 26 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["XXcache_controlXX"] = {"type": "ephemeral"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 27 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["CACHE_CONTROL"] = {"type": "ephemeral"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 28 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["cache_control"] = {"XXtypeXX": "ephemeral"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 29 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["cache_control"] = {"TYPE": "ephemeral"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 30 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["cache_control"] = {"type": "XXephemeralXX"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 31 | `- system[-1]["cache_control"] = {"type": "ephemeral"}`<br>`+ system[-1]["cache_control"] = {"type": "EPHEMERAL"}` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 32 | `- "model": model,`<br>`+ "XXmodelXX": model,` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 33 | `- "model": model,`<br>`+ "MODEL": model,` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 34 | `- "max_tokens": int(max_tokens),`<br>`+ "XXmax_tokensXX": int(max_tokens),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 35 | `- "max_tokens": int(max_tokens),`<br>`+ "MAX_TOKENS": int(max_tokens),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 36 | `- "max_tokens": int(max_tokens),`<br>`+ "max_tokens": int(None),` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 37 | `- "system": system,`<br>`+ "XXsystemXX": system,` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 38 | `- "system": system,`<br>`+ "SYSTEM": system,` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 39 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "XXmessagesXX": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 40 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "MESSAGES": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 41 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"XXroleXX": "user", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 42 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"ROLE": "user", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 43 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "XXuserXX", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 44 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "USER", "content": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_parts.py::test_the_request_body_is_exactly_what_is_sent` |
| 45 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "XXcontentXX": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 46 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "CONTENT": _delimited("data", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 47 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("data", parts) and "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 48 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited(None, parts) or "(no data)"}],` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 49 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("data", None) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 50 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited(parts) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 51 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("data", ) or "(no data)"}],` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 52 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("XXdataXX", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 53 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("DATA", parts) or "(no data)"}],` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 54 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("data", parts) or "XX(no data)XX"}],` | killed | `tests/test_ai_gateway_parts.py::test_a_call_with_no_data_says_so_and_no_context_marks_the_prompt` |
| 55 | `- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`+ "messages": [{"role": "user", "content": _delimited("data", parts) or "(NO DATA)"}],` | killed | `tests/test_ai_gateway_parts.py::test_a_call_with_no_data_says_so_and_no_context_marks_the_prompt` |
| 56 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "XXoutput_configXX": {"format": {"type": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 57 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "OUTPUT_CONFIG": {"format": {"type": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 58 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"XXformatXX": {"type": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 59 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"FORMAT": {"type": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 60 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"format": {"XXtypeXX": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 61 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"format": {"TYPE": "json_schema",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 62 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"format": {"type": "XXjson_schemaXX",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 63 | `- "output_config": {"format": {"type": "json_schema",`<br>`+ "output_config": {"format": {"type": "JSON_SCHEMA",` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 64 | `- "schema": schemas.schema_for(schema_model)}},`<br>`+ "XXschemaXX": schemas.schema_for(schema_model)}},` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 65 | `- "schema": schemas.schema_for(schema_model)}},`<br>`+ "SCHEMA": schemas.schema_for(schema_model)}},` | killed | `tests/test_ai_gateway.py::test_the_data_rides_delimited_and_the_prompt_is_the_system_text` |
| 66 | `- "schema": schemas.schema_for(schema_model)}},`<br>`+ "schema": schemas.schema_for(None)}},` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |

### `modules.ai.gateway.ask`

- Baseline: the tests passed on the committed file (3.5 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged`.
- Mutants: 485, killed 485, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- call_id = calls.new_id()`<br>`+ call_id = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 2 | `- pin = profiles.TASKS.get(feature) or {}`<br>`+ pin = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 3 | `- pin = profiles.TASKS.get(feature) or {}`<br>`+ pin = profiles.TASKS.get(feature) and {}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 4 | `- pin = profiles.TASKS.get(feature) or {}`<br>`+ pin = profiles.TASKS.get(None) or {}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 5 | `- model = pin.get("model", "")`<br>`+ model = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 6 | `- model = pin.get("model", "")`<br>`+ model = pin.get(None, "")` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 7 | `- model = pin.get("model", "")`<br>`+ model = pin.get("model", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 8 | `- model = pin.get("model", "")`<br>`+ model = pin.get("")` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 9 | `- model = pin.get("model", "")`<br>`+ model = pin.get("model", )` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 10 | `- model = pin.get("model", "")`<br>`+ model = pin.get("XXmodelXX", "")` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 11 | `- model = pin.get("model", "")`<br>`+ model = pin.get("MODEL", "")` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 12 | `- model = pin.get("model", "")`<br>`+ model = pin.get("model", "XXXX")` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 13 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ row = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 14 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"XXidXX": call_id, "feature": feature, "actor": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 15 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"ID": call_id, "feature": feature, "actor": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 16 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "XXfeatureXX": feature, "actor": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 17 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "FEATURE": feature, "actor": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 18 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "feature": feature, "XXactorXX": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 19 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "feature": feature, "ACTOR": actor, "model": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 20 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "feature": feature, "actor": actor, "XXmodelXX": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 21 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`+ row = {"id": call_id, "feature": feature, "actor": actor, "MODEL": model,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 22 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "XXpromptXX": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 23 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "PROMPT": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 24 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[1]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 25 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[2]}", "schema": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 26 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "XXschemaXX": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 27 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "SCHEMA": "", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 28 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "XXXX", "detail": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 29 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "XXdetailXX": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 30 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "DETAIL": "", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 31 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "XXXX", "cost_usd": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 32 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "XXcost_usdXX": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 33 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "COST_USD": 0.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 34 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0}`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 1.0}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 35 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 36 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(None)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 37 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(None, verdict=kind, detail=detail, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 38 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(row, verdict=None, detail=detail, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 39 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(row, verdict=kind, detail=None, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 40 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(verdict=kind, detail=detail, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 41 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(row, detail=detail, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 42 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(row, verdict=kind, **extra))` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 43 | `- out = calls.record(dict(row, verdict=kind, detail=detail, **extra))`<br>`+ out = calls.record(dict(row, verdict=kind, detail=detail, ))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 44 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info(None, feature, kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 45 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", None, kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 46 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", feature, None, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 47 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", feature, kind, None)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 48 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info(feature, kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 49 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 50 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", feature, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 51 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("ai: %s refused for %s: %s", feature, kind, )` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 52 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("XXai: %s refused for %s: %sXX", feature, kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 53 | `- log.info("ai: %s refused for %s: %s", feature, kind, detail)`<br>`+ log.info("AI: %S REFUSED FOR %S: %S", feature, kind, detail)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 54 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"XXokXX": False, "error": kind, "detail": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 55 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"OK": False, "error": kind, "detail": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 56 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": True, "error": kind, "detail": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 57 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "XXerrorXX": kind, "detail": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 58 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "ERROR": kind, "detail": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 59 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "error": kind, "XXdetailXX": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 60 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "error": kind, "DETAIL": detail, "call_id": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 61 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "error": kind, "detail": detail, "XXcall_idXX": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 62 | `- return {"ok": False, "error": kind, "detail": detail, "call_id": call_id,`<br>`+ return {"ok": False, "error": kind, "detail": detail, "CALL_ID": call_id,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 63 | `- "recorded": out.get("recorded", False)}`<br>`+ "XXrecordedXX": out.get("recorded", False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 64 | `- "recorded": out.get("recorded", False)}`<br>`+ "RECORDED": out.get("recorded", False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 65 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get(None, False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 66 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", None)}` | killed | `tests/test_ai_gateway_ask.py::test_a_record_that_says_nothing_is_not_recorded` |
| 67 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get(False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 68 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", )}` | killed | `tests/test_ai_gateway_ask.py::test_a_record_that_says_nothing_is_not_recorded` |
| 69 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("XXrecordedXX", False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 70 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("RECORDED", False)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 71 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", True)}` | killed | `tests/test_ai_gateway_ask.py::test_a_record_that_says_nothing_is_not_recorded` |
| 72 | `- hosted = hosted_allowed()`<br>`+ hosted = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 73 | `- if not hosted["allowed"]:`<br>`+ if hosted["allowed"]:` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 74 | `- if not hosted["allowed"]:`<br>`+ if not hosted["XXallowedXX"]:` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 75 | `- if not hosted["allowed"]:`<br>`+ if not hosted["ALLOWED"]:` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 76 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse(None, hosted["why"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 77 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("ai_off", None)` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 78 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse(hosted["why"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 79 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("ai_off", )` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 80 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("XXai_offXX", hosted["why"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 81 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("AI_OFF", hosted["why"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 82 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("ai_off", hosted["XXwhyXX"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 83 | `- return refuse("ai_off", hosted["why"])`<br>`+ return refuse("ai_off", hosted["WHY"])` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 84 | `- key = _api_key()`<br>`+ key = None` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 85 | `- if not key:`<br>`+ if key:` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 86 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse(None, "no Anthropic API key is set (Settings: a person types it)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 87 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no_key", None)` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 88 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no Anthropic API key is set (Settings: a person types it)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 89 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no_key", )` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 90 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("XXno_keyXX", "no Anthropic API key is set (Settings: a person types it)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 91 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("NO_KEY", "no Anthropic API key is set (Settings: a person types it)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 92 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no_key", "XXno Anthropic API key is set (Settings: a person types it)XX")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 93 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no_key", "no anthropic api key is set (settings: a person types it)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 94 | `- return refuse("no_key", "no Anthropic API key is set (Settings: a person types it)")`<br>`+ return refuse("no_key", "NO ANTHROPIC API KEY IS SET (SETTINGS: A PERSON TYPES IT)")` | killed | `tests/test_ai_gateway_ask.py::test_no_key_is_refused_whole` |
| 95 | `- if not pin:`<br>`+ if pin:` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 96 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`+ return refuse(None, f"{feature!r} is not a task profiles.TASKS pins; known: "` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 97 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`- f"{', '.join(sorted(profiles.TASKS))}")`<br>`+ return refuse("unknown_task", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 98 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`+ return refuse(f"{feature!r} is not a task profiles.TASKS pins; known: "` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 99 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`- f"{', '.join(sorted(profiles.TASKS))}")`<br>`+ return refuse("unknown_task", )` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 100 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`+ return refuse("XXunknown_taskXX", f"{feature!r} is not a task profiles.TASKS pins; known: "` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 101 | `- return refuse("unknown_task", f"{feature!r} is not a task profiles.TASKS pins; known: "`<br>`+ return refuse("UNKNOWN_TASK", f"{feature!r} is not a task profiles.TASKS pins; known: "` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 102 | `- f"{', '.join(sorted(profiles.TASKS))}")`<br>`+ f"{', '.join(None)}")` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 103 | `- f"{', '.join(sorted(profiles.TASKS))}")`<br>`+ f"{'XX, XX'.join(sorted(profiles.TASKS))}")` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 104 | `- f"{', '.join(sorted(profiles.TASKS))}")`<br>`+ f"{', '.join(sorted(None))}")` | killed | `tests/test_ai_gateway_ask.py::test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model` |
| 105 | `- max_tokens = int(pin["max_tokens"])`<br>`+ max_tokens = None` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 106 | `- max_tokens = int(pin["max_tokens"])`<br>`+ max_tokens = int(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 107 | `- max_tokens = int(pin["max_tokens"])`<br>`+ max_tokens = int(pin["XXmax_tokensXX"])` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 108 | `- max_tokens = int(pin["max_tokens"])`<br>`+ max_tokens = int(pin["MAX_TOKENS"])` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 109 | `- profile = profiles.profile(model)`<br>`+ profile = None` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 110 | `- profile = profiles.profile(model)`<br>`+ profile = profiles.profile(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 111 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse(None, str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 112 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse("unknown_model", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 113 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse(str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 114 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse("unknown_model", )` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 115 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse("XXunknown_modelXX", str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 116 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse("UNKNOWN_MODEL", str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 117 | `- return refuse("unknown_model", str(exc))`<br>`+ return refuse("unknown_model", str(None))` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 118 | `- if profile["provider"] != profiles.ANTHROPIC:`<br>`+ if profile["XXproviderXX"] != profiles.ANTHROPIC:` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 119 | `- if profile["provider"] != profiles.ANTHROPIC:`<br>`+ if profile["PROVIDER"] != profiles.ANTHROPIC:` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 120 | `- if profile["provider"] != profiles.ANTHROPIC:`<br>`+ if profile["provider"] == profiles.ANTHROPIC:` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 121 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse(None, f"{model} is not served by the Anthropic adapter")` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 122 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse("unknown_model", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 123 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse(f"{model} is not served by the Anthropic adapter")` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 124 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse("unknown_model", )` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 125 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse("XXunknown_modelXX", f"{model} is not served by the Anthropic adapter")` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 126 | `- return refuse("unknown_model", f"{model} is not served by the Anthropic adapter")`<br>`+ return refuse("UNKNOWN_MODEL", f"{model} is not served by the Anthropic adapter")` | killed | `tests/test_ai_gateway_ask.py::test_a_model_another_provider_serves_is_refused` |
| 127 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 128 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(None, "__ai_schema__", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 129 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(schema_model, None, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 130 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr("__ai_schema__", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 131 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(schema_model, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 132 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(schema_model, "__ai_schema__", )` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 133 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(schema_model, "XX__ai_schema__XX", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 134 | `- ident = getattr(schema_model, "__ai_schema__", None)`<br>`+ ident = getattr(schema_model, "__AI_SCHEMA__", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 135 | `- if ident is None or schemas.REGISTRY.get(ident) is not schema_model:`<br>`+ if ident is None and schemas.REGISTRY.get(ident) is not schema_model:` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[claims-an-identity]` |
| 136 | `- if ident is None or schemas.REGISTRY.get(ident) is not schema_model:`<br>`+ if ident is not None or schemas.REGISTRY.get(ident) is not schema_model:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 137 | `- if ident is None or schemas.REGISTRY.get(ident) is not schema_model:`<br>`+ if ident is None or schemas.REGISTRY.get(None) is not schema_model:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 138 | `- if ident is None or schemas.REGISTRY.get(ident) is not schema_model:`<br>`+ if ident is None or schemas.REGISTRY.get(ident) is schema_model:` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[claims-an-identity]` |
| 139 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse(None, f"{getattr(schema_model, '__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 140 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`- "registered AI schema")`<br>`+ return refuse("schema", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 141 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse(f"{getattr(schema_model, '__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 142 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`- "registered AI schema")`<br>`+ return refuse("schema", )` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 143 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("XXschemaXX", f"{getattr(schema_model, '__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 144 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("SCHEMA", f"{getattr(schema_model, '__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 145 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(None, '__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 146 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, None, schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 147 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, '__name__', None)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[not-a-class]` |
| 148 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr('__name__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 149 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 150 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, '__name__', )} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[not-a-class]` |
| 151 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, 'XX__name__XX', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 152 | `- return refuse("schema", f"{getattr(schema_model, '__name__', schema_model)} is not a "`<br>`+ return refuse("schema", f"{getattr(schema_model, '__NAME__', schema_model)} is not a "` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 153 | `- "registered AI schema")`<br>`+ "XXregistered AI schemaXX")` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 154 | `- "registered AI schema")`<br>`+ "registered ai schema")` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 155 | `- "registered AI schema")`<br>`+ "REGISTERED AI SCHEMA")` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 156 | `- row["schema"] = f"{ident[0]}.v{ident[1]}"`<br>`+ row["schema"] = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 157 | `- row["schema"] = f"{ident[0]}.v{ident[1]}"`<br>`+ row["XXschemaXX"] = f"{ident[0]}.v{ident[1]}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 158 | `- row["schema"] = f"{ident[0]}.v{ident[1]}"`<br>`+ row["SCHEMA"] = f"{ident[0]}.v{ident[1]}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 159 | `- row["schema"] = f"{ident[0]}.v{ident[1]}"`<br>`+ row["schema"] = f"{ident[1]}.v{ident[1]}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 160 | `- row["schema"] = f"{ident[0]}.v{ident[1]}"`<br>`+ row["schema"] = f"{ident[0]}.v{ident[2]}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 161 | `- prompt_file = prompts.load(*prompt)`<br>`+ prompt_file = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 162 | `- return refuse("prompt", str(exc))`<br>`+ return refuse(None, str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 163 | `- return refuse("prompt", str(exc))`<br>`+ return refuse("prompt", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 164 | `- return refuse("prompt", str(exc))`<br>`+ return refuse(str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 165 | `- return refuse("prompt", str(exc))`<br>`+ return refuse("prompt", )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 166 | `- return refuse("prompt", str(exc))`<br>`+ return refuse("XXpromptXX", str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 167 | `- return refuse("prompt", str(exc))`<br>`+ return refuse("PROMPT", str(exc))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 168 | `- return refuse("prompt", str(exc))`<br>`+ return refuse("prompt", str(None))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_that_does_not_load_is_refused_in_its_words` |
| 169 | `- row["prompt_sha256"] = prompt_file["sha256"]`<br>`+ row["prompt_sha256"] = None` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 170 | `- row["prompt_sha256"] = prompt_file["sha256"]`<br>`+ row["XXprompt_sha256XX"] = prompt_file["sha256"]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 171 | `- row["prompt_sha256"] = prompt_file["sha256"]`<br>`+ row["PROMPT_SHA256"] = prompt_file["sha256"]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 172 | `- row["prompt_sha256"] = prompt_file["sha256"]`<br>`+ row["prompt_sha256"] = prompt_file["XXsha256XX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 173 | `- row["prompt_sha256"] = prompt_file["sha256"]`<br>`+ row["prompt_sha256"] = prompt_file["SHA256"]` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 174 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`- max_tokens, context=context))`<br>`+ body = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 175 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`- max_tokens, context=context))`<br>`+ body = redact.egress_payload(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 176 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(None, schema_model, parts, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 177 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(prompt_file, None, parts, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 178 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, None, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 179 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, parts, None,` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 180 | `- max_tokens, context=context))`<br>`+ None, context=context))` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 181 | `- max_tokens, context=context))`<br>`+ max_tokens, context=None))` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 182 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(schema_model, parts, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 183 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(prompt_file, parts, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 184 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, model,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 185 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, model,`<br>`- max_tokens, context=context))`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, parts, max_tokens, context=context))` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 186 | `- max_tokens, context=context))`<br>`+ context=context))` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 187 | `- max_tokens, context=context))`<br>`+ max_tokens, ))` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 188 | `- leaked = redact.contains_known_secret(body)`<br>`+ leaked = None` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 189 | `- leaked = redact.contains_known_secret(body)`<br>`+ leaked = redact.contains_known_secret(None)` | killed | `tests/test_ai_gateway.py::test_a_stored_secret_left_after_masking_refuses_and_sends_nothing` |
| 190 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse(None, "a stored secret is still in the request after "` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 191 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`- f"masking ({', '.join(leaked)}); nothing was sent")`<br>`+ return refuse("unmasked_secret", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 192 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse("a stored secret is still in the request after "` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 193 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`- f"masking ({', '.join(leaked)}); nothing was sent")`<br>`+ return refuse("unmasked_secret", )` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 194 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse("XXunmasked_secretXX", "a stored secret is still in the request after "` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 195 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse("UNMASKED_SECRET", "a stored secret is still in the request after "` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 196 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse("unmasked_secret", "XXa stored secret is still in the request after XX"` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 197 | `- return refuse("unmasked_secret", "a stored secret is still in the request after "`<br>`+ return refuse("unmasked_secret", "A STORED SECRET IS STILL IN THE REQUEST AFTER "` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 198 | `- f"masking ({', '.join(leaked)}); nothing was sent")`<br>`+ f"masking ({', '.join(None)}); nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 199 | `- f"masking ({', '.join(leaked)}); nothing was sent")`<br>`+ f"masking ({'XX, XX'.join(leaked)}); nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 200 | `- row["request"] = body`<br>`+ row["request"] = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 201 | `- row["request"] = body`<br>`+ row["XXrequestXX"] = body` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 202 | `- row["request"] = body`<br>`+ row["REQUEST"] = body` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 203 | `- est = prompt_tokens(body)`<br>`+ est = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 204 | `- est = prompt_tokens(body)`<br>`+ est = prompt_tokens(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 205 | `- if est > pin["max_prompt_tokens"]:`<br>`+ if est >= pin["max_prompt_tokens"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 206 | `- if est > pin["max_prompt_tokens"]:`<br>`+ if est > pin["XXmax_prompt_tokensXX"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 207 | `- if est > pin["max_prompt_tokens"]:`<br>`+ if est > pin["MAX_PROMPT_TOKENS"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 208 | `- long_at = profile.get("long_prompt_tokens")`<br>`+ long_at = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 209 | `- long_at = profile.get("long_prompt_tokens")`<br>`+ long_at = profile.get(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 210 | `- long_at = profile.get("long_prompt_tokens")`<br>`+ long_at = profile.get("XXlong_prompt_tokensXX")` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 211 | `- long_at = profile.get("long_prompt_tokens")`<br>`+ long_at = profile.get("LONG_PROMPT_TOKENS")` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 212 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`+ return refuse(None, f"this prompt is about {est} tokens, over the task's "` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 213 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`- f"bound of {pin['max_prompt_tokens']}"`<br>`- + (f" ({model} charges every rate at its long tier over {long_at})"`<br>`- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ return refuse("prompt_too_long", None, prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 214 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "") + "; nothing was sent", prompt_tokens=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 215 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`+ return refuse(f"this prompt is about {est} tokens, over the task's "` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 216 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`- f"bound of {pin['max_prompt_tokens']}"`<br>`- + (f" ({model} charges every rate at its long tier over {long_at})"`<br>`- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ return refuse("prompt_too_long", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 217 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "") + "; nothing was sent", )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 218 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`+ return refuse("XXprompt_too_longXX", f"this prompt is about {est} tokens, over the task's "` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 219 | `- return refuse("prompt_too_long", f"this prompt is about {est} tokens, over the task's "`<br>`+ return refuse("PROMPT_TOO_LONG", f"this prompt is about {est} tokens, over the task's "` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 220 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "") - "; nothing was sent", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 221 | `- f"bound of {pin['max_prompt_tokens']}"`<br>`- + (f" ({model} charges every rate at its long tier over {long_at})"`<br>`+ f"bound of {pin['max_prompt_tokens']}" - (f" ({model} charges every rate at its long tier over {long_at})"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 222 | `- f"bound of {pin['max_prompt_tokens']}"`<br>`+ f"bound of {pin['XXmax_prompt_tokensXX']}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 223 | `- f"bound of {pin['max_prompt_tokens']}"`<br>`+ f"bound of {pin['MAX_PROMPT_TOKENS']}"` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 224 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if (long_at) and False else "") + "; nothing was sent", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 225 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if (long_at) or True else "") + "; nothing was sent", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_model_with_no_long_tier_says_none` |
| 226 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "XXXX") + "; nothing was sent", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_model_with_no_long_tier_says_none` |
| 227 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "") + "XX; nothing was sentXX", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 228 | `- if long_at else "") + "; nothing was sent", prompt_tokens=est)`<br>`+ if long_at else "") + "; NOTHING WAS SENT", prompt_tokens=est)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 229 | `- cap = caps(feature)`<br>`+ cap = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 230 | `- cap = caps(feature)`<br>`+ cap = caps(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 231 | `- worst = worst_case_usd(model, body)`<br>`+ worst = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 232 | `- worst = worst_case_usd(model, body)`<br>`+ worst = worst_case_usd(None, body)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 233 | `- worst = worst_case_usd(model, body)`<br>`+ worst = worst_case_usd(model, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 234 | `- worst = worst_case_usd(model, body)`<br>`+ worst = worst_case_usd(body)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 235 | `- worst = worst_case_usd(model, body)`<br>`+ worst = worst_case_usd(model, )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 236 | `- if worst > cap["per_call"]:`<br>`+ if worst >= cap["per_call"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 237 | `- if worst > cap["per_call"]:`<br>`+ if worst > cap["XXper_callXX"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 238 | `- if worst > cap["per_call"]:`<br>`+ if worst > cap["PER_CALL"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 239 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`+ return refuse(None, f"this call's worst case ${worst:.4f} is over the "` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 240 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ return refuse("over_cap", None, worst_usd=worst)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 241 | `- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 242 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`+ return refuse(f"this call's worst case ${worst:.4f} is over the "` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 243 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ return refuse("over_cap", worst_usd=worst)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 244 | `- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ f"{feature} task's per-call cap ${cap['per_call']:.4f}", )` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 245 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`+ return refuse("XXover_capXX", f"this call's worst case ${worst:.4f} is over the "` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 246 | `- return refuse("over_cap", f"this call's worst case ${worst:.4f} is over the "`<br>`+ return refuse("OVER_CAP", f"this call's worst case ${worst:.4f} is over the "` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 247 | `- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ f"{feature} task's per-call cap ${cap['XXper_callXX']:.4f}", worst_usd=worst)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 248 | `- f"{feature} task's per-call cap ${cap['per_call']:.4f}", worst_usd=worst)`<br>`+ f"{feature} task's per-call cap ${cap['PER_CALL']:.4f}", worst_usd=worst)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 249 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = None` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 250 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today and datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 251 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today or datetime.datetime.now(datetime.timezone.utc).strftime(None)` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 252 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today or datetime.datetime.now(None).strftime("%Y-%m-%d")` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 253 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today or datetime.datetime.now(datetime.timezone.utc).strftime("XX%Y-%m-%dXX")` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 254 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%y-%m-%d")` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 255 | `- day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")`<br>`+ day = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%M-%D")` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_given_the_utc_day_is_counted` |
| 256 | `- spent = calls.spent_usd(day)`<br>`+ spent = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 257 | `- spent = calls.spent_usd(day)`<br>`+ spent = calls.spent_usd(None)` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 258 | `- if spent["state"] == "unreadable":`<br>`+ if spent["XXstateXX"] == "unreadable":` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 259 | `- if spent["state"] == "unreadable":`<br>`+ if spent["STATE"] == "unreadable":` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 260 | `- if spent["state"] == "unreadable":`<br>`+ if spent["state"] != "unreadable":` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 261 | `- if spent["state"] == "unreadable":`<br>`+ if spent["state"] == "XXunreadableXX":` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 262 | `- if spent["state"] == "unreadable":`<br>`+ if spent["state"] == "UNREADABLE":` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 263 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse(None, "the record of AI calls cannot be read, so today's spend "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 264 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`- f"is unknown ({spent['error']}); nothing was sent")`<br>`+ return refuse("over_cap", None)` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 265 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("the record of AI calls cannot be read, so today's spend "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 266 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`- f"is unknown ({spent['error']}); nothing was sent")`<br>`+ return refuse("over_cap", )` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 267 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("XXover_capXX", "the record of AI calls cannot be read, so today's spend "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 268 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("OVER_CAP", "the record of AI calls cannot be read, so today's spend "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 269 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("over_cap", "XXthe record of AI calls cannot be read, so today's spend XX"` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 270 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("over_cap", "the record of ai calls cannot be read, so today's spend "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 271 | `- return refuse("over_cap", "the record of AI calls cannot be read, so today's spend "`<br>`+ return refuse("over_cap", "THE RECORD OF AI CALLS CANNOT BE READ, SO TODAY'S SPEND "` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 272 | `- f"is unknown ({spent['error']}); nothing was sent")`<br>`+ f"is unknown ({spent['XXerrorXX']}); nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 273 | `- f"is unknown ({spent['error']}); nothing was sent")`<br>`+ f"is unknown ({spent['ERROR']}); nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 274 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["usd"] - worst > cap["per_day"]:` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 275 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["XXusdXX"] + worst > cap["per_day"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 276 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["USD"] + worst > cap["per_day"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 277 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["usd"] + worst >= cap["per_day"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_days_spend_reaching_the_cap_exactly_is_sent` |
| 278 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["usd"] + worst > cap["XXper_dayXX"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 279 | `- if spent["usd"] + worst > cap["per_day"]:`<br>`+ if spent["usd"] + worst > cap["PER_DAY"]:` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 280 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse(None, f"today's spend ${spent['usd']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 281 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`- f"case ${worst:.4f} is over the day cap ${cap['per_day']:.4f}",`<br>`+ return refuse("over_cap", None,` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 282 | `- worst_usd=worst)`<br>`+ worst_usd=None)` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 283 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse(f"today's spend ${spent['usd']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 284 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`- f"case ${worst:.4f} is over the day cap ${cap['per_day']:.4f}",`<br>`- worst_usd=worst)`<br>`+ return refuse("over_cap", worst_usd=worst)` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 285 | `- worst_usd=worst)`<br>`+ )` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 286 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse("XXover_capXX", f"today's spend ${spent['usd']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 287 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse("OVER_CAP", f"today's spend ${spent['usd']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 288 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse("over_cap", f"today's spend ${spent['XXusdXX']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 289 | `- return refuse("over_cap", f"today's spend ${spent['usd']:.4f} plus this call's worst "`<br>`+ return refuse("over_cap", f"today's spend ${spent['USD']:.4f} plus this call's worst "` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 290 | `- f"case ${worst:.4f} is over the day cap ${cap['per_day']:.4f}",`<br>`+ f"case ${worst:.4f} is over the day cap ${cap['XXper_dayXX']:.4f}",` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 291 | `- f"case ${worst:.4f} is over the day cap ${cap['per_day']:.4f}",`<br>`+ f"case ${worst:.4f} is over the day cap ${cap['PER_DAY']:.4f}",` | killed | `tests/test_ai_gateway_ask.py::test_the_day_cap_is_refused_with_its_three_operands` |
| 292 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 293 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = (send or anthropic_adapter.send)(None, key)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 294 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = (send or anthropic_adapter.send)(body, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 295 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = (send or anthropic_adapter.send)(key)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 296 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = (send or anthropic_adapter.send)(body, )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 297 | `- reply = (send or anthropic_adapter.send)(body, key)`<br>`+ reply = (send and anthropic_adapter.send)(body, key)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 298 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(None, str(exc), attempts=exc.attempts, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 299 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, None, attempts=exc.attempts, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 300 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, str(exc), attempts=None, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 301 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 302 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(str(exc), attempts=exc.attempts, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 303 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, attempts=exc.attempts, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 304 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, str(exc), ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 305 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, str(exc), attempts=exc.attempts, )` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 306 | `- return refuse(exc.kind, str(exc), attempts=exc.attempts, ratelimit=exc.headers)`<br>`+ return refuse(exc.kind, str(None), attempts=exc.attempts, ratelimit=exc.headers)` | killed | `tests/test_ai_gateway_ask.py::test_a_provider_failure_is_refused_with_its_attempts_and_headers` |
| 307 | `- usage = reply.body.get("usage") or {}`<br>`+ usage = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 308 | `- usage = reply.body.get("usage") or {}`<br>`+ usage = reply.body.get("usage") and {}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 309 | `- usage = reply.body.get("usage") or {}`<br>`+ usage = reply.body.get(None) or {}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 310 | `- usage = reply.body.get("usage") or {}`<br>`+ usage = reply.body.get("XXusageXX") or {}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 311 | `- usage = reply.body.get("usage") or {}`<br>`+ usage = reply.body.get("USAGE") or {}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 312 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`- "cache_read_input_tokens",`<br>`- "cache_creation_input_tokens")}`<br>`+ tokens = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 313 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(None) for k in ("input_tokens", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 314 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) and 0) for k in ("input_tokens", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 315 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(None) or 0) for k in ("input_tokens", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 316 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) or 1) for k in ("input_tokens", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_with_no_usage_and_no_stop_reason_counts_nothing_and_says_none` |
| 317 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) or 0) for k in ("XXinput_tokensXX", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 318 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) or 0) for k in ("INPUT_TOKENS", "output_tokens",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 319 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "XXoutput_tokensXX",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 320 | `- tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",`<br>`+ tokens = {k: int(usage.get(k) or 0) for k in ("input_tokens", "OUTPUT_TOKENS",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 321 | `- "cache_read_input_tokens",`<br>`+ "XXcache_read_input_tokensXX",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 322 | `- "cache_read_input_tokens",`<br>`+ "CACHE_READ_INPUT_TOKENS",` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 323 | `- "cache_creation_input_tokens")}`<br>`+ "XXcache_creation_input_tokensXX")}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 324 | `- "cache_creation_input_tokens")}`<br>`+ "CACHE_CREATION_INPUT_TOKENS")}` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 325 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`- cache_write_tokens=tokens["cache_creation_input_tokens"],`<br>`- cache_read_tokens=tokens["cache_read_input_tokens"])`<br>`+ cost = None` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 326 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(None, tokens["input_tokens"], tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 327 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, None, tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 328 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["input_tokens"], None,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 329 | `- cache_write_tokens=tokens["cache_creation_input_tokens"],`<br>`+ cache_write_tokens=None,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 330 | `- cache_read_tokens=tokens["cache_read_input_tokens"])`<br>`+ cache_read_tokens=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 331 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(tokens["input_tokens"], tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 332 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 333 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`- cache_write_tokens=tokens["cache_creation_input_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["input_tokens"], cache_write_tokens=tokens["cache_creation_input_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 334 | `- cache_write_tokens=tokens["cache_creation_input_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 335 | `- cache_read_tokens=tokens["cache_read_input_tokens"])`<br>`+ )` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 336 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["XXinput_tokensXX"], tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 337 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["INPUT_TOKENS"], tokens["output_tokens"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 338 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["XXoutput_tokensXX"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 339 | `- cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["output_tokens"],`<br>`+ cost = profiles.cost_usd(model, tokens["input_tokens"], tokens["OUTPUT_TOKENS"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 340 | `- cache_write_tokens=tokens["cache_creation_input_tokens"],`<br>`+ cache_write_tokens=tokens["XXcache_creation_input_tokensXX"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 341 | `- cache_write_tokens=tokens["cache_creation_input_tokens"],`<br>`+ cache_write_tokens=tokens["CACHE_CREATION_INPUT_TOKENS"],` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 342 | `- cache_read_tokens=tokens["cache_read_input_tokens"])`<br>`+ cache_read_tokens=tokens["XXcache_read_input_tokensXX"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 343 | `- cache_read_tokens=tokens["cache_read_input_tokens"])`<br>`+ cache_read_tokens=tokens["CACHE_READ_INPUT_TOKENS"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 344 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`- + tokens["cache_creation_input_tokens"]`<br>`- + tokens["cache_read_input_tokens"])`<br>`+ charged = None` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 345 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`+ charged = profiles.prices_for(None, tokens["input_tokens"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 346 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`- + tokens["cache_creation_input_tokens"]`<br>`- + tokens["cache_read_input_tokens"])`<br>`+ charged = profiles.prices_for(model, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 347 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`+ charged = profiles.prices_for(tokens["input_tokens"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 348 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`- + tokens["cache_creation_input_tokens"]`<br>`- + tokens["cache_read_input_tokens"])`<br>`+ charged = profiles.prices_for(model, )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 349 | `- + tokens["cache_creation_input_tokens"]`<br>`- + tokens["cache_read_input_tokens"])`<br>`+ + tokens["cache_creation_input_tokens"] - tokens["cache_read_input_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 350 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`- + tokens["cache_creation_input_tokens"]`<br>`+ charged = profiles.prices_for(model, tokens["input_tokens"] - tokens["cache_creation_input_tokens"]` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 351 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`+ charged = profiles.prices_for(model, tokens["XXinput_tokensXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 352 | `- charged = profiles.prices_for(model, tokens["input_tokens"]`<br>`+ charged = profiles.prices_for(model, tokens["INPUT_TOKENS"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 353 | `- + tokens["cache_creation_input_tokens"]`<br>`+ + tokens["XXcache_creation_input_tokensXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 354 | `- + tokens["cache_creation_input_tokens"]`<br>`+ + tokens["CACHE_CREATION_INPUT_TOKENS"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 355 | `- + tokens["cache_read_input_tokens"])`<br>`+ + tokens["XXcache_read_input_tokensXX"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 356 | `- + tokens["cache_read_input_tokens"])`<br>`+ + tokens["CACHE_READ_INPUT_TOKENS"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 357 | `- text = _text_of(reply.body)`<br>`+ text = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 358 | `- text = _text_of(reply.body)`<br>`+ text = _text_of(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 359 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`- latency_s=round(reply.latency_s, 3),`<br>`- attempts=reply.attempts, ratelimit=reply.headers,`<br>`- stop_reason=reply.body.get("stop_reason", ""),`<br>`- response=redact.redact_egress(text))`<br>`+ sent = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 360 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(None, cost_usd=cost, price=charged, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 361 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(row, cost_usd=None, price=charged, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 362 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(row, cost_usd=cost, price=None, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 363 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(row, cost_usd=cost, price=charged, tokens=None,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 364 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=None,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 365 | `- attempts=reply.attempts, ratelimit=reply.headers,`<br>`+ attempts=None, ratelimit=reply.headers,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 366 | `- attempts=reply.attempts, ratelimit=reply.headers,`<br>`+ attempts=reply.attempts, ratelimit=None,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 367 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=None,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 368 | `- response=redact.redact_egress(text))`<br>`+ response=None)` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 369 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(cost_usd=cost, price=charged, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 370 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(row, price=charged, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 371 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`+ sent = dict(row, cost_usd=cost, tokens=tokens,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 372 | `- sent = dict(row, cost_usd=cost, price=charged, tokens=tokens,`<br>`- latency_s=round(reply.latency_s, 3),`<br>`+ sent = dict(row, cost_usd=cost, price=charged, latency_s=round(reply.latency_s, 3),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 373 | `- latency_s=round(reply.latency_s, 3),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 374 | `- attempts=reply.attempts, ratelimit=reply.headers,`<br>`+ ratelimit=reply.headers,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 375 | `- attempts=reply.attempts, ratelimit=reply.headers,`<br>`- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ attempts=reply.attempts, stop_reason=reply.body.get("stop_reason", ""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 376 | `- stop_reason=reply.body.get("stop_reason", ""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 377 | `- response=redact.redact_egress(text))`<br>`+ )` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 378 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=round(None, 3),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 379 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=round(reply.latency_s, None),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 380 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=round(3),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 381 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=round(reply.latency_s, ),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 382 | `- latency_s=round(reply.latency_s, 3),`<br>`+ latency_s=round(reply.latency_s, 4),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 383 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get(None, ""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 384 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get("stop_reason", None),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_with_no_usage_and_no_stop_reason_counts_nothing_and_says_none` |
| 385 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get(""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 386 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get("stop_reason", ),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_with_no_usage_and_no_stop_reason_counts_nothing_and_says_none` |
| 387 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get("XXstop_reasonXX", ""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 388 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get("STOP_REASON", ""),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 389 | `- stop_reason=reply.body.get("stop_reason", ""),`<br>`+ stop_reason=reply.body.get("stop_reason", "XXXX"),` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_with_no_usage_and_no_stop_reason_counts_nothing_and_says_none` |
| 390 | `- response=redact.redact_egress(text))`<br>`+ response=redact.redact_egress(None))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 391 | `- stop = reply.body.get("stop_reason")`<br>`+ stop = None` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 392 | `- stop = reply.body.get("stop_reason")`<br>`+ stop = reply.body.get(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 393 | `- stop = reply.body.get("stop_reason")`<br>`+ stop = reply.body.get("XXstop_reasonXX")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 394 | `- stop = reply.body.get("stop_reason")`<br>`+ stop = reply.body.get("STOP_REASON")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 395 | `- if stop == "refusal":`<br>`+ if stop != "refusal":` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 396 | `- if stop == "refusal":`<br>`+ if stop == "XXrefusalXX":` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 397 | `- if stop == "refusal":`<br>`+ if stop == "REFUSAL":` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 398 | `- details = reply.body.get("stop_details") or {}`<br>`+ details = None` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 399 | `- details = reply.body.get("stop_details") or {}`<br>`+ details = reply.body.get("stop_details") and {}` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 400 | `- details = reply.body.get("stop_details") or {}`<br>`+ details = reply.body.get(None) or {}` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 401 | `- details = reply.body.get("stop_details") or {}`<br>`+ details = reply.body.get("XXstop_detailsXX") or {}` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 402 | `- details = reply.body.get("stop_details") or {}`<br>`+ details = reply.body.get("STOP_DETAILS") or {}` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 403 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(None, "refusal", "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 404 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, None, "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 405 | `- return _answered(sent, "refusal", "the model declined "`<br>`- f"(category {details.get('category') or 'none given'})")`<br>`+ return _answered(sent, "refusal", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 406 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered("refusal", "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 407 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 408 | `- return _answered(sent, "refusal", "the model declined "`<br>`- f"(category {details.get('category') or 'none given'})")`<br>`+ return _answered(sent, "refusal", )` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 409 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, "XXrefusalXX", "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 410 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, "REFUSAL", "the model declined "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 411 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, "refusal", "XXthe model declined XX"` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 412 | `- return _answered(sent, "refusal", "the model declined "`<br>`+ return _answered(sent, "refusal", "THE MODEL DECLINED "` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 413 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get('category') and 'none given'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 414 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get(None) or 'none given'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 415 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get('XXcategoryXX') or 'none given'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 416 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get('CATEGORY') or 'none given'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 417 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get('category') or 'XXnone givenXX'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_with_no_category_says_none_given[extra0]` |
| 418 | `- f"(category {details.get('category') or 'none given'})")`<br>`+ f"(category {details.get('category') or 'NONE GIVEN'})")` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_with_no_category_says_none_given[extra0]` |
| 419 | `- if stop == "max_tokens":`<br>`+ if stop != "max_tokens":` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 420 | `- if stop == "max_tokens":`<br>`+ if stop == "XXmax_tokensXX":` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 421 | `- if stop == "max_tokens":`<br>`+ if stop == "MAX_TOKENS":` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 422 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(None, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 423 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, None, f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 424 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, "max_tokens", None)` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 425 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered("max_tokens", f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 426 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 427 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, "max_tokens", )` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 428 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, "XXmax_tokensXX", f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 429 | `- return _answered(sent, "max_tokens", f"the answer ran past max_tokens ({max_tokens})")`<br>`+ return _answered(sent, "MAX_TOKENS", f"the answer ran past max_tokens ({max_tokens})")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_past_max_tokens_names_the_bound` |
| 430 | `- output = schema_model.model_validate_json(text)`<br>`+ output = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 431 | `- output = schema_model.model_validate_json(text)`<br>`+ output = schema_model.model_validate_json(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 432 | `- first = exc.errors()[0]`<br>`+ first = None` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 433 | `- first = exc.errors()[0]`<br>`+ first = exc.errors()[1]` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 434 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = None` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 435 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(p) for p in first["loc"]) and "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 436 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(None) or "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 437 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = "XX.XX".join(str(p) for p in first["loc"]) or "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 438 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(None) for p in first["loc"]) or "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 439 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(p) for p in first["XXlocXX"]) or "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 440 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(p) for p in first["LOC"]) or "the answer"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 441 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(p) for p in first["loc"]) or "XXthe answerXX"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_that_is_not_json_is_the_answer_at_fault` |
| 442 | `- where = ".".join(str(p) for p in first["loc"]) or "the answer"`<br>`+ where = ".".join(str(p) for p in first["loc"]) or "THE ANSWER"` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_that_is_not_json_is_the_answer_at_fault` |
| 443 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(None, "schema", f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 444 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, None, f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_not_the_schema_names_where_and_why` |
| 445 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`- f"{first['msg']}")`<br>`+ return _answered(sent, "schema", None)` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 446 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered("schema", f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 447 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 448 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`- f"{first['msg']}")`<br>`+ return _answered(sent, "schema", )` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 449 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, "XXschemaXX", f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_not_the_schema_names_where_and_why` |
| 450 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, "SCHEMA", f"the answer is not {row['schema']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_not_the_schema_names_where_and_why` |
| 451 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, "schema", f"the answer is not {row['XXschemaXX']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 452 | `- return _answered(sent, "schema", f"the answer is not {row['schema']}: {where}: "`<br>`+ return _answered(sent, "schema", f"the answer is not {row['SCHEMA']}: {where}: "` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 453 | `- f"{first['msg']}")`<br>`+ f"{first['XXmsgXX']}")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 454 | `- f"{first['msg']}")`<br>`+ f"{first['MSG']}")` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_wrong_deep_inside_names_its_path` |
| 455 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 456 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 457 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(None, verdict="ok", output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 458 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict=None, output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 459 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="ok", output=None))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 460 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(verdict="ok", output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 461 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 462 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="ok", ))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 463 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="XXokXX", output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 464 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="OK", output=output.model_dump(mode="json")))` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 465 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode=None)))` | killed | `tests/test_ai_gateway_ask.py::test_the_output_is_recorded_as_json_writes_it` |
| 466 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="XXjsonXX")))` | killed | `tests/test_ai_gateway_ask.py::test_the_output_is_recorded_as_json_writes_it` |
| 467 | `- out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="json")))`<br>`+ out = calls.record(dict(sent, verdict="ok", output=output.model_dump(mode="JSON")))` | killed | `tests/test_ai_gateway_ask.py::test_the_output_is_recorded_as_json_writes_it` |
| 468 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"XXokXX": True, "output": output, "call_id": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 469 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"OK": True, "output": output, "call_id": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 470 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": False, "output": output, "call_id": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 471 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "XXoutputXX": output, "call_id": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 472 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "OUTPUT": output, "call_id": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 473 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "output": output, "XXcall_idXX": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 474 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "output": output, "CALL_ID": call_id, "cost_usd": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 475 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "output": output, "call_id": call_id, "XXcost_usdXX": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 476 | `- return {"ok": True, "output": output, "call_id": call_id, "cost_usd": cost,`<br>`+ return {"ok": True, "output": output, "call_id": call_id, "COST_USD": cost,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 477 | `- "recorded": out.get("recorded", False)}`<br>`+ "XXrecordedXX": out.get("recorded", False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 478 | `- "recorded": out.get("recorded", False)}`<br>`+ "RECORDED": out.get("recorded", False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 479 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get(None, False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 480 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", None)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_whose_record_says_nothing_is_not_recorded` |
| 481 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get(False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 482 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", )}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_whose_record_says_nothing_is_not_recorded` |
| 483 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("XXrecordedXX", False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 484 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("RECORDED", False)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 485 | `- "recorded": out.get("recorded", False)}`<br>`+ "recorded": out.get("recorded", True)}` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_whose_record_says_nothing_is_not_recorded` |

### `modules.ai.profiles.profile`

- Baseline: the tests passed on the committed file (3.6 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words`.
- Mutants: 4, killed 4, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}"`<br>`+ raise KeyError(None` | killed | `tests/test_ai_gateway.py::test_a_long_prompt_is_priced_at_the_long_rate` |
| 2 | `- raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}"`<br>`+ raise KeyError(f"no model profile for {model!r}; known: {', '.join(None)}"` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |
| 3 | `- raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}"`<br>`+ raise KeyError(f"no model profile for {model!r}; known: {'XX, XX'.join(sorted(MODELS))}"` | killed | `tests/test_ai_profiles.py::test_a_model_with_no_profile_is_refused_naming_every_known_model` |
| 4 | `- raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(MODELS))}"`<br>`+ raise KeyError(f"no model profile for {model!r}; known: {', '.join(sorted(None))}"` | killed | `tests/test_ai_gateway_ask.py::test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words` |

### `modules.ai.profiles.task`

- Baseline: the tests passed on the committed file (3.9 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 4, killed 4, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- raise KeyError(f"no task {name!r}; known: {', '.join(sorted(TASKS))}") from None`<br>`+ raise KeyError(None) from None` | killed | `tests/test_ai_profiles.py::test_a_task_no_pin_names_is_refused_naming_every_known_task` |
| 2 | `- raise KeyError(f"no task {name!r}; known: {', '.join(sorted(TASKS))}") from None`<br>`+ raise KeyError(f"no task {name!r}; known: {', '.join(None)}") from None` | killed | `tests/test_ai_profiles.py::test_a_task_no_pin_names_is_refused_naming_every_known_task` |
| 3 | `- raise KeyError(f"no task {name!r}; known: {', '.join(sorted(TASKS))}") from None`<br>`+ raise KeyError(f"no task {name!r}; known: {'XX, XX'.join(sorted(TASKS))}") from None` | killed | `tests/test_ai_profiles.py::test_a_task_no_pin_names_is_refused_naming_every_known_task` |
| 4 | `- raise KeyError(f"no task {name!r}; known: {', '.join(sorted(TASKS))}") from None`<br>`+ raise KeyError(f"no task {name!r}; known: {', '.join(sorted(None))}") from None` | killed | `tests/test_ai_profiles.py::test_a_task_no_pin_names_is_refused_naming_every_known_task` |

### `modules.ai.profiles.prices_for`

- Baseline: the tests passed on the committed file (3.6 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 33, killed 33, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- p = profile(model)`<br>`+ p = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 2 | `- p = profile(model)`<br>`+ p = profile(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 3 | `- long_at = p.get("long_prompt_tokens")`<br>`+ long_at = None` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 4 | `- long_at = p.get("long_prompt_tokens")`<br>`+ long_at = p.get(None)` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 5 | `- long_at = p.get("long_prompt_tokens")`<br>`+ long_at = p.get("XXlong_prompt_tokensXX")` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 6 | `- long_at = p.get("long_prompt_tokens")`<br>`+ long_at = p.get("LONG_PROMPT_TOKENS")` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 7 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = None` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 8 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if (long_at and prompt_tokens > long_at) and False else "base"` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 9 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if (long_at and prompt_tokens > long_at) or True else "base"` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 10 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "XXlongXX" if long_at and prompt_tokens > long_at else "base"` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 11 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "LONG" if long_at and prompt_tokens > long_at else "base"` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 12 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if long_at or prompt_tokens > long_at else "base"` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 13 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if long_at and prompt_tokens >= long_at else "base"` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 14 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if long_at and prompt_tokens > long_at else "XXbaseXX"` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 15 | `- tier = "long" if long_at and prompt_tokens > long_at else "base"`<br>`+ tier = "long" if long_at and prompt_tokens > long_at else "BASE"` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 16 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 17 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if (tier == "long") and False else p["price"]` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 18 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if (tier == "long") or True else p["price"]` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 19 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["XXlong_priceXX"] if tier == "long" else p["price"]` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 20 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["LONG_PRICE"] if tier == "long" else p["price"]` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 21 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if tier != "long" else p["price"]` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 22 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if tier == "XXlongXX" else p["price"]` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 23 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if tier == "LONG" else p["price"]` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 24 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if tier == "long" else p["XXpriceXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 25 | `- rates = p["long_price"] if tier == "long" else p["price"]`<br>`+ rates = p["long_price"] if tier == "long" else p["PRICE"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 26 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(None, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 27 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, tier=None, as_of=PRICES_AS_OF, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 28 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, tier=tier, as_of=None, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 29 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=None)` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 30 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 31 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, as_of=PRICES_AS_OF, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway_ask.py::test_the_prices_charged_are_the_tier_of_every_prompt_token_counted` |
| 32 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, tier=tier, source=PRICES_SOURCE)` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |
| 33 | `- return dict(rates, tier=tier, as_of=PRICES_AS_OF, source=PRICES_SOURCE)`<br>`+ return dict(rates, tier=tier, as_of=PRICES_AS_OF, )` | killed | `tests/test_ai_gateway.py::test_the_call_is_the_pinned_model_and_its_row_the_prices_it_was_charged` |

### `modules.ai.profiles.cost_usd`

- Baseline: the tests passed on the committed file (3.4 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 26, killed 26, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:`<br>`+ cache_write_tokens: int = 1, cache_read_tokens: int = 0) -> float:` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 2 | `- cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:`<br>`+ cache_write_tokens: int = 0, cache_read_tokens: int = 1) -> float:` | killed | `tests/test_ai_gateway_ask.py::test_a_refusal_is_said_with_its_category` |
| 3 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 4 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(None, input_tokens + cache_write_tokens + cache_read_tokens)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 5 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(model, None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 6 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(input_tokens + cache_write_tokens + cache_read_tokens)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 7 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(model, )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 8 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(model, input_tokens + cache_write_tokens - cache_read_tokens)` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 9 | `- rates = prices_for(model, input_tokens + cache_write_tokens + cache_read_tokens)`<br>`+ rates = prices_for(model, input_tokens - cache_write_tokens + cache_read_tokens)` | killed | `tests/test_ai_profiles.py::test_the_long_tier_counts_cache_writes_into_the_prompt` |
| 10 | `- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + output_tokens * rates["output"]) * 1_000_000` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 11 | `- + cache_read_tokens * rates["cache_read"]`<br>`- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + cache_read_tokens * rates["cache_read"] - output_tokens * rates["output"]) / 1_000_000` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 12 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`- + cache_read_tokens * rates["cache_read"]`<br>`+ return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"] - cache_read_tokens * rates["cache_read"]` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 13 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["input"] - cache_write_tokens * rates["cache_write"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 14 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens / rates["input"] + cache_write_tokens * rates["cache_write"]` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 15 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["XXinputXX"] + cache_write_tokens * rates["cache_write"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 16 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["INPUT"] + cache_write_tokens * rates["cache_write"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 17 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["input"] + cache_write_tokens / rates["cache_write"]` | killed | `tests/test_ai_gateway.py::test_a_cache_write_and_read_are_priced_at_their_own_rates` |
| 18 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["input"] + cache_write_tokens * rates["XXcache_writeXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 19 | `- return (input_tokens * rates["input"] + cache_write_tokens * rates["cache_write"]`<br>`+ return (input_tokens * rates["input"] + cache_write_tokens * rates["CACHE_WRITE"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 20 | `- + cache_read_tokens * rates["cache_read"]`<br>`+ + cache_read_tokens / rates["cache_read"]` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 21 | `- + cache_read_tokens * rates["cache_read"]`<br>`+ + cache_read_tokens * rates["XXcache_readXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 22 | `- + cache_read_tokens * rates["cache_read"]`<br>`+ + cache_read_tokens * rates["CACHE_READ"]` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 23 | `- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + output_tokens / rates["output"]) / 1_000_000` | killed | `tests/test_ai_gateway.py::test_each_row_records_the_cache_and_is_priced_by_it` |
| 24 | `- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + output_tokens * rates["XXoutputXX"]) / 1_000_000` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 25 | `- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + output_tokens * rates["OUTPUT"]) / 1_000_000` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 26 | `- + output_tokens * rates["output"]) / 1_000_000`<br>`+ + output_tokens * rates["output"]) / 1000001` | killed | `tests/test_ai_profiles.py::test_a_cost_is_its_rates_per_million_exactly` |

### `modules.ai.profiles.cap_per_call`

- Baseline: the tests passed on the committed file (3.5 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 17, killed 17, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- t = task(name)`<br>`+ t = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 2 | `- t = task(name)`<br>`+ t = task(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 3 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(None, 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 4 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], None, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 5 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, None, cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 6 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 7 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 8 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 9 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 10 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["max_tokens"], )` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 11 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["XXmodelXX"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 12 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["MODEL"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 13 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 1, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway.py::test_each_task_s_cap_is_its_pinned_model_s_worst_case_at_its_bounds` |
| 14 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["XXmax_tokensXX"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 15 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["MAX_TOKENS"], cache_write_tokens=t["max_prompt_tokens"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 16 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["XXmax_prompt_tokensXX"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 17 | `- return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["max_prompt_tokens"])`<br>`+ return cost_usd(t["model"], 0, t["max_tokens"], cache_write_tokens=t["MAX_PROMPT_TOKENS"])` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |

### `modules.ai.profiles.cases_off_pin`

- Baseline: the tests passed on the committed file (3.6 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model`.
- Mutants: 51, killed 51, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- out = []`<br>`+ out = None` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 2 | `- if not os.path.isdir(root):`<br>`+ if os.path.isdir(root):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 3 | `- if not os.path.isdir(root):`<br>`+ if not os.path.isdir(None):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 4 | `- for name in sorted(os.listdir(root)):`<br>`+ for name in sorted(None):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 5 | `- for name in sorted(os.listdir(root)):`<br>`+ for name in sorted(os.listdir(None)):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 6 | `- folder = os.path.join(root, name)`<br>`+ folder = None` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 7 | `- folder = os.path.join(root, name)`<br>`+ folder = os.path.join(None, name)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 8 | `- folder = os.path.join(root, name)`<br>`+ folder = os.path.join(root, None)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 9 | `- folder = os.path.join(root, name)`<br>`+ folder = os.path.join(name)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 10 | `- folder = os.path.join(root, name)`<br>`+ folder = os.path.join(root, )` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 11 | `- if not os.path.isdir(folder):`<br>`+ if os.path.isdir(folder):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 12 | `- if not os.path.isdir(folder):`<br>`+ if not os.path.isdir(None):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 13 | `- continue`<br>`+ break` | killed | `tests/test_ai_profiles.py::test_a_file_beside_the_task_folders_is_passed_over_and_the_folders_still_read` |
| 14 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = None` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 15 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get(None, "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 16 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("model", None)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 17 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 18 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("model", )` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 19 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) and {}).get("model", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 20 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(None) or {}).get("model", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 21 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("XXmodelXX", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 22 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("MODEL", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 23 | `- pinned = (TASKS.get(name) or {}).get("model", "")`<br>`+ pinned = (TASKS.get(name) or {}).get("model", "XXXX")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 24 | `- for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):`<br>`+ for case in sorted(None):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 25 | `- for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):`<br>`+ for case in sorted(f for f in os.listdir(None) if f.endswith(".json")):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 26 | `- for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):`<br>`+ for case in sorted(f for f in os.listdir(folder) if f.endswith(None)):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 27 | `- for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):`<br>`+ for case in sorted(f for f in os.listdir(folder) if f.endswith("XX.jsonXX")):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 28 | `- for case in sorted(f for f in os.listdir(folder) if f.endswith(".json")):`<br>`+ for case in sorted(f for f in os.listdir(folder) if f.endswith(".JSON")):` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 29 | `- path = os.path.join(folder, case)`<br>`+ path = None` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 30 | `- path = os.path.join(folder, case)`<br>`+ path = os.path.join(None, case)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 31 | `- path = os.path.join(folder, case)`<br>`+ path = os.path.join(folder, None)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 32 | `- path = os.path.join(folder, case)`<br>`+ path = os.path.join(case)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 33 | `- path = os.path.join(folder, case)`<br>`+ path = os.path.join(folder, )` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 34 | `- with open(path, "rb") as fh:`<br>`+ with open(None, "rb") as fh:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 35 | `- with open(path, "rb") as fh:`<br>`+ with open(path, None) as fh:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 36 | `- with open(path, "rb") as fh:`<br>`+ with open("rb") as fh:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 37 | `- with open(path, "rb") as fh:`<br>`+ with open(path, ) as fh:` | killed | `tests/test_ai_profiles.py::test_a_case_saved_with_a_byte_order_mark_is_read` |
| 38 | `- with open(path, "rb") as fh:`<br>`+ with open(path, "XXrbXX") as fh:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 39 | `- with open(path, "rb") as fh:`<br>`+ with open(path, "RB") as fh:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 40 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = None` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 41 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get(None, "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 42 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("model", None)` | killed | `tests/test_ai_profiles.py::test_a_case_naming_no_model_is_off_its_pin_with_no_model` |
| 43 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 44 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("model", )` | killed | `tests/test_ai_profiles.py::test_a_case_naming_no_model_is_off_its_pin_with_no_model` |
| 45 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) and {}).get("model", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 46 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(None) or {}).get("model", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 47 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("XXmodelXX", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 48 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("MODEL", "")` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 49 | `- recorded = (json.load(fh) or {}).get("model", "")`<br>`+ recorded = (json.load(fh) or {}).get("model", "XXXX")` | killed | `tests/test_ai_profiles.py::test_a_case_naming_no_model_is_off_its_pin_with_no_model` |
| 50 | `- if recorded != pinned:`<br>`+ if recorded == pinned:` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |
| 51 | `- out.append((path, recorded, pinned))`<br>`+ out.append(None)` | killed | `tests/test_ai_gateway.py::test_every_recorded_case_was_recorded_on_its_task_s_pinned_model` |

### `modules.ai.profiles.prices_age_days`

- Baseline: the tests passed on the committed file (3.8 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale`.
- Mutants: 7, killed 7, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- day = (datetime.date.fromisoformat(today) if today`<br>`- else datetime.datetime.now(datetime.timezone.utc).date())`<br>`+ day = None` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 2 | `- day = (datetime.date.fromisoformat(today) if today`<br>`+ day = (datetime.date.fromisoformat(today) if (today) and False` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 3 | `- day = (datetime.date.fromisoformat(today) if today`<br>`+ day = (datetime.date.fromisoformat(today) if (today) or True` | killed | `tests/test_ai_profiles.py::test_the_prices_age_is_counted_by_the_utc_day` |
| 4 | `- day = (datetime.date.fromisoformat(today) if today`<br>`+ day = (datetime.date.fromisoformat(None) if today` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 5 | `- else datetime.datetime.now(datetime.timezone.utc).date())`<br>`+ else datetime.datetime.now(None).date())` | killed | `tests/test_ai_profiles.py::test_the_prices_age_is_counted_by_the_utc_day` |
| 6 | `- return (day - datetime.date.fromisoformat(PRICES_AS_OF)).days`<br>`+ return (day + datetime.date.fromisoformat(PRICES_AS_OF)).days` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 7 | `- return (day - datetime.date.fromisoformat(PRICES_AS_OF)).days`<br>`+ return (day - datetime.date.fromisoformat(None)).days` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |

### `modules.ai.profiles.table`

- Baseline: the tests passed on the committed file (3.6 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale`.
- Mutants: 57, killed 57, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- rows = []`<br>`+ rows = None` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 2 | `- for name in sorted(TASKS):`<br>`+ for name in sorted(None):` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 3 | `- t = TASKS[name]`<br>`+ t = None` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 4 | `- p = profile(t["model"])`<br>`+ p = None` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 5 | `- p = profile(t["model"])`<br>`+ p = profile(None)` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 6 | `- p = profile(t["model"])`<br>`+ p = profile(t["XXmodelXX"])` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 7 | `- p = profile(t["model"])`<br>`+ p = profile(t["MODEL"])` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 8 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`- "model_words": p["words"], "price": p["price"],`<br>`- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`- "cap_usd": cap_per_call(name)})`<br>`+ rows.append(None)` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 9 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"XXtaskXX": name, "words": t["words"], "model": t["model"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 10 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"TASK": name, "words": t["words"], "model": t["model"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 11 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "XXwordsXX": t["words"], "model": t["model"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 12 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "WORDS": t["words"], "model": t["model"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 13 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["XXwordsXX"], "model": t["model"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 14 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["WORDS"], "model": t["model"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 15 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["words"], "XXmodelXX": t["model"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 16 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["words"], "MODEL": t["model"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 17 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["words"], "model": t["XXmodelXX"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 18 | `- rows.append({"task": name, "words": t["words"], "model": t["model"],`<br>`+ rows.append({"task": name, "words": t["words"], "model": t["MODEL"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 19 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "XXmodel_wordsXX": p["words"], "price": p["price"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 20 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "MODEL_WORDS": p["words"], "price": p["price"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 21 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["XXwordsXX"], "price": p["price"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 22 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["WORDS"], "price": p["price"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 23 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["words"], "XXpriceXX": p["price"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 24 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["words"], "PRICE": p["price"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 25 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["words"], "price": p["XXpriceXX"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 26 | `- "model_words": p["words"], "price": p["price"],`<br>`+ "model_words": p["words"], "price": p["PRICE"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 27 | `- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`+ "XXlong_prompt_tokensXX": p.get("long_prompt_tokens"),` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 28 | `- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`+ "LONG_PROMPT_TOKENS": p.get("long_prompt_tokens"),` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 29 | `- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`+ "long_prompt_tokens": p.get(None),` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 30 | `- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`+ "long_prompt_tokens": p.get("XXlong_prompt_tokensXX"),` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 31 | `- "long_prompt_tokens": p.get("long_prompt_tokens"),`<br>`+ "long_prompt_tokens": p.get("LONG_PROMPT_TOKENS"),` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 32 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "XXmax_prompt_tokensXX": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 33 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "MAX_PROMPT_TOKENS": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 34 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["XXmax_prompt_tokensXX"], "max_tokens": t["max_tokens"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 35 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["MAX_PROMPT_TOKENS"], "max_tokens": t["max_tokens"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 36 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["max_prompt_tokens"], "XXmax_tokensXX": t["max_tokens"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 37 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["max_prompt_tokens"], "MAX_TOKENS": t["max_tokens"],` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 38 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["XXmax_tokensXX"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 39 | `- "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["max_tokens"],`<br>`+ "max_prompt_tokens": t["max_prompt_tokens"], "max_tokens": t["MAX_TOKENS"],` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 40 | `- "cap_usd": cap_per_call(name)})`<br>`+ "XXcap_usdXX": cap_per_call(name)})` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 41 | `- "cap_usd": cap_per_call(name)})`<br>`+ "CAP_USD": cap_per_call(name)})` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 42 | `- "cap_usd": cap_per_call(name)})`<br>`+ "cap_usd": cap_per_call(None)})` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 43 | `- age = prices_age_days(today)`<br>`+ age = None` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 44 | `- age = prices_age_days(today)`<br>`+ age = prices_age_days(None)` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 45 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"XXrowsXX": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 46 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"ROWS": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 47 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "XXas_ofXX": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 48 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "AS_OF": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 49 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "as_of": PRICES_AS_OF, "XXsourceXX": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 50 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "as_of": PRICES_AS_OF, "SOURCE": PRICES_SOURCE, "age_days": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 51 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "XXage_daysXX": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 52 | `- return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "age_days": age,`<br>`+ return {"rows": rows, "as_of": PRICES_AS_OF, "source": PRICES_SOURCE, "AGE_DAYS": age,` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 53 | `- "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}`<br>`+ "XXstaleXX": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 54 | `- "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}`<br>`+ "STALE": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}` | killed | `tests/test_ai_gateway.py::test_the_prices_are_the_pricing_page_s_and_the_table_says_when_they_are_stale` |
| 55 | `- "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}`<br>`+ "stale": age >= PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}` | killed | `tests/test_ai_profiles.py::test_prices_are_stale_only_past_their_bound` |
| 56 | `- "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}`<br>`+ "stale": age > PRICES_STALE_DAYS, "XXstale_daysXX": PRICES_STALE_DAYS}` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |
| 57 | `- "stale": age > PRICES_STALE_DAYS, "stale_days": PRICES_STALE_DAYS}`<br>`+ "stale": age > PRICES_STALE_DAYS, "STALE_DAYS": PRICES_STALE_DAYS}` | killed | `tests/test_ai_profiles.py::test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole` |

### `modules.ai.connection.check`

- Baseline: the tests passed on the committed file (3.4 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back`.
- Mutants: 60, killed 60, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = None` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 2 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = "mercury-" - secrets.token_hex(4)` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 3 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = "XXmercury-XX" + secrets.token_hex(4)` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 4 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = "MERCURY-" + secrets.token_hex(4)` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 5 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = "mercury-" + secrets.token_hex(None)` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 6 | `- word = "mercury-" + secrets.token_hex(4)`<br>`+ word = "mercury-" + secrets.token_hex(5)` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 7 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`- today=today)`<br>`+ got = None` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 8 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(None, PROMPT, Ping, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 9 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, None, Ping, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 10 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, None, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 11 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, None, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 12 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=None, send=send,` | killed | `tests/test_ai_card.py::test_a_test_allowed_and_keyed_is_one_recorded_call_as_the_person` |
| 13 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=None,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 14 | `- today=today)`<br>`+ today=None)` | killed | `tests/test_ai_profiles.py::test_the_check_counts_the_day_it_is_given` |
| 15 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(PROMPT, Ping, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 16 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, Ping, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 17 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, {"word": word}, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 18 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, actor=actor, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 19 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, send=send,` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 20 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`- today=today)`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, today=today)` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 21 | `- today=today)`<br>`+ )` | killed | `tests/test_ai_profiles.py::test_the_check_counts_the_day_it_is_given` |
| 22 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"XXwordXX": word}, actor=actor, send=send,` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 23 | `- got = gateway.ask(FEATURE, PROMPT, Ping, {"word": word}, actor=actor, send=send,`<br>`+ got = gateway.ask(FEATURE, PROMPT, Ping, {"WORD": word}, actor=actor, send=send,` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 24 | `- if not got["ok"]:`<br>`+ if got["ok"]:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 25 | `- if not got["ok"]:`<br>`+ if not got["XXokXX"]:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 26 | `- if not got["ok"]:`<br>`+ if not got["OK"]:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 27 | `- if got["output"].echo != word:`<br>`+ if got["XXoutputXX"].echo != word:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 28 | `- if got["output"].echo != word:`<br>`+ if got["OUTPUT"].echo != word:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 29 | `- if got["output"].echo != word:`<br>`+ if got["output"].echo == word:` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 30 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"XXokXX": False, "error": "schema", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 31 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"OK": False, "error": "schema", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 32 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": True, "error": "schema", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 33 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "XXerrorXX": "schema", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 34 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "ERROR": "schema", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 35 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "XXschemaXX", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 36 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "SCHEMA", "call_id": got["call_id"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 37 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "schema", "XXcall_idXX": got["call_id"],` | killed | `tests/test_ai_profiles.py::test_a_wrong_echo_is_refused_naming_both_its_first_40_characters` |
| 38 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "schema", "CALL_ID": got["call_id"],` | killed | `tests/test_ai_profiles.py::test_a_wrong_echo_is_refused_naming_both_its_first_40_characters` |
| 39 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "schema", "call_id": got["XXcall_idXX"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 40 | `- return {"ok": False, "error": "schema", "call_id": got["call_id"],`<br>`+ return {"ok": False, "error": "schema", "call_id": got["CALL_ID"],` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 41 | `- "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}`<br>`+ "XXdetailXX": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 42 | `- "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}`<br>`+ "DETAIL": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 43 | `- "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}`<br>`+ "detail": f"the answer echoed {got['XXoutputXX'].echo[:40]!r}, not {word!r}"}` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 44 | `- "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}`<br>`+ "detail": f"the answer echoed {got['OUTPUT'].echo[:40]!r}, not {word!r}"}` | killed | `tests/test_ai_gateway.py::test_the_connection_check_wants_its_own_word_back` |
| 45 | `- "detail": f"the answer echoed {got['output'].echo[:40]!r}, not {word!r}"}`<br>`+ "detail": f"the answer echoed {got['output'].echo[:41]!r}, not {word!r}"}` | killed | `tests/test_ai_profiles.py::test_a_wrong_echo_is_refused_naming_both_its_first_40_characters` |
| 46 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"XXokXX": True, "detail": f"answered, ${got['cost_usd']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 47 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"OK": True, "detail": f"answered, ${got['cost_usd']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 48 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"ok": False, "detail": f"answered, ${got['cost_usd']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 49 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"ok": True, "XXdetailXX": f"answered, ${got['cost_usd']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 50 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"ok": True, "DETAIL": f"answered, ${got['cost_usd']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 51 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"ok": True, "detail": f"answered, ${got['XXcost_usdXX']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 52 | `- return {"ok": True, "detail": f"answered, ${got['cost_usd']:.5f}",`<br>`+ return {"ok": True, "detail": f"answered, ${got['COST_USD']:.5f}",` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 53 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "XXcall_idXX": got["call_id"], "cost_usd": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 54 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "CALL_ID": got["call_id"], "cost_usd": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 55 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["XXcall_idXX"], "cost_usd": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 56 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["CALL_ID"], "cost_usd": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 57 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["call_id"], "XXcost_usdXX": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 58 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["call_id"], "COST_USD": got["cost_usd"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 59 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["call_id"], "cost_usd": got["XXcost_usdXX"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |
| 60 | `- "call_id": got["call_id"], "cost_usd": got["cost_usd"]}`<br>`+ "call_id": got["call_id"], "cost_usd": got["COST_USD"]}` | killed | `tests/test_ai_profiles.py::test_the_check_sends_one_word_of_its_own_as_the_data_named_word` |

### `modules.redact.redact_positional`

- Baseline: the tests passed on the committed file (5.0 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token`.
- Mutants: 20, killed 20, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- if not text:`<br>`+ if text:` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 2 | `- token = match.group(2)`<br>`+ token = None` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 3 | `- token = match.group(2)`<br>`+ token = match.group(None)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 4 | `- token = match.group(2)`<br>`+ token = match.group(3)` | killed | `tests/test_provider_redaction.py::TestPositionalRedaction::test_a_missing_secret_marker_is_not_re_wrapped` |
| 5 | `- if _ALREADY.match(token):`<br>`+ if _ALREADY.match(None):` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 6 | `- return match.group(0)`<br>`+ return match.group(None)` | killed | `tests/test_provider_redaction.py::TestPositionalRedaction::test_it_is_idempotent` |
| 7 | `- return match.group(0)`<br>`+ return match.group(1)` | killed | `tests/test_provider_redaction.py::TestPositionalRedaction::test_it_is_idempotent` |
| 8 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(1) + PLACEHOLDER.format(label=label) - match.group(3)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 9 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(1) - PLACEHOLDER.format(label=label) + match.group(3)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 10 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(None) + PLACEHOLDER.format(label=label) + match.group(3)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 11 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(2) + PLACEHOLDER.format(label=label) + match.group(3)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 12 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(1) + PLACEHOLDER.format(label=None) + match.group(3)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 13 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(1) + PLACEHOLDER.format(label=label) + match.group(None)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 14 | `- return match.group(1) + PLACEHOLDER.format(label=label) + match.group(3)`<br>`+ return match.group(1) + PLACEHOLDER.format(label=label) + match.group(4)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 15 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = None` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 16 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = pattern.sub(None, text)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 17 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = pattern.sub(_sub(label), None)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 18 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = pattern.sub(text)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 19 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = pattern.sub(_sub(label), )` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |
| 20 | `- text = pattern.sub(_sub(label), text)`<br>`+ text = pattern.sub(_sub(None), text)` | killed | `tests/test_sealed_values_masked.py::test_a_sealed_settings_value_keeps_its_prefix_and_loses_its_token` |

## 2026-10-26: the batched gateway change and the pin files, changed lines only, at b06d8046

**Why only the changed lines.** The operator's sprint ruling of 2026-10-25 (PHASE8_PLAN 15.12,
the same expiry): for a change to tier code, the hand check covers the mutants on the lines
changed since the last proved commit, plus a must-die canary per changed function, logged as
before. cfa0822b's full check (the section above) stands for every other line while their
tests are unchanged.

**What changed in the tier since cfa0822b.**
- `gateway.build_request` reads the request's settings from the task's pin: model,
  `max_tokens`, `thinking` (sent in the model's own form only when off) and `temperature`
  (sent only when named).
- `gateway.ask` builds the effective pin, with a measurement's thinking replacing the file's.
  It refuses a thinking or a temperature the model cannot take, records the thinking asked,
  and passes the pin on.
- `profiles.load_pins` is new: the pin files read, a file whose keys are not exactly
  `PIN_KEYS` refused.
- The changes to `profiles.MODELS` (`thinking_off`, `temperatures`) are data, read by the
  functions above, and no function of `connection` or `redact` changed.

**The method**, as the section above, with one step added:
- Step 3's mutants are only those altering a line in `git diff -U0 cfa0822b <commit>`'s added
  ranges.
- A mutant's lines are found by comparing the committed function's text with the mutant's,
  from the function's def line. mutmut's own diff costs about 5 s a mutant, and agreed on
  every one of 17 sampled across `build_request` and `ask`.
- The aimed tests are the section above's six files.

**The first run, at 222c3686.** 146 mutants on changed lines: 134 killed, 12 survived, and
all three canaries killed.
- 4 survivors in `ask` lay in a dead default (`asked.get("thinking", "adaptive")`): every pin
  names its thinking, so the default could never run. It was removed, and temperature is
  read the same way.
- 4 survivors in `ask` were on a model profile listing no temperatures, a case never asked.
  A test was added: a pin's temperature there is refused, saying "none".
- 1 survivor in `load_pins` (`continue` made `break`) was a file that is not a pin, never
  asked. A test was added: it is passed over and every pin after it loads.
- 3 survivors in `load_pins` change `encoding="utf-8"` to the platform's default or to
  "UTF-8".

The fix is b06d8046, and the check was run again on it.

**The result, at b06d8046.** 139 mutants on changed lines: 136 killed, 3 survived. All
three canaries killed, every baseline passed, and every file restored identical; the
checkout was clean by `git status` at the end.

**The 3 survivors, ruled equivalent by the operator (2026-10-26 ~00:5x UTC).** They are
`load_pins` 10, 12 and 18: `encoding="utf-8"` made `encoding=None`, made absent, and made
`"UTF-8"`. They read the pin files, not egress, masking or a secret.
- **18:** encoding names are case-insensitive, so "UTF-8" is "utf-8".
- **10 and 12:** Python 3.7 and later on Linux reads UTF-8 by default, the C locale included
  (PEP 538 and PEP 540), and Mercury supports Linux containers only.

With the ruling, the change is proved: every mutant on a changed line is killed or ruled
equivalent.

| function | mutants | killed | survived | canary | baseline | file restored |
|---|---|---|---|---|---|---|
| `modules.ai.gateway.build_request` | 32 | 32 | 0 | killed | passed | identical |
| `modules.ai.gateway.ask` | 79 | 79 | 0 | killed | passed | identical |
| `modules.ai.profiles.load_pins` | 28 | 25 | 3 | killed | passed | identical |
| **all 3** | **139** | **136** | **3** | | | |

### `modules.ai.gateway.build_request`

- Baseline: the tests passed on the committed file (3.1 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept`.
- Mutants: 32, killed 32, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 32 | `- body = {`<br>`- "model": pin["model"],`<br>`- "max_tokens": int(pin["max_tokens"]),`<br>`- "system": system,`<br>`- "messages": [{"role": "user", "content": _delimited("data", parts) or "(no data)"}],`<br>`- "output_config": {"format": {"type": "json_schema",`<br>`- "schema": schemas.schema_for(schema_model)}},`<br>`- }`<br>`+ body = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 33 | `- "model": pin["model"],`<br>`+ "XXmodelXX": pin["model"],` | killed | `tests/test_ai_gateway_ask.py::test_a_task_naming_no_thinking_sends_none_and_its_request_is_unchanged` |
| 34 | `- "model": pin["model"],`<br>`+ "MODEL": pin["model"],` | killed | `tests/test_ai_gateway_ask.py::test_a_task_naming_no_thinking_sends_none_and_its_request_is_unchanged` |
| 35 | `- "model": pin["model"],`<br>`+ "model": pin["XXmodelXX"],` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 36 | `- "model": pin["model"],`<br>`+ "model": pin["MODEL"],` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 37 | `- "max_tokens": int(pin["max_tokens"]),`<br>`+ "XXmax_tokensXX": int(pin["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 38 | `- "max_tokens": int(pin["max_tokens"]),`<br>`+ "MAX_TOKENS": int(pin["max_tokens"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent` |
| 39 | `- "max_tokens": int(pin["max_tokens"]),`<br>`+ "max_tokens": int(None),` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 40 | `- "max_tokens": int(pin["max_tokens"]),`<br>`+ "max_tokens": int(pin["XXmax_tokensXX"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 41 | `- "max_tokens": int(pin["max_tokens"]),`<br>`+ "max_tokens": int(pin["MAX_TOKENS"]),` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 72 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get(None) == "off":` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 73 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get("XXthinkingXX") == "off":` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 74 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get("THINKING") == "off":` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 75 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get("thinking") != "off":` | killed | `tests/test_ai_gateway_ask.py::test_a_model_with_no_long_tier_says_none` |
| 76 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get("thinking") == "XXoffXX":` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 77 | `- if pin.get("thinking") == "off":`<br>`+ if pin.get("thinking") == "OFF":` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 78 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["thinking"] = None` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 79 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["XXthinkingXX"] = dict((profile or {})["thinking_off"])` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 80 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["THINKING"] = dict((profile or {})["thinking_off"])` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 81 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["thinking"] = dict(None)` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 82 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["thinking"] = dict((profile and {})["thinking_off"])` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 83 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["thinking"] = dict((profile or {})["XXthinking_offXX"])` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 84 | `- body["thinking"] = dict((profile or {})["thinking_off"])`<br>`+ body["thinking"] = dict((profile or {})["THINKING_OFF"])` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 85 | `- if pin.get("temperature") is not None:`<br>`+ if pin.get(None) is not None:` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 86 | `- if pin.get("temperature") is not None:`<br>`+ if pin.get("XXtemperatureXX") is not None:` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 87 | `- if pin.get("temperature") is not None:`<br>`+ if pin.get("TEMPERATURE") is not None:` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 88 | `- if pin.get("temperature") is not None:`<br>`+ if pin.get("temperature") is None:` | killed | `tests/test_ai_gateway_ask.py::test_a_task_naming_no_thinking_sends_none_and_its_request_is_unchanged` |
| 89 | `- body["temperature"] = pin["temperature"]`<br>`+ body["temperature"] = None` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 90 | `- body["temperature"] = pin["temperature"]`<br>`+ body["XXtemperatureXX"] = pin["temperature"]` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 91 | `- body["temperature"] = pin["temperature"]`<br>`+ body["TEMPERATURE"] = pin["temperature"]` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 92 | `- body["temperature"] = pin["temperature"]`<br>`+ body["temperature"] = pin["XXtemperatureXX"]` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |
| 93 | `- body["temperature"] = pin["temperature"]`<br>`+ body["temperature"] = pin["TEMPERATURE"]` | killed | `tests/test_ai_gateway_ask.py::test_build_request_sends_the_pin_s_settings_only_when_it_names_them` |

### `modules.ai.gateway.ask`

- Baseline: the tests passed on the committed file (3.1 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged`.
- Mutants: 79, killed 79, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 127 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = None` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 128 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(pin, thinking=thinking) if (thinking is not None) and False else pin` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 129 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(pin, thinking=thinking) if (thinking is not None) or True else pin` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 130 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(None, thinking=thinking) if thinking is not None else pin` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 131 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(pin, thinking=None) if thinking is not None else pin` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 132 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(thinking=thinking) if thinking is not None else pin` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 133 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(pin, ) if thinking is not None else pin` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 134 | `- asked = dict(pin, thinking=thinking) if thinking is not None else pin`<br>`+ asked = dict(pin, thinking=thinking) if thinking is None else pin` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 135 | `- mode = asked["thinking"]                    # every pin names it (profiles.PIN_KEYS)`<br>`+ mode = None                    # every pin names it (profiles.PIN_KEYS)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 136 | `- mode = asked["thinking"]                    # every pin names it (profiles.PIN_KEYS)`<br>`+ mode = asked["XXthinkingXX"]                    # every pin names it (profiles.PIN_KEYS)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 137 | `- mode = asked["thinking"]                    # every pin names it (profiles.PIN_KEYS)`<br>`+ mode = asked["THINKING"]                    # every pin names it (profiles.PIN_KEYS)` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 138 | `- row["thinking"] = mode`<br>`+ row["thinking"] = None` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 139 | `- row["thinking"] = mode`<br>`+ row["XXthinkingXX"] = mode` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 140 | `- row["thinking"] = mode`<br>`+ row["THINKING"] = mode` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 141 | `- if mode not in profiles.THINKING:`<br>`+ if mode in profiles.THINKING:` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 142 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`+ return refuse(None, f"thinking {mode!r} is not one of "` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 143 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`- f"{', '.join(profiles.THINKING)}; nothing was sent")`<br>`+ return refuse("thinking", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 144 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`+ return refuse(f"thinking {mode!r} is not one of "` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 145 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`- f"{', '.join(profiles.THINKING)}; nothing was sent")`<br>`+ return refuse("thinking", )` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 146 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`+ return refuse("XXthinkingXX", f"thinking {mode!r} is not one of "` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 147 | `- return refuse("thinking", f"thinking {mode!r} is not one of "`<br>`+ return refuse("THINKING", f"thinking {mode!r} is not one of "` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 148 | `- f"{', '.join(profiles.THINKING)}; nothing was sent")`<br>`+ f"{', '.join(None)}; nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 149 | `- f"{', '.join(profiles.THINKING)}; nothing was sent")`<br>`+ f"{'XX, XX'.join(profiles.THINKING)}; nothing was sent")` | killed | `tests/test_ai_gateway_ask.py::test_a_thinking_not_known_is_refused_before_anything_is_sent` |
| 150 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "off" or not profile.get("thinking_off"):` | killed | `tests/test_ai_gateway_ask.py::test_a_model_with_no_long_tier_says_none` |
| 151 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode != "off" and not profile.get("thinking_off"):` | killed | `tests/test_ai_gateway_ask.py::test_a_model_with_no_long_tier_says_none` |
| 152 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "XXoffXX" and not profile.get("thinking_off"):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 153 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "OFF" and not profile.get("thinking_off"):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 154 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "off" and profile.get("thinking_off"):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 155 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "off" and not profile.get(None):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 156 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "off" and not profile.get("XXthinking_offXX"):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 157 | `- if mode == "off" and not profile.get("thinking_off"):`<br>`+ if mode == "off" and not profile.get("THINKING_OFF"):` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 158 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`+ return refuse(None, f"{model}'s profile names no way to turn thinking off; "` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 159 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`- "nothing was sent")`<br>`+ return refuse("thinking", None)` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 160 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`+ return refuse(f"{model}'s profile names no way to turn thinking off; "` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 161 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`- "nothing was sent")`<br>`+ return refuse("thinking", )` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 162 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`+ return refuse("XXthinkingXX", f"{model}'s profile names no way to turn thinking off; "` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 163 | `- return refuse("thinking", f"{model}'s profile names no way to turn thinking off; "`<br>`+ return refuse("THINKING", f"{model}'s profile names no way to turn thinking off; "` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 164 | `- "nothing was sent")`<br>`+ "XXnothing was sentXX")` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 165 | `- "nothing was sent")`<br>`+ "NOTHING WAS SENT")` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused` |
| 166 | `- temperature = asked["temperature"]`<br>`+ temperature = None` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 167 | `- temperature = asked["temperature"]`<br>`+ temperature = asked["XXtemperatureXX"]` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 168 | `- temperature = asked["temperature"]`<br>`+ temperature = asked["TEMPERATURE"]` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 169 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None or temperature not in profile.get("temperatures", ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 170 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is None and temperature not in profile.get("temperatures", ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_schema_that_is_not_the_registered_one_is_refused_naming_it[unregistered]` |
| 171 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature in profile.get("temperatures", ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_takes_is_sent` |
| 172 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get(None, ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_takes_is_sent` |
| 173 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get("temperatures", None):` | killed | `tests/test_ai_gateway_ask.py::test_a_temperature_on_a_model_that_lists_none_is_refused_saying_none` |
| 174 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get(()):` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_takes_is_sent` |
| 175 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get("temperatures", ):` | killed | `tests/test_ai_gateway_ask.py::test_a_temperature_on_a_model_that_lists_none_is_refused_saying_none` |
| 176 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get("XXtemperaturesXX", ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_takes_is_sent` |
| 177 | `- if temperature is not None and temperature not in profile.get("temperatures", ()):`<br>`+ if temperature is not None and temperature not in profile.get("TEMPERATURES", ()):` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_takes_is_sent` |
| 178 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`+ return refuse(None, f"the pin's temperature {temperature!r} is not one "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 179 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`- "was sent")`<br>`+ return refuse("temperature", None)` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 180 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`+ return refuse(f"the pin's temperature {temperature!r} is not one "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 181 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`- "was sent")`<br>`+ return refuse("temperature", )` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 182 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`+ return refuse("XXtemperatureXX", f"the pin's temperature {temperature!r} is not one "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 183 | `- return refuse("temperature", f"the pin's temperature {temperature!r} is not one "`<br>`+ return refuse("TEMPERATURE", f"the pin's temperature {temperature!r} is not one "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 184 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get('temperatures') and 'none'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 185 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get(None) or 'none'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 186 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get('XXtemperaturesXX') or 'none'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 187 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get('TEMPERATURES') or 'none'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 188 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get('temperatures') or 'XXnoneXX'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_temperature_on_a_model_that_lists_none_is_refused_saying_none` |
| 189 | `- f"{model} takes ({profile.get('temperatures') or 'none'}); nothing "`<br>`+ f"{model} takes ({profile.get('temperatures') or 'NONE'}); nothing "` | killed | `tests/test_ai_gateway_ask.py::test_a_temperature_on_a_model_that_lists_none_is_refused_saying_none` |
| 190 | `- "was sent")`<br>`+ "XXwas sentXX")` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 191 | `- "was sent")`<br>`+ "WAS SENT")` | killed | `tests/test_ai_gateway_ask.py::test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent` |
| 239 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`- context=context, profile=profile))`<br>`+ body = None` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 240 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`- context=context, profile=profile))`<br>`+ body = redact.egress_payload(None)` | killed | `tests/test_ai_gateway_ask.py::test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier` |
| 241 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(None, schema_model, parts, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 242 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(prompt_file, None, parts, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 243 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, None, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 244 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, parts, None,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 245 | `- context=context, profile=profile))`<br>`+ context=None, profile=profile))` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 246 | `- context=context, profile=profile))`<br>`+ context=context, profile=None))` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |
| 247 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(schema_model, parts, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 248 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(prompt_file, parts, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 249 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, asked,` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 250 | `- body = redact.egress_payload(build_request(prompt_file, schema_model, parts, asked,`<br>`- context=context, profile=profile))`<br>`+ body = redact.egress_payload(build_request(prompt_file, schema_model, parts, context=context, profile=profile))` | killed | `tests/test_ai_gateway_ask.py::test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept` |
| 251 | `- context=context, profile=profile))`<br>`+ profile=profile))` | killed | `tests/test_ai_gateway.py::test_the_stable_prefix_is_cached_and_the_calls_own_data_is_not` |
| 252 | `- context=context, profile=profile))`<br>`+ context=context, ))` | killed | `tests/test_ai_gateway_ask.py::test_thinking_off_sends_the_model_s_own_form_and_records_it` |

### `modules.ai.profiles.load_pins`

- Baseline: the tests passed on the committed file (3.1 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py`.
- Mutants: 28, killed 25, survived 3 (modules.ai.profiles.x_load_pins__mutmut_10, modules.ai.profiles.x_load_pins__mutmut_12, modules.ai.profiles.x_load_pins__mutmut_18).

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- out = {}`<br>`+ out = None` | killed | `tests/test_ai_gateway_ask.py` |
| 2 | `- for name in sorted(os.listdir(folder)):`<br>`+ for name in sorted(None):` | killed | `tests/test_ai_gateway_ask.py` |
| 3 | `- for name in sorted(os.listdir(folder)):`<br>`+ for name in sorted(os.listdir(None)):` | killed | `tests/test_ai_gateway_ask.py` |
| 4 | `- if not name.endswith(".json"):`<br>`+ if name.endswith(".json"):` | killed | `tests/test_ai_gateway_ask.py` |
| 5 | `- if not name.endswith(".json"):`<br>`+ if not name.endswith(None):` | killed | `tests/test_ai_gateway_ask.py` |
| 6 | `- if not name.endswith(".json"):`<br>`+ if not name.endswith("XX.jsonXX"):` | killed | `tests/test_ai_gateway_ask.py` |
| 7 | `- if not name.endswith(".json"):`<br>`+ if not name.endswith(".JSON"):` | killed | `tests/test_ai_gateway_ask.py` |
| 8 | `- continue`<br>`+ break` | killed | `tests/test_ai_gateway_ask.py::test_a_file_that_is_not_a_pin_is_passed_over_and_the_rest_still_load` |
| 9 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(None, encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 10 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, name), encoding=None) as fh:` | survived |  |
| 11 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 12 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, name), ) as fh:` | survived |  |
| 13 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(None, name), encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 14 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, None), encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 15 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(name), encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 16 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, ), encoding="utf-8") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 17 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, name), encoding="XXutf-8XX") as fh:` | killed | `tests/test_ai_gateway_ask.py` |
| 18 | `- with open(os.path.join(folder, name), encoding="utf-8") as fh:`<br>`+ with open(os.path.join(folder, name), encoding="UTF-8") as fh:` | survived |  |
| 19 | `- pin = json.load(fh)`<br>`+ pin = None` | killed | `tests/test_ai_gateway_ask.py` |
| 20 | `- pin = json.load(fh)`<br>`+ pin = json.load(None)` | killed | `tests/test_ai_gateway_ask.py` |
| 21 | `- if sorted(pin) != sorted(PIN_KEYS):`<br>`+ if sorted(None) != sorted(PIN_KEYS):` | killed | `tests/test_ai_gateway_ask.py` |
| 22 | `- if sorted(pin) != sorted(PIN_KEYS):`<br>`+ if sorted(pin) == sorted(PIN_KEYS):` | killed | `tests/test_ai_gateway_ask.py` |
| 23 | `- if sorted(pin) != sorted(PIN_KEYS):`<br>`+ if sorted(pin) != sorted(None):` | killed | `tests/test_ai_gateway_ask.py` |
| 24 | `- raise ValueError(f"pin {name}: keys {sorted(pin)}, expected {sorted(PIN_KEYS)}")`<br>`+ raise ValueError(None)` | killed | `tests/test_ai_gateway_ask.py::test_every_pin_file_is_exactly_its_keys_and_every_task_has_one` |
| 25 | `- raise ValueError(f"pin {name}: keys {sorted(pin)}, expected {sorted(PIN_KEYS)}")`<br>`+ raise ValueError(f"pin {name}: keys {sorted(None)}, expected {sorted(PIN_KEYS)}")` | killed | `tests/test_ai_gateway_ask.py::test_every_pin_file_is_exactly_its_keys_and_every_task_has_one` |
| 26 | `- raise ValueError(f"pin {name}: keys {sorted(pin)}, expected {sorted(PIN_KEYS)}")`<br>`+ raise ValueError(f"pin {name}: keys {sorted(pin)}, expected {sorted(None)}")` | killed | `tests/test_ai_gateway_ask.py::test_every_pin_file_is_exactly_its_keys_and_every_task_has_one` |
| 27 | `- out[name[:-len(".json")]] = pin`<br>`+ out[name[:-len(".json")]] = None` | killed | `tests/test_ai_gateway_ask.py` |
| 28 | `- out[name[:-len(".json")]] = pin`<br>`+ out[name[:+len(".json")]] = pin` | killed | `tests/test_ai_gateway_ask.py` |

## 2026-10-26: History's AI-call record (15.14 part A), changed lines only, at 16c65d1b

**What changed in the tier since b06d8046** (the last proved commit, the section above):
`gateway.ask` takes `subject` (what the call is about: the device, the alert or the query)
and writes it on the call's row, sent or refused (PHASE8_PLAN 15.14: "recorded at the source").
The signature (lines 132 to 133), its docstring (140 to 142) and the row (149 to 150); no
other function of the tier changed (`git diff b06d8046 16c65d1b` over `gateway.py`,
`profiles.py`, `connection.py` and `redact.py`: 7 lines added, 3 removed, all in `ask`).

**The method**, as the section above (the operator's sprint ruling of 2026-10-25): the mutants
on the changed lines only, plus a must-die canary, in a clean checkout of 16c65d1b, one at a
time, the aimed tests `tests/test_ai_gateway_ask.py` (the subject written with the call, sent
or refused) and `tests/test_ai_gateway.py`, the file restored from its copy and compared.

**The result: no survivor.** The deploy that carries it waited for this.

| function | mutants | killed | survived | canary | baseline | file restored |
|---|---|---|---|---|---|---|
| `modules.ai.gateway.ask` | 18 | 18 | 0 | killed | passed | identical |
| **all 1** | **18** | **18** | **0** | | | |

### `modules.ai.gateway.ask`

- Baseline: the tests passed on the committed file (1.5 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged`.
- Mutants: 18, killed 18, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 13 | `- row = {"id": call_id, "feature": feature, "actor": actor, "model": model,`<br>`- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`- "subject": dict(subject or {})}`<br>`+ row = None` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 22 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "XXpromptXX": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 23 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "PROMPT": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 24 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[1]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 25 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[2]}", "schema": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 26 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "XXschemaXX": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 27 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "SCHEMA": "", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 28 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "XXXX", "detail": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 29 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "XXdetailXX": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 30 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "DETAIL": "", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 31 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "XXXX", "cost_usd": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_an_answer_is_returned_and_recorded_whole` |
| 32 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "XXcost_usdXX": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 33 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "COST_USD": 0.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 34 | `- "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 0.0,`<br>`+ "prompt": f"{prompt[0]}.v{prompt[1]}", "schema": "", "detail": "", "cost_usd": 1.0,` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 35 | `- "subject": dict(subject or {})}`<br>`+ "XXsubjectXX": dict(subject or {})}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 36 | `- "subject": dict(subject or {})}`<br>`+ "SUBJECT": dict(subject or {})}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 37 | `- "subject": dict(subject or {})}`<br>`+ "subject": dict(None)}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |
| 38 | `- "subject": dict(subject or {})}`<br>`+ "subject": dict(subject and {})}` | killed | `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged` |

## 2026-10-26: the AI day cap's stated boundary, changed lines only, at e87f1dd8

**What changed in the tier since 16c65d1b** (the last proved commit, the section above):
`gateway.ask` reads the cap's day from its one home, `calls.today()` (the stated boundary's
midnight, UTC by default; the operator's order of 2026-10-26 ~07:4x UTC, item 2), where it had
computed the UTC day inline (lines 220 to 222: the comment and `day = today or
calls.today()`), and the module's now-unused `import datetime` is removed. No other function
of the tier changed (`git diff 16c65d1b e87f1dd8` over `gateway.py`, `profiles.py`,
`connection.py` and `redact.py`: 3 lines added, 3 removed, all in `gateway.py`).

**The method**, as the sections above: the mutants on the changed lines only, plus a must-die
canary, in a clean checkout of e87f1dd8, one at a time, the aimed tests
`tests/test_ai_gateway_ask.py`, `tests/test_ai_gateway.py` and `tests/test_ai_day_boundary.py`
(the counter and the gateway counting the stated day), the file restored from its copy and
compared.

**The result: no survivor.** The deploy that carries it waited for this.

| function | mutants | killed | survived | canary | baseline | file restored |
|---|---|---|---|---|---|---|
| `modules.ai.gateway.ask` | 2 | 2 | 0 | killed | passed | identical |
| **all 1** | **2** | **2** | **0** | | | |

### `modules.ai.gateway.ask`

- Baseline: the tests passed on the committed file (4.3 s).
- Canary: the body replaced by `raise RuntimeError("the tier hand check's canary: this function must not pass")`, **killed** by `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged`.
- Mutants: 2, killed 2, survived 0.

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 318 | `- day = today or calls.today()`<br>`+ day = None` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |
| 319 | `- day = today or calls.today()`<br>`+ day = today and calls.today()` | killed | `tests/test_ai_gateway_ask.py::test_an_unreadable_record_is_refused_in_its_words` |

