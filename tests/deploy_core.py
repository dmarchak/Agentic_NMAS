"""THE deploy plan and apply, as v2 calls them (not a test module).

Today's deploy wizard and its two routes (POST /deploy/plan, POST /deploy/apply) left at 7.8 on
2026-10-17 (P7-25). The properties their tests held (the capture hash the plan publishes is the
one the apply recomputes, a program that moved is refused naming both operands, nothing
deployed against a diff nobody saw, the answer masked on the way out) are properties of the
cores every v2 deploy runs: `routes.deploy.plan_devices` with `deploy_preview` and
`mask_payload` (v2's batch preview, `routes.v2._apply_ctx`, and the device page's Deploy…), and
`routes.deploy.apply_batch` (the job each v2 confirm starts, `modules.deploy_job`). These two
helpers call exactly those cores, so the tests rebased onto them keep testing what v2 runs; the
removed routes' own request parsing (an unknown scope, an empty body) is v2's to refuse, and its
tests are v2's (tests/test_device_deploy_v2.py, tests/test_profile_apply_v2.py).
"""


def _list(list_name: str = "") -> str:
    from modules.config import get_current_list_name

    return list_name or get_current_list_name()


def plan(body: dict, list_name: str = "") -> dict:
    """``{ok, list, devices, scope, deployable_count, preview}``, masked: the plan for
    ``body["devices"]`` with its ``authorise``, ``remove`` and ``scope``, as v2's batch preview
    builds it (`plan_devices`, then `deploy_preview`, then `mask_payload`)."""
    import app as nmas
    from modules.outbound import mask_payload
    from modules.preview_confirm import deploy_preview
    from routes.deploy import plan_devices

    name = _list(list_name or body.get("list_name", ""))
    scope = (body.get("scope") or "").strip()
    devices = plan_devices(name, body.get("devices") or [], authorise=body.get("authorise") or {},
                           remove=body.get("remove") or {}, scope=scope)
    with nmas.app.test_request_context("/v2/monitoring/apply"):
        from flask import request

        preview = deploy_preview(devices, request, scope=scope)
    return mask_payload({"ok": True, "list": name, "devices": devices, "scope": scope,
                         "deployable_count": sum(1 for d in devices if d.get("deployable")),
                         "preview": preview})


def apply(body: dict, list_name: str = "") -> dict:
    """``{ok, list, **report}``, masked: `apply_batch` for ``body``'s confirmations, command
    hashes, authorisations, removals and scope, as the deploy job runs it for a v2 confirm: the
    actor and how it was verified read from a request, as the confirm reads them and carries
    them into the job."""
    import app as nmas
    from flask import request
    from modules import identity
    from modules.outbound import mask_payload
    from routes.deploy import apply_batch

    name = _list(list_name or body.get("list_name", ""))
    with nmas.app.test_request_context("/v2/monitoring/apply/confirm", method="POST"):
        actor = identity.request_actor()
        actor_kind = getattr(identity.identify(request), "kind", "")
    report = apply_batch(name, body.get("confirmations") or {}, body.get("command_hashes") or {},
                         authorise=body.get("authorise") or {}, remove=body.get("remove") or {},
                         scope=(body.get("scope") or "").strip(), actor=actor,
                         actor_kind=actor_kind)
    return mask_payload({"ok": True, "list": name, **report})


def post_plan(json: dict = None) -> "Answer":
    """`plan`, response-shaped: the call a test made as ``client.post("/deploy/plan", json=…)``
    before 7.8, now the core v2 runs."""
    return Answer(plan(json or {}))


def post_apply(json: dict = None) -> "Answer":
    """`apply`, response-shaped: the call a test made as ``client.post("/deploy/apply",
    json=…)`` before 7.8, now the core v2's confirms run."""
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
