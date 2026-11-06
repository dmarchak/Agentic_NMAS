"""Jobs: saved, rerunnable scripts that reach the world only through the SDK (the SDN platform
design, rev. 4, section 11, I-1). Phase P1 publishes the contracts as stubs: `base` (the job's
declaration, its inputs and its scope), `sdk` (the context's handles, as signatures; the change
plan records), `lifecycle` (Draft, Published, Retired and the folder's content hash, shared
with controller apps) and `testing` (the context a unit test runs a job in).
docs/DEVELOPING_JOBS_AND_APPS.md is the guide."""

from modules.jobs.base import (ContractError, DeviceRef, HostRef, Job, JobInputs, JobMeta,
                               Scope, ScopeError)
from modules.jobs.sdk import ChangePlan, ChangeRefused, Context, NotBuilt

__all__ = ["ChangePlan", "ChangeRefused", "Context", "ContractError", "DeviceRef", "HostRef",
           "Job", "JobInputs", "JobMeta", "NotBuilt", "Scope", "ScopeError"]
