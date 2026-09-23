"""A C8000v that does not bind a launch patch does not boot here.

Third time this one per-node line has been the difference, measured each
time on the lab host rather than reasoned about:

1. The first bootstrap probe. Stock script, 1 vCPU, never completed in ~40
   minutes. `smp="2"` is the fix and it is the whole patch.
2. Stage B. The stock script concatenates
   `username admin privilege 15 password admin` ahead of the startup config,
   IOS-XE refuses a secret for a user that already has a password, and the
   node boots on admin/admin reporting healthy the whole way.
3. `nmas-onboard-c.clab.yml`, 2026-09-23: shipped with no `binds:`, launched
   *"with 1 SMP/VCPU"*, 112% CPU, grinding rather than stalled.

**The third one is why this file exists.** Twice is a coincidence; three
times is a property nobody is going to remember, and the fix each time was a
line somebody had to know to write. The rule is mechanical, so it belongs in
the suite instead of in a runbook or in a head.

**Reason 2 is the one that matters, and it is the one a probe cannot show
you.** A node short of a vCPU fails loudly and wastes 40 minutes. A node
short of the user-skip *succeeds* -- boots, answers SSH, reports healthy --
while holding a credential nobody intended, which inside the Stage 4C
onboarding probe would mean the probe passes by reproducing the exact hazard
stage 2 exists to prevent.

Scope: `docs/bootstrap-probe/` only. These are throwaway measurement labs in
this repository; `rcn-lab1` is not here and is not this suite's business.
"""

import glob
import os

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE_DIR = os.path.join(ROOT, "docs", "bootstrap-probe")

#: The kind whose launch script must be patched. vIOS is not in this set:
#: nothing is injected ahead of its startup config and it boots on one vCPU,
#: which is why four vIOS nodes in this directory correctly bind nothing.
PATCH_REQUIRED_KINDS = {"cisco_c8000v"}

#: What the patch must be mounted over. vrnetlab runs `/launch.py`; a bind
#: landing anywhere else is a file the container never executes.
LAUNCH_TARGET = "/launch.py"

#: Floors. An assertion over "no offenders" passes just as happily when the
#: scan found nothing at all, so both the file count and the node count are
#: pinned as numbers. Measured 2026-09-23: 6 topologies, 4 c8000v nodes.
#: These are deliberately lower than the real figures -- the failure being
#: guarded is the glob matching NOTHING, not the directory growing.
MIN_TOPOLOGIES = 4
MIN_C8000V_NODES = 3


def _topologies():
    return sorted(glob.glob(os.path.join(PROBE_DIR, "*.clab.yml")))


def _nodes(path):
    """(node_name, kind, binds) for every node, with the kind RESOLVED.

    A node carrying no `kind` raises rather than being skipped. Treating an
    unresolvable kind as "not a c8000v" is a lookup that misses reported as
    a fact about the system -- the shape that let the slug/dialect gate open
    silently.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    nodes = ((doc.get("topology") or {}).get("nodes") or {})
    out = []
    for name, cfg in nodes.items():
        cfg = cfg or {}
        kind = cfg.get("kind")
        if not kind:
            raise AssertionError(
                f"{os.path.basename(path)}: node {name!r} declares no kind, so "
                f"this check cannot tell whether it needs a launch patch")
        out.append((name, kind, list(cfg.get("binds") or [])))
    return out


def _launch_binds(binds):
    return [b for b in binds if b.rsplit(":", 1)[-1] == LAUNCH_TARGET]


def unpatched_c8000v_nodes(paths):
    """Every c8000v node that binds nothing over `/launch.py`.

    Separate from the test so the negative control can drive the same code
    with a topology built to fail.
    """
    offenders = []
    for path in paths:
        for name, kind, binds in _nodes(path):
            if kind in PATCH_REQUIRED_KINDS and not _launch_binds(binds):
                offenders.append(f"{os.path.basename(path)}:{name}")
    return offenders


# --------------------------------------------------------------------------
# The floors, first. Everything below is a "nothing is wrong" assertion and
# means nothing without them.
# --------------------------------------------------------------------------

def test_the_scan_finds_something():
    paths = _topologies()
    assert len(paths) >= MIN_TOPOLOGIES, (
        f"found {len(paths)} topologies under {PROBE_DIR} -- the glob is "
        f"matching almost nothing and every check below would pass vacuously")

    c8000v = [n for p in paths for n in _nodes(p)
              if n[1] in PATCH_REQUIRED_KINDS]
    assert len(c8000v) >= MIN_C8000V_NODES, (
        f"found {len(c8000v)} cisco_c8000v nodes -- if the kind string "
        f"changed, this file now checks nothing and says so by passing")


def test_every_c8000v_binds_a_launch_patch():
    offenders = unpatched_c8000v_nodes(_topologies())
    assert not offenders, (
        "cisco_c8000v node(s) with no launch patch bound over /launch.py: "
        + ", ".join(offenders)
        + ". Without it the node boots on 1 vCPU (and here has never finished "
          "booting), AND vrnetlab injects `username admin ... password admin` "
          "ahead of the startup config, so a generated `secret 9` line is "
          "rejected and the node comes up on admin/admin reporting healthy.")


def test_the_check_can_fail(tmp_path):
    """The negative control. Shown failing, or it means nothing.

    Same function, a topology written to break it. Without this, a typo in
    the kind string or in the bind parsing would make the test above pass
    for the wrong reason, and nothing would say so.
    """
    bad = tmp_path / "unpatched.clab.yml"
    bad.write_text(
        "topology:\n"
        "  nodes:\n"
        "    lonely-c8k:\n"
        "      kind: cisco_c8000v\n",
        encoding="utf-8")
    assert unpatched_c8000v_nodes([str(bad)]) == ["unpatched.clab.yml:lonely-c8k"]

    # A bind that exists but lands somewhere vrnetlab never runs is still
    # unpatched. This is the near miss, and it is the one a reader would
    # assume is covered.
    wrong = tmp_path / "wrongmount.clab.yml"
    wrong.write_text(
        "topology:\n"
        "  nodes:\n"
        "    misbound-c8k:\n"
        "      kind: cisco_c8000v\n"
        "      binds:\n"
        "        - patches/c8000v-launch.py:/opt/launch.py\n",
        encoding="utf-8")
    assert unpatched_c8000v_nodes([str(wrong)]) == [
        "wrongmount.clab.yml:misbound-c8k"]

    # And a vIOS with no bind is NOT an offender -- the check has to be
    # about the kind, not about binds in general.
    vios = tmp_path / "vios.clab.yml"
    vios.write_text(
        "topology:\n"
        "  nodes:\n"
        "    a-vios:\n"
        "      kind: cisco_vios\n",
        encoding="utf-8")
    assert unpatched_c8000v_nodes([str(vios)]) == []


def test_the_bind_source_is_the_probes_own_copy():
    """A throwaway lab whose teardown can reach into production is not one.

    The host side of the bind must be relative, so it resolves inside the
    topology's own directory. An absolute path or a `~` would mount the
    live `rcn-lab1` patch into a lab built to be destroyed.
    """
    offenders = []
    for path in _topologies():
        for name, kind, binds in _nodes(path):
            if kind not in PATCH_REQUIRED_KINDS:
                continue
            for bind in _launch_binds(binds):
                src = bind.rsplit(":", 1)[0]
                if os.path.isabs(src) or src.startswith("~"):
                    offenders.append(
                        f"{os.path.basename(path)}:{name} -> {src}")
    assert not offenders, (
        "launch patch bound from outside the probe directory: "
        + ", ".join(offenders)
        + ". Stage the probe's own copy instead (runbook step 3a).")
