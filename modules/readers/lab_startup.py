"""Does each device's lab startup file hold what its committed golden would
produce? A reader job (the operator, 2026-10-01): the comparison is
``modules/lab_startup.py``'s; this keeps its last answer for Needs attention.

A redeploy boots the lab's file, not the golden, so a difference is a device
that would come back other than as recorded. One SSH read per lab directory
per cycle, never per device.
"""

from modules import reader_job

#: The clab sync rewrites the files every 30 minutes (its timer), and a capture
#: moves the golden when a person runs one: a read every 10 minutes sees either
#: within a third of the sync's own period, at one SSH command per lab.
INTERVAL_SECONDS = 600


def read() -> dict:
    from modules.lab_startup import check
    return check()


READER = reader_job.register(reader_job.Reader(
    name="lab-startup",
    what="whether each device's lab startup file holds what its committed golden would produce",
    endpoints=("the lab host, over SSH (clab_host): one read of each lab's configs directory",
               "this host: each list's committed goldens at HEAD"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the clab sync rewrites the files every 30 minutes; a read every 10 sees a "
                    "new file or a new golden within a third of that, one SSH command per lab"),
    read=read,
    invalidates=("lab_startup",),
    remedy="Read the error above: it names what the lab host or the repository answered",
    window="the lab's startup files and the goldens at the read",
))
