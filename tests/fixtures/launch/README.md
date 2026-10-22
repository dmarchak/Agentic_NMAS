# Launch-script fixtures

`c8000v-launch-adopted.py` is the C8000v launch script the probes bind over
`/launch.py`: vrnetlab's own `launch.py` for `vrnetlab/cisco_c8000v:17.06.01a`
(from hellt/vrnetlab, MIT licence) with this project's stage-C user-skip
applied by `docs/bootstrap-probe/patches/patch-skip-injected-user.py`.

Copied byte for byte from the lab host on 2026-09-26, where all three probe
copies (`labs/bootstrap-probe`, `labs/dhcp-a`, `labs/r6`) were identical:

    sha256 e483dd2475b505bda4b2a95e5e26468971f05f856394f49849917e4cb15a8484

It is here so a patcher can be tested against the REAL text rather than a
hand-built stand-in: a fixture that contains only the anchors a patcher
looks for passes whether or not the real script has them.
`tests/test_configless_patch.py` pins the hash, so a changed fixture is
a decision rather than an accident.

`vios-launch.py` is vrnetlab's own, unmodified `launch.py` for
`vrnetlab/cisco_vios:L2-20180619` (hellt/vrnetlab, MIT licence), the image s1 to s4 run.
Copied byte for byte from s1's running container on 2026-10-22 (`docker exec ... cat
/launch.py`; nothing is bound over it there):

    sha256 794788bcada997dac7aac239d86d1867f165482ae30b03376463b89418c8e93d

`docs/bootstrap-probe/patches/patch-vios-configless.py` (C1349, Lab 9's s5) is tested against
it by `tests/test_vios_configless_patch.py`, which pins the hash.
