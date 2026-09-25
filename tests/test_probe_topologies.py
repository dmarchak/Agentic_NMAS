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


# --------------------------------------------------------------------------
# Gi1 belongs to vrnetlab, on the topology side too
# --------------------------------------------------------------------------

def _link_endpoints(link):
    """``[(node, interface, as-written)]`` for **both** link formats.

    containerlab has two. The brief one is a list of ``"node:iface"`` strings;
    the **extended** one is a list of mappings, and it is the only one with a
    per-endpoint ``mac:`` — which phase 2's probe needs, because a DHCP
    reservation is keyed on a MAC that has to be known before the first boot.

    **This function exists because the check was blind to the second.**
    `str(endpoint).partition(":")` on a dict yields garbage, so a `Gi1` cabled
    in the extended format was not an offender and not an error — it simply was
    not seen. Measured before changing it: the whole suite passed against a
    topology deliberately cabling a c8000v's reserved interface.

    A gate that silently opens produces no offenders, which is exactly what a
    clean run looks like. The first file to use the newer format would have
    lost the protection and nothing would have said so.
    """
    out = []
    for endpoint in (link or {}).get("endpoints") or []:
        if isinstance(endpoint, dict):
            node = str(endpoint.get("node", ""))
            iface = str(endpoint.get("interface", ""))
            out.append((node, iface, f"{node}:{iface}"))
        else:
            node, _, iface = str(endpoint).partition(":")
            out.append((node, iface, str(endpoint)))
    return out


def c8000v_links_on_the_reserved_interface(paths):
    """Every c8000v link endpoint that lands on Gi1.

    `bootstrap_config.manager_interface_lines()` refuses to put a management
    address on a platform's vrnetlab-owned interface, and `build_plan()`
    makes it a blocking reason. **The topology can make the same mistake from
    the other end**: cabling a node's Gi1 to the management bridge produces a
    file that is internally consistent, deploys, and fights vrnetlab for the
    interface.

    A generator refusal cannot see a YAML file, so the property is asserted
    where it is representable. Same reasoning as the launch-patch check
    above: a rule that has to be remembered will be forgotten once.
    """
    offenders = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        topology = doc.get("topology") or {}
        kinds = {name: (cfg or {}).get("kind")
                 for name, cfg in (topology.get("nodes") or {}).items()}
        for link in (topology.get("links") or []):
            for node, iface, shown in _link_endpoints(link):
                if kinds.get(node) not in PATCH_REQUIRED_KINDS:
                    continue
                # Gi1 exactly -- Gi10 and Gi11 are ordinary data interfaces.
                if iface.lower() in ("gi1", "gigabitethernet1"):
                    offenders.append(f"{os.path.basename(path)}:{shown}")
    return offenders


def test_no_c8000v_is_cabled_on_its_reserved_interface():
    offenders = c8000v_links_on_the_reserved_interface(_topologies())
    assert not offenders, (
        "c8000v link(s) on Gi1, which vrnetlab owns: " + ", ".join(offenders)
        + ". Data interfaces start at Gi2; a management address cabled to "
          "Gi1 fights the launch script for the interface.")


def test_the_reserved_interface_check_can_fail(tmp_path):
    """Shown failing, and shown NOT firing on the interface next to it."""
    bad = tmp_path / "gi1.clab.yml"
    bad.write_text(
        "topology:\n"
        "  nodes:\n"
        "    c8k:\n"
        "      kind: cisco_c8000v\n"
        "    br-mgmt:\n"
        "      kind: bridge\n"
        "  links:\n"
        "    - endpoints: [\"c8k:Gi1\", \"br-mgmt:x-mgmt\"]\n",
        encoding="utf-8")
    assert c8000v_links_on_the_reserved_interface([str(bad)]) == [
        "gi1.clab.yml:c8k:Gi1"]

    # Gi2 is fine, and so is Gi10 -- a substring match would have caught it.
    for good in ("Gi2", "Gi10", "GigabitEthernet2"):
        ok = tmp_path / f"ok-{good}.clab.yml"
        ok.write_text(
            "topology:\n  nodes:\n    c8k:\n      kind: cisco_c8000v\n"
            "    br-mgmt:\n      kind: bridge\n  links:\n"
            f"    - endpoints: [\"c8k:{good}\", \"br-mgmt:x-mgmt\"]\n",
            encoding="utf-8")
        assert c8000v_links_on_the_reserved_interface([str(ok)]) == [], good


# --------------------------------------------------------------------------
# Both link formats, because the check was blind to the newer one
# --------------------------------------------------------------------------

def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


_EXTENDED = """name: x
topology:
  nodes:
    lonely-c8k:
      kind: cisco_c8000v
      binds: ["patches/c8000v-launch-adopted.py:/launch.py"]
    br-mgmt: {kind: bridge}
  links:
    - type: veth
      endpoints:
        - node: lonely-c8k
          interface: %s
          mac: aa:bb:cc:00:02:40
        - node: br-mgmt
          interface: x-mgmt
"""


def test_the_reserved_interface_check_sees_the_EXTENDED_format(tmp_path):
    """**The blindness, pinned.** Before `_link_endpoints`, a `Gi1` cabled in
    the extended format was not an offender and not an error — it was not
    seen, and the whole suite passed against it. A gate that silently opens
    produces no offenders, which is what a clean run looks like."""
    bad = _write(tmp_path, "extended.clab.yml", _EXTENDED % "Gi1")
    assert c8000v_links_on_the_reserved_interface([bad]) == \
        ["extended.clab.yml:lonely-c8k:Gi1"]


def test_the_extended_format_on_Gi2_is_accepted(tmp_path):
    """**The floor.** A parser that flagged every extended link would satisfy
    the test above and make the format unusable."""
    good = _write(tmp_path, "ok.clab.yml", _EXTENDED % "Gi2")
    assert c8000v_links_on_the_reserved_interface([good]) == []


def test_the_phase_2_probe_uses_the_extended_format():
    """A positive anchor: the format really is in the corpus, so the parser
    above is exercised by a real file and not only by a fixture."""
    import yaml as _yaml

    path = os.path.join(PROBE_DIR, "nmas-dhcp-a.clab.yml")
    doc = _yaml.safe_load(open(path, encoding="utf-8"))
    endpoints = (doc["topology"]["links"][0] or {})["endpoints"]
    assert isinstance(endpoints[0], dict), "the probe no longer pins a MAC"
    assert endpoints[0]["mac"] == "aa:bb:cc:00:02:40"


def test_the_pinned_mac_matches_the_documented_reservation():
    """The pair is written in two files and a mismatch is silence on the wire,
    which looks exactly like a Kea problem."""
    path = os.path.join(PROBE_DIR, "nmas-dhcp-a.clab.yml")
    topology = open(path, encoding="utf-8").read()
    scope = open(os.path.join(os.path.dirname(PROBE_DIR), "PHASE2_DHCP.md"),
                 encoding="utf-8").read()
    assert "aa:bb:cc:00:02:40" in topology
    assert "aa:bb:cc:00:02:40" in scope, \
        "the reservation in the scope document no longer matches the topology"
