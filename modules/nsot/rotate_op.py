"""ROTATE, from the Device page (7.3): a device's login credential rotated,
recorded and persisted, previewed and confirmed, run as a job.

`credential_rotation` is the one implementation (`nmas-rotate-credential` is
the other entry point): `plan()` does the preflight, including a LIVE read of
the account's line; `rotate()` generates, stages before the push, pushes on a
held session, verifies on a fresh login, reverts only on a failed verify, and
records; `persist()` saves on the device and runs the boot-file chain. This
module runs the two as ONE operation, holding the device across both so no
other operation lands between the record and the persist.

**Built assuming a fourth failure mode exists** (the operator, 2026-09-27:
three ways in three days for a rotation to leave a device unmanageable, B15,
C53, C106). So:

* every state between "the device changed" and "the tool holds it" is named,
  and the result draws each with its one action (`STATE_ACTIONS`);
* the apply is a JOB: rotate plus persist can pass the 100 s edge limit, and a
  request that dies mid-rotation must not be the only thing that knew;
* the job carries the confirming person's VERIFIED identity into its thread,
  so the rotation's commit says `Actor-Verified: access`;
* a process that dies mid-rotation (an app restart; a deploy causes one) leaves
  the staged credential, which job health names and `nmas-rotation-recover`
  settles by asking the device (C210, built first for exactly this);
* nothing the operation writes is removed until the record it protects is
  proven: the staged copy is cleared by `rotate()` only after the commit.
"""

import logging
import time

log = logging.getLogger(__name__)

KIND = "credential rotation"
ANNOUNCER = "rotation"
ANNOUNCE_KEYS = ("rotation",)


def plan(list_name: str, hostname: str) -> dict:
    """`credential_rotation.plan()`: the preflight (which reads the device's
    account line LIVE), the masked program and the fingerprint to confirm."""
    from modules.nsot import credential_rotation as cr

    p = cr.plan(list_name, hostname)
    p.setdefault("device", hostname)
    p["list_name"] = list_name
    return p


def _inventory_password(list_name: str, hostname: str) -> str:
    """The credential the record holds NOW, which after a rotation is the new
    one: persist is handed what the rotation recorded, read back from where it
    was written, never passed from step to step."""
    from modules.device import decrypt_field, load_saved_devices
    from modules.nsot import credential_rotation as cr

    row = next((d for d in load_saved_devices(cr._csv_path_for(list_name))
                if d.get("hostname") == hostname), None)
    return decrypt_field(row.get("password", "")) if row else ""


def run(list_name: str, hostname: str, *, actor: str, fingerprint: str,
        started_iso: str = "") -> dict:
    """Rotate, then persist, holding the device across both. The result of the
    last step that ran, with `persist_skipped` saying why when it did not."""
    from modules.nsot import credential_rotation as cr
    from modules.nsot import device_ops

    started_iso = started_iso or cr.utc_now()
    try:
        with device_ops.hold(list_name, hostname, "rotate", actor):
            result = cr.rotate(list_name, hostname, confirmed_fingerprint=fingerprint,
                               actor=actor, actor_kind="person", via="device page")
            if result.get("state") != cr.ROTATED_PENDING_PERSIST:
                return result
            password = _inventory_password(list_name, hostname)
            if not result.get("new_hash") or not password:
                result["persist_skipped"] = (
                    "the rotation did not carry the hash, or the inventory holds no credential "
                    "after it: the device IS rotated and recorded; persist it from this page "
                    "or with nmas-persist-credential")
                return result
            device_ops.note("persisting")
            return cr.persist(result, mgmt_ip=result.get("mgmt_ip", ""),
                              username=result.get("username", ""), password=password,
                              hostname=hostname, new_hash=result["new_hash"],
                              after_iso=started_iso,
                              platform=cr.platform_of(list_name, hostname),
                              list_name=list_name, via="device page", actor=actor)
    except device_ops.DeviceBusy as exc:
        return {"device": hostname, "state": cr.NOT_STARTED, "steps": [],
                "reason": f"{exc}. Nothing was sent."}


def start(list_name: str, hostname: str, *, actor: str, fingerprint: str, ident=None,
          work=None) -> str:
    """Run the rotation as a job and return its id at once. *ident* is the
    request's verified identity, carried into the job's thread."""
    from modules import identity
    from modules.nsot import capture_job

    def _work(_job_id):
        with identity.carried(ident):
            return (work or run)(list_name, hostname, actor=actor, fingerprint=fingerprint)

    return capture_job.start(list_name, f"rotating {hostname}", actor, _work,
                             kind=KIND, announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER)
