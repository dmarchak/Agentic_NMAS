"""Reader jobs (modules/reader_job.py): one module per outside service read.

A module here registers its reader when imported, and is listed in
`reader_job.DECLARED_MODULES`, or job health does not watch it.
"""
