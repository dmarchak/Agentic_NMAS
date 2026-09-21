"""nsot/sections.py

Indentation → ancestry. One algorithm, no normalisation of its own.

IOS nests by indentation, and three different places in this codebase needed to
know a line's ancestors. Two of them computed it; one did not, and that one was
the *measurement*:

* ``deploy._section_chains()`` — correct, and its docstring names the exact
  hazard: "sending ``neighbor … activate`` after only ``router bgp 65001``
  applies it to the wrong address family, silently and successfully."
* ``parsers.base.split_blocks()`` — deliberately one level. Parsers want a
  block and its body; that is the right shape for them.
* ``roundtrip._sections()`` — built on ``split_blocks``, so it compared a
  two-level block as one level. Every line was present, so it scored 100%
  while the render hoisted BGP networks out of their address-families.

The deploy path could therefore compute the right answer and the report could
simultaneously say there was nothing to compute.

This module holds the algorithm alone. **Normalisation stays with the caller**:
the filters in :mod:`modules.nsot.normalize` are four different jobs, and
folding one of them in here would make this the fifth place that decides which
lines count.
"""


def chains(lines, norm=None) -> list:
    """``[(line, (ancestors, outermost first))]`` for already-filtered *lines*.

    Ancestry is read from the **raw** line's indentation, so *norm* — which
    typically strips — is applied only to the stored values, never before the
    depth is measured.
    """
    norm = norm or (lambda text: text)
    out, stack = [], []
    for raw in lines:
        line = (raw or "").rstrip()
        if not line.strip() or line.strip() in ("!", "end"):
            continue
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        value = norm(line)
        out.append((value, tuple(entry[1] for entry in stack)))
        stack.append((indent, value))
    return out


#: How a path reads in a diff. Chosen to be unmistakable in a report: a bare
#: "address-family ipv4" says nothing about which router it belongs to.
PATH_SEPARATOR = " > "


def path_of(chain) -> str:
    """The container path a line sits under. ``""`` means top level."""
    return PATH_SEPARATOR.join(chain)
