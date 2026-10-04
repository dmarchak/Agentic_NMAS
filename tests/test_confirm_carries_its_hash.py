"""A deploy or restore confirm without the program's hash sends nothing (CONCURRENCY_AUDIT R16,
2026-10-04).

R16: the command hash was optional. With none, only the capture hash was compared, so an intent
or template change between the plan and the apply was pushed unseen: the bypass-by-omission
shape (what is confirmed is what is sent). Every shipped client sends it; now the apply refuses a
device without it, by name, before anything else, deploy and restore alike.

Through the real `/deploy/apply` over the plan-apply seam's artifact, and the real
`run_targets` over a real restore target.
"""

from tests.test_deploy_plan_apply_seam import _plan, client  # noqa: F401 (the fixture)
from tests.test_device_ops import _spy_pipeline


def test_a_deploy_without_the_hash_is_refused_and_nothing_sent(client, monkeypatch):  # noqa: F811
    ran = _spy_pipeline(monkeypatch)
    device = _plan(client)
    body = client.post("/deploy/apply",
                       json={"confirmations": {"r6": device["capture_hash"]}}).get_json()
    row = next(r for r in body["results"] if r["device"] == "r6")
    assert row["outcome"] == "refused"
    assert "needs the command hash the preview showed" in row["reason"]
    assert ran == [] and "r6" not in body.get("deployed", [])


def test_the_same_apply_with_the_hash_deploys(client, monkeypatch):  # noqa: F811
    device = _plan(client)
    body = client.post("/deploy/apply",
                       json={"confirmations": {"r6": device["capture_hash"]},
                             "command_hashes": {"r6": device["command_hash"]}}).get_json()
    assert "r6" in body.get("deployed", []), body.get("by_outcome")


def test_a_restore_without_the_hash_is_refused_and_nothing_sent(monkeypatch):
    import routes.deploy as rd
    from routes.deploy import _capture_hash
    from tests.test_p3_restore_is_guarded import _target

    ran = _spy_pipeline(monkeypatch)
    target = _target("r1", target_config="hostname r1\nlogging buffered 4096\n",
                     captured="hostname r1\n")
    report = rd.run_targets("Lab", [target],
                            {"confirmations": {"r1": _capture_hash("hostname r1\n")}},
                            label="re-apply X", source_ref="X")
    row = next(r for r in report["results"] if r["device"] == "r1")
    assert row["outcome"] == "refused"
    assert "needs the command hash the preview showed" in row["reason"]
    assert ran == []
