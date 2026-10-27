"""The ratchets: every list, table or number in the tests (and the few in the product) that may
move only one way, declared so scripts/nmas-test-weakening-check can refuse a commit that moves
one the other way without a `Test-Weakened: <list> — C<n>: <reason>` trailer (CLAUDE.md,
"Measurement and testing": a ceiling, allowlist, known-gap or excused list only goes down).
(Not a test module; tests/test_test_weakening_check.py holds it whole.)

`RATCHETS` is `(file, the module-level name, kind)`, the kinds:

- `shrinks`: a list, tuple, set or dict that may only lose members. A member in the commit that
  is not in its parent is refused even where another left; a dict's members are its keys, and
  the members of a value that is itself a collection; a record's last item is its reason (an
  edited reason is no new member) and its leading number a count that may not rise.
- `grows`: the mirror, a list or dict that may only gain members: a member of the parent the
  commit no longer holds is refused (a hook test's refused forms: removing one stops testing a
  refusal; the operator, 2026-10-26).
- `ceiling`: a number that may not rise. `floor`: a number that may not fall (the operator's
  spec names ceilings; a lowered population floor is the same weakening, mirrored).
- `ceilings` / `floors`: a table of numbers, each held the same way.
- `uncovered`: the coverage baseline's modules, each one's uncovered count (functions less
  covered_unit, scripts/nmas_coverage.py's `ratchet`) may not rise.
- `registry`: this file's own `RATCHETS`: an entry may not leave while its list is still there.

The script reads this file by parsing it at the commit and at its parent (the union), so an
entry added in the same commit as a loosening, or dropped by it, still holds that commit.

The population is DEFINED by a property, not by guessing names: tests/test_test_weakening_check.py
scans every module-level assignment in tests/ and modules/ whose value is a collection or a
number and whose name carries a ratchet's stem (EXCUS, EXEMPT, KNOWN, GAP, ALLOW, PENDING,
UNCHECKED, UNDRAWN, UNREACH, UNSIGNED, MISSING, NOT_YET, CEILING, FLOOR, ... `STEMS` there), or
whose own comment says it only shrinks; each is here or in `NOT_RATCHETS` with why.

Bounds that live inside a test (`assert len(found) >= 16`, `assert n <= LIMIT`) need no entry:
the script compares every assert that bounds an expression by a number, or by a name bound to
one in the same function or module.
"""

RATCHETS = (
    # ── A hook test's refused forms: they only grow (the operator, 2026-10-26; every one is
    #    declared, tests/test_test_weakening_check.py's hook-test scan) ────────────────────
    ("tests/test_claude_heredoc_hook.py", "REFUSED", "grows"),
    ("tests/test_claude_host_writes_hook.py", "REFUSED", "grows"),
    ("tests/test_claude_md_edit_hook.py", "REFUSED_BASH", "grows"),
    ("tests/test_claude_md_edit_hook.py", "REFUSED_FILE", "grows"),
    ("tests/test_claude_prose_edit_hook.py", "REFUSED", "grows"),
    ("tests/test_claude_restore_hook.py", "REFUSED", "grows"),
    # ── Known gaps, excused and pending lists: they only shrink ─────────────────────────────
    ("modules/manual.py", "ON_TODAYS_APP", "shrinks"),
    ("modules/manual.py", "UNDECLARED", "shrinks"),
    ("tests/conftest.py", "STORE_WRITERS_EXEMPT", "shrinks"),
    ("tests/conftest.py", "STORE_REWRITERS_EXEMPT", "shrinks"),
    ("tests/conftest.py", "READER_STORES_SHARED", "shrinks"),
    ("tests/mutation_equivalent.py", "EQUIVALENT", "shrinks"),
    ("tests/publication_exemptions.py", "EXEMPT", "shrinks"),
    ("tests/signed_off_screens.py", "UNSIGNED", "shrinks"),
    ("tests/test_ai_explain_cases.py", "AWAITING", "shrinks"),
    ("tests/test_app_interpreter.py", "EXEMPT", "shrinks"),
    ("tests/test_blueprint_reachability.py", "KNOWN_UNREACHABLE", "shrinks"),
    ("tests/test_board_fidelity.py", "UNCHECKED", "shrinks"),
    ("tests/test_concepts_are_taught.py", "PENDING", "shrinks"),
    ("tests/test_confirm_buttons_drawn.py", "EXCUSED", "shrinks"),
    ("tests/test_deploy_receipts.py", "STILL_NAMED", "shrinks"),
    ("tests/test_deploy_receipts.py", "UNDRAWN_ON_V2", "shrinks"),
    ("tests/test_device_names.py", "INVENTORY", "shrinks"),
    ("tests/test_device_text_is_refused.py", "NOT_REQUEST_TEXT", "shrinks"),
    ("tests/test_host_step_scripts.py", "UNEXPORTED_EXCUSED", "shrinks"),
    ("tests/test_invalidation_map.py", "NOT_YET_SUBSCRIBED", "shrinks"),
    ("tests/test_lab_specifics.py", "INVENTORY", "shrinks"),
    ("tests/test_large_fleets.py", "EXCUSED", "shrinks"),
    ("tests/test_network_settings_read_for_a_list.py", "INVENTORY", "shrinks"),
    ("tests/test_network_settings_read_for_a_list.py", "COMPUTED", "shrinks"),
    ("tests/test_no_get_returns_a_stored_secret.py", "KNOWN_LEAKS", "shrinks"),
    ("tests/test_no_ip_literals.py", "ALLOWED_EXACT", "shrinks"),
    ("tests/test_no_new_v1_capability.py", "EXCEPTIONS", "shrinks"),
    ("tests/test_no_new_v1_capability.py", "NON_GUI", "shrinks"),
    ("tests/test_no_unreachable_ui.py", "KNOWN_DEAD", "shrinks"),
    ("tests/test_one_home_per_action.py", "KNOWN_DUPLICATES", "shrinks"),
    ("tests/test_one_stepper.py", "NOT_YET", "shrinks"),
    ("tests/test_one_template_resolver.py", "EXEMPT", "shrinks"),
    ("tests/test_profile_apply.py", "NOT_YET_ON_A_DEVICE", "shrinks"),
    ("tests/test_reads_create_no_list.py", "KNOWN_CREATORS", "shrinks"),
    ("tests/test_reads_write_nothing.py", "KNOWN_WRITERS", "shrinks"),
    ("tests/test_render_helpers_are_called.py", "_ALLOWED", "shrinks"),
    ("tests/test_results_are_drawn.py", "PENDING", "shrinks"),
    ("tests/test_results_are_drawn.py", "FALSE_GREEN", "shrinks"),
    ("tests/test_results_are_drawn.py", "UNESCAPED", "shrinks"),
    ("tests/test_route_gates.py", "ACTOR_EXEMPTIONS", "shrinks"),
    ("tests/test_route_reachability.py", "NON_GUI", "shrinks"),
    ("tests/test_route_reachability.py", "KNOWN_UNREACHABLE", "shrinks"),
    ("tests/test_script_entry_points.py", "_SKIP_DIRS", "shrinks"),
    ("tests/test_session_write_guard.py", "HELD_BY_CALLER", "shrinks"),
    ("tests/test_session_write_guard.py", "KNOWN_UNHELD", "shrinks"),
    ("tests/test_swaps_in_a_browser.py", "KNOWN", "shrinks"),
    ("tests/test_unknown_platform_refused.py", "EXCUSED", "shrinks"),
    ("tests/test_v2_brand.py", "KEPT_STRINGS", "shrinks"),
    ("tests/test_v2_context_is_drawn.py", "UNDRAWN", "shrinks"),
    ("tests/test_v2_context_is_drawn.py", "UPSTREAM", "shrinks"),
    ("tests/test_v2_context_is_drawn.py", "UNREACHED", "shrinks"),
    ("tests/test_v2_context_is_drawn.py", "EMPTY_IN_FIXTURE", "shrinks"),
    ("tests/test_v2_layout_in_a_browser.py", "C503_KNOWN_GAPS", "shrinks"),
    ("tests/test_v2_one_confirm.py", "SECOND_IMPLEMENTATIONS", "shrinks"),
    ("tests/test_v2_one_confirm.py", "LEGACY_HOMES", "shrinks"),
    ("tests/test_v2_text_sends_nowhere_old.py", "EXCUSED", "shrinks"),
    ("tests/test_host_actor_is_labelled.py", "EXCUSED", "shrinks"),
    ("tests/todays_page_links.py", "GAPS", "shrinks"),
    ("tests/todays_page_links.py", "OTHER_GAPS", "shrinks"),
    ("tests/coverage_baseline.json", "assertion_free", "shrinks"),
    ("tests/ratchet_lists.py", "NOT_RATCHETS", "shrinks"),
    # ── Ceilings: they never rise ───────────────────────────────────────────────────────────
    ("modules/operation_stages.py", "MISSING_CEILING", "ceiling"),
    ("modules/operation_stages.py", "HISTORY_MISSING_CEILING", "ceiling"),
    ("tests/signed_off_screens.py", "UNSIGNED_CEILING", "ceiling"),
    ("tests/test_board_fidelity.py", "UNCHECKED_CEILING", "ceiling"),
    ("tests/test_concepts_are_taught.py", "PENDING_CEILING", "ceiling"),
    ("tests/test_confirm_buttons_drawn.py", "EXCUSED_CEILING", "ceiling"),
    ("tests/test_invalidation_map.py", "NOT_YET_CEILING", "ceiling"),
    ("tests/test_large_fleets.py", "LIMIT", "ceiling"),
    ("tests/test_manual.py", "UNDECLARED_CEILING", "ceiling"),
    ("tests/test_no_get_returns_a_stored_secret.py", "KNOWN_LEAKS_CEILING", "ceiling"),
    ("tests/test_no_new_v1_capability.py", "CONTROLS_CEILING", "ceiling"),
    ("tests/test_no_new_v1_capability.py", "HANDLERS_CEILING", "ceiling"),
    ("tests/test_no_new_v1_capability.py", "FUNCTIONS_CEILING", "ceiling"),
    ("tests/test_no_new_v1_capability.py", "FIELDS_CEILING", "ceiling"),
    ("tests/test_route_reachability.py", "CEILING", "ceiling"),
    ("tests/test_v2_context_is_drawn.py", "UNDRAWN_CEILING", "ceiling"),
    ("tests/test_v2_context_is_drawn.py", "UPSTREAM_CEILING", "ceiling"),
    ("tests/test_v2_context_is_drawn.py", "UNREACHED_CEILING", "ceiling"),
    ("tests/test_v2_context_is_drawn.py", "EMPTY_IN_FIXTURE_CEILING", "ceiling"),
    ("tests/test_v2_layout_in_a_browser.py", "C503_GAPS_CEILING", "ceiling"),
    ("tests/test_v2_one_confirm.py", "SECOND_IMPLEMENTATIONS_CEILING", "ceiling"),
    ("tests/todays_page_links.py", "CEILING", "ceiling"),
    ("tests/test_results_are_drawn.py", "CEILINGS", "ceilings"),
    ("tests/coverage_baseline.json", "modules", "uncovered"),
    # ── Floors: they never fall (a population a scan must keep finding) ─────────────────────
    ("tests/test_concepts_are_taught.py", "MIN_WORDS", "floor"),
    ("tests/test_confirm_buttons_drawn.py", "FLOOR", "floor"),
    ("tests/test_console_records_at_rest.py", "FLOOR", "floor"),
    ("tests/test_oxidized_settings_inert.py", "FLOOR", "floor"),
    ("tests/test_probe_topologies.py", "MIN_TOPOLOGIES", "floor"),
    ("tests/test_probe_topologies.py", "MIN_C8000V_NODES", "floor"),
    ("tests/test_route_gates.py", "MUTATING_FLOOR", "floor"),
    ("tests/test_sdn_authority.py", "POPULATION_FLOOR", "floor"),
    ("tests/test_v2_busy_on_itself.py", "MEMBERS_FLOOR", "floor"),
    ("tests/test_v2_busy_on_itself.py", "FORM_SUBMITS_FLOOR", "floor"),
    ("tests/test_v2_busy_on_itself.py", "SCRIPT_POSTERS_FLOOR", "floor"),
    ("tests/test_v2_context_is_drawn.py", "LOOPS_FLOOR", "floor"),
    ("tests/test_v2_context_is_drawn.py", "DREW_FLOOR", "floor"),
    ("tests/test_v2_layout_in_a_browser.py", "TABLE_GAP_PX", "floor"),
    ("tests/test_v2_one_confirm.py", "POPULATION_FLOOR", "floor"),
    ("tests/test_v2_one_confirm.py", "PATTERN_FLOOR", "floor"),
    ("tests/test_v2_one_confirm.py", "V2_SCRIPTS_FLOOR", "floor"),
    # ── This registry ───────────────────────────────────────────────────────────────────────
    ("tests/ratchet_lists.py", "RATCHETS", "registry"),
)

#: (file, name) -> why: what the completeness scan finds that is not a ratchet. Only shrinks
#: (a ratchet excused here is a ratchet unwatched).
NOT_RATCHETS = {
    # The product's own thresholds and data, whose name only shares a stem.
    ("modules/ai/nl_query.py", "OFFER_FLOOR"): "a product threshold: the fewest metrics the context budget rule trims an offer to, the deepest rank a case's right metric was measured at (C1830); a better ranking may lower it",
    ("modules/sdn/detect.py", "BASELINE_FLOOR_PPS"): "a product threshold: the least packets a second an idle port's flood baseline counts as, so a quiet port is not flooded by its first ping; to be measured on the slice's first run (C1865), up or down",
    ("modules/sdn/flow_ops.py", "RESPONSE_PRIORITY_FLOOR"): "a product constant: the lowest OpenFlow priority a response's flow takes (300, the boards' figure), a documented priority scheme, not a count any test holds; it moves with the scheme, up or down (C1837)",
    ("tests/test_sdn_drivers.py", "LEAK_PATHS"): "test data, not a ratchet: each way a controller's answer could carry a credential back, one parametrized case each; it only grows as paths are found (C1837)",
    ("modules/attention.py", "INCIDENT_GAP_SECONDS"): "a product setting: the gap that splits incidents",
    ("modules/config_read.py", "SIZE_FLOOR"): "a product threshold on a config's size, not a test's",
    ("modules/drained.py", "FLOOR_PPS"): "a product threshold: the packet rate read as drained",
    ("modules/drift_check.py", "_SKIP_STARTSWITH"): "the product's normaliser: lines a comparison ignores",
    ("modules/goldens.py", "_LEGACY_SCAN_WARNED"): "a run-time set of warnings given",
    ("modules/host_steps.py", "LOKI_UNKNOWN_SECONDS"): "a product bound: how long an unknown Loki answer is kept (C1246)",
    ("modules/job_health.py", "LEAK_AFTER_SECONDS"): "a product threshold: when a job's lock is called leaked",
    ("modules/nsot/bulk_intent.py", "KNOWN_CHILDREN"): "the product's model of a section's children",
    ("modules/nsot/normalize.py", "PUSH_SKIP_PREFIXES"): "the product's normaliser: lines a push never sends",
    ("modules/nsot/onboard.py", "BLOCKED_PENDING_MEASUREMENT"): "platforms the product REFUSES until measured: adding one refuses more",
    ("modules/nsot/record_exceptions.py", "EXCEPTIONS"): "history's known misstatements, drawn beside the record; it excuses no test",
    ("modules/nsot/record_exceptions.py", "ROW_EXCEPTIONS"): "history's known misstatements, drawn beside the record; it excuses no test",
    ("modules/pipeline.py", "_SKIP_STARTSWITH"): "the product's normaliser: lines a comparison ignores",
    ("modules/readers/ztp_discovery.py", "GAPS"): "a product setting: the discovery range's gap count",
    ("modules/settings_schema.py", "GUARD_GATING_EMPTY_DEFAULTS"): "settings whose empty default makes a guard refuse: adding one refuses more",
    ("modules/topology_layout.py", "MIN_GAP"): "a drawing's spacing in pixels",
    # Test data and test cases: a member is a case the test asserts, so adding one checks more.
    ("tests/conftest.py", "LEAK_GRACE_SECONDS"): "a measured wait before a thread is named leaked (a bound, CLAUDE.md's 2.5x rule)",
    ("tests/coverage_scope.py", "EXCEPTIONS"): "the coverage tool's placement of each module; tests/test_nmas_coverage.py holds it whole",
    ("tests/test_checker_reads_database_receipts.py", "LEAK"): "a planted receipt holding a secret (fixture)",
    ("tests/test_claude_heredoc_hook.py", "ALLOWED"): "commands the test asserts the hook allows (cases)",
    ("tests/test_claude_host_writes_hook.py", "ALLOWED"): "commands the test asserts the hook allows (cases)",
    ("tests/test_claude_md_edit_hook.py", "ALLOWED_FILE"): "edits the test asserts the hook allows (cases)",
    ("tests/test_claude_md_edit_hook.py", "ALLOWED_BASH"): "commands the test asserts the hook allows (cases)",
    ("tests/test_claude_md_edit_hook.py", "FLAG_ALLOWED"): "commands the test asserts the hook allows (cases)",
    ("tests/test_claude_prose_edit_hook.py", "ALLOWED"): "commands the test asserts the hook allows (cases)",
    ("tests/test_claude_restore_hook.py", "ALLOWED"): "commands the test asserts the hook allows (cases)",
    ("tests/test_dhcp_exclusions.py", "EMPTY"): "an empty Kea document (fixture)",
    ("tests/test_golden_panel_says_what_to_do.py", "INVENTORY"): "a fixture's devices",
    ("tests/test_grafana_reader.py", "INVENTORY"): "a fixture's devices",
    ("tests/test_netbox_dry_run_placeholders.py", "UNKNOWN_VALUE"): "the planted unknown value the fake must refuse (C1248's cases)",
    ("tests/test_network_stores_never_fall_back.py", "LEGACY"): "a legacy settings file (fixture)",
    ("tests/test_normalize_equivalence.py", "LEGACY_DRIFT"): "a legacy prefix list the test compares (fixture)",
    ("tests/test_normalize_equivalence.py", "LEGACY_PIPELINE"): "a legacy prefix list the test compares (fixture)",
    ("tests/test_normalize_equivalence.py", "LEGACY_CONFIG_GIT"): "a legacy prefix list the test compares (fixture)",
    ("tests/test_normalize_equivalence.py", "LEGACY_PUSH"): "a legacy prefix list the test compares (fixture)",
    ("tests/test_update_when_ci_passes.py", "PENDING"): "a pending CI answer (fixture)",
    ("tests/test_verify_verdict_follows_receipt.py", "R7_MISSING"): "a real receipt's read-back misses (fixture, C1541)",
    ("tests/test_verify_verdict_follows_receipt.py", "R7_SKIPPED"): "a real receipt's skipped read-back lines (fixture, C1541)",
}
