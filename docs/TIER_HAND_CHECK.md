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

## 2026-10-27: the AI spend caps with no program maximum, changed lines only, on the change's tree

**What changed in the tier since e87f1dd8** (the last proved change, the section above): the
operator's cap order of 2026-10-27 (C1861). `gateway.day_cap()` is new: the installation's day
cap in US dollars, or None, an admin's explicit "no cap" stored as null, never read from a key
that was not set. `gateway.caps` reads it. `gateway.ask` skips the day cap's comparison when it
is None and says "no day cap is set" in every cap refusal. No other function of the tier
changed (`git diff` over `gateway.py`, `profiles.py`, `connection.py` and `redact.py`: only
`gateway.py`, lines 22 to 23, 59 to 85, 233 to 240 and 247 to 248).

**The method**, as the sections above: the mutants mutmut 3.8.0 generates on those lines, plus
a must-die canary, one at a time, the aimed tests `tests/test_ai_gateway_ask.py`,
`tests/test_ai_gateway.py`, `tests/test_ai_gateway_parts.py`, `tests/test_ai_day_cap.py` and
`tests/test_ai_card.py`, the file restored from its copy and compared. It ran in a throwaway
worktree of e314aec9 with the change applied (its `gateway.py` the one committed with C1861),
before the commit, so the deploy waits for nothing.

**The result: 53 mutants, 51 killed, 2 survived, both equivalent.** Every canary was killed.

| function | mutants | killed | survived | canary | baseline | file restored |
|---|---|---|---|---|---|---|
| `modules.ai.gateway.day_cap` | 9 | 7 | 2 (equivalent) | killed | passed | identical |
| `modules.ai.gateway.caps` | 5 | 5 | 0 | killed | passed | identical |
| `modules.ai.gateway.ask` | 39 | 39 | 0 | killed | passed | identical |
| **all 3** | **53** | **51** | **2** | | | |

**The two survivors are equivalent, listed by hand (CLAUDE.md: never chased with a test).**
Mutants 3 and 5 of `day_cap` change only the fallback argument of
`get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)` (to None, or to nothing). `get_setting`
returns the stored value, else `DEFAULTS.get(key, default)`, and the schema declares this key's
default (1.5, read from `settings_schema.DEFAULTS` on the change's tree), so the argument is
never reached. It is kept as a second statement of "a key never set is never no cap"; were the
schema's default removed, `tests/test_ai_gateway_parts.py`'s stored-value cases would read it.

### `modules.ai.gateway.day_cap`

- Baseline: the tests passed on the file as committed (5.5 s).
- Canary: the body replaced by a raise, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 9, killed 7, survived 2 (equivalent, above).

| # | change (− committed, + mutant) | outcome | killed by |
|---|---|---|---|
| 1 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = None` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 2 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting(None, DEFAULT_CAP_PER_DAY)` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_cap_a_call_is_sent_whatever_today_s_spend` |
| 3 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting("ai_cap_usd_per_day", None)` | survived, equivalent | |
| 4 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting(DEFAULT_CAP_PER_DAY)` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 5 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting("ai_cap_usd_per_day", )` | survived, equivalent | |
| 6 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting("XXai_cap_usd_per_dayXX", DEFAULT_CAP_PER_DAY)` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_cap_a_call_is_sent_whatever_today_s_spend` |
| 7 | `- raw = get_setting("ai_cap_usd_per_day", DEFAULT_CAP_PER_DAY)`<br>`+ raw = get_setting("AI_CAP_USD_PER_DAY", DEFAULT_CAP_PER_DAY)` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_cap_a_call_is_sent_whatever_today_s_spend` |
| 8 | `- if raw is None:`<br>`+ if raw is not None:` | killed | `tests/test_ai_gateway_ask.py::test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 9 | `- return float(raw)`<br>`+ return float(None)` | killed | `tests/test_ai_gateway_ask.py::test_with_no_day_cap_a_call_is_sent_whatever_today_s_spend` |

### `modules.ai.gateway.caps`

- Baseline: the tests passed on the file as committed (4.3 s).
- Canary: the body replaced by a raise, **killed** by `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.
- Mutants: 5, killed 5, survived 0: each renames a key of the returned dict (`per_call` or
  `per_day`, to `XX…XX` or upper case) or passes None for the feature, and each is killed by
  `tests/test_ai_gateway_ask.py::test_a_prompt_at_its_bound_is_sent`.

### `modules.ai.gateway.ask`

- Baseline: the tests passed on the file as committed (4.3 s).
- Canary: the body replaced by a raise, **killed** by `tests/test_ai_gateway_ask.py::test_hosted_ai_off_is_refused_whole_and_logged`.
- Mutants: 39 (numbers 300 to 324, 335, 337, 343 to 354), killed 39, survived 0.

| # | change (− committed, + mutant) | killed by |
|---|---|---|
| 300 to 306 | `uncapped = "" if cap["per_day"] is not None else f"; {NO_DAY_CAP_WORDS}"`: None; the condition forced either way; "XXXX"; the key renamed (2); `is None` | `test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` (300, 301, 303, 306), `test_with_no_day_cap_a_cap_s_refusal_says_no_day_cap_is_set` (302), `test_a_prompt_at_its_bound_is_sent` (304, 305) |
| 307 to 311 | `worst = worst_case_usd(model, body)`: None, either argument None or dropped | `test_a_prompt_at_its_bound_is_sent` |
| 312 to 314 | `if worst > cap["per_call"]`: `>=`, the key renamed (2) | `test_a_prompt_at_its_bound_is_sent` |
| 315 to 324 | the per-call refusal: its kind None, dropped or renamed (2); its words None, dropped or the key renamed (2); `worst_usd` None or dropped | `test_a_worst_case_over_the_call_cap_is_refused_with_both_operands` |
| 335, 337, 343, 344 | the unreadable record's refusal: its words None or dropped; `spent["error"]` renamed (2) | `test_an_unreadable_record_is_refused_in_its_words` |
| 345 to 354 | `if cap["per_day"] is not None and spent["usd"] + worst > cap["per_day"]`: `or`; the keys renamed (6); `is None`; `-` for `+`; `>=` | `test_a_prompt_at_its_bound_is_sent` (345, 346, 347, 350, 351, 353, 354), `test_the_day_cap_is_refused_with_its_three_operands` (348, 349), `test_a_days_spend_reaching_the_cap_exactly_is_sent` (352) |

(All in `tests/test_ai_gateway_ask.py`. The machine log, one JSON line per step, is scratch
tooling, as above.)

## 2026-10-27: an SDN controller's answer masked whole, changed lines only, on the change's tree

**What changed in the tier:** `modules/sdn/drivers/base.py`'s `ControllerDriver._scrub`, the
masking of every answer an SDN controller gives (S1). It replaced the connection's own
credential values in every string but ran `redact_text` on the `error` and `detail` words
alone; the masking scan (tests/test_url_userinfo_masked.py, with `_scrub` added as an entry
point) found a URL's user part in a list's string unmasked. Now every string is masked: its
credential values replaced, then `redact_text` (`return redact_text(node) if node else node`),
and the walk's result returned (`return walk(answer)`, the separate `error`/`detail` pass gone).

**The method:** `_scrub` is a class method, which the harness's function finder does not reach,
so each mutant of the changed lines was applied by hand (`scrub_mut.py`, scratch tooling), one
at a time, in a throwaway worktree of the working state (`scripts/nmas-control`, the untracked
SDN files staged there as the gate's snapshot does), the aimed tests run with `-x`:
tests/test_url_userinfo_masked.py, tests/test_sdn_drivers.py, tests/test_sdn_ryu.py,
tests/test_sdn_collect.py.

**The result: 5 mutants, 5 killed, the canary killed, one equivalent.**

| mutant | change | outcome | killed by |
|---|---|---|---|
| baseline | none | passed (567) | |
| canary | the body replaced by a raise | killed | `test_every_masking_entry_point_masks_a_url_s_user_part[modules/sdn/drivers/base.py:_scrub]` |
| no_mask | `return node` (no `redact_text`) | killed | the same |
| cond_inverted | `if not node` | killed | the same |
| no_walk | `return answer` | killed | the same |
| walk_none | `return walk(None)` | killed | the same |
| mask_raw | a line after the `return` | equivalent | (unreachable: the hand-written mutant put a statement after the return, so nothing changed) |

The machine log is scratch tooling, as above.

## 2026-10-27: one press, one provider call (C1854) with the operator's request identity, changed lines only, on the change's tree

**What changed in the tier:** the gateway's egress path (`modules/ai/gateway.py` `ask`, `from_row`,
the new `_joined`; `modules/ai/presses.py`, new: `_sha`, `request_digest`, `current_press`,
`_prune`, `_done_call`, `_join`, `once`, `_Slot`), `modules/identity.py`'s new `access_scope`, and
`modules/ai/calls.py`'s `spent_usd`. A press carries a key; a key already seen returns its call;
an identical request in flight is joined; the request's identity is explicit (the operator's
design, 2026-10-27 ~06:3x UTC: feature, network, subject, prompt version, model and the
requester's access scope, `presses.IDENTITY`); a join across access scopes is refused
(`other_scope`, recorded, nothing returned or sent); each joiner has its own row in the record of
AI calls (verdict `joined`, cost 0, the call it joined), which replaced `calls.record_use` on the
call. One defect found by the check and fixed: `request_digest` dumped with `ensure_ascii=False`,
so a lone surrogate in a call's data raised before anything was recorded; it is `ensure_ascii=True`,
which is also what the adapter sends.

**The method:** `scratchpad/hand_check.py` over each top-level function holding changed lines
(the changed lines' mutants and a canary that must die), in a throwaway worktree of the change
(ec01d2d5 plus C1852's commit plus this change), the aimed tests: tests/test_ai_presses.py,
tests/test_explain_kept.py, tests/test_ai_gateway_ask.py, tests/test_ai_gateway.py,
tests/test_ai_gateway_parts.py, tests/test_identity.py, tests/test_history_ai_calls.py. `_Slot`'s
methods, which the harness's function finder does not reach, by hand (`slot_mut.py`).
`history_sources.ai_calls`'s changed lines draw History rows (not the tier); its harness run was
stopped at 18 GiB (the harness builds every mutant of a large module in memory) and its lines are
held by four hand controls instead (the join drawn as an ordinary call; its outcome not the
call's; its row opening itself; no "Joined by").

**The result: every non-equivalent mutant killed; every canary killed; every file restored
identical.**

| function | mutants | killed | equivalent (survived) |
|---|---|---|---|
| presses `_sha` | 8 | 6 | 2 |
| presses `request_digest` | 34 | 32 | 2 |
| presses `current_press` | 32 | 29 | 3 |
| presses `_prune` | 13 | 13 | 0 |
| presses `_done_call` | 11 | 11 | 0 |
| presses `_join` | 44 | 44 | 0 |
| presses `once` | 146 | 135 | 11 |
| gateway `ask` (changed lines) | 67 | 67 | 0 |
| gateway `from_row` | 57 | 51 | 6 |
| gateway `_joined` | 38 | 34 | 4 |
| identity `access_scope` | 38 | 37 | 1 |
| calls `spent_usd` | 24 | 24 | 0 |
| `_Slot` (by hand, with two canaries) | 9 | 8 | 1 |

**Each equivalent, and why nothing observable changes:**
- `_sha`: the codec named `"UTF-8"` (codec names are case-insensitive); the separator `b"XX\0XX"`
  (within one program equal parts hash equal and different parts different; nothing outside the
  process computes the digest).
- `request_digest`: `ensure_ascii` omitted, twice (`True` is the default).
- `current_press`: `or "XXXX"` (four characters still fail `KEY_SHAPE`, so the press has no key);
  the `"XXkey-XX"` and `"KEY-"` prefixes (nothing reads slot names by prefix; both still differ
  from `req-`).
- `once`: the "running" marks on the request and key slots (a marker is read only after its lock
  is taken, and only `done` with a string id is compared, so any other state reads as no finished
  call); `slots[1]` marked running (differs only when a holder died after a `done` naming a call
  missing from the record, where the press still makes its own call with one true warning);
  `or "XXXX"` on the call id (every `make()` result carries a non-empty one).
- `from_row`: the `id` default, three (the row comes from `calls.find(id)`, which matches on it);
  `"unknown"`, two (every recorded row has a verdict); the detail's `or "XXXX"` (every failure's
  detail is non-empty).
- `_joined`: the explicit cost 0 dropped (the row's own `cost_usd` is 0.0, no send having priced
  it); the `recorded` default, three (`calls.record` always returns `recorded`).
- `access_scope`: the defensive `except` (`request_identity()` and `viewer()` already catch
  everything).
- `_Slot.release` without its unlock: `os.close` of the slot's only descriptor releases its
  `flock`. (`claim_never_times_out` is killed by the process bound, the slot-held test never
  returning, exit 124 at `NMAS_TEST_TIMEOUT=60`, not by an assertion.)

The machine logs are scratch tooling (`hc-c1852.jsonl`, `c1854-kill3.jsonl`).

## 2026-10-27: secrets compared by keyed hash (C1693, C1792), on the change's tree

**What changed in the tier:** a new module, `modules/secret_compare.py` (C1792's design, built
for C1693's Normalise proof; C924 reuses it), which reads the values in masked positions and
compares them by HMAC under a per-process key; `modules/nsot/intent_normalise.py`'s
`_masked_compared`, which hydrates each document's secrets from the credential store and
renders the true configuration to hand it the values; and `modules/nsot/hostvars.py`'s
`write_committed_text`, the leak check before committed intent is written, whose changed lines
now check the text given and the canonical text written.

**The method.** In a throwaway worktree of the working state (`scripts/nmas-control`), one
function at a time. `secret_compare.py` is small: the harness (`hand_check.py`, mutmut 3.8.0's
generator) ran every mutant of each function, with tests/test_secret_compare.py. The two larger
modules were not given to the harness (it builds every mutant of the whole file in memory):
their changed lines were mutated by hand (`c1693_hand_mutants.py`, scratch tooling), each
mutant one exact replacement, the aimed tests run with `-x` (tests/test_intent_normalise.py for
`_masked_compared`; tests/test_hostvars_secrets.py, tests/test_intent_round_trips.py and
tests/test_intent_normalise.py for `write_committed_text`).

**The result.** Every canary killed. Every non-equivalent survivor killed by a test written for
it, and the run repeated.

| function | mutants | killed | equivalent | canary |
|---|---|---|---|---|
| `secret_compare._digest` | 9 | 8 | 1 | killed |
| `secret_compare.masked_values` | 34 | 34 | 0 | killed |
| `secret_compare._masked_lines` | 17 | 16 | 1 | killed |
| `secret_compare._same` | 11 | 11 | 0 | killed |
| `secret_compare.compare` | 88 | 88 | 0 | killed |
| `intent_normalise._masked_compared` (by hand) | 12 | 12 | 0 | killed |
| `hostvars.write_committed_text`, changed lines (by hand) | 6 | 5 | 1 | killed |

**Survivors killed by new tests:** `compare`'s `continue` made `break` and the `paired` entry's
key renamed (`test_an_unpaired_line_does_not_stop_the_lines_after_it`); the unpaired lines'
sort key dropped or made constant (`test_the_unpaired_are_in_order_by_side_then_line`);
`masked_values`' known-value label given a default (four mutants: removed by reading the table
by its key, which the pattern is built from); `_masked_compared`'s template name dropped
(`test_the_template_bound_to_the_device_is_the_one_compared`), the profile skipped
(`test_what_the_profile_adds_is_compared_too`), the platform taken from the inventory row
(`test_the_document_s_own_platform_is_rendered`), each document rendered twice or one
compared with itself (`test_each_document_is_rendered_with_its_own_values`); and
`write_committed_text`'s second leak check dropped
(`test_a_secret_spelled_in_escapes_is_refused_in_the_text_written`: a stored value hidden in
YAML escapes passes the first check and is written plainly by the serialiser).

**Equivalents, with why:**
- `_digest`: `"utf-8"` made `"UTF-8"`: Python's codec names are case-insensitive.
- `_masked_lines`: `(text or "")` made `(text or "XXXX")`: the line `XXXX` holds no masked
  value, so an empty text yields no masked line either way.
- `write_committed_text`: `canonical(text, hostname)` made `canonical(text)`: the name only
  words `canonical`'s refusal, which this path cannot reach (the leak check before it refuses a
  `secrets` block, and the document is otherwise its own serialisation).

The machine logs (one JSON line per step for the harness, one line per mutant by hand) are
scratch tooling, as above.

## 2026-10-27: AI cost safety, rules 1 to 5 and 9 (C1843): every call's trigger, the background switches and their caps, rebased on C1854's change, on the change's tree

**What changed in the tier:** two new modules and the gateway's spending path. `modules/ai/triggers.py`:
every AI call names its trigger (a person's press inside a verified request, an evaluation run,
or a background job on a finding deterministic code made), and `check` refuses one that names
none, or a malformed one, before the allowance, the key or the record is read.
`modules/ai/background.py`: background features are off by default per network; `admit` asks
whether the feature is on for its network, and `over_cap` asks whether the feature's spend today
and this month, plus this call's worst case, fits its own caps. The gateway: `ask` checks the
trigger first, then `admit` before the key; `_capped_send` asks `over_cap` after the
installation's day cap. `modules/ai/calls.py` gains the windowed reads the caps rest on:
`day_start`, `rows_since`, `day_rows` and `spent_usd`.

**The method:** `hand_check.py` (mutmut 3.8.0's generator) in a throwaway worktree of the change
(717a1c72, plus C1854's change, plus C1843). It ran one function at a time, with a canary that
must die for each, one pytest at a time. The functions: the gateway's `ask` and `_capped_send`
(changed lines); every function of `triggers`; background's `switches`, `entry_of`, `enabled`,
`caps_of`, `admit` and `over_cap`; and calls' four reads (changed lines). The aimed tests:
tests/test_ai_triggers.py, test_ai_background.py, test_ai_spend.py, test_ai_gateway.py,
test_ai_gateway_ask.py, test_ai_gateway_parts.py, test_ai_presses.py, test_ai_day_boundary.py.
Background's estimate and the admin's actions (`_frequency`, `measured_cost`, `estimate`,
`turn_on`, `turn_off`, `set_caps`, `_caps`, `_write`) send nothing, so they were outside the
check. A cap they write reaches a call only through `caps_of` and `over_cap`, which were
checked. Each survivor judged non-equivalent then got a test. To prove each kill, the survivor's
own line was applied by hand in a throwaway worktree of the working state
(`scripts/nmas-control`, `c1843_prove.py`), its aimed test run, and the failing test's name read:
66 survivors, 66 killed.

**The result: every non-equivalent mutant killed, every canary killed, every file restored
identical; no defect in the code.**

| function | mutants | killed by the suite | killed by a new test | equivalent |
|---|---|---|---|---|
| gateway `ask` (changed lines) | 39 | 39 | 0 | 0 |
| gateway `_capped_send` (changed lines) | 28 | 25 | 3 | 0 |
| triggers `person` | 4 | 4 | 0 | 0 |
| triggers `evaluation` | 12 | 11 | 0 | 1 |
| triggers `background` | 18 | 16 | 2 | 0 |
| triggers `actor_of` | 22 | 19 | 0 | 3 |
| triggers `_refused` | 7 | 7 | 0 | 0 |
| triggers `_person` | 38 | 33 | 5 | 0 |
| triggers `_evaluation` | 22 | 19 | 3 | 0 |
| triggers `_background` | 93 | 85 | 8 | 0 |
| triggers `check` | 32 | 32 | 0 | 0 |
| background `switches` | 7 | 5 | 0 | 2 |
| background `entry_of` | 14 | 13 | 1 | 0 |
| background `enabled` | 12 | 8 | 2 | 2 |
| background `caps_of` | 23 | 23 | 0 | 0 |
| background `admit` | 21 | 17 | 4 | 0 |
| background `over_cap` | 95 | 85 | 10 | 0 |
| calls `day_start` (changed lines) | 18 | 15 | 1 | 2 |
| calls `rows_since` (changed lines) | 34 | 19 | 15 | 0 |
| calls `day_rows` (changed lines) | 29 | 17 | 12 | 0 |
| calls `spent_usd` (changed lines) | 8 | 8 | 0 | 0 |
| **all** | **576** | **500** | **66** | **10** |

**Survivors killed by new tests** (in tests/test_ai_background.py unless named):
- `_capped_send`: the feature's caps judged on no day (so on the clock's day, not the day the
  gateway counts), and the refusal's worst case dropped from its row
  (`test_the_features_caps_count_on_the_calls_own_day_and_record_its_worst_case`).
  `over_cap`'s day dropped is killed by the same test.
- triggers `background`: a trigger naming no network given `list_slug("")`, which is
  `"default"` (it would spend under the Default list), or a made-up name
  (`test_a_background_call_naming_no_network_names_none_and_is_refused`).
- triggers `_person`, `_evaluation`, `_background`, five places: the taken trigger's `why` renamed
  or non-empty (tests/test_ai_triggers.py
  `test_a_trigger_taken_says_no_why_and_names_itself`). `_person`'s refusal reworded
  (`test_a_person_trigger_naming_an_evaluation_says_each_kind_names_its_own`). `_background`'s
  `isinstance` guard on the feature made always true, so a list raised `TypeError`, and its
  network test's `or` made `and`, so `7` reached `list_slug`
  (`test_a_background_trigger_whose_names_are_not_text_is_refused_not_raised`). The known
  features' and finding kinds' separators reworded
  (`test_the_refusals_list_every_feature_and_finding_kind`).
- `entry_of`: the `on is True` test made always true, so `{"on": false}`, `"true"`, `1` or no
  `on` read as on (`test_a_switch_stored_anything_but_on_true_admits_nothing`).
- `enabled`: the sort key made `(feature, feature)` or `(network, entry)`
  (`test_the_switches_on_are_listed_by_network_then_feature`).
- `admit`: the unreadable switches' words (the exception's type, the feature named)
  (`test_switches_that_cannot_be_read_are_said_and_refused`).
- `over_cap`: a switch turned off mid-call says `admit`'s words, not the fallback's, and its row
  names no cap (`test_a_switch_turned_off_mid_call_says_admits_words_and_names_no_cap`). An
  unreadable record's refusal names the day cap
  (`test_an_unreadable_record_stops_the_feature_on_its_day_cap`). `>` made `>=`, which refused a
  call that brings the spend exactly to the cap. The cap is what may be spent, and the
  installation's day cap uses `>` too
  (`test_a_call_that_brings_the_spend_exactly_to_the_cap_is_sent`; binary fractions keep the
  sum exact). The month's refusal said "today", or a reworded "this month"
  (`test_the_month_caps_refusal_names_this_month`; the existing month test skips on a month's
  first day, and this one names its own day).
- calls `day_start`: `astimezone(None)`, the host's local zone in place of UTC
  (tests/test_ai_day_boundary.py
  `test_a_days_start_is_said_in_utc_whatever_the_hosts_zone`, with `TZ=Asia/Tokyo`). Not a
  defect in the code, which converts to UTC. The mutant also changed no figure: every consumer
  compares instants or takes `.timestamp()`, and the mutant survived the suite on a host in
  MDT. The test holds the docstring's promise for a caller that writes the start with a "Z".
- calls `rows_since` (tests/test_ai_spend.py): the store's name dropped, so a record moved to
  the records database read the file left behind
  (`test_rows_since_reads_the_records_database_once_the_record_moved_there`). `skip_unparsable`
  dropped or false, so one torn line made every spend figure, and so every cap, unreadable
  (`test_rows_since_skips_a_torn_line_as_the_whole_read_does`). The unreadable check inverted,
  or matched against a misspelled state, and the log line's every part (11 mutants; two of them
  raised `KeyError` on an unreadable record)
  (`test_an_unreadable_record_is_said_and_logged_once`). The inverted check changes only the
  log: the answer is the store's either way.
- calls `day_rows` (tests/test_ai_spend.py): the zone asked dropped from the window's start or
  the row's day, so a zone east of UTC lost its day's first hours
  (`test_a_days_rows_are_read_in_the_zone_asked`). A day that is no date answered in another
  shape, which `spent_usd` then indexed
  (`test_a_day_that_is_no_date_holds_no_row`, nine mutants).

**Equivalents, with why:**
- triggers `evaluation`: `actor or ""` made `actor or "XXXX"`. `XXXX` does not start with
  `evaluation:`, so the run is `""` either way.
- triggers `actor_of`, three: the `or ""` defaults for `by`, `run` and `job` made `"XXXX"`.
  `actor_of` is called only from `check`, after the kind's own validation, so each is a
  non-empty string there: `by` a verified person, `run` matching the run's shape, `job` matching
  `_ID`.
- background `switches`, two: `get_setting(SETTING, {})` with its default `None` or omitted.
  The `or {}` after it reads both as `{}`.
- background `enabled`, two: the sort key `None` or omitted. The tuples' first two members
  (network, feature) are a dict's keys and never tie, so the entry is never compared and the
  order is the same.
- calls `day_start`, two: `datetime.time(0, 0)` made `time(0)` or `time(0, )`, which equal it.

The machine logs (`hc-c1843.jsonl`, one JSON line per step; `c1843-prove.jsonl`, one line per
survivor applied by hand) are scratch tooling, as above.

## 2026-10-27: an alert rule's change recorded masked (C1886), the masking lines only, by hand

**What touches the tier:** `modules/alert_rule_changes.py` keeps each alert rule change in a
records store; the row is masked by `redact.redact_payload` before it is kept, and a rule's
current facets are masked before they are compared with the kept ones, so a secret in a label
is never stored and a masked value never reads as moved. It changes no masking code; the two
lines that apply it are the tier's here.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
line in a `scripts/nmas-control` throwaway worktree of the change, then
tests/test_alert_rule_changes.py (`scratchpad/c1886_hm.py`).

| mutant | result | killed by |
|---|---|---|
| the kept row unmasked (`kept = dict(row)`) | killed | `test_a_secret_in_a_label_is_kept_masked_and_never_reads_as_moved` |
| the current facets compared unmasked | killed | the same test |
| canary: the record step raises | killed | `test_two_reads_record_a_baseline_then_the_change_once` |

**The result: every mutant killed; the canary killed; the working tree untouched (nmas-control's
fingerprint).**

## 2026-10-27: SDN classify_threat's egress gates (S7), by hand

**What touches the tier:** `closed_loop.classify_pack` sends a detection's flows and port rates
(the topology class) to the provider through `gateway.ask`. In front of the call it refuses a
pack whose hash moved, a network carrying a classification marking, and a network whose topology
class is off; each refusal sends nothing. No line of `gateway.py` or `triggers.py` changed; the
background feature `sdn_classify` (`background.FEATURES`) is declared, and the gateway still
refuses it as `feature_off` until an admin turns it on (its controls: the feature undeclared
fails 6 tests).

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
lines in a `scripts/nmas-control` throwaway worktree, then tests/test_sdn_classify.py and
tests/test_sdn_classify_cases.py (`scratchpad/s7_hm.py`).

| mutant | result | killed by |
|---|---|---|
| the marking ignored (`if False:`) | killed, by a test written for it | `test_a_network_carrying_a_classification_marking_sends_nothing` |
| the marking inverted | killed | 25 tests (every call refused) |
| the topology gate ignored | killed | `test_the_topology_class_off_sends_nothing` |
| the topology gate inverted | killed | 25 tests |
| the pack's hash ignored | killed | `test_a_pack_changed_since_it_was_kept_is_refused_and_nothing_is_sent` |
| canary: the marking step raises | killed | 25 tests |

**The result: every mutant killed (the marking's first run survived; the test above was written
and the mutant run again); the canary killed.**

## 2026-10-27: a background feature's approval lasts 14 days (Settings › AI, C1843), by hand

**What touches the tier:** `modules/ai/background.py`, the gateway's switch question. Board
AI3's decision 5 (docs/STANDING_APPROVAL_LOG.md, "Boards AI1 to AI5") makes an approval last
14 days: `approval_ends` (the switch's `at` plus `APPROVAL_DAYS` days; None for an `at` Mercury
did not write) and `in_force` are new; `entry_of` and `enabled` answer only a switch in force,
so `admit` refuses a call whose approval ended (`feature_off`, naming when it ended). Every
change makes the gateway refuse more, never less. `turn_off` (sends nothing) now removes a
switch whose approval ended.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
line in a `scripts/nmas-control` throwaway worktree, then tests/test_settings_ai_v2.py and
tests/test_ai_background.py (`scratchpad/settings_ai_controls.py`).

| mutant | result | killed by |
|---|---|---|
| `in_force`: `<` made `<=` (in force at its end) | killed | `test_an_approval_ends_after_14_days_and_the_gateway_refuses_naming_its_end` |
| `approval_ends`: `at - 14 days` | killed | 21 tests |
| `approval_ends`: one day, not 14 | killed, by the test made independent of `approval_ends` | the same test (its first run survived: it counted the end with `approval_ends` itself) |
| `approval_ends`: an unreadable `at` in force for ever | killed, by a test written for it | `test_a_switch_with_no_time_mercury_wrote_is_never_in_force` (4 cases) |
| `entry_of` ignores the approval's end | killed | `test_an_approval_ends_after_14_days_and_the_gateway_refuses_naming_its_end` |
| `enabled` ignores the approval's end | killed | the same test |
| `admit`'s ended words dropped | killed | the same test |
| `turn_off` reads only a switch in force | killed | `test_turn_off_removes_a_switch_whose_approval_ended` |
| canary: `in_force` raises | killed | 31 tests |

**The result: every mutant killed (two first survived; the test above was made independent and
one written, and both run again); the canary killed.**

## 2026-10-27: a background call's network asked by its one id (C1945), by hand

**What touches the tier:** `modules/ai/background.py`, the gateway's switch question. `_network`
now asks `listref.network_id` (C1903's resolver, which raises for a name no network answers to)
in place of `listref.resolve` (which derives a slug for any name and never raised, so its "not a
network Mercury holds" refusal could not fire). `admit` asks it first: a trigger naming a
network Mercury does not hold is refused naming the name and the registered networks, and one
naming another spelling of a network is refused naming its id, before any switch is read. Every
change makes the gateway refuse more, never less: before it, a switch stored on under a name no
network answers to admitted its call.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
line in a `scripts/nmas-control` throwaway worktree of the change, then
tests/test_ai_background.py, tests/test_settings_ai_v2.py, tests/test_sdn_classify.py and
tests/test_ai_spend.py (`scratchpad/bfix_hm.py`). The baseline passed (137 tests).

| mutant | result | killed by |
|---|---|---|
| `_network` back to `listref.resolve(network).slug` | killed | `test_an_unknown_feature_or_network_is_refused`, `test_a_background_call_for_a_network_mercury_does_not_hold_is_refused_naming_it` |
| `admit` does not ask the network (`canonical = trigger.get("network")`) | killed | `test_a_background_call_for_a_network_mercury_does_not_hold_is_refused_naming_it`, `test_a_background_call_naming_another_spelling_of_a_network_is_refused_naming_its_id` |
| the network's refusal admits (`return ""`) | killed | `test_a_background_call_for_a_network_mercury_does_not_hold_is_refused_naming_it` |
| the spelling check removed (`if False:`) | killed | `test_a_background_call_naming_another_spelling_of_a_network_is_refused_naming_its_id` |
| the spelling check inverted (`==`) | killed | 23 tests |
| canary: `_network` raises | killed | 80 tests |

**The result: every mutant killed; the canary killed; the working tree untouched (nmas-control's
fingerprint).**

## 2026-10-27: the AI calls record's window kept per process (C1973), by hand

**What touches the tier:** `modules/records_migrate.py`, the read every spend figure is taken from
(`calls.rows_since` → `day_rows` → `spent_usd`, which the gateway's day and month caps and the
background features' caps compare against). `store_rows_since` now reads the file through
`_tail_rows_kept`: the window's rows are kept per process, and a later read parses only the lines
appended since, after checking that the file is the same one (device and inode), no shorter, and
unchanged in its last `KEPT_EDGE` bytes before the kept end; otherwise it reads the file whole
again. A line is kept only once its newline is written. Each kept row leaves out the keys the
caller names (`calls.WINDOW_WITHOUT`, the request as sent): a month of whole rows measured 363 MiB
in a process on the host. The cap's risk is an undercount, which would let a call past its cap, so
each mutant below makes the kept answer differ from a whole read's, or a request survive.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
line in a `scripts/nmas-control` throwaway worktree of the change, then
tests/test_v2_page_work_budget.py, tests/test_ai_spend.py, tests/test_ai_gateway.py,
tests/test_ai_background.py and tests/test_records_db.py (`scratchpad/kept_hm.py`). The baseline
passed (176 tests).

| mutant | result | killed by |
|---|---|---|
| the file's identity not compared (a replaced file answered from the kept rows) | killed | `test_a_file_replaced_by_another_is_read_whole` |
| the kept window's floor not compared (an older window answered from a newer kept one) | killed | `test_the_features_month_cap_stops_it`, `test_the_month_caps_refusal_names_this_month` |
| the edge not compared (`and True`) | killed | `test_the_windows_work_is_the_windows_not_the_records` |
| a half-written line taken (`whole = len(added)`) | killed | `test_a_line_half_written_at_a_read_is_counted_once_it_is_whole` |
| the kept end not advanced (appended rows counted again) | killed | `test_the_kept_read_answers_what_a_whole_read_answers` |
| an appended row from before the floor kept (the window not ended there) | killed | `test_a_row_appended_from_before_the_window_ends_it_as_a_whole_read_does` |
| a narrower window not cut at its own floor (`_window`'s `if False:`) | killed | `test_a_row_appended_from_before_the_window_ends_it_as_a_whole_read_does` |
| the window's start made strict (`at > since`) | killed | `test_the_window_is_exactly_what_a_whole_read_filtered_by_time_gives` |
| the first read keeps the request | killed | `test_a_windowed_call_holds_no_request_and_a_found_call_does` |
| an appended row keeps the request | killed | `test_a_windowed_call_holds_no_request_and_a_found_call_does` |
| `_without` keeps every key | killed | `test_a_windowed_call_holds_no_request_and_a_found_call_does` |
| `calls.rows_since` passes no `drop` | killed | `test_a_windowed_call_holds_no_request_and_a_found_call_does` |
| the size not compared (`st.st_size >= k["end"]` removed) | survived: equivalent | a file shorter than the kept end gives fewer than the compared bytes at the edge (`_edge` reads from `end - KEPT_EDGE` to `end`, or from 0 when `end` is under `KEPT_EDGE`), so the edge comparison already sees every shortening |
| canary: `_tail_rows_kept` raises | killed | 45 tests |

The first run, before the request was left out and the four tests named above were added, had
four survivors (identity, size, half-written line, out-of-order row) and the request kept per
process; the tests and the drop are what this change adds to the agent's version.

**The result: every mutant killed but one equivalent, named; the canary killed; the working tree
untouched (nmas-control's fingerprint).**

## 2026-10-27: SDN's response policy in what the classifier is sent, and a normal-traffic collection classified (the Lab 8 walk's objectives 3.1 and 2.3), by hand

**What touches the tier:** `modules/sdn/closed_loop.py`, what leaves the host for the AI
provider. (1) The response policy (`policy`, `policy_refusal`): the catalogue the model is sent
(`catalogue_for_ai(allowed)`, through `request_blocks`) lists only the actions the network allows
for the detection's rule, and `none`; an unreadable policy allows nothing and sends nothing. (2)
`prepare_collection`, a new request shape: one live collection with no detection (prompt
`sdn_classify.v2`), behind the same gates as `classify_pack` (the classification marking, the
topology class, the limits, the policy), plus a refusal for another network's collection or one
that read no switch; the 50 busiest flows sent and the rest counted; the call made only by
`scripts/nmas-sdn-classify-normal`, as an evaluation.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it: each
mutant applied as its exact line in a `scripts/nmas-control` throwaway worktree, then the aimed
tests (tests/test_sdn_policy.py, tests/test_sdn_classify_normal.py, tests/test_sdn_response_log.py
and the SDN classify tests); a must-die canary first for each part.

**Part 1, the policy in what is sent.** Canary: `request_blocks` returns `{}`: killed, 38 tests.

| mutant | result | killed by |
|---|---|---|
| H1 the catalogue sent unfiltered | killed | tests/test_sdn_policy.py's two catalogue-sent tests; tests/test_sdn_classify_normal.py's catalogue test |
| H2 classify sends every action | killed | tests/test_sdn_policy.py's two catalogue-sent tests |
| H3 classify's policy gate skipped | killed | `test_a_policy_that_cannot_be_read_allows_nothing_and_sends_nothing` |
| H4 the check's policy test skipped | killed | `test_a_drop_for_a_scan…`, `test_in_the_loop_the_refused_drop…` |
| H5 the refusal's comparison skipped | killed | 4 tests in tests/test_sdn_policy.py (preview, confirm, check, loop) |
| H6 the unreadable branch skipped | killed | `test_a_policy_that_cannot_be_read_allows_nothing…` |
| H7 the policy's read fails open | killed | both fail-closed tests |
| H8 the names not sent | killed | `test_the_request_says_no_rule_fired…` |
| H9 `none` answers no rule | survived, then killed by the test added for it | `test_sdn_lab_s_policy_sends…` |
| H10 a flow piece loses its packet counts | killed | `test_a_busy_collection_sends_its_busiest_flows…` |

**Part 3, a collection classified.** Canary: the request's data emptied: killed, 6 tests.

| mutant | result | killed by |
|---|---|---|
| N1 every flow sent | killed | the busy-collection test |
| N2 the detection piece cites the flows | killed | `test_the_request_says_no_rule_fired…` |
| N3 the DPIDs not added to the names | killed | the request test, the threat test |
| N4 the marking gate skipped | killed | the gates test |
| N5 the topology gate skipped | killed | the gates test |
| N6 the policy gate skipped | killed | the gates test |
| N7 the no-switch gate skipped | killed | the no-switch and other-network test |
| N8 the network gate skipped | killed | the no-switch and other-network test |
| N9 the catalogue every action | killed | `test_the_catalogue_sent_is_the_actions_the_network_allows` |
| N10 prompt v1 used | killed | the request test |
| N11 a threat never reported | killed | the threat test, the runs test |
| N12 the call not an evaluation | killed | 6 tests |

**The result: every mutant killed (H9 after its test was added); both canaries killed; the
working tree untouched (nmas-control's fingerprint).**

## 2026-10-27: the classifier's catalogue in the policy's order, its default marked (C1988), by hand

**What touches the tier:** `modules/sdn/closed_loop.py`, `catalogue_for_ai`: what the
classifier is sent in its cached context. The allowed actions are listed in the network's policy
order (they were in the catalogue's), the first marked `default: true` and the others `false`,
`none` last and unmarked; duplicates and ids not in the catalogue dropped. Prompt v3 (a new file,
`prompts/sdn_classify.v3.md`, not adopted by this change) tells the model to take the action
marked default. Nothing new is sent but the mark; nothing the policy disallows is sent, as before.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12): each mutant applied as its exact
line in a `scripts/nmas-control` throwaway worktree of the change, then tests/test_sdn_policy.py,
tests/test_sdn_classify.py, tests/test_sdn_classify_normal.py, tests/test_sdn_loop_live.py and
tests/test_sdn_classify_cases.py (`scratchpad/cat_hm.py`). The baseline passed (126 tests).

| mutant | result | killed by |
|---|---|---|
| the catalogue's order (`[k for k in CATALOGUE if k in allowed]`) | killed | `test_the_catalogue_is_sent_in_the_policy_s_order_its_default_first_and_marked` |
| unfiltered (every catalogue action) | killed | 4 tests: SDN lab's policy sends only the rate limit, the default policy's two actions, the order test, and one more |
| no action marked default | killed | the order test |
| every action marked default | killed | the order test |
| the last action marked default | killed | the order test |
| canary: `catalogue_for_ai` raises | killed | 76 tests |

**The result: every mutant killed; the canary killed; the working tree untouched (nmas-control's
fingerprint).**

## 2026-10-27: prompt v3 adopted for the SDN classifier (C1988), by hand

**What touches the tier:** `modules/sdn/closed_loop.py`, `CLASSIFY_PROMPT` from v1 to v3: the
prompt text the loop's and the screen's classify send (prompts/sdn_classify.v3.md, committed and
hand-checked with the catalogue's order in the entry above; measured before adoption, C1988).

**The method:** each mutant its exact line in a `scripts/nmas-control` throwaway worktree, then
tests/test_sdn_policy.py, tests/test_sdn_classify.py and tests/test_sdn_classify_cases.py
(`scratchpad/adopt_hm.py`); the baseline passed (72 tests).

| mutant | result | killed by |
|---|---|---|
| back to v1 | killed | `test_the_adopted_prompt_is_v3_and_the_request_carries_it`, both case files' prompt test |
| canary: a version with no file (99) | killed | 32 tests |

**The result: both killed; the working tree untouched (nmas-control's fingerprint).**

## 2026-10-27: the normal-traffic classification sends the loop's prompt (Lab 8 objective 2.3), by hand

**What touches the tier:** `modules/sdn/closed_loop.py`, `COLLECTION_PROMPT` from v2 (a prompt
written for this path alone) to `CLASSIFY_PROMPT` (v3, the loop's): the operator's order, since
2.3 asks whether the classifier the loop uses false-positives on normal traffic. The request is
unchanged but its system text.

**The method:** each mutant its exact line in a `scripts/nmas-control` throwaway worktree, then
tests/test_sdn_classify_normal.py and tests/test_sdn_policy.py (`scratchpad/coll_hm.py`).

| mutant | result | killed by |
|---|---|---|
| back to v2 | killed | `test_the_request_says_no_rule_fired_and_every_id_sent_may_be_cited` |
| canary: a version with no file (99) | killed | 7 tests |

**The result: both killed; the working tree untouched (nmas-control's fingerprint).**

## 2026-10-28: the caps reserved atomically (C2039) and the provider's token count (C1898), by hand

**What touches the tier.** (1) C2039, the operator's decision: `gateway._capped_send` reserves
each call's worst case against every cap it is held to (the day cap; a background feature's
day and month caps) under one cross-process lock (`filestore.PathLock` on
`ai_reservations.json`, beside the record of AI calls), the spend read inside the lock, and
settles it once the call's row is recorded, whatever the outcome (a `finally`; an exception
records the worst case as its cost). New: `modules/ai/reservations.py` (`_read`, `_write`,
`in_flight`, `reserve`, `settle`, `open_reservations`); `gateway.send_bound_s`,
`reservation_ttl_s` (2.5 times the adapter's longest call, 235 s: 587.5 s); `_received` (the
answer's half of the old `_capped_send`, unchanged lines); `background.over_cap`'s `reserved`.
(2) C1898, the operator's decision: the provider's count of the masked request
(`anthropic_adapter.count_body`, `count_tokens`: `POST /v1/messages/count_tokens`, its own
bound, never retried) is what the prompt's bound and the worst case are judged on, recorded on
the row (``prompt_count``); when it is not had, the fallback estimate at 1.8 characters a
token (`CHARS_PER_TOKEN`, from 3.0; `tokens_of_chars`, `CALIBRATION`), said. New:
`gateway.Counter` (`measure`), `counter` (a selector's counter, counting only where the call's
own gates pass); `ask`'s measurement and its refusal's words; `worst_case_usd`'s `tokens`;
`nl_query.select_context` and `explain.budgeted` measure by the counter (data leaves the host
to be counted, so the counter masks first and never sends a stored secret).

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it: each
mutant one exact text replacement in a `scripts/nmas-control` throwaway worktree of the
change, the aimed tests run (tests/test_ai_reservations.py, test_ai_token_count.py,
test_ai_gateway_ask.py, test_ai_gateway.py, test_ai_background.py, test_ai_presses.py,
test_anthropic_adapter.py; for the selectors also test_ai_nl_query.py and test_ai_explain.py),
the file restored before the next (`scratchpad/caps_count_hm.py`). The baseline passed (301
tests, and 1,375 across the AI files, the manual and the secret scans). A must-die canary
first: `_capped_send` refusing every call: killed. The first run had 9 survivors; each was
read, a test added or a planted value corrected, and the mutant run again (marked *then
killed*). One, G14, is equivalent, named below.

**The reservations (C2039).**

| mutant | result | killed by |
|---|---|---|
| R1 an expired reservation never dropped | killed | `test_a_reservation_a_dead_process_left_expires_and_is_dropped` |
| R2 a reservation expiring as it is made | killed | 4, both two-calls-at-once tests among them |
| R3 the judge never asked | killed | 23 |
| R4 the reservation never written | killed | 7 |
| R5 an unreadable store read as empty at once | killed | 4, `test_an_unreadable_store_refuses_the_call_and_sends_nothing` among them |
| R6 the shape check's expiry dropped | killed | `test_a_store_out_of_shape_is_unreadable_too` |
| R7 settle removing nothing | killed | 12 |
| R8 a feature's in-flight counting every reservation | survived (the planted amount fitted under the cap whoever's it was), then killed | `test_a_background_features_day_cap_counts_its_calls_in_flight_and_only_those` |
| R9 another network's counted | survived, then killed | the same |
| R10 a person's press counted | survived, then killed | the same |
| R11 a refused call not writing the prune | survived, then killed | `test_a_refused_call_still_drops_an_expired_reservation_from_the_store` (added) |
| R12 a store that cannot be written raising | killed | `test_a_store_that_cannot_be_written_refuses_the_call` |
| R13 a settle that cannot read raising | killed | `test_a_reservation_that_cannot_be_settled_is_logged_and_the_answer_returned` |
| R14 an old unreadable store kept refusing | killed (its pattern first failed to apply; fixed) | `test_an_unreadable_store_older_than_a_reservation_lives_is_kept_aside_and_replaced` |
| R15 the old store replaced without being kept aside | killed | the same |
| B1 `over_cap` without what is reserved | killed | the background in-flight test; `test_two_background_calls_at_once_cannot_pass_the_features_day_cap_together` |
| G1 the worst case from the estimate, not the count | killed | 12 |
| G2 the day cap without what is in flight | killed | the two-calls test, the other-process test, the not-yet-expired test |
| G3 `>` to `>=` at the day cap | killed | `test_a_days_spend_reaching_the_cap_exactly_is_sent` |
| G4 the feature's caps without its in-flight | killed | 2 background tests |
| G5 a background reservation without its network | killed | the two-background-calls test |
| G6 a background reservation not marked background | killed | the same |
| G6b a background reservation naming its task, not its feature | killed | the same (it found this bug in the first build) |
| G7 settled though the row was not recorded | killed | `test_a_row_that_could_not_be_recorded_leaves_its_reservation_to_expire` |
| G8 never settled | killed | 13 |
| G9 an exception's row costing 0 | killed | `test_an_exception_counts_its_worst_case_and_settles` |
| G10 an exception's row never settled | killed | the same |
| G11 an unrecorded answer settled | killed | the row-not-recorded test |
| G12 the reservation's life one call, not 2.5 | killed | `test_the_reservations_life_is_two_and_a_half_times_one_calls_longest` |
| G13 one attempt fewer in the adapter's bound | killed | that test and the press wait's |
| G13b an exception not caught | killed | the exception test |

**The count (C1898).**

| mutant | result | killed by |
|---|---|---|
| G14 `ask`'s counter masking the masked body again | **survived: equivalent** | masking is idempotent on what `redact.egress_payload` already masked (its placeholders match no secret shape), so the counted bytes are the same; under the mutant the counted body still equalled the sent one (`test_the_count_is_used_when_it_answers`) |
| G15 `>` to `>=` at the prompt's bound | killed | `test_a_prompt_at_its_bound_is_sent`, `test_nothing_is_sent_when_the_counted_prompt_is_over_the_bound` |
| G16 the bound judged on the estimate | killed | 18 |
| G17 the worst case handed no count | killed | 12 |
| G18 `<=` to `<` in the fallback's within-bound check | killed | `test_a_request_the_fallback_puts_exactly_at_the_bound_is_not_counted` |
| G19 no cache by digest | killed | `test_the_same_request_is_counted_once` |
| G20 a counter not allowed still counting | killed | the two counter-gate tests |
| G21 the skip margin 100 times the bound | survived (the test's candidate was far over either way), then killed | `test_a_candidate_far_over_by_the_measured_ratio_is_skipped_uncounted` |
| G22 a stored secret sent to be counted | killed | `test_a_stored_secret_left_after_masking_is_never_sent_to_be_counted` |
| G23 one count past `MAX_COUNTS` | killed | `test_a_press_asks_at_most_max_counts` |
| G24 counts never counted | killed | the same |
| G25 the selector's body counted unmasked | killed | `test_the_counter_counts_only_the_masked_request` |
| G26 no measured ratio | killed | the skip test |
| G27 only the adapter's kinds caught | killed | the fallback test's `RuntimeError` case |
| G28 the counter not asking whether hosted AI is allowed | killed | the counter-gate test |
| G29 nor whether the background feature is on | killed | `test_a_counter_without_a_key_or_with_its_feature_off_counts_nothing` |
| G30 nor whether a key is set | killed | the same |
| G30b nor the trigger | survived (hosted AI was off in the test, so the counter was refused for that), then killed | `test_a_counter_whose_call_could_not_be_sent_counts_nothing_and_says_why` |
| G31 the fallback's `+ 1` dropped | killed | 2 |
| G32 the fallback at 2.0 characters a token | killed | the sample test and the margin test |
| G33 the row's `prompt_count` dropped | killed | 11 |
| G34 the refusal's words inverted | killed | 4 |
| G35 `worst_case_usd` ignoring its tokens | killed | 2 |
| A1 every key of the send counted | killed | `test_the_count_is_asked_of_the_count_endpoint_with_the_sends_key_and_its_own_bound` |
| A2 `system` not counted | killed | the same, and the background test |
| A3 no headers | killed | the same |
| A4 no bound | killed | the same |
| A5 a boolean count taken | killed | the failures test's `True` case |
| A6 a negative count taken | killed | its `-1` case |
| A7 a 429 not `rate_limited` | killed | its 429 case |
| A8 a count with no key asked | killed | `test_a_count_with_no_key_asks_nothing` |
| A9 the count sent to the Messages endpoint | killed | the endpoint test |
| A10 the count's bound the send's | killed | the same |
| N1 Ask in words' selector on the estimate | killed | 4 |
| N2 Ask in words handing its selector no counter | killed | 2 |
| E1 Explain's budget on the estimate | killed | `test_explains_budget_keeps_what_the_count_fits_where_the_fallback_trims` |
| E2 Explain handing its budget no counter | survived (nothing ran v6 through `explain_pack` with a count), then killed | `test_v6_fits_its_budget_by_the_providers_count` (added) |

**The result: every mutant killed but G14, equivalent and named; the canary killed. The first
run's `nmas-control` exit was 3 because the agent edited tests in the checkout while it ran
(docs/TESTING.md and the two new test files), not the mutants: the reruns of the survivors
left the working tree untouched (nmas-control's fingerprint).**

## 2026-10-28: what a person types masked at the gateway, and the person told (C1845), by hand

**What touches the tier.** C1845 (PHASE8_PLAN 18.1 A1 prerequisite (b), the operator's of
2026-10-27): what a person types or pastes into an AI feature is masked before it leaves, by
position and by known value, and the person told what was masked, in words, never the value.
Measured first: `ask` already passed the whole request through `redact.egress_payload`, so a
typed secret of a known shape or a held value was already kept from the bytes sent
(tests/test_ai_nl_query.py's `test_a_planted_secret_is_masked_in_the_bytes_sent` held it for a
stored value in the question); what was missing was a mask of the typed text's own, the person
told, the record saying it, and a declaration no feature could forget. New in
`modules/ai/gateway.py`: `TYPED_PARTS` (every pinned task's typed parts or none: `nl_query`'s
`question`, `intent_patch`'s `sentence`), `ask` refusing a task it does not name
(`typed_undeclared`), `mask_typed` (each typed part through `redact.redact_egress` with the one
table of held values, every other part the object given), `_new_masks`, `typed_said` and
`MASK_WORDS` (each redact label in words; a held value as "a credential Mercury holds", its
store label never said), the row's and every result's ``typed_masked`` from the mask on (the
refusals' `**told`, the press's result). Carried to the screens: `nl_query.CARRIED`,
`intent_words._drafted`'s base, `routes/intent_v2.words`' drawn keys; the boxes draw the words
as sent (`routes/v2._ask_words`, `routes/intent_v2.words`, `redact.redact_egress`); the note,
`_ai.html`'s `typed_masked`, under both rows.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it: each
mutant one exact text replacement, found exactly once, in its own `scripts/nmas-control`
throwaway worktree of the change, the aimed tests run (tests/test_ai_typed_text.py,
test_ai_gateway.py, test_ai_gateway_ask.py, and the screens' own:
test_ai_nl_query.py's, test_ai_nl_logs.py's and test_ai_intent_change.py's
`test_a_pasted_secret_is_masked_and_the_person_told`, test_ai_nl_query.py's
`test_a_question_with_nothing_to_mask_says_nothing_of_masking`, test_ai_intent_change.py's
`test_an_answer_is_previewed_by_the_intent_editor_and_writes_nothing`), 149 tests
(`scratchpad/hm.py`, `hm_all.py`). The baseline passed (149). A must-die canary first:
`mask_typed` returning the parts unmasked and nothing said: killed (23 failed). The first run
had five survivors; one was a missing test (M18), added and the mutant run again (marked *then
killed*); four are equivalent, named below. Every run left the working tree untouched (each
`nmas-control` exit 0).

| mutant | result | killed by |
|---|---|---|
| C0 canary: `mask_typed` masks nothing and says nothing | killed | 23, every masked-and-told test |
| M1 Ask's `question` not typed | killed | the metrics and logs screens' tests; `test_every_pinned_task_names_its_typed_parts`; the typed-field test |
| M2 Change it in words' `sentence` not typed | killed | the Intent tab's test; the same two |
| M3 a task `TYPED_PARTS` does not name not refused | killed | `test_a_task_naming_no_typed_parts_is_refused_and_nothing_is_sent` |
| M4 a typed part with nothing masked not skipped early | **survived: equivalent** | the per-line comparison after it finds no changed line in a text the mask left unchanged, so nothing is said, and the part handed on is an equal string; the early `continue` only saves the split |
| M5 the typed part handed on unmasked | killed | `test_other_parts_are_the_objects_given` |
| M6 lines never told apart | killed | `test_text_of_several_lines_is_said_line_by_line` |
| M7 every line said as line 1 | killed | the same |
| M8 a mask the person typed counted as one made | killed | `test_a_mask_the_person_typed_themselves_is_not_said_as_one_made` |
| M9 `_new_masks` never subtracting what was there | killed | the same |
| M10 one line said as lines (`>` to `>=`) | killed | 21 |
| M11 values counted by line, not by mask | killed | 4, the SNMPv3 two-key line among them |
| M12 a held value's store label said | killed | 5, `test_a_value_mercury_holds_is_masked_by_value_and_its_label_never_said` among them |
| M13 the row without what was said | killed | 18 |
| M14 the result without what was said | killed | 22 |
| M15 the request built from the unmasked parts | **survived: equivalent** | the request's own mask (`redact.egress_payload`, the same `redact_egress` over every string) masks the typed part in the request exactly as `mask_typed` did, so the bytes sent are the same; the typed mask's own output is held by `test_other_parts_are_the_objects_given` (M5), and what it says by the tests above. Two masks, one function: defence in depth, not a second rule |
| M16 the request's mask reading its own table | **survived: equivalent** | `known_secret_values` answers the same table both times within a call (cached for 30 s, and the tests' planted table is one function) |
| M17 an answered call not saying what was masked | killed | 21 |
| M18 a refusal after the mask not saying it | survived (the cap's refusal is wrapped again as the press's result, so it said it anyway), then killed | `test_a_call_refused_after_the_mask_still_says_what_was_masked` (its prompt-over-the-bound case, added: refused before the caps) |
| M19 a redact label with no words | killed | `test_every_mask_redact_makes_has_its_words`; `test_the_words_name_kinds_and_lines_never_a_value` |
| M20 the typed mask without the egress shapes (`redact_text`) | killed | 5, the logs screen's BGP neighbour password and the pasted neighbour and SNMPv3 lines |
| M21 an empty typed part masked | **survived: equivalent** | `redact_egress` returns an empty text unchanged, so nothing is masked or said either way |
| M22 every part masked as typed (Mercury's own data said as the person's) | killed (a control of the pack test's premise, run after) | `test_other_parts_are_the_objects_given`; test_ai_gateway.py's `test_a_stored_secret_left_after_masking_refuses_and_sends_nothing` |
| N1 Ask in words not carrying the tell (`nl_query.CARRIED`) | killed | the metrics and logs screens' tests |
| I1 Change it in words not carrying it (`_drafted`'s base) | killed | the Intent tab's test |
| R1 the tab's route not drawing it | killed | the same |
| R2 Ask's box drawing the value back | killed | the metrics and logs screens' tests |
| R3 the tab's box and Why, in one line drawing the value back | killed | the Intent tab's test |
| T1 Ask in words' row not drawing the note | killed | the metrics and logs screens' tests |
| T2 Change it in words' row not drawing it | killed | the Intent tab's test |
| T3 the note without its words | killed | 6 |

**The result: every mutant killed but M4, M15, M16 and M21, equivalent and named; the canary
killed. Not covered by a mutant here: the shapes `redact_egress` does not yet know (an IKE
`crypto isakmp key`, an OSPF `authentication-key` with no key number, a server block's bare
`key`, HSRP's `standby N authentication`), measured unmasked the same day and C745's to add.**

## 2026-10-28: the IOS credential shapes masking did not know, by position (C745), by hand

**What touches the tier.** C745: eight entries added to `redact._POSITIONAL`, so goldens'
reads, logs, responses, the archive, the parsers' secret references, the config check and the
egress mask all get them (goldens stay verbatim at rest): `ospf_key` (`ip ospf
authentication-key [0|7] <k>`, `ip ospf message-digest-key N md5 [0|7] <k>`),
`neighbor_password` (`neighbor <IPv4|IPv6|peer group> password [0|7] <pw>`, LDP's too),
`snmp_user_auth` and `snmp_user_priv` (`snmp-server user <u> <g> [remote <host> [udp-port N]
[vrf X]] v3 [encrypted] auth {md5|sha} <a> [priv {des|3des|aes {128|192|256}} <p>]`),
`isakmp_key` (`crypto isakmp key [0|6] <k> {address <IPv4> | address ipv6 <prefix> |
hostname <name>}`), `server_key` (a block's `key [0|6|7] <k>` indented, or unindented with its
type; never a key chain's `key <N>` nor an assignment), `fhrp_authentication` (`standby [N]
authentication [text] <s>`, `vrrp N` and `glbp N authentication text <s>`), `ntp_key` (`ntp
authentication-key N <algorithm> [7] <k> [7]`); `gateway.MASK_WORDS` gives each its words.
No capture holds any of these shapes (the fleet's captures scanned, counts only); each line is
the Cisco command reference's documented form with an invented value. The ordering hazards and
how they are held: every rule names its carrier, so NTP's key number and `md5` are never taken
for a type and a value (C1845's trap, mutant T4); `[ \t]`, never `\s`, between tokens, so no
match crosses a line (O7, N5, S13, I5, K9, F10, T5); an encryption type is one digit, so a
numeric clear value is the value (O6, N4, I4, T6). Found while building, before this check:
the first `server_key` (any `key <word>` leading a line) masked the break-glass preview's
operand "key fingerprint" and a traceback's `key = …` (tests/test_breakglass_export.py failed);
narrowed to an indented line or a typed one, and an assignment refused.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it: each
mutant one or more exact text replacements, each found the stated number of times, in its own
`scripts/nmas-control` throwaway worktree of the change, then tests/test_redact_ios_shapes.py,
test_redact_egress.py, test_s3_archive.py, test_ai_typed_text.py, test_ai_nl_logs.py,
test_provider_redaction.py, test_secret_compare.py, test_unmodeled_secrets.py,
test_breakglass_export.py, test_claude_config_reads.py and test_url_userinfo_masked.py
(`scratchpad/hm.py`, `hm_all.py`). The baseline passed (528; 536 after the tests added below).
A must-die canary first: every C745 rule matching nothing: killed (152 failed). The first run
had seven survivors; four were a missing test (a clear value of digits with words after it,
and a type 7 value of digits alone), added and the mutants run again (marked *then killed*);
I2's first form did not compile and was run again in a form that does; two survive, named
below. Every run left the working tree untouched (each `nmas-control` exit 0).

| mutant | result | killed by |
|---|---|---|
| C0 canary: every C745 rule matches nothing | killed | 152, every form, the archive's and the screens' |
| O1 `ospf_key` matches nothing | killed | 23 |
| O2 without `authentication-key` | killed | 10 |
| O3 without `message-digest-key` | killed | 13 |
| O4 its `md5` keyword dropped | killed | 13 |
| O5 without its type | killed | 11 |
| O6 its type any number (`\d+`) | survived, then killed | `test_a_shape_quoted_mid_sentence_is_masked_by_position` (`authentication-key 12345678 set on …`, added) |
| O7 crossing lines (`\s`) | killed | `test_a_keyword_ending_its_line_takes_nothing_from_the_next` |
| N1 `neighbor_password` matches nothing | killed | 29 |
| N2 a neighbor of IPv4 or a name only (no `:`) | killed | 10, every IPv6 case |
| N3 without its type | killed | 19 |
| N4 its type any number | survived, then killed | the quoted test (IPv4 and IPv6 `password 12345678 refused`, added) |
| N5 crossing lines | killed | the line-end test |
| S1 `snmp_user_auth` matches nothing | killed | 27 |
| S2 `snmp_user_priv` matches nothing | killed | 24 |
| S3 the `remote` clause dropped (both rules) | killed | 6 |
| S4 `udp-port` dropped | killed | 3 |
| S5 `vrf` dropped | killed | 3 |
| S6 `encrypted` dropped (auth) | killed | 3 |
| S7 `encrypted` dropped (priv) | killed | 3 |
| S8 `md5` dropped (auth) | killed | 3 |
| S9 `3des` dropped | killed | 3 |
| S10 AES's key size optional | killed | the line-end test (`priv aes 128` with nothing after) |
| S11 the user and group read lazily up to `auth` | killed | 3, the user named `auth` in a group named `sha` |
| S12 the priv rule's auth value token dropped | killed | 24 |
| S13 crossing lines | killed | the line-end test |
| I1 `isakmp_key` matches nothing | killed | 18 |
| I2 without the `address`/`hostname` refusal | killed | 3, the one-character key |
| I3 without its type | killed | 7 |
| I4 its type any number | survived, then killed | the quoted test (`crypto isakmp key 12345678 was set …`, added) |
| I5 crossing lines | killed | the line-end test |
| K1 `server_key` matches nothing | killed | 17 |
| K2 a key chain's `key <N>` not refused | killed | 4 |
| K3 an assignment not refused | killed | `test_a_line_holding_no_secret_is_left_whole` (`    key = live_key()`) |
| K4 the unindented (typed) branch dropped | killed | 3 |
| K5 the unindented branch any type digit | killed | the no-secret test (`key 1 of 1 stored value(s)`) |
| K6 the indent optional | killed | 7, "key fingerprint" and "key opens" among them |
| K7 the indented branch without its type | killed | 11 |
| K8 the key chain refusal on `[ \t]` (CRLF) | killed | `test_a_key_chain_read_with_crlf_line_ends_is_left_whole` |
| K9 crossing lines | killed | the line-end test |
| K10 without multiline | killed | the golden block's test |
| F1 `fhrp_authentication` matches nothing | killed | 20 |
| F2 `standby` dropped | killed | 14 |
| F3 `vrrp` dropped | killed | 3 |
| F4 `glbp` dropped | killed | 3 |
| F5 the group number required | killed | 3 |
| F6 `text` not consumed | killed | 12 |
| F7 the `md5`/`text` refusal dropped | killed | 12, `md5 key-chain <name>` among them |
| F8 `md5` not refused | killed | 10 |
| F9 `text` not refused as the value | killed | the line-end test (`authentication text` with nothing after) |
| F10 crossing lines | killed | the line-end test |
| T1 `ntp_key` matches nothing | killed | 24 |
| T2 without its type | killed | 6 |
| T3 its algorithm `md5` only | **survived: not equivalent, explained** | `\S+` reads any algorithm token on purpose (a wider rule refuses more, the safe direction); every form this check's documented sources give is `md5`, so no case tells the two apart, and a case of another algorithm would be typed from memory |
| T4 the trap: a bare `authentication-key [type] <value>` rule in NTP's place | killed | 28, NTP's key number and `md5` kept by every mask among them |
| T5 crossing lines | killed | the line-end test |
| T6 its type any number | survived, then killed | the forms test (`md5 110219001105 7`, a type 7 value of digits alone, added) |
| L1 `ntp_key` labelled `egress_key` | killed | 26 |
| L2 `server_key` labelled `shared_key` | killed | 19 |
| P1 `snmp_user_priv` before `snmp_user_auth` | **survived: equivalent** | the privacy rule's prefix holds the authentication value as one token, masked or not, so either order masks the same tokens with the same labels (the rule's comment says so) |
| W1 a C745 label with no words | killed | `test_every_mask_redact_makes_has_its_words` |
| W2 a neighbor's password said in other words | killed | the logs screen's and the typed text's tests |

**The result: every mutant killed but T3 (explained) and P1 (equivalent); the canary killed.
Not covered here: the shapes still unknown (an older `tacacs-server host … key` or
`radius-server host … key` with a clear key, `server-private … key`, `server-key`, `pac key`,
`key config-key`, NHRP's and IKEv2's keys, an OSPF virtual link's, OSPFv3's IPsec keys),
measured in clear the same day, the register's.**

## 2026-10-28: the IOS credential shapes still in clear after C745, by position (C2074), by hand

**What touches the tier.** C2074: ten entries added to `redact._POSITIONAL` and two changed,
so goldens' reads, logs, responses, the archive, the parsers' secret references, the config
check and the egress mask all get them (goldens stay verbatim at rest): `server_host_key`
(`radius-server host …`, `tacacs-server host …` and `server-private …`, any options, the last
`key [0-9] <k>` on the line), `dynamic_author_key` (`client <host> [vrf X] server-key [0|7]
<k>`, or a `server-key` line), `pac_key` (a line's `pac key [0|6|7] <k>`), `config_key` (`key
config-key password-encrypt <k>`), `nhrp_authentication` (`ip` or `ipv6 nhrp authentication
<s>`), `ikev2_pre_share_key` (`authentication {local|remote} pre-share key [0|6] <k>`),
`ospf_virtual_link_key` (`area N virtual-link <id> … {authentication-key | message-digest-key N
md5} [0|7] <k>`), `ospfv3_ipsec_encryption_key` and `ospfv3_ipsec_authentication_key`
(`authentication ipsec spi N {md5|sha1} [0|7] <k>`, `encryption ipsec spi N esp {des|3des|
aes-cbc N|null} [[0|7] <k>] {md5|sha1} [0|7] <k>`, wherever configured), `server_block_key` (a
`radius server`, `tacacs server` or ISAKMP client group block's `key <digits>` ending its line);
`pre_shared_key` rewritten for every keyring form (ISAKMP `address <IPv4> [mask]`, `address
ipv6`, `ipv6`, `hostname`; IKEv2 `[local|remote] [0|6] [hex]`), its value never one of those
keywords; `server_key` refuses `config-key`. `gateway.MASK_WORDS` gives each new label its
words. Measured before the change: 31 planted lines, one or more per shape, each kept its value
through `redact_text` (21 through the egress mask too); after it, none. No capture holds any of these shapes (the
fleet's captures scanned, counts only); each line is the Cisco command reference's documented
form with an invented value.

**The ordering hazards and how they are held.** `pre_shared_key` versus IKEv2's keyring: the
first rule masked `local`, the type, `hex`, the mask, `ipv6` or `hostname` and printed the key;
a new rule placed before it would still have lost the keyword to it, so the rule itself was
rewritten (P1 to P12). `config_key` versus `server_key`: an indented `key config-key …` read by
`server_key` first lost `config-key` and printed the key; `server_key` refuses `config-key`,
so the order does not matter (G2 killed, G3 equivalent). `pac_key` versus `server_host_key`: a
host line's `… pac key <k>` read by both named one value twice to the parsers and the config
check; `pac_key` leads its line (A3). `server_block_key` versus `server_key`: disjoint by
construction, digits ending the line against everything else (B7, B10). `ospf_key` versus the
virtual link's: `ip ospf` names the interface's, `area … virtual-link` the link's (L3; the
golden test's neighbours). `isakmp_key` versus IKEv2: different carriers, each its own label
beside the other in one golden. `[ \t]`, never `\s`, between tokens (P11, H8, D8, A4, G4, N4,
I6, V9, E8, U9); a one-digit type (P10, H7, D9, A6, I5, V8, E7, U10).

**The digits-alone server key.** By its line alone ` key 12345678` is a key chain's ID, and
`server_key` refuses it (C745's decision, kept). The positional pass runs over the whole text,
so `server_block_key` reads the block: the header at a line's start, indented children, the key
of digits ending its line; a `!`, a blank line, an unindented line or an indented header ends or
refuses it. A caller masking one line at a time (the config check, the secret comparison, the
parsers' unmodelled children) still cannot tell, and leaves it: stated in the rule's comment
and a test, and the register's.

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it: each
mutant one or more exact text replacements, each found the stated number of times (checked
read-only first: 96 mutants, every one found, compiled and its table loaded), in its own
`scripts/nmas-control` throwaway worktree of the change, then a first stage of
tests/test_redact_ios_shapes.py and test_ai_typed_text.py and, when that killed nothing, the
whole aimed set: those two and test_redact_egress.py, test_ai_nl_logs.py,
test_secret_compare.py, test_unmodeled_secrets.py, test_breakglass_export.py,
test_claude_config_reads.py, test_url_userinfo_masked.py, test_s3_archive.py,
test_provider_redaction.py and test_config_check.py (`scratchpad/hm_one.py`, `hm_all.sh`,
`c2074_mutants.py`). The baseline passed (935, 1 skipped). A must-die canary first: C2074's
rules removed and the two changed rules restored: killed (207 failed). Three runs (the
baseline, the canary and P2) overlapped an edit of three docs in the working tree, and
`nmas-control` said so (exit 3); they were run again with nothing editing, each exit 0, with
the same results. Every other run exited 0. Counts are the first stage's failures.

| mutant | result | killed by |
|---|---|---|
| C0 canary: C2074's rules removed, the two changed rules restored | killed | 207, every form |
| P1 `pre_shared_key` restored to its first form | killed | 40 |
| P2 the ISAKMP mask dropped | killed | 4, `address 192.0.2.0 255.255.255.0 key` |
| P3 `address ipv6`'s `ipv6` keyword dropped | **survived: equivalent** | `address <token> [<token>] key` reads `address ipv6 <prefix> key` with `ipv6` as the address and the prefix as the optional mask, so every form masks the same token; the keyword states the documented form |
| P4 the `ipv6 <prefix>` form dropped | killed | 4 |
| P5 the `hostname` form dropped | killed | 4 |
| P6 IKEv2's `local`/`remote` dropped | killed | 19 |
| P7 without its type | killed | 12 |
| P8 without `hex` | killed | 4 |
| P9 the keyword refusal dropped | killed | 4, `pre-shared-key local` ending its line |
| P10 its type any number | killed | the quoted test (`pre-shared-key local 12345678 is weak`) |
| P11 crossing lines | killed | the line-end test |
| P12 the keyring forms without `key` | killed | 11 |
| H1 `server_host_key` matches nothing | killed | 45 |
| H2 `radius-server` dropped | killed | 23 |
| H3 `tacacs-server` dropped | killed | 13 |
| H4 `server-private` dropped | killed | 9 |
| H5 the first `key` on the line, not the last | killed | 3, a test user named `key` |
| H6 without its type | killed | 28 |
| H7 its type any number | killed | the quoted test (`key 12345678 is wrong`, IPv6) |
| H8 crossing lines | killed | the line-end test |
| H9 no options between the host and `key` | killed | 24 |
| D1 `dynamic_author_key` matches nothing | killed | 21 |
| D2 the line-leading `server-key` dropped | killed | 7 |
| D3 the `client` carrier dropped | killed | 15 |
| D4 `vrf` before `server-key` dropped | killed | 3 |
| D5 without its type | killed | 10 |
| D6 a bare `server-key` anywhere | killed | the no-secret test ("the console-server-key page opens") |
| D7 without multiline | killed | the neighbours' golden (a `server-key` line mid-text) |
| D8 crossing lines | killed | the line-end test |
| D9 its type any number | killed | the quoted test (`server-key 12345678 was refused`) |
| A1 `pac_key` matches nothing | killed | 11 |
| A2 without its type | killed | 7 |
| A3 `pac key` anywhere, not leading its line | killed | the parsers' test: a host line's `pac key` value named twice |
| A4 crossing lines | killed | the line-end test |
| A5 without multiline | killed | the neighbours' golden |
| A6 its type any number | killed | the quoted test (`pac key 12345678 is set`) |
| G1 `config_key` matches nothing | killed | 8 |
| G2 `server_key`'s `config-key` refusal dropped | killed | 3, the indented form |
| G3 `config_key` after `server_key` | **survived: equivalent** | `server_key` refuses `config-key`, so either order masks the same token with the same label (the rule's comment says so) |
| G4 crossing lines | killed | the line-end test |
| N1 `nhrp_authentication` matches nothing | killed | 9 |
| N2 IPv4's only (`ipv6` dropped) | killed | 4, every IPv6 case |
| N3 IPv6's only | killed | 5 |
| N4 crossing lines | killed | the line-end test |
| I1 `ikev2_pre_share_key` matches nothing | killed | 12 |
| I2 `local` dropped | killed | 5 |
| I3 `remote` dropped | killed | 7 |
| I4 without its type | killed | 7 |
| I5 its type any number | killed | the quoted test (`pre-share key 12345678 is weak`) |
| I6 crossing lines | killed | the line-end test |
| V1 `ospf_virtual_link_key` matches nothing | killed | 19 |
| V2 without `authentication-key` | killed | 11 |
| V3 without `message-digest-key` | killed | 8 |
| V4 its `md5` keyword dropped | killed | 9 |
| V5 no options between the router ID and the key | killed | 6 |
| V6 the first carrier on the line, not the last | **survived: equivalent** | every documented form has one carrier (`authentication-key` and `message-digest-key` are alternatives), so the first and the last are the same token |
| V7 without its type | killed | 7 |
| V8 its type any number | killed | the quoted test (`authentication-key 12345678 is set`) |
| V9 crossing lines | killed | the line-end test |
| E1 `ospfv3_ipsec_encryption_key` matches nothing | killed | 16 |
| E2 `3des` dropped | killed | 6 |
| E3 `des` dropped | killed | 4 |
| E4 `aes-cbc` dropped | killed | 6 |
| E5 AES's key size optional | killed | the line-end test (`esp aes-cbc 128` with nothing after) |
| E6 without its type | killed | 6 |
| E7 its type any number | killed | the quoted test (a DES key of digits alone) |
| E8 crossing lines | killed | the line-end test |
| U1 `ospfv3_ipsec_authentication_key` matches nothing | killed | 41 |
| U2 the `authentication ipsec` form dropped | killed | 22 |
| U3 the encryption line's authentication key dropped | killed | 19 |
| U4 `esp null` dropped | killed | 3 |
| U5 `md5` dropped | killed | 29 |
| U6 `sha1` dropped | killed | 12 |
| U7 without its type | killed | 9 |
| U8 the encryption key's type in its prefix dropped | killed | 6 |
| U9 crossing lines | killed | the line-end test |
| U10 its type any number | killed | the quoted test (an MD5 key of digits alone) |
| O1 the authentication rule before the encryption rule | **survived: equivalent** | the authentication rule's prefix holds the encryption key as one token, masked or not, so either order masks the same tokens with the same labels (the rule's comment says so) |
| B1 `server_block_key` matches nothing | killed | 6 |
| B2 `tacacs server` dropped | killed | 1, the TACACS IPv6 block |
| B3 `radius server` dropped | killed | 4 |
| B4 the ISAKMP client group dropped | killed | 1 |
| B5 an indented header allowed | killed | 1, the indented header |
| B6 unindented children allowed | killed | 3, a key chain after a server block |
| B7 the key not required to end its line | killed | 4, C745's golden block among them |
| B8 the header without `\r` | killed | the CRLF block |
| B9 the key's line end without `\r` | killed | the CRLF block |
| B10 any token, not digits | killed | C745's golden block (`key PlantedRadiusKey` labelled `server_key`) |
| B11 without multiline | killed | 2, a block not at the text's start |
| B12 the children read greedily | **survived: equivalent** | a server block holds one key, so the nearest and the farthest `key <digits>` line in the block are the same line |
| L1 `server_host_key` labelled `shared_key` | killed | 47 |
| L2 `server_block_key` labelled `server_key` | killed | 7 |
| L3 `ospf_virtual_link_key` labelled `ospf_key` | killed | 21 |
| W1 a C2074 label with no words | killed | the typed text's pasted case (`key config-key …`) |
| W2 two labels with the same words | killed | `test_every_mask_redact_makes_has_its_words` |

**The result: 96 mutants; every one killed but P3, G3, V6, O1 and B12 (each equivalent, the
reason given); the canary killed; no survivor needed a test, and none was added after the run.
Not covered here: a TACACS or RADIUS key containing spaces (documented as allowed: masking
takes the first word, every path, the egress mask too); a server key of digits alone where a
caller masks line by line; the shapes masked only on egress (`ip ftp password`, IS-IS
`isis password`, `area-password` and `domain-password`, `l2tp tunnel password`), measured in
clear through `redact_text` the same day; the register's.**

## 2026-10-28: a TACACS+ or RADIUS key holding spaces, read to its line's end (C2085), by hand

**What touches the tier.** C2085: four rules of `redact._POSITIONAL` rewritten, so goldens'
reads, logs, responses, the archive, the parsers' secret references, the config check and the
egress mask all get the whole key (goldens stay verbatim at rest). IOS reads "spaces within and
at the end of the key" as part of it (Cisco IOS Security Command Reference: `tacacs-server key`,
`radius-server key`, `key (config-radius-server)`; `radius-server host`: "Always configure the
key as the last item"), and every mask took the first word. Where the command ends with its key
(`tacacs-server key`, `radius-server key`, `radius-server host … key`, `server-private … key` in
both families, a server block's or ISAKMP client group's `key`, a `pac key`), each rule is now
two: the clear form (`0` or no type, `_KEY_CLEAR`) read to the line's end (`_VALUE_TO_EOL`: the
first character as `_VALUE`'s, then everything but `\r` and `\n`), and the hidden or AES form
(`7`, `6`, `_KEY_HIDDEN`) one token. `radius-server host` and `server-private` take the FIRST
bare `key` on the line, a test user's `username <name>` read as a pair. Left one token, stated
and tested: `tacacs-server host … key`, whose syntax lists `[nat] [port] [single-connection]
[timeout]` after `[key string]`; a dynamic-author `server-key [0|7] word` (a word, by its
reference). Labels unchanged (`shared_key`, `server_host_key`, `pac_key`, `server_key`), so
`gateway.MASK_WORDS` needs nothing new. No capture holds any of these lines (the fleet's 21
captures: no TACACS+ or RADIUS line, counted); each line is the command reference's documented
form with an invented key.

**The ordering hazards and how they are held.** A key read to its line's end may hold another
carrier's keyword (`radius-server key a key-string b`): placed where `shared_key` stood, after
`key_string`, the parsers got `b` as one reference and then the whole key holding that
reference. The eight rules lead the table, so the key is taken whole first and later rules see
one placeholder (O1 killed). The clear and hidden rules of one carrier are disjoint by
`_KEY_CLEAR`'s refusal of a `6` or `7` with a value after it (O2 equivalent). `pac_key` leads its
line, so a host line's `… pac key` is `server_host_key`'s alone (A2). `server_key` keeps
refusing digits alone (a key chain's ID, `server_block_key`'s inside a block), `=` and
`config-key` (K2 to K4). `[ \t]`, never `\s`, between tokens (S4); a one-digit type, the
documented 0, 6 and 7 only (T1, T4).

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it, as
C2074's: each mutant one or more exact text replacements, each found the stated number of times
(checked read-only first: 37 mutants, every one found, compiled and its table loaded), in its own
`scripts/nmas-control` throwaway worktree of the change, then a first stage of
tests/test_redact_ios_shapes.py and test_ai_typed_text.py and, when that killed nothing, the
whole aimed set (the twelve files C2074 named) (`scratchpad/c2085_mutants.py`, `c2085_one.py`,
`c2085_all.sh`). The baseline passed (1085, 1 skipped). A must-die canary first: C2085's rules
out and the four rules as they stood before it back: killed (85 failed). Every run exited 0.
Counts are the first stage's failures.

| mutant | result | killed by |
|---|---|---|
| C0 canary: the four rules as they stood before C2085 | killed | 85, every key with a space |
| V1 the value one token, not to the line's end | killed | 83 |
| V2 the value runs over a `\r` | killed | 1, the CRLF test |
| V3 the value runs over line ends | killed | 4, the golden blocks and the CRLF test |
| V4 the value's first-character refusals dropped | killed | 2, a search's `[in …]` and a template's `{{` |
| V5 its `<` refusal dropped | killed | 1, a template's `<jinja>` on a host line |
| T1 the hidden type any digit | killed | 14, a `0` value named twice to the parsers |
| T2 the clear form's 6-or-7 refusal dropped | killed | 52 |
| T3 the clear form without its `0` | killed | 32 |
| T4 the clear form's type any digit | killed | 21 |
| T5 the hidden type `7` only | killed | 25, every type 6 form |
| T6 the hidden value read to the line's end | killed | 2, a type 7 key quoted mid-sentence |
| T7 the clear form refuses any 6 or 7 | killed | 3, `radius-server key 7` |
| S1 the global keys' clear rule matches nothing | killed | 37 |
| S2 `tacacs-server` dropped | killed | 16 |
| S3 `radius-server` dropped | killed | 21 |
| S4 `\s` after `key` (crossing lines) | killed | 2, the line-end test |
| H1 the host lines' clear rule matches nothing | killed | 49 |
| H2 `radius-server host` dropped | killed | 50 |
| H3 `server-private` dropped | killed | 22 |
| H4 the last `key` on the line, not the first | killed | 5, a key holding the word `key` |
| H5 `username <name>` not read as a pair | killed | 6, a test user named `key` |
| H6 a bare `username` allowed as an option | killed | 4, the user named `key` with no key |
| H7 no options between the host and `key` | killed | 45 |
| H8 `tacacs-server host` read to the line's end | killed | 5, the stated limit's test among them |
| H9 the host lines' hidden rule removed | killed | 23 |
| A1 `pac_key`'s clear rule matches nothing | killed | 15 |
| A2 `pac key` anywhere, not leading its line | killed | 1, a host line's `pac key` named twice |
| K1 `server_key`'s clear rule matches nothing | killed | 27 |
| K2 its digits-alone refusal dropped | killed | 16 |
| K3 its `=` refusal dropped | killed | 2 |
| K4 its `config-key` refusal dropped | killed | 3 |
| K5 unindented `key 0 <k>` dropped | killed | 4 |
| K6 unindented without a type allowed | killed | 17, "key fingerprint" among them |
| K7 the hidden form indented only | killed | 3, `key 7 <hex>` unindented |
| O1 the C2085 rules after the rest of the table | killed | 3, a key holding another carrier's keyword |
| O2 each carrier's hidden rule before its clear rule | **survived: equivalent** | the clear form refuses a `6` or `7` with a value after it, and the hidden form needs one, so the two never match one value and their order changes nothing |

**The result: 37 mutants; every one killed but O2 (equivalent, the reason given); the canary
killed; no survivor needed a test, and none was added after the run. Not covered here: the
`tacacs-server host … key` form (its key one token, a stated limit); a `radius-server host`
line's `key-wrap encryption-key <k> message-auth-code-key <k>`, measured in clear through every
mask, the egress mask too, the same day; the register's.**

## 2026-10-28: a RADIUS server's key-wrap keys, by position (C2098), by hand

**What touches the tier.** C2098: two rules added to `redact._POSITIONAL`
(`key_wrap_mac_key`, `key_wrap_encryption_key`) and the host lines' carrier
(`_RADIUS_HOST_KEY`) taught the key-wrap clause, so goldens' reads, logs, responses, the archive,
the parsers' secret references, the config check and the egress mask all mask both keys, each
its own value (goldens stay verbatim at rest). Measured before (the same day): `key-wrap
encryption-key <k> message-auth-code-key <k>` kept both keys through every mask, the egress mask
too; with a type (`0`, `7`) through `redact_text`, the egress mask catching them only as
`egress_key`'s by resemblance. The forms: on a host line, Cisco's IOS Security Command Reference
(`radius-server host`, read 2026-10-28): `… [key-wrap encryption-key encryption-key
message-auth-code-key encryption-key [format {ascii | hex}] | pac] [key encryption-key]`, the
clause BEFORE the server's key ("Always configure the key as the last item"); in a `radius
server` block, a child line with a type, from Cisco's "Configure RADIUS KeyWrap in ISE"
(document 222863): `key-wrap encryption-key 0 <k> message-auth-code-key 0 <k> format ascii`,
the keys 16 and 20 characters (the command reference has no `key-wrap (config-radius-server)`
page found; the block form is that document's). Each key is one token: a keyword follows the
first, and `format` or the server's `key` the second. New labels with their words in
`gateway.MASK_WORDS`: "a RADIUS key-wrap encryption key", "a RADIUS key-wrap message
authentication code key". No capture holds a key-wrap line (the fleet's captures: no RADIUS line
at all, C2085's count); each line is the documented form with an invented key.

**The ordering against C2085 and how it is held.** The server's key is the host line's last
item and runs to the line's end (C2085), so the clause stands before it and both rules are
independent of it. The host rule's carrier is the first bare `key`: each key-wrap keyword is now
read with its value there (as `username <name>` is), so a key-wrap key named `key` is never the
carrier (H1, H4 to H6), and its optional type is read exactly as the key-wrap rules read it
(`_KW_ENC_TYPE`, `_KW_MAC_TYPE`), so no token is read two ways: read with a free type, a one-digit
code key before `key` made a later `Key` inside the server's key the carrier and printed the
server key's first word (H2, H3). The key-wrap rules stand right after the eight rules read to
the line's end: a server key typed before the clause runs over it and is one value (O1), and a
key-wrap key holding a later rule's shape (`url_userinfo`'s) is taken whole before that rule
reads inside it (O3). The code key's rule names its keyword alone and runs first, so the
encryption key's rule cannot take that keyword for a missing key and leave the code key unread
(O2, M2). A type is one digit (T8), taken only when the next token is not the keyword that
follows the key: a one-digit key read as a type would mask the keyword and print the key (T1 to
T4, `isakmp_key`'s case); the value itself is never refused by its resemblance. The encryption
key's rule names `key-wrap` (C745's third rule; prose naming `encryption-key` keeps its words,
E2).

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it, as
C2085's: each mutant one or more exact text replacements, each found the stated number of times
(checked read-only first: 31 mutants, every one found, compiled and its table loaded; the
canary's module compared with 431cd023's, its code lines the same but for the two unused type
fragments), in its own `scripts/nmas-control` throwaway worktree of the change, then a first
stage of tests/test_redact_ios_shapes.py and test_ai_typed_text.py and, when that killed nothing,
the whole aimed set (the twelve files C2074 named) (`scratchpad/c2098_mutants.py`,
`c2098_one.py`, `c2098_all.sh`). A must-die canary first: the two rules out and the host carrier
read as before: killed (63 failed). Counts are the first stage's failures. The first run's
baseline passed (1171, 1 skipped) but nmas-control exited 3 for it: the manual and TESTING.md
were edited while it ran (the working tree's fingerprint moved; no test file); rerun with
nothing edited, it passed (1174, 1 skipped) and exited 0. Every mutant's run exited 0.

| mutant | result | killed by |
|---|---|---|
| C0 canary: the two rules out, the host carrier read as before C2098 | killed | 63, every key-wrap form |
| M1 the code key's rule matches nothing | killed | 59 |
| E1 the encryption key's rule matches nothing | killed | 59 |
| E2 the encryption key named by `encryption-key` alone | killed | 1, prose naming `encryption-key` |
| M2 the code key's rule needs the encryption key before it | killed | 3, a missing encryption key, a quoted code key, a line-ending `0` |
| T1 the encryption key's type refuses no keyword | killed | 2, a one-digit key before `message-auth-code-key` |
| T2 the code key's type refuses no keyword | killed | 3 |
| T3 the code key's type refuses `format` only | killed | 2, a one-digit code key before `key` |
| T4 the code key's type refuses `key` only | killed | 1, a one-digit code key before `format` |
| T5 the encryption key read with no type | killed | 18, every typed form |
| T6 the code key read with no type | killed | 17 |
| T7 a type `6` or `7` only | killed | 12, every `0` form |
| T8 a type of any number of digits | survived, then killed | 1, by the test added after the run (below) |
| S1 `\s` after `message-auth-code-key` (crossing lines) | killed | 1, the line-end test |
| S2 `\s` after `encryption-key` | killed | 2, the line-end tests |
| V1 the code key's value without `_VALUE`'s refusals | killed | 2, a template's `{{` and a search's `[in …]` |
| V2 the code key read to the line's end | killed | 34 |
| V3 the encryption key read to the line's end | killed | 52 |
| I1 the code key's rule case-sensitive | killed | 3, the upper-case form |
| I2 the encryption key's rule case-sensitive | killed | 3 |
| O1 the key-wrap rules at the table's head | killed | 1, a server key typed before the clause |
| O2 the encryption key's rule before the code key's | killed | 1, a missing encryption key |
| O3 the key-wrap rules at the table's end | survived, then killed | 2, by the test added after the run (below) |
| H1 the host carrier without the key-wrap pairs | killed | 22 |
| H2 the host's encryption-key pair with a free type | killed | 1, `encryption-key 7 message-auth-code-key key key …` |
| H3 the host's code-key pair with a free type | killed | 1, `message-auth-code-key 7 key Planted Key Word` |
| H4 the key-wrap keywords allowed as bare options | killed | 1, a key-wrap key named `key` with no server key |
| H5 the host's encryption-key pair removed | killed | 22 |
| H6 the host's code-key pair removed | killed | 22 |
| L1 the two labels the same | killed | 55 |
| W1 the code key's words removed from `gateway.MASK_WORDS` | killed | 1, `test_every_mask_redact_makes_has_its_words` |

**The two survivors, neither equivalent, each given a test after the run and the mutant rerun
in its own worktree.** T8: a multi-digit "type" reads a key of digits with a word after it as a
type and prints the digits (C745's one-digit rule; never in a documented line, which has no
extra token, but in typed words): `test_a_one_digit_key_is_never_read_as_a_type_that_hides_a_keyword`
gained ` key-wrap encryption-key 1234567890123456 extra …`; rerun, killed (1). O3: at the
table's end, `url_userinfo` reads inside a key-wrap key holding `scheme://user:pw@` and gives
the parsers a reference inside the stored key (the masked text is the same, so only the
references show it): `test_a_key_wrap_key_is_taken_whole_before_a_later_rule_reads_inside_it`
(a block's encryption key and a host line's code key); rerun, killed (2).

**The result: 31 mutants; every one killed, two (T8, O3) after a test added for each, said
above; the canary killed. Not covered here: the `tacacs-server host … key` form (C2097's); a
key-wrap key holding a space (IOS reads each as one token, so a second word is not part of it).**

## 2026-10-29: a port's source from the topology in what the SDN classifier sends (C2002), by hand

**What touches the tier.** C2002 (built and held 2026-10-28, applied with C2147 on 6b67bc59's
tree) names a flood's, or a fallback scan's, source from the controller's topology when the
flows entering its port name no address. For such a detection, what leaves the host for the AI
provider grows in two places, and only there: the classifier's `detection` block (the pack's
detection piece as sent, `closed_loop.as_sent`) gains `source_from` (how, state, port, the
port's hosts each as its MAC and one address, the topology read's time, the words) and `source`
when the port resolves to one host; its `names` block gains the port's hosts' addresses. Explain
sends the same pack section, so its `sdn` section carries `source_from` too. A detection whose
flows name its source, a recorded case rebuilt with no topology, and a normal-traffic collection
(`collection_request`) send exactly what they sent before. The changed lines that decide it:
- `modules/sdn/detect.py`: `section`, line 790 (the piece carries `source_from`);
  `_port_detection_source`, lines 345 to 349 (no topology names nothing; the keys `source_from`
  carries; the topology's source as the detection's); `port_source`, lines 308 and 318 (each
  host as its MAC and one address; one host named, several not); `host_address`, line 234 (no
  link-local address); `observe`, lines 897 and 898 (the SDN reader's stored topology read).
- `modules/sdn/closed_loop.py`: `sent_evidence`, lines 471 and 472 (the port's hosts' addresses
  in `names`).
No line of the gate or of masking changed: `closed_loop.classify_pack`'s topology-class gate
(line 618, `egress_classes.topology_allowed`, egress_classes.py line 33) and Explain's
(`explain.sent_sections`, line 340) stand in front of every byte of both; the pack is masked
before it is hashed or kept (`evidence_pack.build_detection`, after line 1163,
`redact.redact_payload`), and the gateway masks the whole request (`redact.egress_payload`).
The mutants below include the gates and the pack's mask, to show they cover the new field.

**Within what the topology-class gate permits: yes.** The class is the network context model's
slice, devices, links and "expected and observed adjacencies", no configuration line and no
secret (egress_classes.py's docstring; PHASE8_PLAN 15.11's table), and the model's endpoint
layer, MAC and IP by device and interface, is part of it (PHASE8_PLAN 15.15 item 2; Explain
withholds its endpoints with the topology, explain.py line 346, "Endpoints (MAC, address,
hostname) are the topology class (15.15, the operator's ruling)"). A host the controller lists
on a switch port is that: an observed endpoint, by MAC and address, on a switch's interface.
The `sdn` section, the flows and port rates, was already sent as that class, and the walk's MAC
pairs were already in its flows' matches; what is new is the topology's read of the port (a
host there whose MAC no flow names, and when it was read). Neither is a secret, so neither is
masked anywhere (by design: `redact` masks credentials, by position and by value, and never a
MAC or an address; measured on a host's words, `scratchpad/c2002_mask_probe.py`). A
credential-shaped string a controller put in a host's entry is masked in the pack and the
request (the test below, E11).

**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that applied the
change: each mutant one exact text replacement, found exactly once, in its own
`scripts/nmas-control` throwaway worktree of the change, then the aimed tests in CI's
interpreter, confined (`scratchpad/c2002-egress-hm.sh <name>`, one mutant per invocation;
tests/test_sdn_source_egress.py, test_sdn_source_from_topology.py, test_sdn_lab8.py,
test_sdn_classify.py, test_sdn_classify_cases.py, test_sdn_classify_walk_cases.py,
test_sdn_detect.py, test_sdn_evidence_v2.py, test_ai_explain.py and
test_sdn_auto_inferred_source.py). Baseline: 231 passed, 1 skipped. tests/test_sdn_source_egress.py
was written for this check before the mutants were run: the request as the gateway would send
it, through the real gateway and a fake provider, its detection block's keys and `source_from`
exact and its names exact (IPv4, and an IPv6 host beside one), the class off sending nothing
(the classifier, and Explain withholding the section), and a credential shape in a host's entry
masked in the pack and the request with its MAC and address sent as they are. Every run's
worktree was removed with the working tree untouched (nmas-control's fingerprint).

| mutant | result | killed by |
|---|---|---|
| C0 canary: the piece's `source_from` line raises | killed | 7: the four egress tests, the walk's flood, `observe`'s pack, the classifier test |
| E1 the piece carries no `source_from` (narrower) | killed | 7, the same |
| E2 `source_from` carries the whole lookup (its `source` too) | killed | 2: `test_the_request_carries_how_the_source_was_found_and_the_port_s_hosts_and_no_more` (both); C2002's own tests let it live |
| E3 each host carried as the controller's whole entry (every address, link-local included, its switch and port) | killed | 5: the request test (both), the class-off test, the walk's flood, the IPv6-only host |
| E4 a link-local IPv6 address taken as a host's address | killed | 7: test_sdn_lab8's no-ipv4, the IPv6-only host, no address, the host beside one with an address, and C2147's three IPv6 cases |
| E5 several hosts read as one, the first sent as the source | killed | 14: the request test's several case, the several and picker tests, C2147's several |
| E6 `names` gains the port's hosts' MACs | killed | 2: the request test (both); C2002's own tests let it live |
| E7 `names` loses the port's hosts (narrower) | killed | 2: the request test's several case, the classifier test |
| E8 the topology's source never the detection's (narrower) | killed | 15 |
| E9 the classifier's topology gate ignored | killed | 2: `test_the_topology_class_off_sends_nothing_of_a_port_s_source`, test_sdn_classify's `test_the_topology_class_off_sends_nothing` |
| E10 Explain's withheld section keeps the detection piece (`source_from` sent with the class off) | killed | 2: the class-off test, test_sdn_detect's `test_the_section_is_withheld_when_the_class_is_off` |
| E11 the SDN pack not masked before it is kept | killed | 1: `test_a_credential_shape_in_a_host_s_entry_is_masked_and_its_mac_and_address_are_not`; C2002's own tests let it live |
| E12 `observe` never reads the stored topology | killed | 1: `test_observe_reads_the_stored_topology` |
| E13 a rule given no topology looks it up anyway (a recorded case's rebuild changed) | killed | 20: test_sdn_classify_walk_cases's every case |

**Three would have lived on C2002's own tests (E2, E6, E11):** each widens what is sent (a
field, the MACs in `names`, an unmasked string) without changing what a detection names, and no
test of C2002's looked at the request as sent; each is killed by tests/test_sdn_source_egress.py,
written for this check. **Not covered here:** the gateway's own mask (`redact.egress_payload` in
`gateway.ask`), unchanged and checked by hand 2026-10-25 (`gateway.ask`, 485 mutants): the pack
is masked when it is kept, so a request built from a kept pack cannot tell the gateway's mask
from the pack's, and E11 shows the pack's covers the new field.

**The result: 13 mutants, every one killed; the canary killed.**

## 2026-10-29: Explain's fact sheet, new data off the host (C2117), by hand
**What touches the tier:** data off the host. Every Explain request but v1's carries a new data
block, `fact_sheet` (`modules/ai/fact_sheet.py`, `explain.facts`, `parts`, `budgeted`), computed
from the pack. What it may hold is bounded by what it is built from: the pack AS SENT
(`explain.sent_sections`, so a class gate's withholding holds in it) and the roles of the
topology sent; and it passes `redact.redact_text` before the gateway's own `egress_payload` over
the whole request. No masking code changed: the gateway's egress mask is as it was.
**The method:** each mutant its exact line in its own `scripts/nmas-control` throwaway worktree,
then tests/test_explain_fact_sheet.py and, where it reaches, tests/test_ai_explain_topology.py
(`scratchpad/ctl/ctl_16` to `ctl_18` and `ctl_21`; `ctl_common.py` replaces the line, which must
be there once, and names each failing test).
| the sheet not masked (`sheet` returns its lines unmasked) | killed | 1, `test_every_line_is_labelled_and_the_sheet_is_masked` |
| the sheet built from the stored pack, not the pack as sent | killed | 1, test_ai_explain_topology's `test_the_topology_class_off_sends_none_and_says_so` (a device id beyond the alert's own in the bytes sent) |
| the sheet's block not first (`PART` sorting last) | killed | 5 |
| canary: the sheet's builder raising | killed | 18 |
**The result: every mutant killed; the canary killed. The unmasked sheet is killed only by the
sheet's own test, which calls the sheet directly: no test plants a secret in a pack's log line
and reads the bytes sent, so the gateway's egress mask over the sheet is its own tests', not
shown here.**

## 2026-10-29: evaluation rounds through the provider's Message Batches API, by hand
**What touches the tier.** The operator's decision of 2026-10-29 (PHASE8_PLAN 15.12, "The
measurement budget and screening"): evaluation rounds, never a live feature, go through the
provider's Message Batches API, at half the standard rates. New: `gateway.ask_batch` (an
evaluation trigger only, refused by name before anything is read; the batch's shape, the
provider's limits; each request through `_prepared`, `ask`'s own gates and builder moved
unchanged out of `ask`, with the 1-hour TTL on the one cache mark; the per-call cap; the
evaluation's stop and the day cap judged on the batch's worst case and reserved for the
provider's 24 hours and one more; the bounded wait, a cancel past it; each result recorded,
errored, canceled and expired at no cost, a missing or unknown result at its worst case),
`batch_worst_case_usd`, `cache_writes`, `_received`'s batch pricing, `build_request`'s
`cache_ttl`; `anthropic_adapter.batch_create`, `batch_get`, `batch_cancel`, `batch_results`
(the key sent only to an address built from a batch id of the provider's shape, never to an
answer's `results_url`); `profiles.batch_prices_for`, `batch_cost_usd` (`BATCH_MULTIPLIER`
0.5, `CACHE_WRITE_1H_MULTIPLIER` 2.0, dated); `explain.explain_packs_batch` (what it sends).
**The method:** the narrowed hand check (PHASE8_PLAN 15.12), by the agent that built it, on
the change's tree. Each mutant is one exact text replacement in one `scripts/nmas-control`
throwaway worktree. The aimed tests run through `scripts/nmas-test` (tests/test_ai_batch.py
and test_ai_batch_explain.py; for the lines `ask` shares, also test_ai_gateway_ask.py,
test_ai_gateway.py, test_ai_gateway_parts.py and test_ai_typed_text.py). The file is restored
and compared byte for byte before the next. The baseline passed (61 tests). A must-die canary
went first: `ask_batch` raising at its start, killed by 39. The first run had 6 survivors. Each
was read, given a test, and run again in its own worktree (marked *then killed*). Separately,
11 controls, each in its own `nmas-control` invocation, showed the new tests able to fail (the
trigger refusal, the TTL, the day cap, the stop, the batch rate, an unbilled result, matching
by custom_id, the wait's bound, the batch id's check, Explain's check, History's drawing): each
was killed.
| T1 a person or background trigger admitted (`not in KINDS`) | killed | the person and background cases of `test_a_person_a_background_job_or_no_trigger_is_refused_before_anything`, and the Explain round's |
| T2 no trigger refusal | killed | its three cases, and the Explain round's |
| T3 every trigger read as an evaluation | killed | the same |
| T4 the refusal's words naming no trigger whatever was given | killed | its person and background cases |
| S1 a batch out of shape not refused | killed | the four cases of `test_a_batch_out_of_shape_is_refused_and_nothing_sent`, and another |
| S2 a custom_id named twice taken | killed | its named-twice case |
| S3 a custom_id out of the provider's shape taken | killed | its shape case |
| S4 the provider's request limit not asked | killed | `test_a_batch_over_the_providers_limits_is_refused[BATCH_MAX_REQUESTS]` |
| S5 the provider's byte limit not asked | killed | its `BATCH_MAX_BYTES` case |
| S6 an empty batch taken | killed | the empty case |
| P1 a request `ask`'s gates refuse sent anyway | killed | `test_a_request_the_gateway_refuses_is_refused_alone_and_the_rest_sent`, `test_a_batch_while_a_workspace_limit_is_held_is_refused_and_nothing_sent` |
| P2 the per-call cap 1,000 times | survived (the test's cap was 0, under any multiple), then killed | `test_a_per_call_cap_holds_each_batched_request` (the cap planted just under and just over the worst case) |
| P3 the batched request built with no TTL | killed | the two body tests (the gateway's, Explain's) |
| P4 the TTL "5m" | killed | the same |
| P5 `build_request` dropping the TTL it is given | killed | the same |
| P6 `_prepared` never passing the TTL | killed | the same |
| P7 `_prepared` passing a TTL of None to every call | killed | `test_an_explain_pack_is_sent_as_the_request_s_one_mask_makes_it_and_nothing_said` (a call's builder takes no TTL) |
| P8 a batched request built without its context | killed | `test_each_batched_request_is_explain_packs_but_its_cache_ttl` |
| C1 the evaluation's stop doubled | killed | `test_a_batch_over_the_evaluations_stop_is_refused_naming_both` |
| C2 the stop never asked | killed | the same |
| C3 the day cap without the batch's worst case | killed | the day-cap refusal, and the spend-and-in-flight test |
| C4 the day cap without what is in flight | killed | `test_the_day_cap_counts_todays_spend_and_whats_in_flight` |
| C5 the day cap without today's spend | killed | the same |
| C6 `>` to `>=` at the day cap | killed | `test_a_batch_reaching_the_day_cap_exactly_is_sent` |
| C7 an unreadable record read as nothing spent | killed | `test_an_unreadable_record_refuses_the_batch` |
| C8 the batch reserved at $0 | killed | `test_the_batchs_worst_case_is_reserved_while_in_flight_and_settled_after` |
| C9 a reservation refused, the batch sent anyway | killed | 3, the day-cap refusal among them |
| C10 the reservation living 24 hours, not 25 | killed | the in-flight test, `test_the_reservation_lives_as_long_as_the_batch_could_bill` |
| C11 never settled | killed | 7 |
| C12 settled though a row was not recorded | survived (no test had a row refused), then killed | `test_a_row_that_could_not_be_recorded_leaves_the_batchs_reservation_to_expire` (added) |
| C13 a workspace limit held from before not cleared once the batch was taken | killed | `test_a_submitted_batch_clears_a_workspace_limit_held_from_before` |
| R1 the batch rate 1.0 | killed | 4, the batch-rate record test among them |
| R2 the 1-hour write at 1.25x input | killed | the record test, `test_the_batch_rate_is_half_of_every_standard_rate_and_dated` |
| R3 a 1-hour write priced as a 5-minute one | killed | the record test |
| R4 writes without a breakdown read as 5-minute | killed | `test_cache_writes_without_a_breakdown_are_the_dearer_1_hour[usage0]` |
| R5 a breakdown short of the total dropping the rest | killed | its `usage2` case |
| R6 a batched answer priced at the standard rate | killed | the record test |
| R7 an unbilled result counted at its worst case | killed | `test_errored_canceled_and_expired_are_recorded_so_unbilled_never_a_success` |
| R8 a result whose bill is unknown counted at $0 | killed | the missing-result test, the wait's bound test |
| R9 an error's message unmasked | killed | the errored test (a planted community string) |
| R10 every request given the first result | killed | 5, `test_results_are_matched_by_custom_id_in_any_order` among them |
| R11 a result for no waiting request kept unsaid | survived (it is never read), then killed | `test_a_missing_or_unknown_result_counts_its_worst_case` (its log line asserted) |
| R12 any result carrying a message read as an answer | survived, then killed | `test_an_errored_result_carrying_a_message_is_never_read_as_an_answer` (added) |
| W1 the wait's bound 10 times | killed | `test_the_wait_is_bounded_and_fires_naming_what_ran`, the canceled-past-its-bound test |
| W2 the bound 1x the stated hour | killed | the bound test (its words) |
| W3 no cancel past the bound | killed | 3 |
| W4 a transient state read ending the wait | survived (the cancel then ended the batch), then killed | `test_a_state_read_failing_transiently_is_asked_again` (now: never canceled, read twice) |
| W5 a refused state read asked again | killed | `test_a_state_read_refused_ends_the_wait_and_counts_the_worst_case` |
| A1 a batch id put in the address unchecked | killed | 4 cases of `test_a_batch_id_out_of_shape_is_refused_before_anything_is_sent` |
| A2 the id's shape a prefix only | killed | its `msgbatch_01/../x` case |
| A3 an answer's batch id not checked | killed | `test_an_answer_naming_a_batch_id_out_of_shape_is_provider_down` |
| A4 the results read from the batch's own address | killed | `test_the_adapter_submits_reads_cancels_and_reads_results_on_the_providers_host` |
| A5 a batch call with no key sent | killed | `test_no_key_sends_no_batch` |
| A6 a results line not JSON skipped | killed | `test_a_results_line_that_is_not_json_is_never_skipped` |
| A7 only the first request submitted | survived (the test submitted one), then killed | the adapter's wire test (now two requests) |
| A8 a workspace limit read as a plain bad request | killed | its `WorkspaceLimit` case |
| E1 v6's first request without its `looked_up` block | killed | `test_v6s_need_is_looked_up_once_and_its_follow_up_batched` |
| E2 Explain's batched request without its context | killed | `test_each_batched_request_is_explain_packs_but_its_cache_ttl` |
| E3 the follow-up without what was looked up | killed | the v6 test |
| E4 Explain's batched answers not checked | killed | `test_each_answer_is_checked_as_explain_pack_checks_it`, the body test |
**The result: 60 mutants; every one killed, six (P2, C12, R11, R12, W4, A7) after a test was
added or strengthened, each named above; the canary killed. The harness names a failing
parametrized test only up to the first space in its id. Not covered here: a live batch. No
provider request was made, and the wire shape is the provider's documentation, read
2026-10-29.**

