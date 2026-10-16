# Reload fixtures

`r6_archive_config_differences.txt`: r6, W1 2026-10-16, the operator's capture. The output of
`show archive config differences nvram:startup-config system:running-config` on r6 (a C8000v,
IOS-XE 17.6), read through Mercury's Show commands at about 00:51 UTC, after a successful
Persist, when Reload's "running against startup" gate still failed with "4 line(s) differ".
Read masked through `redact.redact_text` (nothing was masked: the lines are certificate
storage, and certificates are public). One edit: the page's own words above the device's
output (the run's heading and buttons) are left out. Used by
`tests/test_reload_certificate_storage.py`.
