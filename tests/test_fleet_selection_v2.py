"""Board FC phase 2 (f2), FC1: Devices › Change across the N ticked… (routes/intent_layers_v2.py
`change` with ticked devices, `change_plan`, `change_job`, `change_approve`, `change_run`),
on r2's real config and committed intent (`tests.test_capture.build_capture_lab`), its row
tagged. THE apply (`routes.deploy.apply_batch`) is replaced by a recorder: no test reaches a
device.

- **The menu:** Devices' Actions offer Change across the N ticked…, its form sent to the
  change's form with the ticked devices.
- **The form:** the ticked devices carried, Where: each device's own intent (the default) or
  each layer every ticked device takes, with how many it reaches beyond them.
- **The plan:** the change across the ticked, its steps on each device, r2's one line, the
  approval carrying the selection; nothing written.
- **The approval:** one commit of r2's intent file, the canary sent, the run card titled for
  the selection.
"""

from modules.nsot import capture_job, hostvars
from tests.test_fleet_change_plan import _head, lab, r2  # noqa: F401 (the fixtures)
from tests.test_fleet_change_run import sent  # noqa: F401 (the fixture)
from tests.test_fleet_change_selection import own  # noqa: F401 (the fixture)
from tests.test_fleet_plan_v2 import _commit_layer, page  # noqa: F401 (the fixtures)


def _plan_selection(client, devices, target="devices", before="[]"):
    data = {"list": "Lab", "target": target, "device": devices, "path": "ntp_servers",
            "before": before, "after": "[192.0.2.123]"}
    html = client.post("/v2/intent/change/plan", data=data).get_data(as_text=True)
    job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
    assert capture_job.wait(job, 30)
    return client.get(f"/v2/intent/change/job/{job}?list=Lab").get_data(as_text=True)


def test_devices_actions_offer_change_across_the_ticked():
    """The menu's entry, read in the template (the capture lab's Devices page draws no selection
    bar): its form sent to the change's form, its how-link beside it."""
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "templates", "v2", "_devices.html"), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r'<button type="submit" role="menuitem" class="menu-item" data-op="fleet-change" '
                  r'formaction="\{\{ url_for\(\'intent_layers_v2.change\'\) \}\}"[^>]*>.*?</button>'
                  r"\{\{ how\('fleet-change'", text, re.S)
    assert m and "Change across the" in m.group(0) and "ticked…" in m.group(0)


class TestTheForm:
    def test_the_ticked_devices_are_carried_and_each_devices_own_intent_is_the_default(
            self, page):  # noqa: F811
        html = page.get("/v2/intent/change?list=Lab&device=r2").get_data(as_text=True)
        assert "Change across the 1 ticked" in html and "data-fc-where" in html
        assert '<input type="hidden" name="device" value="r2">' in html
        assert 'name="target" value="devices" checked' in html
        assert "No layer reaches every ticked device" in html

    def test_add_a_setting_keeps_what_was_typed_and_draws_one_more(self, page):  # noqa: F811
        """Bulk intent's Add a setting, on the change's own form: the rows typed are kept, one
        empty row follows, and the ticked devices and the Where chosen ride along."""
        r = page.get("/v2/intent/change?list=Lab&device=r2&target=devices&more=1"
                     "&path=ntp_servers&before=%5B%5D&after=%5B192.0.2.123%5D",
                     headers={"HX-Request": "true"})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and html.lstrip().startswith("<section"), html[:200]
        assert html.count('name="path"') == 2 and 'value="ntp_servers"' in html
        assert 'value="[192.0.2.123]"' in html
        assert '<input type="hidden" name="device" value="r2">' in html
        assert 'name="target" value="devices" checked' in html
        assert ">Add a setting</button>" in html

    def test_add_a_setting_on_a_new_layer_keeps_its_rank_and_slug(self, page):  # noqa: F811
        html = page.get("/v2/intent/change?list=Lab&more=1&rank=tag&slug=blind-lab&path=x",
                        headers={"HX-Request": "true"}).get_data(as_text=True)
        assert '<option value="tag" selected>' in html and 'value="blind-lab"' in html, html

    def test_a_layer_every_ticked_device_takes_is_offered(self, page, r2):  # noqa: F811
        _commit_layer(r2["repo"], "tag-blind-lab.yml", "domain_name: corp.example\n")
        html = page.get("/v2/intent/change?list=Lab&device=r2").get_data(as_text=True)
        assert 'name="target" value="layer:tag-blind-lab"' in html, html
        assert "Tag blind-lab" in html and "reaches 1 device" in html


class TestThePlanAndTheApproval:
    def test_the_plan_is_the_change_across_the_ticked_and_writes_nothing(self, page, own):  # noqa: F811
        head = _head(own["repo"])
        html = _plan_selection(page, ["r2"])
        assert "Change across the 1 ticked" in html and "data-fc-steps" in html, html
        assert "+ ntp server 192.0.2.123" in html
        assert '<input type="hidden" name="target" value="devices">' in html
        assert '<input type="hidden" name="device" value="r2">' in html
        assert 'name="layer"' not in html.split("change/approve", 1)[1].split("</form>", 1)[0]
        assert _head(own["repo"]) == head, "a plan commits nothing"

    def test_approving_commits_r2s_document_once_and_runs_the_canary(self, page, own, sent):  # noqa: F811
        from tests.test_fleet_run_v2 import _form_of
        html = _plan_selection(page, ["r2"])
        _form, fields = _form_of(html)
        head = _head(own["repo"])
        data = dict(fields, summary=["r2's NTP server"], reason=["its time source"],
                    canary=["r2"], batch=["1"], after_canary=["pause"])
        html = page.post("/v2/intent/change/approve", data=data).get_data(as_text=True)
        run = html.split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(run, 30)
        html = page.get(f"/v2/intent/change/run/{run}?list=Lab").get_data(as_text=True)
        assert "Change across the 1 ticked · done" in html, html
        assert sent["calls"] == [["r2"]]
        assert "192.0.2.123" in hostvars.committed_at_head(own["repo"], "r2")[0]
        assert _head(own["repo"]) != head

    def test_no_device_ticked_is_refused(self, page):  # noqa: F811
        r = page.post("/v2/intent/change/plan", data={
            "list": "Lab", "target": "devices", "path": "ntp_servers", "before": "[]",
            "after": "[192.0.2.123]"})
        assert r.status_code == 400 and "no device is ticked" in r.get_data(as_text=True)


def test_a_layer_chosen_in_where_plans_the_layers_change(page, r2):  # noqa: F811
    """Where: a layer every ticked device takes plans that layer's change, a layer's plan
    (its file, its before and after), never the devices' own documents."""
    html = _plan_selection(page, ["r2"], target="layer:tag-blind-lab", before="(absent)")
    assert "Tag blind-lab's change" in html and "layers/tag-blind-lab.yml" in html, html
    assert "data-fc-steps" not in html
    assert '<input type="hidden" name="layer" value="tag-blind-lab">' in html
