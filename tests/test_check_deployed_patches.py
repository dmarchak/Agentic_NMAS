"""C1546: `lab/check-deployed-patches`, the lab's check that it runs the launcher Mercury tests.

LAB TOOLING, run on the lab host from the lab repository. Here it runs as a program in a
temporary lab repository, with a fake `docker` first on PATH that answers `inspect` (what is
bound over a container's `/launch.py`) and `exec ... sha256sum /launch.py` from files this test
writes, and records every docker command it was given. Every outcome prints both operands:
all match is 0, a mismatch is 1 naming it, an absent file, container or `/launch.py` is 2.

The table's expected sha is the generator's output that tests/test_vios_configless_patch.py
pins (`GENERATED_SHA`), so the lab's check and Mercury's test name one value.
"""

import hashlib
import importlib.machinery
import importlib.util
import os
import stat
import subprocess
import sys

import pytest

from tests.test_vios_configless_patch import GENERATED_SHA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "lab", "check-deployed-patches")
NAME = "patches/vios-launch-configless.py"
LAUNCHER = b"# the patched launcher, as the generator wrote it\n"
SHA = hashlib.sha256(LAUNCHER).hexdigest()

#: A fake docker: `inspect --format {{json .Mounts}} C` prints C's bind of /launch.py from
#: $FAKE_DOCKER/C.source; `exec C sha256sum /launch.py` hashes $FAKE_DOCKER/C.launch; a
#: container with neither file is "No such container". Every call is appended to calls.log.
FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_DOCKER/calls.log"
case "$1" in
  inspect) c="$4" ;;
  exec) c="$2" ;;
  *) echo "fake docker: unexpected command $1" >&2; exit 64 ;;
esac
if [ ! -e "$FAKE_DOCKER/$c.source" ] && [ ! -e "$FAKE_DOCKER/$c.launch" ]; then
  echo "Error response from daemon: No such container: $c" >&2; exit 1
fi
if [ "$1" = inspect ]; then
  if [ -e "$FAKE_DOCKER/$c.source" ]; then
    printf '[{"Type":"bind","Source":"%s","Destination":"/launch.py"}]\\n' "$(cat "$FAKE_DOCKER/$c.source")"
  else
    echo '[]'
  fi
  exit 0
fi
if [ ! -e "$FAKE_DOCKER/$c.launch" ]; then
  echo "sha256sum: /launch.py: No such file or directory" >&2; exit 1
fi
sum=$(sha256sum "$FAKE_DOCKER/$c.launch" | cut -d' ' -f1)
echo "$sum  /launch.py"
"""


@pytest.fixture
def lab(tmp_path):
    """A lab repository holding the patched launcher, s5 binding it and running it."""
    repo, fake, bin_ = tmp_path / "lab", tmp_path / "docker", tmp_path / "bin"
    for d in (repo / "patches", fake, bin_):
        d.mkdir(parents=True)
    (repo / NAME).write_bytes(LAUNCHER)
    (fake / "clab-rcn-lab1-s5.source").write_text(str(repo / NAME))
    (fake / "clab-rcn-lab1-s5.launch").write_bytes(LAUNCHER)
    (bin_ / "docker").write_text(FAKE_DOCKER)
    (bin_ / "docker").chmod(stat.S_IRWXU)

    def run(*args):
        env = dict(os.environ, PATH=f"{bin_}{os.pathsep}{os.environ.get('PATH', '')}",
                   FAKE_DOCKER=str(fake))
        done = subprocess.run([sys.executable, SCRIPT, f"{NAME}={SHA}", *args], cwd=repo,
                              env=env, capture_output=True, text=True, timeout=60)
        calls = (fake / "calls.log").read_text().splitlines() if (fake / "calls.log").exists() \
            else []
        return done.returncode, done.stdout, calls

    run.repo, run.fake = repo, fake
    return run


def _script():
    loader = importlib.machinery.SourceFileLoader("check_deployed_patches", SCRIPT)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def test_the_table_expects_the_output_mercurys_test_pins():
    mod = _script()
    assert mod.EXPECTED[NAME] == GENERATED_SHA
    assert mod.CONTAINERS[NAME] == ["clab-rcn-lab1-s5"]     # the documented default list


def test_all_matching_is_0_with_both_operands_printed(lab):
    code, out, calls = lab()
    assert code == 0, out
    assert f"ok        {NAME} (sha256): {SHA} = expected {SHA}" in out
    assert f"ok        clab-rcn-lab1-s5 /launch.py (sha256): {SHA} = expected {SHA}" in out
    real = os.path.realpath(lab.repo / NAME)
    assert f"ok        clab-rcn-lab1-s5 /launch.py bound from: {real} = expected {real}" in out
    # Read-only: the only docker commands given are the two reads.
    assert calls == ["inspect --format {{json .Mounts}} clab-rcn-lab1-s5",
                     "exec clab-rcn-lab1-s5 sha256sum /launch.py"]


def test_a_container_running_another_launcher_is_1_naming_it(lab):
    (lab.fake / "clab-rcn-lab1-s5.launch").write_bytes(b"# the stock launcher\n")
    other = hashlib.sha256(b"# the stock launcher\n").hexdigest()
    code, out, _ = lab()
    assert code == 1, out
    assert f"MISMATCH  clab-rcn-lab1-s5 /launch.py (sha256): {other} != expected {SHA}" in out
    assert out.strip().splitlines()[-1] == "mismatched: clab-rcn-lab1-s5 /launch.py (sha256)"


def test_the_lab_repositorys_file_differing_is_1_naming_it(lab):
    (lab.repo / NAME).write_bytes(LAUNCHER + b"# edited by hand\n")
    code, out, _ = lab()
    assert code == 1, out
    assert f"MISMATCH  {NAME} (sha256): " in out and f"!= expected {SHA}" in out
    assert out.strip().splitlines()[-1] == f"mismatched: {NAME} (sha256)"


def test_a_container_binding_another_file_is_1_naming_both(lab, tmp_path):
    elsewhere = tmp_path / "old-launch.py"
    elsewhere.write_bytes(LAUNCHER)
    (lab.fake / "clab-rcn-lab1-s5.source").write_text(str(elsewhere))
    code, out, _ = lab()
    assert code == 1, out
    assert (f"MISMATCH  clab-rcn-lab1-s5 /launch.py bound from: {os.path.realpath(elsewhere)} "
            f"!= expected {os.path.realpath(lab.repo / NAME)}") in out


def test_the_lab_repositorys_file_absent_is_2(lab):
    (lab.repo / NAME).unlink()
    code, out, _ = lab()
    assert code == 2, out
    assert f"ABSENT    {NAME}: no such file in {lab.repo}" in out


def test_a_container_not_running_is_2_naming_docker_s_answer(lab):
    for suffix in (".source", ".launch"):
        (lab.fake / f"clab-rcn-lab1-s5{suffix}").unlink()
    code, out, _ = lab()
    assert code == 2, out
    assert ("ABSENT    clab-rcn-lab1-s5: Error response from daemon: No such container: "
            "clab-rcn-lab1-s5") in out


def test_a_container_without_launch_py_is_2_and_a_mismatch_found_is_still_named(lab):
    (lab.fake / "clab-rcn-lab1-s5.launch").unlink()
    (lab.repo / NAME).write_bytes(b"# another\n")
    code, out, _ = lab()
    assert code == 2, out
    assert "ABSENT    clab-rcn-lab1-s5 /launch.py: sha256sum: /launch.py: No such file" in out
    assert out.strip().splitlines()[-1] == (
        f"could not compare: clab-rcn-lab1-s5 /launch.py; mismatched: {NAME} (sha256)")


def test_the_container_list_is_the_operators_to_change(lab):
    (lab.fake / "clab-other-s9.source").write_text(str(lab.repo / NAME))
    (lab.fake / "clab-other-s9.launch").write_bytes(LAUNCHER)
    code, out, calls = lab("--container", f"{NAME}=clab-other-s9")
    assert code == 0, out
    assert all("clab-rcn-lab1-s5" not in c for c in calls) and len(calls) == 2


def test_without_docker_it_says_so_and_is_2(lab, tmp_path):
    env = dict(os.environ, PATH=str(tmp_path / "empty"))
    done = subprocess.run([sys.executable, SCRIPT, f"{NAME}={SHA}"], cwd=lab.repo, env=env,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 2, done.stdout
    assert "ABSENT    clab-rcn-lab1-s5: docker is not on PATH" in done.stdout
