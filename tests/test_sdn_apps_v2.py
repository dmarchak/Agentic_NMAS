"""SDN › Apps on v2 (P6, C2677; the signed board docs/boards/controller-app-deploy.html,
artboards A to H, J and L): through the real app, the real routes and templates, the real plan,
post-check and receipt store, with `deploy_op.Sources` faked at its seam (the registry and the
controller host's reads are not wired yet) and the transport's send faked.

Cases, each planted:
- the tab is on every SDN page, under the strict policy; with the sources not wired, it says
  what is not built and draws nothing as known;
- the controller card leads with what it runs against Mercury's record (a drift line names
  both sides), its last deploy with its receipt, and the apps grouped by what to do;
- an app's page draws its versions with their state and pins, a Draft never offered, and the
  preview of the running version disabled with its reason on hover;
- the preview draws the plan (the set in load order, the change, the drop-in before and after,
  what the post-check waits for with its placeholder bound, the window, the rollback, the
  hash) and one confirm naming the work; a refused plan draws each refusal; a plan that
  changes nothing offers the redeploy (K4);
- the confirm starts the job and answers its running card, busy on itself; the job deploys and
  its card is then the result, green only when everything came back; the receipt downloads as
  JSON and is on History; a confirm whose plan moved sends nothing and names what moved;
- every route is declared in the gate table, the invalidation map and the operation stages."""

import json
import re
from html import unescape

import pytest

from modules import csp
from modules import controller_deploy_receipts as deploy_receipts
from modules.apps import deploy_op
from modules.nsot import capture_job
from tests.test_controller_deploy_op import ALL_BACK_TWO, CTL, HEADER, UNIT, FakeSources
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"


@pytest.fixture
def apps(networks, tmp_path, monkeypatch):  # noqa: F811 - the fixture, used
    src = FakeSources(tmp_path / "src")
    monkeypatch.setattr(deploy_op, "SOURCES", src)
    import app as A
    return {"client": A.app.test_client(), "src": src}


def fields(html):
    return {m.group(1): unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)}


def preview(c, chosen="of_versions=1.0.0", **extra):
    return c.post("/v2/sdn/apps/preview", data=dict({"list": NET, "controller": CTL,
                                                     "set": chosen}, **extra))


def confirm(c, html):
    f = fields(html)
    r = c.post("/v2/sdn/apps/confirm", data={k: f[k] for k in
                                             ("list", "controller", "set", "hash", "parts")})
    assert r.status_code == 202, r.get_data(as_text=True)
    job = re.search(r'hx-get="/v2/sdn/apps/run/([0-9a-f]+)', r.get_data(as_text=True)).group(1)
    assert capture_job.wait(job, 60)
    return r, c.get(f"/v2/sdn/apps/run/{job}").get_data(as_text=True)


def as_recorded(src):
    """The controller's stored read as the record's deploy left it: its unit's command line
    loading the recorded apps and its drop-in the record's render."""
    from modules.apps import channel
    from tests.test_controller_deploy import MANAGER

    req = deploy_receipts.record(NET, CTL)["request"]
    paths = " ".join(f"/opt/ryu-apps/{a['name']}/{a['version']}/{a['name']}.py"
                     for a in req["apps"])
    show = (f"User=ryu\nExecStart={{ path={MANAGER} ; argv[]={MANAGER} --observe-links {paths} "
            "; ignore_errors=no ; start_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }\n")
    cat = f"{HEADER}\n{channel.render_dropin(req, MANAGER)}"
    src.controller_read = lambda n, c: {"state": "ok", "at": "2026-11-08T05:00:00Z",
                                        "show": show, "cat": cat, "health": {},
                                        "observed": None, "error": ""}


def deploy(a, chosen="of_versions=1.0.0"):
    html = preview(a["client"], chosen).get_data(as_text=True)
    a["src"].reads = [ALL_BACK_TWO]
    return confirm(a["client"], html)


# ── the tab ───────────────────────────────────────────────────────────────────────────────────

def test_the_apps_tab_is_on_every_sdn_page_under_the_strict_policy(apps):
    c = apps["client"]
    for path in ("/v2/sdn", "/v2/sdn/flows", "/v2/sdn/apps"):
        r = c.get(path)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == \
            csp.STRICT_POLICY
        assert 'href="/v2/sdn/apps?list=Default"' in r.get_data(as_text=True)
    html = c.get("/v2/sdn/apps").get_data(as_text=True)
    assert "<h1>SDN · Apps" in html and 'aria-current="page">Apps</a>' in html
    assert "nmas:controller_deploy from:body" in html
    # The effect: drawing the tab on every page sent nothing and wrote no receipt.
    assert apps["src"].sent == [] and deploy_receipts.read(NET)["rows"] == []


def test_sources_not_wired_say_what_is_not_built_and_draw_nothing_as_known(apps, monkeypatch):
    monkeypatch.setattr(deploy_op, "SOURCES", deploy_op.Unwired())
    html = apps["client"].get("/v2/sdn/apps").get_data(as_text=True)
    assert "controller hosts can't be listed:" in unescape(html)
    assert unescape(deploy_op.NOT_WIRED["controllers"]) in unescape(html)
    assert "apps-ctl" not in html
    # The effect: a page read writes no receipt (CLAUDE.md, "A read writes nothing").
    assert deploy_receipts.read(NET)["rows"] == []


def test_the_controller_card_leads_with_the_record_and_groups_the_apps(apps):
    c = apps["client"]
    html = c.get("/v2/sdn/apps").get_data(as_text=True)
    assert "no deploy through Mercury" in html and "none through Mercury" in html
    assert "Registered, not in the set (1)" in html
    # No record: the whole-set preview is disabled, its reason on hover.
    assert re.search(r'disabled aria-disabled="true" title="Mercury&#39;s record holds no set '
                     r'for ctl: choose an app&#39;s version on its page"', html)
    _, done = deploy(apps)
    assert "Deployed" in done
    as_recorded(apps["src"])
    html = c.get("/v2/sdn/apps").get_data(as_text=True)
    assert "runs Mercury&#39;s record" in html
    assert "A newer Published version (1)" in html and "1.1.0 Published" in html
    rid = deploy_receipts.read(NET)["rows"][0]["id"]
    assert f'/v2/sdn/apps?list={NET}&amp;receipt={rid}' in html
    assert "kind=controller_deploy" in html


def test_drift_names_both_sides_and_offers_the_redeploy(apps):
    deploy(apps)
    apps["src"].cat = f"{HEADER}\n[Service]\nUser=ryu\n"
    html = apps["client"].get("/v2/sdn/apps").get_data(as_text=True)
    assert "differs from Mercury&#39;s record" in html
    assert "<td>The drop-in</td>" in html and "<strong>not that render</strong>" in html
    assert "Preview the redeploy…" in html


def test_an_app_s_page_draws_its_versions_and_never_offers_the_running_one(apps):
    deploy(apps)
    html = apps["client"].get(f"/v2/sdn/apps?app=of_versions&controller={CTL}") \
        .get_data(as_text=True)
    assert "› of_versions" in html and "Versions (2)" in html
    assert html.count("Published</span>") == 2 and "running</span>" in html
    assert 'title="1.0.0 is what ctl runs: choose another version"' in html
    picked = apps["client"].get(f"/v2/sdn/view?tab=apps&app=of_versions&controller={CTL}"
                                "&v=1.1.0").get_data(as_text=True)
    assert "Preview deploying 1.1.0…" in picked
    assert fields(picked)["set"] == "of_versions=1.1.0"
    assert "What 1.1.0 declares" in picked and "/of_versions/health" in picked


# ── the preview ───────────────────────────────────────────────────────────────────────────────

def test_the_preview_draws_the_plan_and_one_confirm_naming_the_work(apps):
    r = preview(apps["client"])
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
    assert "Deploy to ctl: of_versions None → 1.0.0" not in html
    assert "The set, in load order" in html and "<strong>1.0.0</strong> added" in html
    assert "The drop-in, before and after" in html and 'class="apps-add"' in html
    assert "placeholder" in html and "Planned-restart window" in html
    f = fields(html)
    assert len(f["hash"]) == 64 and json.loads(f["parts"])["the request"]
    assert ("Deploy of_versions 1.0.0 and restart ctl, with no rollback" in html)
    assert html.count('hx-post="/v2/sdn/apps/confirm') == 1
    assert 'data-holds-live="review"' in html


def test_a_refused_plan_draws_each_refusal_naming_what_it_compared(apps):
    apps["src"].user = "root"
    apps["src"].host_reads = lambda n, c: {"state": "ok", "show": "User=root\n", "ls": "",
                                           "cat": "", "at": 1.0, "error": ""}
    r = preview(apps["client"])
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "refused before anything was staged" in html
    assert "can't tell ryu-manager.service's User or command line" in html
    assert "/opt/ryu-apps cannot be staged into: it is unreadable" in html
    assert 'hx-post="/v2/sdn/apps/confirm' not in html
    # The effect: a refused plan stages and sends nothing.
    assert apps["src"].sent == [] and apps["src"].held_at_send == []


def test_a_malformed_set_is_refused_before_anything_is_read(apps):
    r = preview(apps["client"], chosen="of_versions")
    assert r.status_code == 400 and "is not name=version" in unescape(r.get_data(as_text=True))
    # The effect: nothing was sent to the controller and no receipt was written.
    assert apps["src"].sent == [] and deploy_receipts.read(NET)["rows"] == []


def test_a_plan_that_changes_nothing_offers_the_redeploy(apps):
    _, done = deploy(apps)
    rec = deploy_receipts.record(NET, CTL)
    from modules.apps import channel
    apps["src"].cat = (f"# /lib/systemd/system/{UNIT}\n[Service]\n\n{HEADER}\n"
                       + channel.render_dropin(rec["request"], "/opt/ryu-venv/bin/ryu-manager"))
    html = preview(apps["client"]).get_data(as_text=True)
    assert "Deploy to ctl: no app changes" in html and "Nothing to deploy" in html
    assert "Redeploy the same set and restart ctl…" in html
    assert 'hx-post="/v2/sdn/apps/confirm' not in html
    full = preview(apps["client"], redeploy="1").get_data(as_text=True)
    assert "Redeploy the same set and restart ctl</span>" in full


# ── the confirm ───────────────────────────────────────────────────────────────────────────────

def test_the_confirm_runs_busy_on_itself_and_ends_in_its_result_and_receipt(apps):
    r, done = deploy(apps)
    running = r.get_data(as_text=True)
    assert 'aria-busy="true"' in running and "Deploying…" in running
    assert 'hx-trigger="nmas:controller_deploy from:body"' in running
    assert "Deployed: ctl runs" in done and "badge-ok" in done
    [row] = deploy_receipts.read(NET)["rows"]
    assert row["outcome"] == "deployed"
    got = apps["client"].get(f"/v2/sdn/apps/receipt/{row['id']}.json")
    assert got.status_code == 200 and json.loads(got.get_data())["id"] == row["id"]
    card = apps["client"].get(f"/v2/sdn/apps?receipt={row['id']}").get_data(as_text=True)
    assert f"Receipt: {CTL}," in card and "Download the receipt (JSON)" in card
    from modules import history_sources as HS
    from modules.nsot import listref
    got = HS.timeline(listref.resolve(NET), kinds=["controller_deploy"])
    assert [e["outcome"] for e in got["events"]] == ["deployed"], got["errors"]
    assert got["events"][0]["kind"] == "controller_deploy"


def test_a_confirm_whose_plan_moved_sends_nothing_and_names_what_moved(apps):
    html = preview(apps["client"]).get_data(as_text=True)
    apps["src"].cat = f"{HEADER}\n[Service]\nUser=ryu\n"
    _, done = confirm(apps["client"], html)
    assert apps["src"].sent == []
    text = unescape(done)
    assert "Refused" in done and "What moved: the drop-in before (" in text


def test_an_unknown_outcome_offers_the_rollback_as_a_preview_never_runs_it(apps):
    deploy(apps)
    html = preview(apps["client"], "of_versions=1.1.0").get_data(as_text=True)
    apps["src"].send = lambda dev, tplan: {"ok": False, "step": "done", "command_sent": True,
                                           "error": "outcome.json did not read",
                                           "printed": None, "outcome": None, "staged": [],
                                           "not_staged": []}
    _, done = confirm(apps["client"], html)
    assert "outcome is not known" in unescape(done) and "badge-muted" in done
    assert "Preview a rollback…" in done and "Open its Needs attention row" in done
    form = re.search(r'<form class="apps-act".*?</form>', done, re.S).group(0)
    assert fields(form)["set"] == "of_versions=1.0.0"
    assert deploy_receipts.read(NET)["rows"][0]["outcome"] == "unknown"


def test_the_routes_are_declared_everywhere_a_mutating_route_must_be():
    from modules import invalidation, operation_stages, route_gates
    assert route_gates.GATES["sdn_v2.apps_confirm"].kind == "confirm"
    assert route_gates.GATES["sdn_v2.apps_preview"].kind == "reveal"
    assert "controller_deploy" in invalidation.DECLARED["sdn_v2.apps_confirm"]
    assert operation_stages.STAGES["sdn_v2.apps_confirm"].preview == "sdn_v2.apps_preview"
    assert operation_stages.HISTORY["sdn_v2.apps_confirm"] == ("controller_deploys",)
