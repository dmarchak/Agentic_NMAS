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
config as a read returns it NOW, configs a caller supplies (a second backup
to compare left with today's Backups at 7.8, C632), a NetBox to preview against, and a list that has what a
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
        # Today's deploy plan (deploy.plan) left with the deploy wizard at 7.8 (2026-10-17,
        # P7-25): the v2 device page's Deploy… is a GET, read in `swept` below with this body's
        # device; its committed intent renders a community the device does not hold.
        "settings_v2.diag_drift_check": (409, ("form", {}),
                                         "the network filled in ('zz') is none, so it is "
                                         "refused naming the networks; it starts nothing"),
        "netbox_v2.preview": (404, ("form", {}), "no operation named: refused naming the three, "
                              "nothing started"),
        "sdn_v2.flow_preview": (400, ("form", {"list": LIST, "do": "add"}),
                                "no controller connection named: refused before any read"),
        "sdn_v2.response_preview": (404, ("form", {"list": LIST}),
                                    "no response by that id awaits a person: refused naming it, "
                                    "nothing read"),
        # C2018: Re-apply… on SDN › Flows.
        "sdn_v2.reapply_preview": (409, ("form", {"list": LIST}),
                                   "no connection, switch or response named: refused naming "
                                   "what is missing, nothing read"),
        "device_v2.reload_start": (400, ("form", {}),
                                   "no network named: refused before any job starts"),
        "device_v2.persist_read": (400, ("form", {}),
                                   "no network named: refused before any job starts"),
        "templates_v2.bindings_preview": (400, ("form", {"list": LIST, "add_device": "zz",
                                                         "add_template": "cisco_iosxe/base.j2"}),
                                         "a device the network does not have: refused naming "
                                         "it, nothing written"),
        "templates_v2.edit_check": (200, ("form", {"list": LIST, "path": "cisco_iosxe/base.j2",
                                                   "text": "hostname {{ hostname }}\n"}),
                                    "the edit checked against every governed device's golden, "
                                    "masked on the way out"),
        "templates_v2.coverage_check": (404, ("form", {"list": "no-such-network"}),
                                        "a network that does not exist: refused, nothing "
                                        "measured"),
        # Bulk intent's render delta, through v2's Change a setting since its JSON route left
        # at 7.8 (2026-10-15): the same core, `bulk_plan_of`.
        "bulk_intent_v2.preview": (200, ("form", {"list": LIST, "device": "r1",
                                                  "path": "hostname", "before": "r1",
                                                  "after": "r1x"}),
                                   "a bulk intent change's render delta"),
        "adopt_v2.preview": (400,("form", {"hostname": "r9"}),
                             "no network named: refused before the device is read"),
        "onboard_v2.preview": (400, ("form", {"hostname": "r9"}),
                               "no network named: refused saying why the list is carried, "
                               "nothing planned"),
        "onboard_v2.verify_preview": (400, ("form", {}),
                                      "no network named: refused before any device is read"),
        "onboard_v2.abandon_preview": (400, ("form", {}),
                                       "no network named: refused before the dry run reads"),
        "remote_v2.publication": (409, ("form", {"list": LIST}),
                                  "the planted list has no remote: refused naming it, reading "
                                  "no history"),
        "settings_v2.network_source_preview": (409, ("form", {"source": "zz"}),
                                               "a source that is neither local nor netbox: "
                                               "refused naming both, NetBox not read"),
        "settings_v2.network_source_refresh": (409, ("form", {}),
                                               "the planted network is its own list: refused, "
                                               "naming it as not NetBox-sourced"),
        "settings_v2.network_create_preview": (200, ("form", {"name": "Swept Net"}),
                                               "a new network's preview: its folder named, "
                                               "nothing created"),
        "settings_v2.network_delete_preview": (200, ("form", {}),
                                               "the planted network's delete preview: its "
                                               "counts and where its data would go, nothing moved"),
        "settings_v2.records_store_preview": (404, ("form", {}),
                                              "the direction filled in ('zz') is neither move "
                                              "nor back: refused naming both, counting nothing"),
        # Today's capture preview (golden.capture_preview, the whole-fleet job), the inventory
        # refresh (inventory.refresh) and the monitoring profile's proposal
        # (templatize.profile_propose_preview) left with today's index at 7.8 (2026-10-17,
        # P7-27): the device page's Capture below, Settings › a network's Refresh now
        # (settings_v2.network_source_refresh) and Monitoring › Profile's Propose (a GET, swept
        # by the GET sweep) do their jobs.
        # The device page's Rotate (7.3): the plan's live read of r1 is refused here (no
        # network), so the card draws the failing preflight; it reads no store a GET does not.
        "device_v2.rotate_preview": (200, ("form", {"list": LIST}),
                                     "the rotation's plan for r1: its live read refused, drawn as "
                                     "the failing preflight"),
        # The device page's Capture (7.3): the same job, for one device, its name filled as r1.
        "device_v2.capture_start": (200, ("form", {"list": LIST}),
                                    "starts the same job reading r1 NOW; FOLLOWED to its card "
                                    "(JOB_RESULTS): the golden diff and the intent departure"),
        # Today's restore preview (golden.restore_preview) left at 7.8 (2026-10-17): the v2
        # device page's restore preview is a GET, read in `swept` below with this body's moment.
        # Today's onboarding plan and Verify preview (onboard.plan, onboard.verify_preview)
        # left at 7.8 (2026-10-17, P7-25); v2's (onboard_v2.preview, onboard_v2.verify_preview)
        # are declared with v2's routes.
        "remote.verify": (200, ("json", {}),
                          "no remote configured: a configured one would start ssh, which the "
                          "harness refuses and counts as a failure; the remote is an alias "
                          "and a key PATH, never a stored secret"),
        # Today's retire, rotate and persist previews (retire.preview, rotate.preview,
        # persist.preview) and templatize's seed, revert and retry previews left at 7.8
        # (2026-10-17, P7-24): the device page's cards are GETs (rotate's preview, a POST,
        # is device_v2.rotate_preview above), read in `swept` below for r1 (V2_CARDS).
        "jobs.job_finished": (409, ("json", {"unit": "nmas-startup-check"}),
                              "a declared job, and the reader jobs do not run in the test "
                              "process: refused by name, nothing read"),
        "update.check": (409, ("json", {}),
                         "the reader jobs do not run in the test process: refused by name, "
                         "nothing asked (no network, no store)"),
        # Today's Validate (templates.validate) and intent editor preview
        # (templatize.preview_committed_edit) left at 7.8 (2026-10-17, P7-23): Templates ›
        # Edit…'s check above and the Intent tab's check below.
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
        # Out-of-band ZTP (O6b): each preview reads NetBox's console path and Mercury's stores;
        # this list's NetBox holds no such device with a console path, so each is refused,
        # naming why, and nothing is contacted or written.
        "console_ztp_v2.survey_preview": (409, ("form", {"list_name": LIST, "step": "survey",
                                                         "profile": "cisco_ios_switch"}),
                                          "no console path for the device: refused, naming the "
                                          "check that failed, nothing contacted"),
        "console_ztp_v2.kickstart_preview": (409, ("form", {"list_name": LIST,
                                                            "step": "kickstart"}),
                                             "no survey of the device is recorded: refused, "
                                             "naming it, nothing contacted"),
        # The one-decision out-of-band onboarding's review: this list's NetBox holds no Planned
        # record of the name, so it is refused, naming why; nothing contacted or written.
        "oob_onboard_v2.preview_view": (409, ("form", {"list_name": LIST, "hostname": "r1",
                                                       "platform": "cisco_ios",
                                                       "role": "switch"}),
                                        "no Planned record of the name: refused, naming the "
                                        "check that failed, nothing contacted"),
        # C1560: the console server's key is read only for a port Mercury has a record of.
        "console_servers_v2.rekey_preview": (409, ("form", {}),
                                             "no console-server port record: refused, naming "
                                             "the port, no key read"),
    }


#: Responses that draw stored config: the masked slot must be in them.
#: The drift run (today's `drift_check_sync` until 7.8, 2026-10-15) was never among them: it
#: answers with counts and queues the diff as an approval item, which the GET sweep covers;
#: its result is held to no planted value by `TestTheDriftRun` below.
REACHES = {"device_v2.capture_start"}
# `golden.capture_preview` LEFT this set 2026-10-17 with today's index (7.8, P7-27): the device
# page's Capture (`device_v2.capture_start`, above) starts the same job and draws its result.
# `deploy.plan` LEFT this set 2026-10-17 with today's deploy wizard (7.8, P7-25): THE plan is
# drawn by the v2 device page's Deploy… card, a GET, read by the fixture below and held by
# `test_the_v2_deploy_preview_drew_the_masked_slot_and_no_value`.
# `templatize.preview_committed_edit` LEFT this set 2026-10-17 with today's intent editor (7.8,
# P7-23): the Intent tab's check (`intent_v2.check`, in the population) draws the edit's diffs
# with the masked lines left uncompared, never a rendered secret slot.
# `golden.restore_preview` LEFT this set 2026-10-17 with the route (7.8, P7-21): THE restore plan
# is drawn by the v2 device page's restore preview, a GET, read by the fixture below and held by
# `test_the_v2_restore_preview_drew_the_masked_slot_and_no_value`.
# `templates.preview` LEFT this set 2026-10-15 (its POST half) and its GET on 2026-10-17 with
# today's template editor (7.8, P7-23); the GET had been read by the fixture below.
# `netbox_safety.preview_import` LEFT this set in 7.1: its response no longer
# carries the dry run's object payloads (each device's golden rode in
# `local_context_data`), only the preview drawn from them, so there is no
# stored config in it to mask. The sweep drove it for a planted value until today's NetBox
# routes left at 7.8 (2026-10-17); v2's NetBox preview card is held to a planted value by
# tests/test_netbox_preview_token_round_trip.py, and its preview job is driven here only to
# its refusal (`netbox_v2.preview` above).

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
    from modules import config, credentials
    from modules.nsot import repo as R
    from modules.nsot import templates_repo

    repo = os.path.join(config.list_data_path(LIST), "config_repo")

    # A list that has what a real list has.
    templates_repo.seed_templates(repo)
    # r1's intent is SEEDED from its golden (C148), the one path to full intent: its device
    # page's Seed intent… card and its confirm (today's /templatize/seed/* left at 7.8,
    # 2026-10-17, P7-24).
    import html as html_mod
    import re
    pv = client.get(f"/v2/device/r1/seed?list={LIST}")
    assert pv.status_code == 200, pv.get_data(as_text=True)[:300]
    card = pv.get_data(as_text=True)
    # The card for r1 UNSEEDED, its golden parsed into the document a seed would commit: the
    # one moment the seed card reaches r1's config (afterwards it says r1 has full intent).
    v["_seed_card"] = (pv.status_code, card)
    vals = json.loads(html_mod.unescape(re.search(
        r"hx-vals='([^']*)'", card[card.index("op-confirm"):]).group(1)))
    r = client.post("/v2/device/r1/seed/confirm", data=vals)
    assert r.status_code == 200 and "op-ok" in r.get_data(as_text=True), \
        r.get_data(as_text=True)[:300]
    # Approve sends the fingerprint and the check its card showed (R12's client half), on
    # Templates › Approve… (today's /templates/approve left at 7.8, 2026-10-17, P7-23).
    card = client.get(f"/v2/templates/approve?list={LIST}&path=cisco_ios/base.j2").get_data(
        as_text=True)
    shown = {k: re.search(rf'name="{k}" value="([^"]*)"', card).group(1)
             for k in ("fingerprint", "seen")}
    r = client.post("/v2/templates/approve", data={"list": LIST, "path": "cisco_ios/base.j2",
                                                   **shown})
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

    # The device, as a read returns it NOW (capture preview and drift).
    import routes.golden as rg
    running = _config_body("Run")
    mp.setattr(rg, "_read_running", lambda d, phases=None: (running, ""))
    mp.setattr("modules.connection.get_persistent_connection", lambda *a, **k: object())
    mp.setattr("modules.commands.run_device_command", lambda conn, cmd, *a, **k: running)
    v["device_read"] = [_p("RunSec"), _p("RunComm")]
    v["caller_supplied"] = [_p("OxiSec"), _p("OxiComm")]

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
JOB_RESULTS = {  # today's golden.capture_preview's JSON job left at 7.8 (P7-27)
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
            # One body per route (each integration's Test, once a name per integration here,
            # is driven by `_drive_tests` since today's left at 7.8).
            for name in [None]:
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


#: The device page's action cards for r1 whose previews were today's `not_device` POSTs
#: (retire.preview, persist.preview, templatize.seed_preview, revert_preview, retry_preview)
#: until they left at 7.8 (2026-10-17, P7-24): op -> the card's GET.
V2_CARDS = {
    "seed": f"/v2/device/r1/seed?list={LIST}",
    "revert": f"/v2/device/r1/revert?list={LIST}",
    "retry": f"/v2/device/r1/retry?list={LIST}",
    "retire": f"/v2/device/r1/retire?list={LIST}&reason=leaving+management",
    "persist": f"/v2/device/r1/persist?list={LIST}",
}


@pytest.fixture(scope="module")
def swept():
    import app as A
    from modules import identity

    from modules import drift_check

    mp = pytest.MonkeyPatch()
    # The drift run below is a real check, whose result the process-wide checker
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
            anon = _drive(values, person=False)
            person = _drive(values, person=True, writes=writes)
            with pytest.MonkeyPatch.context() as test_mp:
                test_mp.setattr(identity, "identify", lambda _r: who)
                tests = _drive_tests(A.app.test_client())
            # A known writer, through the same instrument (C134's store hash): the drift run
            # Check now starts, r1 read NOW against its golden and the run recorded in the
            # network's drift state. Today's /drift/check/sync was the population's one writer
            # and the instrument's floor until it left at 7.8 (2026-10-15); no `not_device`
            # POST left writes when driven, so the floor is this run, driven directly.
            before = _store_state()
            drift_result = drift_check.get_checker().run_one(LIST, "manual")
            after = _store_state()
            drift_run = {"result": json.dumps(drift_result, default=str),
                         "writes": sorted(k for k in set(before) | set(after)
                                          if before.get(k) != after.get(k))}
            # Today's template preview (a GET, read here) left at 7.8 (2026-10-17, P7-23).
            # The v2 restore preview (a GET, the device page's Restore from…), at the first
            # golden against HEAD: a program that adds its community, and HEAD's as residue.
            # Today's POST /golden/restore/preview was in the population until it left at 7.8
            # (2026-10-17); read here because only this fixture builds that moment.
            with pytest.MonkeyPatch.context() as rp_mp:
                rp_mp.setattr(identity, "identify", lambda _r: who)
                rp = A.app.test_client().get(
                    f"/v2/device/r1/restore/preview?list={LIST}"
                    f"&moment={values['_first_golden']}")
                # THE deploy plan as the device page's Deploy… draws it (a GET; today's POST
                # /deploy/plan was in the population until it left at 7.8, 2026-10-17, P7-25).
                dp = A.app.test_client().get(f"/v2/device/r1/deploy?list={LIST}")
            # The device page's action cards whose previews were today's `not_device` POSTs
            # until they left at 7.8 (2026-10-17, P7-24): each read for r1, as nobody and as a
            # person, over the same planted stores.
            cards = {"seed_unseeded:person": values["_seed_card"]}
            for who_name, ident in (("anon", identity.Identity(peer="198.51.100.7")),
                                    ("person", who)):
                with pytest.MonkeyPatch.context() as c_mp:
                    c_mp.setattr(identity, "identify", lambda _r, i=ident: i)
                    client = A.app.test_client()
                    for op, url in V2_CARDS.items():
                        r = client.get(url)
                        cards[f"{op}:{who_name}"] = (r.status_code, r.get_data(as_text=True))
            yield {"writes": writes, "values": values, "planted": planted, "anon": anon,
                   "person": person, "tests": tests, "drift_run": drift_run,
                   "restore_preview": (rp.status_code, rp.get_data(as_text=True)),
                   "deploy_preview": (dp.status_code, dp.get_data(as_text=True)),
                   "cards": cards}
    finally:
        mp.undo()


def _test_routes() -> dict:
    """Each registered integration's Test on v2, ``{name: url}``: its Installation card's
    (NetBox, Proxmox) or the Default network's card for its group. Today's per-integration
    Test (`settings_integrations.test_integration`, a `not_device` POST this sweep drove once
    per integration) left with today's Settings modal at 7.8 (2026-10-15); v2's Tests are a
    person's (`configure`), so they are driven here, as a person, outside the population."""
    from modules import installation_settings as I
    from modules import settings_page
    from modules.settings_scope import network_groups

    out = {spec["integration"]: f"/v2/settings/installation/card/{card}/test"
           for card, spec in I.CARDS.items() if spec["integration"]}
    for group in network_groups():
        cls = settings_page.integration_for(group)
        if cls is not None:
            out.setdefault(cls.name, f"/v2/settings/network/Default/group/{group}/test")
    return out


def _drive_tests(client) -> dict:
    """``{name: (status, text)}``: every integration's v2 Test, driven over the planted stores
    (the harness refuses every connection, so each answers with its failure, which must carry
    no stored value)."""
    from modules.integrations import REGISTRY

    routes = _test_routes()
    out = {}
    for name in sorted(set(REGISTRY) - set(INTEGRATIONS_NOT_DRIVEN)):
        if name in routes:
            r = client.post(routes[name], headers={"HX-Request": "true"})
            out[name] = (r.status_code, r.get_data(as_text=True))
    return out


def _hits(result, planted):
    return sorted({(key, store) for key, (_s, text) in result.items()
                   for value, store in planted.items() if value in text})


class TestThePopulation:
    def test_every_not_device_post_has_a_body(self, swept):
        population = set(_population())
        declared = set(_bodies(swept["values"]))
        assert population - declared == set(), "undeclared: give each a body that reaches it"
        assert declared - population == set(), "declared but no longer in the population"
        # 29 measured 2026-10-17 once P7-24's and P7-25's POSTs left together; 26 measured the
        # same day once today's capture preview, inventory refresh and profile proposal left
        # with today's index (P7-27); a floor.
        assert len(population) >= 24, len(population)

    def test_the_known_computing_posts_are_in_it(self):
        """The anchor: the capture preview and Add device's review are in the population the
        gate table gives (C77's deploy plan and restore preview, the first two, left at 7.8
        and are read as v2's GETs in `swept`; today's capture preview left at P7-27, and the
        device page's is the anchor now)."""
        assert {"device_v2.capture_start", "onboard_v2.preview"} <= set(_population())

    def test_every_integration_is_driven_or_named(self, swept):
        from modules.integrations import REGISTRY
        driven = {name for name, (status, _t) in swept["tests"].items() if status == 200}
        assert driven | set(INTEGRATIONS_NOT_DRIVEN) == set(REGISTRY), (
            sorted(set(REGISTRY) - driven - set(INTEGRATIONS_NOT_DRIVEN)),
            {n: s for n, (s, _t) in swept["tests"].items()})
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
        assert len(REACHES) >= 1   # 2 -> 1: golden.capture_preview left with today's index (7.8, 2026-10-17, P7-27), the device page's Capture its v2 home; 8 -> 7: the import preview left it (7.1); 7 -> 6: compare_backups left with today's Backups (7.8, C632); 6 -> 5: templates.preview's POST left (7.8, 2026-10-15); 5 -> 4: golden.restore_preview left (7.8, 2026-10-17), the v2 restore preview held below; 4 -> 3: templatize.preview_committed_edit left with today's intent editor (7.8, 2026-10-17, P7-23); 3 -> 2: deploy.plan left with today's deploy wizard (7.8, 2026-10-17, P7-25), the v2 deploy preview held below

    def test_the_v2_deploy_preview_drew_the_masked_slot_and_no_value(self, swept):
        """THE deploy plan as the v2 device page draws it (`device_v2.deploy`), held as
        REACHES held today's POST /deploy/plan: committed intent renders a community r1 does
        not hold, so the program adds it, and the card draws it masked, and no planted value."""
        status, text = swept["deploy_preview"]
        assert status == 200, text[:300]
        assert 'id="device-op"' in text and "snmp-server community" in text, text[:300]
        assert any(m in text for m in MASKS), text[:300]
        assert [s for v, s in swept["planted"].items() if v in text] == []

    def test_the_v2_restore_preview_drew_the_masked_slot_and_no_value(self, swept):
        """THE restore plan as the v2 device page draws it (`device_v2.restore_preview`), held
        as REACHES held today's POST: the plan at the first golden reached the planted
        community and drew it masked, and no planted value. (The card refuses that moment,
        naming the community lines its intent no longer reproduces, masked.)"""
        status, text = swept["restore_preview"]
        assert status == 200, text[:300]
        assert 'id="device-op"' in text and "snmp-server community" in text, text[:300]
        assert any(m in text for m in MASKS), text[:300]
        assert [s for v, s in swept["planted"].items() if v in text] == []


class TestNoPostReturnsAStoredSecret:
    @pytest.mark.parametrize("who", ["anon", "person"])
    def test_no_planted_value_comes_back(self, swept, who):
        hits = _hits(swept[who], swept["planted"])
        assert hits == [], "\n".join(f"{k} <- {s}" for k, s in hits)

    def test_no_integrations_test_returns_one(self, swept):
        hits = _hits(swept["tests"], swept["planted"])
        assert hits == [], "\n".join(f"{k} <- {s}" for k, s in hits)

    def test_no_device_action_card_returns_one(self, swept):
        """The previews today's POSTs answered (P7-24), as v2's cards draw them for r1: each
        drawn (its card, as nobody and as a person), and no planted value in any."""
        cards = swept["cards"]
        assert len(cards) == 2 * len(V2_CARDS) + 1 and len(V2_CARDS) >= 5
        undrawn = {k: (s, t[:200]) for k, (s, t) in cards.items()
                   if s != 200 or 'id="device-op"' not in t}
        assert undrawn == {}, undrawn
        hits = _hits(cards, swept["planted"])
        assert hits == [], "\n".join(f"{k} <- {s}" for k, s in hits)

    def test_every_store_is_planted(self, swept):
        from tests.test_no_get_returns_a_stored_secret import STORES
        values = swept["values"]
        assert all(values.get(s) for s in STORES), [s for s in STORES if not values.get(s)]
        for extra in ("device_read", "caller_supplied"):
            assert values[extra]


#: `not_device` POSTs that may WRITE our own stores, each with its reason.
#: Everything else in the population is a preview, a plan, a check or a read,
#: and must leave the store byte-identical (C134's sweep, below). Empty since 2026-10-15: its
#: one member, `drift_check_sync` (a check run, recorded in drift_state.json), left at 7.8;
#: v2's Check now starts the run in the background and writes nothing in the request.
MAY_WRITE: dict = {}


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
    check run, the only writer (it left at 7.8, 2026-10-15). Positive control,
    run by hand: with C134's fix removed, this named
    `netbox_safety.preview_import` writing `netbox_sync_status.json`; that route
    left with today's NetBox tab at 7.8 (2026-10-17), and v2's preview job is
    driven here only to its refusal, so C134 itself is held by
    tests/test_import_preview_is_what_happens.py and C130 by
    tests/test_removal_reads_before_it_forgets.py."""

    def test_no_undeclared_route_writes_the_store(self, swept):
        writers = {k.split(":")[0]: v for k, v in swept["writes"].items() if v}
        undeclared = {k: v for k, v in writers.items() if k not in MAY_WRITE}
        assert undeclared == {}, (
            f"these wrote our own stores and are not declared writers: {undeclared}. "
            "A preview must change nothing; declare a genuine writer with its reason.")

    def test_the_instrument_sees_a_write(self, swept):
        """The floor: a store hash that saw nothing would pass the test above. The known
        writer is the drift run, through the same `_store_state` (the fixture)."""
        assert any(w.endswith("drift_state.json") for w in swept["drift_run"]["writes"]), \
            swept["drift_run"]["writes"]


class TestTheDriftRun:
    def test_its_result_carries_no_planted_value(self, swept):
        """r1 read NOW against its golden, both holding planted values: the run's result
        (what Diagnostics' card and Needs attention draw) carries counts and names, never a
        stored value (today's /drift/check/sync answered with it until 7.8)."""
        text = swept["drift_run"]["result"]
        assert '"inventory"' in text, text[:300]
        assert [s for v, s in swept["planted"].items() if v in text] == []

    def test_every_declared_writer_is_in_the_population(self):
        assert set(MAY_WRITE) <= set(_population()), set(MAY_WRITE) - set(_population())
