# Worked example: a weekly task view

This is an illustrative, invented interview. It shows the sort of decisions and
readback Intentwright aims to produce. It is not a recorded user session,
published package, signed approval, benchmark or proof that an implementation
passed acceptance. The full machine-valid specification has additional contract
sections; the excerpts below are not an input to the lifecycle helper.

## Starting request

> Add a polished weekly view to my task app. I want it to feel useful instead of
> becoming another empty calendar.

The request leaves the core behavior open: what counts as a week, which tasks
appear, where unscheduled or overdue work goes, whether tasks can be moved, and
what existing behavior must be preserved.

## A few consequential interview branches

The interviewer first checks the existing repository read-only. It establishes
that this is an existing local task app and that its list view and task storage
must be preserved.

**Interviewer:** When you open the weekly view, should it show the current week,
or the next seven days starting today?

**Owner:** The calendar week, Monday through Sunday, using my local date. Add
previous and next week buttons and a way to return to this week.

**Interviewer:** Where should overdue tasks and tasks without a due date appear?

**Owner:** Overdue incomplete tasks go in a clearly labeled panel. Tasks with no
date stay in the existing list view; do not invent a date for them.

**Interviewer:** Does dragging a task need to change its date in this version?

**Owner:** No dragging yet. A task opens the existing editor. Date changes there
update both views after saving.

**Interviewer:** What would make the result feel useful in a nearly empty week?

**Owner:** Every day remains visible. Empty days say “No tasks”. Show a task's
title, completion state and project color. Keep today's column recognizable
without relying only on color.

Later questions resolve narrow-screen behavior, keyboard operation, date
boundaries, navigation persistence, validation and the intended write scope.
The skill also challenges the word “polished” with examples and a review rubric.

## Ledger excerpt

| ID | Type | Status | Decision |
| --- | --- | --- | --- |
| D1 | Decision | CONFIRMED | Calendar weeks start Monday and end Sunday using the browser's local date. |
| D2 | Decision | CONFIRMED | Incomplete overdue tasks appear in a labeled panel. Unscheduled tasks remain in the list view. |
| C1 | Constraint | CONFIRMED | Preserve current storage format, list view and existing editor behavior. |
| N1 | Non-goal | CONFIRMED | Dragging, recurrence, reminders, accounts and cloud synchronization are out of scope. |
| E1 | Delegation | DELEGATED | The executor may choose spacing and typography within the existing design system, with readable labels and no color-only state. |

The complete approvable ledger cannot contain unresolved decisions. Every
delegation needs boundaries and a review rubric.

## Acceptance excerpt

| Criterion | Required demonstration |
| --- | --- |
| Week navigation is correct across month and year boundaries. | Automated date tests cover a Monday-start week, a month transition and a December/January transition. |
| Both views reflect an edited task date. | A browser interaction creates a dated task, edits its date through the existing editor, and verifies its updated position in both views. |
| Empty and overdue states match the agreed behavior. | An inspected fixture includes an empty week, an unscheduled task, an overdue incomplete task and a completed task. |
| Narrow screens remain usable. | Browser checks at 390 and 1440 CSS pixels verify readable content, navigation and access to every day. |
| Existing task behavior is preserved. | The existing task suite passes and the owner reviews the preserved list/editor behavior. |

These are example criteria. Before approval, Intentwright must confirm the
actual commands, fixtures, manual-check owner and available environment for the
particular repository. An unavailable check needs explicit pending and terminal
behavior rather than an invented pass.

## Approval and execution

Intentwright reads back the complete numbered specification revision and its
execution envelope, including the exact workspace and write scopes. The helper
computes the approval receipt. The owner uses the exact approval phrase shown
for that revision after checking the readback.

Only then does the helper publish a package under `goals/goal_pending`. The
returned `/goal` command identifies its exact package ID and path. In a fresh
Codex session, the executor verifies that package, claims its permitted scope,
implements the weekly view and records criterion-specific evidence.

The helper checks the evidence structure, hashes and lifecycle state. It cannot
independently establish that a screenshot or human review proves a subjective
quality criterion; the executor and named reviewer remain responsible for those
judgments. Completed work archives to `goal_achieved` only when its required
criteria are satisfied. Other terminal outcomes preserve the remaining work
under `goal_not_achieved`.

For actual automated proof of publication, claims, evidence, archival and
recovery mechanics, run `python -m unittest discover -s tests -v` from a source
checkout. The example above is documentation of the intended workflow.
