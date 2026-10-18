"""THE capture preview and apply, as v2 calls them (not a test module).

Today's capture routes (POST /golden/capture/preview, GET /golden/capture/preview/<job>, POST
/golden/capture/apply) left at 7.8 on 2026-10-17 (P7-27) with today's index, their one caller
(its Save All Configs and Capture devices with no golden). The properties their tests held (the
preview reads each device now and judges it against its golden and committed intent, the apply
reads it again and refuses one that moved, one commit as the verified person, the job answers at
once and is read back, the answer masked on the way out) are properties of the cores the v2
device page's Capture runs: `routes.golden.start_capture_preview` (the job; v2's
`device_v2.capture_start`) read back through `modules.nsot.capture_job` (v2's
`device_v2.capture_job_card`), and `routes.golden.apply_captures` (v2's
`device_v2.capture_confirm`). These helpers call exactly those cores, so the tests rebased onto
them keep testing what v2 runs.

**The whole-fleet form** (no device named: what Save All opened) is the same core with
``fleet=True``. No v2 route starts it since today's index left: Devices › Save records every
device of a network through `modules/nsot/save_op.py` (tests/test_save_v2.py). Its tests stay
on the core while the code does (the register row named in the P7-27 commit).

What the removed routes alone did is gone with them: the "no golden" scope (v2: Devices filtered
to no golden, then Save for the ticked devices) and the request parsing of an unknown scope, an
unknown device or an empty confirm, which v2's device routes refuse in their own words
(tests/test_device_capture_v2.py).
"""


def _list(list_name: str = "") -> str:
    from modules.config import get_current_list_name

    return list_name or get_current_list_name()


def start(body: dict, list_name: str = "") -> dict:
    """``{ok, list, job, devices, nothing}``: the preview job started for ``body["devices"]``
    (none named: the whole fleet), in a v2 request, as `device_v2.capture_start` starts it."""
    import app as nmas
    from modules.nsot.restore import _devices_of
    from routes.golden import start_capture_preview

    name = _list(list_name or body.get("list_name", ""))
    inventory = _devices_of(name)
    wanted = [d for d in (body.get("devices") or []) if d]
    fleet = not wanted
    devices = [d for d in inventory if fleet or d.get("hostname") in set(wanted)]
    with nmas.app.test_request_context("/v2/device/capture/start", method="POST"):
        job = start_capture_preview(name, inventory, devices, fleet=fleet)
    return {"ok": True, "list": name, "job": job,
            "devices": [d.get("hostname", "") for d in devices], "nothing": ""}


def result(job: str) -> dict:
    """The job as v2's card reads it (`capture_job.get`, its progress words from
    `op_progress`): running, done (its preview), failed (why), or None for an id this server
    has no record of."""
    from modules import op_progress
    from modules.nsot import capture_job

    got = capture_job.get(job)
    if got is None:
        return None
    op = op_progress.get(job) or {}
    out = {"ok": got["state"] != "failed", "job": job, "state": got["state"],
           "list": got["list"], "elapsed_s": got["elapsed_s"],
           "step_words": op.get("step_words", ""), "error": got["error"], "fleet": None,
           "preview": None, "nothing": ""}
    if got["state"] == "done":
        out.update(got["payload"] or {})
    return out


def preview(body: dict, list_name: str = "", wait_s: float = 60) -> dict:
    """`start`, waited for, then `result`: the preview a card draws."""
    from modules.nsot import capture_job

    started = start(body, list_name)
    assert capture_job.wait(started["job"], wait_s), (
        f"capture preview {started['job']} still running after {wait_s} s")
    return result(started["job"])


def apply(body: dict, list_name: str = "") -> dict:
    """``{ok, list, fleet, result, approvals}``, masked: `apply_captures` for ``body``'s
    confirmations (``fleet``, ``acknowledge``, ``approvals``, ``mode``), as v2's confirm
    calls it, in a v2 request (the commit's actor is the request's verified person)."""
    import app as nmas
    from modules.outbound import mask_payload
    from routes.golden import acknowledged_reasons, apply_captures

    name = _list(list_name or body.get("list_name", ""))
    acknowledged, problem = acknowledged_reasons(body.get("acknowledge") or {})
    assert not problem, problem
    fleet = bool(body.get("fleet"))
    with nmas.app.test_request_context("/v2/device/capture/confirm", method="POST"):
        got = apply_captures(name, {k: v for k, v in (body.get("confirmations") or {}).items()
                                    if k},
                             fleet=fleet, acknowledged=acknowledged,
                             approvals=body.get("approvals") or {}, mode=body.get("mode") or "")
    return mask_payload({"ok": True, "list": name, "fleet": fleet, "result": got["result"],
                         "approvals": got["approvals"]})


def post_preview(json: dict = None) -> "Answer":
    """`preview`, response-shaped: the call a test made as `run_capture_preview(client, …)`
    over today's two routes before 7.8, now the core v2 runs."""
    return Answer(preview(json or {}))


def post_apply(json: dict = None) -> "Answer":
    """`apply`, response-shaped: the call a test made as ``client.post("/golden/capture/apply",
    json=…)`` before 7.8, now the core v2's confirm runs."""
    return Answer(apply(json or {}))


class Answer:
    """A response-shaped wrapper, so a test that read ``r.get_json()`` reads the same."""

    status_code = 200

    def __init__(self, body: dict):
        self._body = body

    def get_json(self, silent: bool = False):
        return self._body

    def get_data(self, as_text: bool = False):
        import json

        text = json.dumps(self._body)
        return text if as_text else text.encode()
