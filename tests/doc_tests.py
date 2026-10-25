"""The doc set (the operator, 2026-10-25): the test files a commit whose every path is under
`docs/` (the register among them) runs, in the gate (`scripts/nmas-gate`) and in CI (the `docs`
job, `scripts/nmas-shards docs`). Any other commit runs everything. (Not a test module.)

Two halves, so a reader is neither missed nor guessed:

- MEASURED (2026-10-25): the whole suite run once with an audit hook recording, per test, every
  file it opened in the checkout and every `git`/`grep` it started (14916 passed): each test
  file that opened a file under `docs/` or `CLAUDE.md`, and each whose `git ls-files` or
  `grep -r` reads every tracked file. A test that only lists `modules/`, `routes/` or
  `scripts/` is not here: a docs-only commit cannot change what it reads.
- READS_DOCS: every test file whose source names a read of one, found when the set is asked
  for, so a test written after the measurement that reads a document joins the set by itself.

What it cannot see: a test reading a document only through a helper in another file, with no
pattern in its own source. Every commit touching anything outside `docs/` runs every test, so
such a test still runs on the next code commit.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_PREFIX = "docs/"

MEASURED = (
    "test_blueprint_reachability.py", "test_board_fidelity.py", "test_bootstrap_config.py",
    "test_cache_policy.py", "test_claude_md_c663_script.py", "test_claude_md.py",
    "test_concepts_are_taught.py", "test_csp.py", "test_cutover_rows.py", "test_device_names.py",
    "test_dhcp_leases.py", "test_golden_panel_says_what_to_do.py", "test_host_step_check.py",
    "test_hostvars_secrets.py", "test_identity.py", "test_inline_javascript.py",
    "test_inventory_dispatch_refuses.py", "test_kea_m5_helper.py", "test_lab_specifics.py",
    "test_manual.py", "test_manual_references.py", "test_netbox_test_says_why.py",
    "test_no_conflict_markers.py", "test_no_duplicate_definitions.py", "test_no_pattern_kill.py",
    "test_nothing_personal_is_published.py", "test_no_unreachable_ui.py", "test_page_network.py",
    "test_persist_effect.py", "test_phase7_mode.py", "test_probe_topologies.py",
    "test_prometheus_targets.py", "test_register_hygiene.py",
    "test_rotation_left_unpersisted.py", "test_route_reachability.py",
    "test_secret_responses_no_store.py", "test_settings_write_path.py",
    "test_swaps_in_a_browser.py", "test_swap_targets_resolve.py", "test_test_weakening_check.py",
    "test_third_party_inventory.py", "test_update_button.py", "test_v2_brand.py",
    "test_v2_context_is_drawn.py", "test_v2_layout_in_a_browser.py",
    "test_v2_links_stay_on_v2.py", "test_v2_swaps_never_silent.py", "test_venv_deploy.py",
    "test_vios_configless_patch.py", "test_ztp_reservations.py",
)

#: A read of a document in a test's own source: a path joined onto `docs`, a quoted path to a
#: file under `docs/`, `CLAUDE.md` as a path, or a read of every tracked file.
READS_DOCS = re.compile(
    r"""join\([^)]*["']docs["']|/ *["']docs["']|["']docs/[A-Za-z0-9_./-]+\.(?:md|txt|json|html|yml)["']"""
    r"""|["']CLAUDE\.md["']|ls-files|grep -r|rglob\(|os\.walk\(""")


def reads_docs(source: str) -> bool:
    return bool(READS_DOCS.search(source))


def doc_set(root: str = ROOT) -> list:
    """The doc set's test files, as `tests/<file>` paths, sorted: MEASURED and every test file
    whose source READS_DOCS. A measured file that no longer exists is left out."""
    tests = os.path.join(root, "tests")
    names = set()
    for name in os.listdir(tests):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(tests, name), encoding="utf-8") as fh:
                if name in MEASURED or reads_docs(fh.read()):
                    names.add(name)
    return sorted(f"tests/{n}" for n in names)


def docs_only(paths) -> bool:
    """Does every one of *paths* lie under `docs/`? An empty change is never docs-only (it
    runs everything), and CLAUDE.md is not under `docs/`."""
    paths = [p for p in paths if p]
    return bool(paths) and all(p.startswith(DOC_PREFIX) for p in paths)
