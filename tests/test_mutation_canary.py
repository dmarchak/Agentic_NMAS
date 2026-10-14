"""The nightly mutation run's canary tests (tests/mutation_canary.py says why). Each pins its
function so that every mutant of it fails a test: every boundary, both operands, the result.
`in_child` is reached ONLY through a child process, by its dotted name, as Mercury's scripts
reach the modules they run."""
import os
import subprocess
import sys

import pytest

from tests import mutation_canary as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("a, b, want", [(2, 3, 5), (0, 0, 0), (7, 0, 7), (0, 7, 7),
                                        (-1, 3, -1), (3, -1, -1)])
def test_in_process(a, b, want):
    assert C.in_process(a, b) == want


def _in_child(a, b):
    got = subprocess.run(
        [sys.executable, "-c",
         "import sys; from tests.mutation_canary import in_child; "
         "print(in_child(int(sys.argv[1]), int(sys.argv[2])))", str(a), str(b)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr
    return int(got.stdout.strip())


def test_in_child():
    assert [_in_child(a, b) for a, b in [(2, 3), (4, 0)]] == [23, 40]
