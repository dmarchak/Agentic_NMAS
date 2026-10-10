"""C77's sweep: no POST that computes returns a stored secret.

B11's sweep (`test_no_get_returns_a_stored_secret.py`) planted every store
and drove every GET. Its population was defined by the HTTP method, and
`/deploy/plan` and `/golden/restore/preview` are POSTs that compute and
return stored config: both returned a planted community (C77, fixed). The
property is "returns stored config", not "is a GET" (B16's lesson).

**The population is the gate table's `not_device` POSTs** (the routes
that neither reach a device nor change the record: they compute, read, or
save layout), read from `route_gates.GATES` and `app.url_map`, so a new
computing POST is swept by being declared. The other kinds change a device
or the record and are pinned per route (the apply side of C77, whose
responses are masked; `test_previews_mask_secrets.py`).

**Every store is planted** by B11's own planting (`planted_stores`), and
the sweep adds what a POST reads that a GET does not: a device's running
config as a read returns it NOW, a second backup to compare, configs a
caller supplies, a NetBox to preview against, and a list that has what a
real list has (seeded templates, r1's intent extracted and committed
through the routes a person uses, the template approved, a template secret
that differs from the device, and a second golden).

**A refusal proves nothing**, so each route declares the status it must
answer with and, where its response draws stored config, `REACHES`: the
masked slot must be present, which shows the line was reached and masked
rather than never reached. Each route is driven twice, anonymous and as a
verified person.
"""

import json
import os

import pytest

from tests.test_no_get_returns_a_stored_secret import (DEVICE, LIST, _config_body, _fill,
                                                       _p, planted_stores)

PERSON = "test-person@example.invalid"


def _head_golden():
    """r1 as its golden holds it NOW: the same account line as the first
    golden (so a restore's credential guard passes), a different community."""
    return (f"hostname r1\n"
            f"username admin privilege 15 secret 9 {_p('GoldSec')}\n"
            f"snmp-server community {_p('HeadComm')} RO\n"
            f"end\n")


#: endpoint -> (expected status, body builder, why this body reaches it).
#: Every `not_device` POST must be here: a missing one fails the population
#: test, so a new computing POST cannot go unswept by being new.
def _bodies(v):
    return {
        "ai_clear": (200, ("json", {}), "clears the caller's history; returns a status"),
        "ai_stop": (200, ("json", {}), "a stop flag; returns a status"),
        "ai_approval_approve_all": (200, ("json", {}),
                                    "a capture handoff built from the planted queue: "
                                    "device names and item ids, never a diff (C105)"),
        "bulk_clear": (200, ("json", {}), "clears an on-screen result; returns a status"),
        "compare_backups_route": (200, ("form", {"file1": v["_backup_file"],
                                                 "file2": v["_backup_file_2"]}),
                                  "two different backups of r1: the diff carries both"),
        "deploy.plan": (200, ("json", {"devices": ["r1"], "list_name": LIST}),
                        "committed intent renders a community the device does not hold: "
                        "the program adds one, and the device's is residue"),
        "backup_config": (302, ("form", {}), "a form post that redirects; no body"),
        "refresh_files": (302, ("form", {}), "a form post that redirects; no body"),
        "drift_check_trigger": (200, ("json", {}), "schedules a run; returns a message"),
        "settings_v2.diag_drift_check": (409, ("form", {}),
                                         "the network filled in ('zz') is none, so it is "
                                         "refused naming the networks; it starts nothing"),
        "settings_v2.records_store_preview": (404, ("form", {}),
                                              "the direction filled in ('zz') is neither move "
                                              "nor back: refused naming both, counting nothing"),
        "drift_check_sync": (200, ("json", {}),
                             "r1 read NOW differs from its golden: the drift carries both"),
        "golden.capture_preview": (202, ("json", {"devices": ["r1"]}),
                                   "starts a job reading r1 NOW; FOLLOWED to its result "
                                   "(JOB_RESULTS): the golden diff and the intent departure"),
        # The device page's Rotate (7.3): the plan's live read of r1 is refused here (no
        # network), so the card draws the failing preflight; it reads no store a GET does not.
        "device_v2.rotate_preview": (200, ("form", {"list": LIST}),
                                     "the rotation's plan for r1: its live read refused, drawn as "
                                     "the failing preflight"),
        # The device page's Capture (7.3): the same job, for one device, its name filled as r1.
        "device_v2.capture_start": (200, ("form", {"list": LIST}),
                                    "starts the same job reading r1 NOW; FOLLOWED to its card "
                                    "(JOB_RESULTS): the golden diff and the intent departure"),
        "golden.migrate_plan": (200, ("json", {}), "a dry run over the legacy store"),
        "golden.restore_preview": (200, ("json", {"ref": v["_first_golden"],
                                                  "devices": ["r1"]}),
                                   "the first golden against HEAD: a program that adds its "
                                   "community, and HEAD's as residue"),
        "inventory.refresh": (200, ("json", {}), "a local list: refused as not NetBox-sourced"),
        "monitoring_snmp_poll": (200, ("json", {"device_ip": DEVICE["ip"]}),
                                 "an SNMP read with the stored community; the read is faked"),
        "netbox_safety.preview_import": (200, ("json", {"list_name": LIST}),
                                         "a dry-run import of r1 from its golden"),
        "netbox_safety.preview_import_all": (200, ("json", {}), "the same, every list"),
        "netbox_safety.preview_removal": (200, ("json", {"list_name": LIST}),
                                          "a dry-run removal"),
        "netbox_test_connection": (200, ("json", {}),
                                   "the stored URL and token: the connection is refused"),
        "onboard.plan": (200, ("json", {"list_name": LIST, "hostname": "r8",
                                        "platform": "cisco_ios"}),
                         "a plan for a new device; creates nothing"),
        "onboard.verify_preview": (409, ("json", {"list_name": LIST}),
                                   "r1 is managed, never onboarded: refused by name before "
                                   "anything is reached"),
        "remote.verify": (200, ("json", {}),
                          "no remote configured: a configured one would start ssh, which the "
                          "harness refuses and counts as a failure; the remote is an alias "
                          "and a key PATH, never a stored secret"),
        "settings_integrations.test_integration": (200, ("json", {}),
                                                   "driven once per registered integration "
                                                   "below; this row is the grafana one"),
        "templates.preview": (200, ("json", {"list_name": LIST}),
                              "the render (a community the device lacks) against the golden"),
        "templates.refresh_capture": (200, ("json", {}), "delegates to the backup flow"),
        "templates.validate": (200, ("json", {"list_name": LIST}), "validates the template"),
        "templatize.bulk_preview": (200, ("json", {"list_name": LIST, "devices": ["r1"],
                                                   "steps": [{"path": ["hostname"],
                                                              "before": "r1",
                                                              "after": "r1x"}]}),
                                    "a bulk intent change's render delta"),
        "retire.preview": (200, ("json", {"list_name": LIST, "device": "r1",
                                          "reason": "leaving management"}),
                           "r1's retire plan: its steps, the credential gate, the export log"),
        "breakglass.preview": (200, ("json", {"list_name": LIST}),
                               "the list's devices by name and the key's fingerprint an export "
                               "would hold; no value"),
        "rotate.preview": (200, ("json", {"list_name": LIST, "device": "r1"}),
                           "r1's rotation plan: its preflight (the live read refused by the "
                           "suite's network guard, drawn as a failed gate), the masked program"),
        "jobs.job_finished": (409, ("json", {"unit": "nmas-startup-check"}),
                              "a declared job, and the reader jobs do not run in the test "
                              "process: refused by name, nothing read"),
        "update.check": (409, ("json", {}),
                         "the reader jobs do not run in the test process: refused by name, "
                         "nothing asked (no network, no store)"),
        "persist.preview": (200, ("json", {"list_name": LIST, "device": "r1"}),
                            "r1's persist plan: its steps, the inventory gates and the "
                            "startup check's last reading; no device contacted"),
        "templatize.profile_propose_preview": (200, ("json", {"list_name": LIST}),
                                               "the monitoring profile the planted fleet's "
                                               "committed intent agrees on, and each device's "
                                               "stored secret compared IN MEMORY, never shown"),
        "templatize.seed_preview": (200, ("json", {"list_name": LIST, "devices": ["r1"]}),
                                    "r1's committed golden parsed into the intent a seed "
                                    "would commit (r1 already seeded: shown, not selectable)"),
        "templatize.revert_preview": (200, ("json", {"list_name": LIST, "device": "r1"}),
                                      "r1's intent commits and the revert of the newest, "
                                      "computed from git"),
        "templatize.retry_preview": (200, ("json", {"list_name": LIST, "device": "r1"}),
                                     "r1's rollback record (none: nothing to retry) and its "
                                     "retry history"),
        "templatize.preview_committed_edit": (200, ("json", {"list_name": LIST,
                                                             "yaml": v["_intent_text"]}),
                                              "committed intent, previewed against the device"),
        "templatize.report": (200, ("json", {"list_name": LIST}), "the fleet report"),
        # H, the v2 intent editor (board H): its check, acknowledgement and reopen.
        "intent_v2.check": (200, ("form", {"yaml": v["_intent_text"]}),
                            "r1's committed intent checked as typed: its diffs against the "
                            "golden, masked lines never compared, so never drawn"),
        "intent_v2.acknowledge": (200, ("form", {"yaml": v["_intent_text"],
                                                 "ack": "some line"}),
                                  "the editor on the document with its unmodeled_ack block: "
                                  "references only, no stored value"),
        "intent_v2.reopen": (200, ("form", {"yaml": v["_intent_text"]}),
                             "the editor on the document sent"),
        "topology_save_hidden": (200, ("json", {"hidden": []}), "layout"),
        "topology_save_positions": (200, ("json", {"positions": {}}), "layout"),
        "topology_save_proto_hidden": (200, ("json", {"view": "ospf", "hidden": []}), "layout"),
        "topology_save_proto_positions": (200, ("json", {"view": "ospf", "positions": {}}),
                                          "layout"),
    }


#: Responses that draw stored config: the masked slot must be in them.
#: `drift_check_sync` is not among them: it answers with counts and queues
#: the diff as an approval item, which the GET sweep covers.
REACHES = {"compare_backups_route", "deploy.plan", "device_v2.capture_start",
           "golden.capture_preview", "golden.restore_preview", "templates.preview",
           "templatize.preview_committed_edit"}
# `netbox_safety.preview_import` LEFT this set in 7.1: its response no longer
# carries the dry run's object payloads (each device's golden rode in
# `local_context_data`), only the preview drawn from them, so there is no
# stored config in it to mask. The sweep still drives it for a planted value.

#: The two masks: the outbound redactor's, and the template preview's
#: (`render_artifact.MASK`, which JSON carries escaped).
MASKS = ("<redacted:", "\\u2022\\u2022",
         # The v2 card is HTML: the same slot, escaped by Jinja.
         "&lt;redacted:")

#: Integrations whose connection test cannot be driven here, with the reason.
INTEGRATIONS_NOT_DRIVEN = {
    "nsot_git": "its test runs `git ls-remote` against a remote; the harness refuses a "
                "remote git and counts the attempt as a failure",
}


def _population():
    import app as A
    from modules.route_gates import GATES

    out = {}
    for rule in A.app.url_map.iter_rules():
        g = GATES.get(rule.endpoint)
        if g and g.kind == "not_device" and "POST" in (rule.methods or ()):
            out[rule.endpoint] = rule
    return out


def _setup(v, mp, client):
    """What a POST reads that the planting does not provide. Everything is
    built through the program's own writers and routes, as a person."""
    from modules import backups, config, credentials
    from modules.nsot import repo as R
    from modules.nsot import templates_repo

    repo = os.path.join(config.list_data_path(LIST), "config_repo")

    # A list that has what a real list has.
    templates_repo.seed_templates(repo)
    # r1's intent is SEEDED from its golden (C148), the one path to full intent.
    pv = client.post("/templatize/seed/preview", json={"list_name": LIST, "devices": ["r1"]})
    assert pv.status_code == 200, pv.get_data(as_text=True)[:300]
    seed_hash = pv.get_json()["preview"]["what"]["targets"][0]["select_data"]["hash"]
    r = client.post("/templatize/seed/apply",
                    json={"list_name": LIST, "confirmations": {"r1": seed_hash}})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    # Approve sends the fingerprint the library row showed (R12's client half).
    shown = client.get(f"/templates/approval/cisco_ios/base.j2?list_name={LIST}").get_json()
    r = client.post("/templates/approve/cisco_ios/base.j2",
                    json={"list_name": LIST, "fingerprint": shown["fingerprint"]})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    v["_intent_text"] = open(os.path.join(repo, "host_vars", "r1.yml"), encoding="utf-8").read()
    key = credentials.template_secret_key(LIST, "r1", "snmp_community_ro")
    assert credentials.get_template_secret(key), "the commit stored r1's community"
    credentials.set_template_secret(key, _p("Rend"))
    # The restore's ref: r1's golden WITH its committed intent (the first
    # golden predates the intent, and a restore correctly skips it).
    v["_first_golden"] = R.git(repo, "rev-parse", "HEAD")[1].strip()
    v["template_secret"].append(_p("Rend"))
    R.save_golden(LIST, [R.GoldenItem("r1", _head_golden(), DEVICE["ip"], platform="cisco_ios")],
                  source="manual", actor="t", baseline=False)
    v["golden"].append(_p("HeadComm"))

    # A second backup, under its own name BY CONSTRUCTION: a startup backup,
    # whose filename can never be the running one's. It was a second running
    # backup, which in the same second as the first OVERWROTE it, was renamed,
    # and re-planted the first, which then took the NEXT second's name if the
    # clock ticked in between: `_backup_file` named nothing (2026-10-01,
    # measured: the overwrite ran on every local run).
    second = backups.save_config_backup(DEVICE["ip"], "r1", _config_body("Back2"),
                                        config_type="startup")
    assert second["filename"] != v["_backup_file"], second["filename"]
    v["_backup_file_2"] = second["filename"]
    v["backup"] += [_p("Back2Sec"), _p("Back2Comm")]

    # The device, as a read returns it NOW (capture preview and drift).
    import routes.golden as rg
    running = _config_body("Run")
    mp.setattr(rg, "_read_running", lambda d, phases=None: (running, ""))
    mp.setattr("modules.connection.get_persistent_connection", lambda *a, **k: object())
    mp.setattr("modules.commands.run_device_command", lambda conn, cmd, *a, **k: running)
    v["device_read"] = [_p("RunSec"), _p("RunComm")]
    v["caller_supplied"] = [_p("OxiSec"), _p("OxiComm")]

    # An SNMP read, faked: the route reads the stored community to make it.
    mp.setattr("modules.snmp_collector.snmp_get",
               lambda ip, oids, community, version=2: [{"oid": o, "value": "x"} for o in oids])

    # A NetBox to preview against, behind a URL nothing answers.
    from tests.fake_netbox import FakeNetBox
    import modules.netbox_client as nbc

    config.set_user_setting("netbox_url", "http://127.0.0.1:9")
    nb = FakeNetBox()
    nb.seed("dcim/sites", {"name": LIST, "slug": "default"})
    mp.setattr(nbc, "_session_from_config", lambda cfg: nb)
    mp.setattr(nbc, "_managed_tag_ids", {})

    # Every integration pointed at a closed loopback port, so each connection
    # test runs and fails with its own words.
    from modules.integrations import REGISTRY
    for name, cls in REGISTRY.items():
        if name not in INTEGRATIONS_NOT_DRIVEN:
            config.set_user_setting(cls().url_key, "http://127.0.0.1:9")


def _planted_backups_present(v, when):
    """The sweep's precondition, asserted where it can be read (the operator,
    2026-10-01: CI answered 404 "Backup file not found" for compare_backups on
    gw1 twice, while 28 simulated schedules here passed). Order-independent: it
    says what is missing, where it went, and what ran before, whatever ran."""
    from modules import backups, config
    from tests import run_history

    where = backups.get_backups_dir()
    missing = [n for n in (v["_backup_file"], v["_backup_file_2"])
               if not os.path.exists(os.path.join(where, n))]
    if not missing:
        return
    found = [os.path.join(root, f) for root, _d, files in os.walk(config.DATA_DIR)
             for f in files if f in missing]
    listing = sorted(os.listdir(where)) if os.path.isdir(where) else "(no such directory)"
    raise AssertionError(
        f"the backup(s) the fixture planted are gone {when}: {missing} (not in {where}, "
        f"current list {config.get_current_list_name()!r}). Found elsewhere in the store: "
        f"{found or 'nowhere'}. The directory holds: {listing}. "
        + run_history.last_line() + "\n" + run_history.describe())


def _store_state():
    """Every file under the store with its hash, `.git/objects` aside (a
    commit also moves refs and logs, which are hashed). What a request WROTE
    is the difference between two of these (C134's sweep)."""
    import hashlib

    from modules import config

    state = {}
    for dirpath, dirnames, filenames in os.walk(config.DATA_DIR):
        if os.sep + os.path.join(".git", "objects") in dirpath + os.sep:
            dirnames[:] = []
            continue
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "rb") as fh:
                    state[os.path.relpath(path, config.DATA_DIR)] = hashlib.sha256(
                        fh.read()).hexdigest()
            except OSError:
                state[os.path.relpath(path, config.DATA_DIR)] = "unreadable"
    return state


#: POSTs that answer 202 with a `job` and put their result behind a GET
#: (C188 step 2: the capture preview's reads run as a job). The sweep FOLLOWS
#: each to its result, because the result is where stored config lands now:
#: stopping at the 202 would sweep a body that holds no config at all, and
#: the GET sweep cannot reach a job (it fills arguments with planted names).
JOB_RESULTS = {"golden.capture_preview": "/golden/capture/preview/{job}",
               # The v2 card names its job in the URL it re-reads (an HTML answer).
               "device_v2.capture_start": "/v2/device/r1/capture/job/{job}"}


def _follow_job(client, endpoint, r):
    """The POST's body plus its job's result, once the job has finished."""
    from modules.nsot import capture_job

    job = (r.get_json(silent=True) or {}).get("job") if r.status_code == 202 else None
    if job is None and r.status_code == 200 and endpoint in JOB_RESULTS:
        import re
        m = re.search(r"/capture/job/([0-9a-f]+)", r.get_data(as_text=True))
        job = m.group(1) if m else None
    if endpoint not in JOB_RESULTS or not job:
        return r.get_data(as_text=True)
    assert capture_job.wait(job, 60), f"{endpoint}: job {job} still running after 60 s"
    got = client.get(JOB_RESULTS[endpoint].format(job=job))
    assert got.status_code == 200, (endpoint, got.status_code, got.get_data(as_text=True)[:200])
    return r.get_data(as_text=True) + "\n" + got.get_data(as_text=True)


def _drive(v, person, writes=None):
    import app as A
    from modules import identity
    from modules.integrations import REGISTRY

    mp = pytest.MonkeyPatch()
    if person:
        who = identity.Identity(actor=PERSON, email=PERSON, kind="person", verified=True,
                                outcome="ok", peer="198.51.100.7", peer_trusted=True,
                                header_present=True)
        mp.setattr(identity, "identify", lambda _r: who)
    else:
        mp.setattr(identity, "identify", lambda _r: identity.Identity(peer="198.51.100.7"))
    client = A.app.test_client()
    out = {}
    try:
        bodies = _bodies(v)
        for endpoint, rule in sorted(_population().items()):
            status, (kind, body), _why = bodies[endpoint]
            names = [None]
            if endpoint == "settings_integrations.test_integration":
                names = sorted(set(REGISTRY) - set(INTEGRATIONS_NOT_DRIVEN))
            for name in names:
                url = _fill(rule, dict(v, **({"_integration": name} if name else {})))
                if name:
                    url = url.replace("/planted-profile/", f"/{name}/")
                if endpoint.startswith(("device_v2.", "intent_v2.")):
                    # A device page route names its device `name`: the planted device.
                    url = url.replace("/planted-profile/", f"/{DEVICE['hostname']}/")
                before = _store_state() if writes is not None else None
                r = (client.post(url, data=body) if kind == "form"
                     else client.post(url, json=body))
                text = _follow_job(client, endpoint, r)
                if writes is not None:
                    after = _store_state()
                    writes[endpoint if not name else f"{endpoint}:{name}"] = sorted(
                        k for k in set(before) | set(after) if before.get(k) != after.get(k))
                out[endpoint if not name else f"{endpoint}:{name}"] = (r.status_code, text)
    finally:
        mp.undo()
    return out


@pytest.fixture(scope="module")
def swept():
    import app as A
    from modules import identity

    from modules import drift_check

    mp = pytest.MonkeyPatch()
    # The drift routes run a real check, whose result the process-wide checker
    # holds in MEMORY. Restoring the store's files does not undo that, and a
    # later test read a drift run its own fixture never made (found by the
    # full suite: the payload check saw four fields of a run). The sweep gets
    # a checker of its own, discarded afterwards.
    mp.setattr(drift_check, "_checker", None)
    who = identity.Identity(actor=PERSON, email=PERSON, kind="person", verified=True,
                            outcome="ok", peer="198.51.100.7", peer_trusted=True,
                            header_present=True)
    try:
        with planted_stores() as values:
            with pytest.MonkeyPatch.context() as setup_mp:
                setup_mp.setattr(identity, "identify", lambda _r: who)
                _setup(values, mp, A.app.test_client())
            planted = {x: store for store, xs in values.items() if not store.startswith("_")
                       for x in xs}
            writes = {}
            _planted_backups_present(values, "after the setup, before any route ran")
            anon = _drive(values, person=False)
            _planted_backups_present(values, "after the anonymous pass, before the person's")
            yield {"writes": writes, "values": values, "planted": planted, "anon": anon,
                   "person": _drive(values, person=True, writes=writes)}
    finally:
        mp.undo()


def _hits(result, planted):
    return sorted({(key, store) for key, (_s, text) in result.items()
                   for value, store in planted.items() if value in text})


class TestThePopulation:
    def test_every_not_device_post_has_a_body(self, swept):
        population = set(_population())
        declared = set(_bodies(swept["values"]))
        assert population - declared == set(), "undeclared: give each a body that reaches it"
        assert declared - population == set(), "declared but no longer in the population"
        assert len(population) >= 30, len(population)

    def test_the_known_computing_posts_are_in_it(self):
        """The anchor: C77's two are in the population the gate table gives."""
        assert {"deploy.plan", "golden.restore_preview"} <= set(_population())

    def test_every_integration_is_driven_or_named(self, swept):
        from modules.integrations import REGISTRY
        driven = {k.split(":", 1)[1] for k in swept["person"] if ":" in k}
        assert driven | set(INTEGRATIONS_NOT_DRIVEN) == set(REGISTRY)
        assert len(driven) >= 8


class TestEveryRouteReachedItsState:
    @pytest.mark.parametrize("who", ["anon", "person"])
    def test_each_answered_with_its_declared_status(self, swept, who):
        bodies = _bodies(swept["values"])
        wrong = {k: (s, t[:200]) for k, (s, t) in swept[who].items()
                 if s != bodies[k.split(":")[0]][0]}
        assert wrong == {}, "a different status means the fixture no longer reaches the state"

    def test_the_config_reaching_routes_drew_the_masked_slot(self, swept):
        """The positive control, per route: the line was REACHED and masked.
        A response that never held the line passes the leak test too."""
        missing = sorted(k for k in REACHES
                         if not any(m in swept["person"][k][1] for m in MASKS))
        assert missing == [], missing
        assert len(REACHES) >= 7   # 8 -> 7: the import preview left it (7.1)


class TestNoPostReturnsAStoredSecret:
    @pytest.mark.parametrize("who", ["anon", "person"])
    def test_no_planted_value_comes_back(self, swept, who):
        hits = _hits(swept[who], swept["planted"])
        assert hits == [], "\n".join(f"{k} <- {s}" for k, s in hits)

    def test_every_store_is_planted(self, swept):
        from tests.test_no_get_returns_a_stored_secret import STORES
        values = swept["values"]
        assert all(values.get(s) for s in STORES), [s for s in STORES if not values.get(s)]
        for extra in ("device_read", "caller_supplied"):
            assert values[extra]


#: `not_device` POSTs that may WRITE our own stores, each with its reason.
#: Everything else in the population is a preview, a plan, a check or a read,
#: and must leave the store byte-identical (C134's sweep, below).
MAY_WRITE = {
    "drift_check_sync": "runs the drift check NOW and records its run in drift_state.json; "
                        "a check run, not a preview",
    "topology_save_hidden": "layout: saves which topology nodes are hidden",
    "topology_save_positions": "layout: saves node positions",
    "topology_save_proto_hidden": "layout: saves hidden nodes per protocol view",
    "topology_save_proto_positions": "layout: saves positions per protocol view",
}


class TestNoPreviewWritesTheStore:
    """C134, and the class the operator named (2026-09-28): A PREVIEW RUNS THE
    REAL CODE, SO EVERY WRITE THAT CODE MAKES IS A WRITE THE PREVIEW MAKES. The
    dry-run flag stops writes to NetBox, not writes to our own stores, and
    nobody had enumerated the second kind. C130 (a removal preview forgetting
    provenance) and C134 (an import preview overwriting the last import's
    record) were found hours apart, each by accident.

    So every `not_device` POST (the gate table's population, each driven with a
    body that reaches its state) is driven with the store hashed before and
    after, as a person. A route not in MAY_WRITE that changes any file fails.
    Measured the first time: every preview clean, and `drift_check_sync`, a
    check run, the only writer. Positive control, run by hand: with C134's fix
    removed, this names `netbox_safety.preview_import` writing
    `netbox_sync_status.json`."""

    def test_no_undeclared_route_writes_the_store(self, swept):
        writers = {k.split(":")[0]: v for k, v in swept["writes"].items() if v}
        undeclared = {k: v for k, v in writers.items() if k not in MAY_WRITE}
        assert undeclared == {}, (
            f"these wrote our own stores and are not declared writers: {undeclared}. "
            "A preview must change nothing; declare a genuine writer with its reason.")

    def test_the_instrument_sees_a_write(self, swept):
        """The floor: a store hash that saw nothing would pass the test above."""
        assert swept["writes"].get("drift_check_sync"), "the drift run's record was not seen"

    def test_every_declared_writer_is_in_the_population(self):
        assert set(MAY_WRITE) <= set(_population()), set(MAY_WRITE) - set(_population())


class TestThePreconditionIsSaid:
    """The sweep's own precondition (CI run #245, 2026-10-01): a missing
    planted backup is named with where it was looked for, where it is, and what
    this worker ran before, on the FIRST line, which is all CI's annotation
    carries."""

    def _v(self, tmp_path, monkeypatch, names):
        from modules import backups
        monkeypatch.setattr(backups, "get_backups_dir", lambda: str(tmp_path))
        for n in names:
            (tmp_path / n).write_text("x")
        return {"_backup_file": "first.cfg", "_backup_file_2": "second.cfg"}

    def test_both_present_says_nothing(self, tmp_path, monkeypatch):
        _planted_backups_present(self._v(tmp_path, monkeypatch, ["first.cfg", "second.cfg"]),
                                 "now")

    def test_one_gone_is_named_with_what_ran_before(self, tmp_path, monkeypatch):
        from tests import run_history
        v = self._v(tmp_path, monkeypatch, ["second.cfg"])
        with pytest.raises(AssertionError) as exc:
            _planted_backups_present(v, "before the drive")
        first = str(exc.value).splitlines()[0]
        assert "gone before the drive: ['first.cfg']" in first and str(tmp_path) in first
        assert "The directory holds: ['second.cfg']" in first
        assert "before it, worker" in first
        # The history is this process's own, the running test last.
        assert run_history.RAN[-1].endswith("test_one_gone_is_named_with_what_ran_before")
        assert "other threads alive now" in str(exc.value)
