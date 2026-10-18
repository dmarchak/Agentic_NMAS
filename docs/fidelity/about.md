# Fidelity: Help › About this installation

The About page as built, compared region by region with its two boards from the operator's own
screenshot (C650's step), taken in the P7-27 walk (2026-10-18, step 12): `/v2/help/about` at
desktop width (1280 CSS pixels, light theme), scrolled to the top, nothing open, the whole page,
running c60a7a54 with the host three commits behind what was pushed (the real state during the
walk, so the Pushed row shows "behind"). Read beside the agent's shots of the boards
(`about-board-BrandAbout-1440`, `about-board-HelpAbout-1440`) and the page shots of 2026-10-15
(`about-page-1440`, `about-page-390-first`) for the phone layout, which the walk did not take;
the footer's words were corrected after the walk (below) and are compared from the template and
tests/test_update_button.py's `test_about_says_when_a_host_behind_becomes_a_row`.

Boards: on the second canvas ("NMAS v2 mockups"): `BrandAbout.dc.html` (board B, the product
card, NSOT_STAGE7_PLAN 19, approved 2026-10-05); and `HelpAbout.dc.html` (NSOT_STAGE7_PLAN 1g,
mockup version 7, "Help > About carries the version", signed off 2026-09-30: the installation
card and a "When something is wrong" card). Board B is the later for the product card; the
earlier board for the rest.
Shots: the operator's screenshot (`<home>/Documents/nmas-reports/P7-27-2026-10-18/about.png`,
full page at 1280); the boards at 1440; the page at 390 from 2026-10-15.
Compared 2026-10-18.
Templates compared: templates/v2/about.html, templates/v2/_installation.html, templates/v2/_helpnav.html
Templates sha256: `10d73045f9fb1a805c1b99aadbd11c04ece1e82d986b6304f3139c097455ffd8`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The sidebar | every section, Help highlighted at the foot (HelpAbout) | the same, the product's name and line at its head | **same** |
| The top bar | Network, Go to device, Integrations, Live, Assistant, the person | Network, Go to device, Update available, Integrations, Live, the theme switch, the person; no Assistant | **deviation** (log: About: the top bar has no Assistant and carries Update available and the theme switch) |
| The heading | "Help", "The manual, and what this installation is running." | the same, with its (i) | **same** |
| The help navigation | a short list, About current | every page of the manual by section (Getting started, How it works, Concepts, Screens, About), "About this installation" current | **deviation** (log: About: the help navigation lists every page of the manual) |
| The product card | the square icon, the name, its line, "Running <sha> (a release number comes with Stage 10)", the licence words, the third-party link, the origin line (board B) | the same, word for word | **same** |
| Running commit | the short sha, loaded when and by which process | the same, with the commit's subject | **same** |
| CI verdict | a verdict chip and the run | "verified" and "CI passed for <sha>: run #<n>, <link>", judged when | **same** |
| Pushed | "the running commit is the tip of origin/main" | a state chip ("behind") and its sentence, with Check again, Update… and its (i) beside it | **deviation** (log: About: Pushed carries Check again and Update… beside its state) |
| Version, Last update, Checkout | a Version row ("Stage 7.3, the GUI redesign in progress") | no Version row (the product card carries the running commit); Last update (the last update's outcome, who, when, the Update page) and Checkout ("the same commit") rows | **deviation** (log: About: Last update and Checkout rows in place of Version) |
| Who you are | the person, verified by Cloudflare Access | the same | **same** |
| When something is wrong | a card listing Needs attention's rows (a host 2 commits behind as a Warning, a commit not CI-verified as Danger) | no such card: the footer says what is a row and when (a release on offer is information, the operator, 2026-10-02); the operator's walk found the footer's words claimed a host behind was always a row, corrected 2026-10-18 | **deviation** (log: About: no card of Needs attention's rows; the footer says when a release is one) |
| The footer | "Quiet when fine: the top bar no longer carries the commit or its verdict." | "Quiet when fine: the top bar carries no commit.", then when a release becomes a row, its hours read from the code | **same** |
| Phone width | the boards draw none | one column, the help navigation above the cards (2026-10-15's shot) | **same** |
| Theme | light | light; dark by the theme switch | **same** |
