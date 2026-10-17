"""No new capability on a v1 page (the operator, 2026-10-03: "nothing new on the v1 export;
once the v2 card exists, every link opens it and the v1 export joins CUTOVER's remove list").

Today's interface (every template outside `templates/v2`, and every script no v2 page loads)
is frozen: what a person can press there, and what its scripts define, may only shrink. A
fix to today's pages keeps its counts; a new control or function there fails here, and the
capability is built on v2 instead. The ceilings were measured 2026-10-03 and only fall:
lower one when a cutover removes what it counted.

The population is defined by where a thing is drawn or loaded, never by a list of files:
a new v1 template or script is counted the moment it exists.
"""

import os
import re

from tests import manual_actions as M
from tests.source_index import track_all, tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
JS = os.path.join(ROOT, "static", "js")

#: Measured 2026-10-03.
CONTROLS_CEILING = 23    # 2026-10-17: today's Git tab left (7.8, P7-21: its Refresh and its commit dialog's Close; the device page's Restore from… left with the page). Before: 2026-10-17: today's device page left (7.8, P7-22: its Restore from…, Capture as golden, Seed intent, Revert intent…, Retry rolled-back change…, Rotate credential…, Persist…, Retire…, Back to Devices, Run Command and Copy). Before: 2026-10-17: today's NetBox tab left (7.8: its Open NetBox, Refresh, Import Current List and Import All Lists, and its dialog's Cancel, Just stop tracking and Confirm). Before: 2026-10-15: today's Settings modal, Logs tab and status bar left (7.8: the list bar's Settings, the NetBox tab's Open Settings, the modal's Test Connection, Cancel and Save Settings, the Logs tab's Refresh). Before: 2026-10-15: today's Drift tab left (7.8: its panel's Check Now). Before: 2026-10-15: today's bulk commands and Restore Golden Config at HEAD left (7.8: the bulk panel's Execute, Clear Selection and Restore Golden Config, the results modal's Close, the device page's Restore Golden Config). Before: 2026-10-14: today's Backups left (7.8, C632: the device page's Backups tab, Backup Config, Compare Backups and its modal's Compare). Before: 2026-10-14: the AI family left (D15: the AI panel, the Agent, Approvals and Ansible tabs, the AI settings). Before: 2026-10-13: the TFTP setting left (7.8, D16). Before: 2026-10-13: Bulk file actions left (7.8, D16). Before: 2026-10-13: Device files left (7.8, D16). Before: 2026-10-13: Quick actions left (7.8, D16). Before: 2026-10-12: today's Topology tab left (7.8). Before: the topology service panel left (7.8). Before: the Monitoring tab left with the legacy collectors (7.8). Before: the Configure tab left (7.8). Before: the stack panel's Refresh left (7.8). Before: Reload Devices left with /bulk_reload (7.8). Before: Refresh Hostnames left (7.8). Before: today's History tab left with /list/change_log (7.8). Before: 2026-10-08: the freshness panel left (Phase 3). Before: 2026-10-04: the 81 CCIE-KB config types left with ccie_kb/ (NSOT_PLAN 8.12)
HANDLERS_CEILING = 16    # 2026-10-17: today's Git tab left (7.8, P7-21: its Refresh onclick and its commit row's onclick). Before: 2026-10-17: today's device page left (7.8, P7-22: its eight action buttons' onclicks). Before: 2026-10-17: today's NetBox tab left (7.8: Refresh's, Import Current List's and Import All Lists' onclicks, and its dialog's Just stop tracking and Confirm). Before: 2026-10-15: today's Settings modal and Logs tab left (7.8: the two openSettingsModal onclicks, Test Connection's, Save Settings', the Logs Refresh's onclick and its filter's oninput). Before: 2026-10-15: today's Drift tab left (7.8: the interval's and the switch's onchange, Check Now's onclick). Before: 2026-10-15: today's bulk commands and Restore Golden Config at HEAD left (7.8). Before: 2026-10-14: today's Backups left (7.8, C632). Before: 2026-10-14: the AI family left (D15). Before: 2026-10-13: the TFTP setting left (7.8, D16). Before: 2026-10-13: Bulk file actions left (7.8, D16). Before: 2026-10-13: Device files left (7.8, D16). Before: 2026-10-12: today's Topology tab left (7.8). Before: the topology service panel left (7.8). Before: the Monitoring tab left with the legacy collectors (7.8). Before: the Configure tab left (7.8). Before: the stack panel's Refresh left (7.8). Before: Reload Devices left with /bulk_reload (7.8). Before: Refresh Hostnames left (7.8). Before: today's History tab left (7.8). Before: 2026-10-08: the freshness panel left (Phase 3)
FUNCTIONS_CEILING = 281   # 2026-10-17: thirty-one left with today's Git tab, Remote card and Baselines (7.8, P7-21: the Remote card's five (partials__golden_repo.2.js), the Baselines panel's and its re-apply dialog's eight (partials__golden_repo.3.js) and nine (the panel's rows in partials__golden_repo.1.js), and nmas_restore_scope.js's nine). Before: 2026-10-17: two left with today's device page (7.8, P7-22: its Changes tab's deviceChangesHtml and loadDeviceChanges). Before: 2026-10-17: nineteen left with today's NetBox tab (7.8: index.4.js's NetBox section, the import and removal dialog's script, nmas_netbox_removals.js). Before: 2026-10-15: twenty-one left with today's Settings modal and status bar (7.8: the integrations and security posture partials' scripts, netboxTestFromSettings, the status bar's). Before: 2026-10-15: today's drift panel's four left with its tab (7.8: loadDriftStatus, driftDetailHtml, saveDriftSettings, runDriftCheck). Before: 2026-10-15: the bulk panel's functions left with today's bulk commands (7.8: the selection, the command and its results, Restore Golden Config at HEAD). Before: 2026-10-14: refreshCapture left with the template preview's backup store (7.8, C632). Before: 2026-10-14: the AI family's functions left (D15: the AI panel's, index.2.js, the agent, approvals and playbook functions in index.4.js, the usage summary). Before: 2026-10-12: applyDeviceRegions and refreshDeviceRegions left with /devices/regions (7.8). Before: the status polling (deviceIps, updateStatus) left with /status (7.8). Before: today's Topology tab (index.3.js) left (7.8). Before: the topology service panel's left (7.8). Before: the Monitoring tab's twelve left with the legacy collectors (7.8). Before: the stack panel's four functions left (7.8). Before: saveInventoryOrder left with /inventory/order (7.8). Before: the break-glass modal's eight functions left with /breakglass/preview (7.8). Before: the legacy store's card, the migration's card and its apply left (7.8). Before: Sync device names left with the renames routes (7.8). Before: today's History tab left (7.8). Before: 2026-10-08: the freshness panel left (Phase 3)
#: Fields a person can fill on today's pages: form elements in its templates, and the
#: settings fields its scripts draw from a spec (`{key: '<setting>', ...}`), less the
#: recorded exceptions below. Measured 2026-10-03 (261 elements and 68 spec fields).
FIELDS_CEILING = 17   # 2026-10-17: today's device page's command box and its filesystem field left (7.8, P7-22). Before: 2026-10-17: today's NetBox dialog's Permit NetBox writes left (7.8). Before: 2026-10-15: today's Settings modal left (7.8: its NetBox fields, the integrations cards' spec fields, the general block, the write switch, and the Logs tab's four). Before: 2026-10-15: today's Drift tab's interval and Enabled switch left (7.8). Before: 2026-10-15: the bulk panel's fields left (7.8: the command mode, the command, Select all and each row's checkbox). Before: 2026-10-14: today's Backups' fields left (7.8, C632: the config type and the two compare choosers). Before: 2026-10-14: the AI settings and the agent timer and task fields left (D15). Before: 2026-10-13: the TFTP root field left (7.8, D16). Before: 2026-10-13: the TFTP setting left (7.8, D16). Before: 2026-10-13: Bulk file actions left (7.8, D16). Before: 2026-10-13: Device files left (7.8, D16). Before: 2026-10-12: the topology service's Settings card left (7.8). Before: today's Topology tab left (7.8). Before: the topology service panel's interval left (7.8). Before: the Monitoring tab's forms left (7.8). Before: the Configure tab's forms left (7.8). Before: 2026-10-08: the Oxidized settings card left (Phase 3). Before: 2026-10-04: the KB's dynamic form left with it

#: RECORDED EXCEPTIONS to the rule, each a v1 settings field by its key, with its reason and
#: where it goes at cutover. A field is excepted only by the operator's decision.
#: Empty since 2026-10-15: the two (grafana_token_expires and proxmox_token_expires, the
#: operator's of 2026-10-03) moved at cutover as decided, leaving with today's Settings modal at
#: 7.8; they are fields of Settings › Default's Grafana card and Installation's Proxmox card.
EXCEPTIONS = {}
_SPEC_FIELD = re.compile(r"\{\s*key:\s*'([a-z0-9_]+)'")
_FORM_FIELD = re.compile(r"<(?:input|select|textarea)\b")

_FN = re.compile(r"^\s*(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(|^\s*root\.\w+\s*=\s*function",
                 re.M)


def v1_templates() -> list:
    return [p for p in tracked(TEMPLATES, suffix=".html", root=os.path.dirname(TEMPLATES))
            if os.path.relpath(p, TEMPLATES).split(os.sep)[0] != "v2"]


def v2_scripts() -> set:
    """Every script a v2 template loads: v2's own, free to grow."""
    found = set()
    for path in tracked(os.path.join(TEMPLATES, "v2"), root=os.path.dirname(TEMPLATES)):
        text = open(path, encoding="utf-8").read()
        found |= set(re.findall(r"js/(nmas_\w+\.js)", text))
    return found


def v1_scripts() -> list:
    v2 = v2_scripts()
    out = [os.path.join(JS, f) for f in os.listdir(JS) if f.endswith(".js") and f not in v2]
    gen = os.path.join(JS, "gen")
    out += [os.path.join(gen, f) for f in os.listdir(gen) if f.endswith(".js")]
    return sorted(out)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def spec_fields() -> list:
    """Every settings field a v1 script draws from a spec, by its key."""
    return [k for p in v1_scripts() for k in _SPEC_FIELD.findall(_read(p))]


def counts() -> dict:
    texts = [_read(p) for p in v1_templates()]
    return {"fields": (sum(len(_FORM_FIELD.findall(t)) for t in texts)
                       + len([k for k in spec_fields() if k not in EXCEPTIONS])),
            "controls": sum(len(M.controls(t)) for t in texts),
            "handlers": sum(len(re.findall(r"\bon(click|change|submit|input)=", t))
                            for t in texts),
            "functions": sum(len(_FN.findall(_read(p))) for p in v1_scripts())}


class TestTodaysInterfaceOnlyShrinks:
    def test_the_populations_are_found(self):
        # v1 templates 19 and scripts 37 since 2026-10-12: the stack and topology service panels and
        # today's Topology tab's script left (7.8). Scripts 36 since 2026-10-14: index.2.js (the AI
        # device cache) left with the AI family (D15). Templates 17 and scripts 33 since
        # 2026-10-15: today's Settings modal's two partials and their scripts, and the status
        # bar's script, left (7.8). Templates 15 and scripts 31 since 2026-10-17: today's NetBox
        # tab's two partials (the import and removal dialog, the removals panel) and their two
        # scripts left (7.8). Templates 13 and scripts 30 since 2026-10-17 (later the same day):
        # today's device page and its Changes partial, and the partial's script, left (7.8, P7-22).
        # Scripts 26 the same day (P7-21): today's Git tab's index.4.js, the Remote card's and the
        # Baselines panel's two (partials__golden_repo.2.js and .3.js) and nmas_restore_scope.js.
        assert len(v1_templates()) >= 13 and len(v1_scripts()) >= 26
        assert {"nmas_v2.js", "nmas_update.js"} <= v2_scripts()

    def test_no_new_control_handler_or_function(self):
        c = counts()
        assert c["controls"] <= CONTROLS_CEILING, (
            f"{c['controls']} controls on today's pages, the ceiling {CONTROLS_CEILING}: build "
            "the new capability on v2 (a v1 page gains nothing new)")
        assert c["handlers"] <= HANDLERS_CEILING, (c["handlers"], HANDLERS_CEILING)
        assert c["functions"] <= FUNCTIONS_CEILING, (c["functions"], FUNCTIONS_CEILING)
        assert c["fields"] <= FIELDS_CEILING, (
            f"{c['fields']} fields on today's pages, the ceiling {FIELDS_CEILING}: a new field "
            "goes on v2, or is a recorded exception the operator decided (EXCEPTIONS)")

    def test_each_exception_is_there_with_its_reason_and_where_it_goes(self):
        """An exception names a field that exists (a stale one would excuse the next field
        under its key), the operator's decision, and that it moves at cutover."""
        present = set(spec_fields())
        for key, why in EXCEPTIONS.items():
            assert key in present, f"{key}: excepted and not on today's pages: remove it"
            assert "the operator" in why and why.endswith("Moves at cutover"), key

    def test_a_ceiling_never_sits_above_what_is_there(self):
        """A ceiling left high after a removal would let the next addition through."""
        c = counts()
        assert (c["controls"], c["handlers"], c["functions"], c["fields"]) == (
            CONTROLS_CEILING, HANDLERS_CEILING, FUNCTIONS_CEILING, FIELDS_CEILING), (
            f"lower the ceilings to what is there now: {c}")

    def test_a_planted_control_is_found(self, tmp_path, monkeypatch):
        planted = tmp_path / "templates"
        (planted / "v2").mkdir(parents=True)
        (planted / "page.html").write_text('<button class="btn">Do a new thing…</button>')
        track_all(tmp_path)
        monkeypatch.setattr(__import__(__name__), "TEMPLATES", str(planted))
        assert len(v1_templates()) == 1
        assert sum(len(M.controls(_read(p))) for p in v1_templates()) == 1
