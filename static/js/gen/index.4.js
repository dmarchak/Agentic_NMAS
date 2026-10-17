/* ------------------------------------------------------------------ */
/* Today's index page: the Git tab's load on switch (the AI family's    */
/* tabs left with D15; the drift panel at 7.8, its home Settings ›      */
/* Installation; the NetBox tab at 7.8, its home Source of truth ›      */
/* NetBox)                                                              */
/* ------------------------------------------------------------------ */

// Load tab data when tab becomes active for the first time
document.addEventListener('DOMContentLoaded', function () {
  const gitTabBtn        = document.getElementById('git-tab');

  // Unlike every other tab above, Git had no auto-load-on-switch wiring --
  // it only ever loaded via the explicit Refresh button, so re-opening the
  // tab after committing/saving elsewhere in the app showed stale data.
  if (gitTabBtn)        gitTabBtn.addEventListener('shown.bs.tab', loadGitTab);
});
