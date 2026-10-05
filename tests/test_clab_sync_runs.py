"""The WHOLE clab sync, run end to end under bash (the operator, 2026-10-02).

Its first run on the baseline source found every device unchanged, printed
"Nothing to copy", then crashed on `NOT_BUILT: unbound variable` (under
`set -u` bash calls a declared-but-empty associative array unbound), ran on
past the exit, and exited 1: the job failed on its best outcome. Every other
test of the script lifts ONE block, so none reached that exit with every
device built. Here the real `scripts/oxidized-to-config.sh` runs with fakes
standing in for the network only: `ssh` runs its command here, `rsync`
copies here, `sudo` refuses, the map and the baseline source are files, the
two labs and Oxidized are real git repositories. Each exit path is driven:
first sync (everything new, copied and committed), nothing to copy, some
copied, a device not built, the cross-check reporting.
"""

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "oxidized-to-config.sh")
TAG = "baseline/20261001T235242Z"

CONFIG = ("hostname {h}\ninterface Loopback0\n ip address 192.0.2.{n} 255.255.255.255\n!\n"
          "interface GigabitEthernet2\n ip address 198.51.100.{n} 255.255.255.0\n!\nend\n")
DEVICES = {"r1": ("labA", 1), "r2": ("labA", 2), "r6": ("labB", 6)}

FAKE_SSH = '#!/bin/bash\n# the remote command is the last argument: run it here\nexec bash -c "${@: -1}"\n'
FAKE_RSYNC = r'''#!/bin/bash
files=""; args=()
for a in "$@"; do
  case "$a" in --files-from=*) files="${a#--files-from=}" ;; -*) ;; *) args+=("${a#clab:}") ;; esac
done
src="${args[0]}"; dst="${args[1]}"; mkdir -p "$dst"
if [ -n "$files" ]; then
  while read -r f; do [ -n "$f" ] || continue; mkdir -p "$dst/$(dirname "$f")"; cp "$src/$f" "$dst/$f"; done < "$files"
else
  cp -a "$src/." "$dst/"
fi
'''


def _env(tmp_path):
    return {"PATH": str(tmp_path / "bin") + os.pathsep + os.environ["PATH"],
            "HOME": str(tmp_path / "home"), "GIT_CONFIG_NOSYSTEM": "1"}


def _git(tmp_path, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          env=_env(tmp_path), capture_output=True, text=True, check=True)


def _exe(path, text):
    path.write_text(text)
    path.chmod(0o755)
    return path


@pytest.fixture
def world(tmp_path):
    (tmp_path / "home").mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    _exe(bin_ / "ssh", FAKE_SSH)
    _exe(bin_ / "rsync", FAKE_RSYNC)
    _exe(bin_ / "sudo", "#!/bin/sh\nexit 1\n")
    # Oxidized, a real repository holding what each device runs now.
    ox = tmp_path / "oxidized"
    ox.mkdir()
    _git(tmp_path, "init", "-q", str(ox))
    # The two labs, each a repository with an empty configs/.
    for lab in ("labA", "labB"):
        d = tmp_path / lab / "configs"
        d.mkdir(parents=True)
        (d / ".keep").write_text("")
        _git(tmp_path, "init", "-q", str(tmp_path / lab))
        _git(tmp_path, "-C", str(tmp_path / lab), "add", "-A")
        _git(tmp_path, "-C", str(tmp_path / lab), "commit", "-q", "-m", "init")
    rows = "".join(f"{h}\t{tmp_path / lab / 'configs'}\t{lab}\tclab\tcisco_iosxe\t{h}\n"
                   for h, (lab, _n) in DEVICES.items())
    (tmp_path / "map.tsv").write_text(rows)
    _exe(bin_ / "targets", '#!/bin/bash\ncase " $* " in *" --reconcile "*) '
                           'echo "map: reconciled"; exit 0 ;; esac\n'
                           f'cat {tmp_path / "map.tsv"}\n')
    _exe(bin_ / "source", f'#!/bin/bash\nmkdir -p "$2"\ncp {tmp_path / "src"}/* "$2"/\n')
    world = {"tmp": tmp_path, "ox": ox}
    set_source(world, {h: CONFIG.format(h=h, n=n) for h, (_l, n) in DEVICES.items()})
    set_oxidized(world, {h: CONFIG.format(h=h, n=n) for h, (_l, n) in DEVICES.items()})
    return world


def set_source(world, configs: dict, refused=()):
    """What `nmas-startup-source` writes: each device's file and its row."""
    src = world["tmp"] / "src"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir()
    rows = [f"# baseline\t{TAG}\tabcdef0123456789"]
    for h in DEVICES:
        if h in refused:
            rows.append(f"{h}\trefused\t{TAG} holds no golden for {h} (onboarded since)")
        else:
            (src / f"{h}.cfg").write_text(configs[h])
            rows.append(f"{h}\tok\tcredentials from its current golden: accounts")
    (src / "sources.tsv").write_text("\n".join(rows) + "\n")


def set_oxidized(world, configs: dict):
    for h, text in configs.items():
        (world["ox"] / h).write_text(text)
    _git(world["tmp"], "-C", str(world["ox"]), "add", "-A")
    _git(world["tmp"], "-C", str(world["ox"]), "commit", "-q", "--allow-empty", "-m", "poll")


def run(world):
    tmp = world["tmp"]
    env = {**_env(tmp), "CLAB": "clab", "NMAS_URL": "http://127.0.0.1:9", "REF": "HEAD",
           "REPO": str(world["ox"]), "OUT": str(tmp / "out"), "STAGE": str(tmp / "stage"),
           "TARGETS": str(tmp / "bin" / "targets"), "SOURCE": str(tmp / "bin" / "source")}
    p = subprocess.run(["bash", SCRIPT, "--yes"], env=env, capture_output=True, text=True,
                       cwd=str(tmp), timeout=120)
    return p.returncode, p.stdout + p.stderr


def _lab_log(world, lab):
    return _git(world["tmp"], "-C", str(world["tmp"] / lab), "log", "--format=%s").stdout


def test_the_first_sync_writes_and_commits_every_file(world):
    rc, out = run(world)
    assert rc == 0, out
    assert "unbound variable" not in out
    for h, (lab, _n) in DEVICES.items():
        assert (world["tmp"] / lab / "configs" / f"{h}.cfg").read_text().startswith("hostname " + h)
    assert _lab_log(world, "labA").splitlines()[0].startswith(f"startup from {TAG} (")
    assert "Startup-configs updated for 2 of 2 lab(s)" in out


def test_every_device_built_and_nothing_changed_exits_0_saying_so(world):
    """The host's 01:51 run: the best outcome, which crashed."""
    assert run(world)[0] == 0
    rc, out = run(world)
    assert rc == 0, out
    assert "unbound variable" not in out
    assert f"Both labs already hold {TAG}; nothing to update." in out
    assert "updated for 0 of 0" not in out


def test_some_copied_moves_only_the_changed_file(world):
    assert run(world)[0] == 0
    before = _lab_log(world, "labB")
    set_source(world, {h: CONFIG.format(h=h, n=n).replace("hostname r1\n", "hostname r1\n"
                                                           "ip domain lookup\n")
                       for h, (_l, n) in DEVICES.items()})
    rc, out = run(world)
    assert rc == 0, out
    assert "r1   labA             CHANGED" in out and "r6   labB             unchanged" in out
    assert "ip domain lookup" in (world["tmp"] / "labA" / "configs" / "r1.cfg").read_text()
    assert _lab_log(world, "labA").splitlines()[0].endswith("): r1")
    assert _lab_log(world, "labB") == before, "a lab with nothing to move is not touched"


def test_a_device_not_built_is_named_the_rest_written_and_the_run_exits_3(world):
    set_source(world, {h: CONFIG.format(h=h, n=n) for h, (_l, n) in DEVICES.items()},
               refused=("r6",))
    rc, out = run(world)
    assert rc == 3, out
    assert "unbound variable" not in out
    assert f"NOT BUILT - {TAG} holds no golden for r6" in out
    assert (world["tmp"] / "labA" / "configs" / "r1.cfg").exists()
    assert not (world["tmp"] / "labB" / "configs" / "r6.cfg").exists()


def test_not_built_on_the_nothing_to_copy_path_still_exits_3(world):
    assert run(world)[0] == 0
    set_source(world, {h: CONFIG.format(h=h, n=n) for h, (_l, n) in DEVICES.items()},
               refused=("r6",))
    rc, out = run(world)
    assert rc == 3 and "unbound variable" not in out, out
    assert "The lab already holds" in out and "1 device(s) NOT BUILT" in out


def test_the_cross_check_reports_a_device_that_moved_and_never_blocks(world):
    assert run(world)[0] == 0
    set_oxidized(world, {"r2": CONFIG.format(h="r2", n=2).replace(
        "interface Loopback0\n", "interface Loopback0\n description by hand\n")})
    rc, out = run(world)
    assert rc == 0, out
    assert "r2   DIFFERS from what runs now: it runs 1 line(s) the file lacks" in out
    assert "r1   runs what its file boots" in out
    assert f"Both labs already hold {TAG}; nothing to update." in out


def _recording(world):
    """Wrap the two helpers so each records the arguments the script gave it."""
    tmp = world["tmp"]
    for name in ("targets", "source"):
        real = tmp / "bin" / name
        real.rename(tmp / "bin" / f"{name}.real")
        _exe(real, f'#!/bin/bash\necho "$*" >> {tmp / (name + ".args")}\n'
                   f'exec {tmp / "bin" / (name + ".real")} "$@"\n')


def test_the_sync_names_its_network_never_the_active_list(world):
    """C482 (2026-10-05): both helpers asked for the installation's ACTIVE list, so making a
    second network active on today's page failed every sync, for every network."""
    _recording(world)
    rc, out = run(world)
    assert rc == 0, out
    tmp = world["tmp"]
    targets = (tmp / "targets.args").read_text().splitlines()
    assert targets and all("--list Default" in a for a in targets), targets
    assert (tmp / "source.args").read_text().split() [2:4] == ["--list", "Default"]
    assert "device(s) of Default from" in out
    # A lab that boots another network says so, through the unit's environment.
    for f in ("targets.args", "source.args"):
        (tmp / f).unlink()
    env_run = subprocess.run(
        ["bash", SCRIPT, "--yes"], cwd=str(tmp), capture_output=True, text=True, timeout=120,
        env={**_env(tmp), "CLAB": "clab", "NMAS_URL": "http://127.0.0.1:9", "REF": "HEAD",
             "REPO": str(world["ox"]), "OUT": str(tmp / "out"), "STAGE": str(tmp / "stage"),
             "TARGETS": str(tmp / "bin" / "targets"), "SOURCE": str(tmp / "bin" / "source"),
             "CLAB_LIST": "Branch"})
    assert "--list Branch" in (tmp / "targets.args").read_text(), env_run.stdout
    assert "--list Branch" in (tmp / "source.args").read_text()


def test_a_source_naming_no_baseline_refuses_writing_nothing(world):
    src = world["tmp"] / "src" / "sources.tsv"
    src.write_text("\n".join(l for l in src.read_text().splitlines()
                             if not l.startswith("# baseline")) + "\n")
    rc, out = run(world)
    assert rc == 2 and "named no baseline" in out, out
    assert not (world["tmp"] / "labA" / "configs" / "r1.cfg").exists()
