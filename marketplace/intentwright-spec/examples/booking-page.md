# Example: from "a booking page" to an approved scope

This is a fictional, illustrative walkthrough written to explain the workflow.
It is not a customer conversation, a benchmark, or a claim that a website was
built or tested. The answers below are example user choices, not recommended
defaults for every booking site.

## Starting request

> I want a nice booking page for a private dog exercise field. People should
> be able to pick a time and book it. Keep it simple.

Several important choices are still hidden: does "book" confirm a reservation,
how is availability established, and who receives the request?

## First consequential question

**Assistant:** My understanding is that visitors need to request a private visit
to the field. Does choosing a time immediately confirm the booking, or does the
owner review and confirm each request?

**Example user answer:** The owner confirms it. A request must never imply the
slot is reserved. No online payments.

**Decision change:** D-001: manual confirmation. C-001: no promise of a reserved
slot. N-001: payments are excluded.

## Follow-up questions

**Assistant:** Where should requests go, and what happens if submission fails?

**Example user answer:** For the first version, use an email link that opens the
visitor's own mail app. Say explicitly that they still have to send the email.
Show a copyable address if that does not open. There is no backend yet.

**Assistant:** Which contact details, time choices, and visual references matter?

**Example user answer:** Ask for a name, email, preferred date and preferred
time. Nothing sensitive. Any future date can be requested; times are preferences,
not live availability. Use a calm, readable mobile layout. I will provide the
real field name, photos, rules and contact email before publication.

**Assistant:** What would make a technically working page still disappoint?

**Example user answer:** If it looks like a confirmed checkout, loses my input,
has tiny mobile controls, or quietly sends my details anywhere. The whole form
must work with a keyboard. You can choose the exact spacing and colors.

The interview now has meaningful behavior, exclusions, a bounded visual
delegation, and a publication dependency. The assistant checks the remaining
scope, privacy, and validation details and presents the complete revision.

## Illustrative specification

### Field visit request — IW-field-request-01 — v1

Status: READY_FOR_APPROVAL

### 1. Outcome and audience

Visitors can prepare an email requesting a private field visit from a readable
mobile page. The owner reviews and confirms requests separately. The convincing
demonstration fills the form, opens a correctly addressed email draft, and shows
the manual-send and manual-confirmation explanation.

### 2. Context and evidence

The owner described the workflow in this example. No existing website, mailbox,
schedule, or external system has been inspected. No backend is in scope.

### 3. Scope and non-goals

One page with field information, a request form, and contact fallback. Required:
responsive layout, keyboard access, validation, correct email draft, and honest
confirmation language. Excluded: payments, user accounts, calendar synchronization,
live availability, and automated reservation confirmation.

### 4. Requirements

| ID | Required behavior | Priority | Decision/source |
|---|---|---|---|
| REQ-001 | Collect name, email, preferred future date and preferred time. | Mandatory | D-002 |
| REQ-002 | Prepare an email draft to the owner's supplied address; the visitor sends it. | Mandatory | D-003 |
| REQ-003 | Explain that submission is a request and requires owner confirmation. | Mandatory | D-001, C-001 |
| REQ-004 | Offer a copyable contact address and preserve form values. | Mandatory | D-003, C-002 |
| REQ-005 | Support keyboard operation and readable narrow-screen layouts. | Mandatory | C-003 |
| REQ-006 | Avoid background submission, analytics and persistent storage of form entries. | Mandatory | C-004 |

### 5. Behavior and quality

Empty required fields, an invalid email, or a date on or before the visitor's current
local date produce adjacent text errors. The visitor can correct them without
losing other values. The preferred time is plain text; it does not represent
availability. Opening an email draft leaves the page and its form values intact.

The page states before the main button that the visitor must send the opened
email and await the owner's confirmation. There is no "booking confirmed" state.
If a mail app is unavailable, the address remains visible and copyable. The
interface does not claim it detected successful email delivery.

Visual rubric: readable body text, clear labels, visible keyboard focus, no
horizontal scrolling at a 360px viewport, and comfortably spaced touch controls.
Exact typography, colors and spacing are delegated within that rubric.

### 6. Dependencies, assumptions and failure behavior

The owner supplies the real public name, approved photos, rules and contact
email before publication. Development uses clearly labeled placeholders.
Publication remains pending until the owner checks the final content and email
destination. The visitor's mail app is external; a prepared draft does not prove
delivery. The owner and tester must exercise a real mail app before release.

### 7. Acceptance criteria

| ID | Covers | Pass condition | Evidence | Owner/environment |
|---|---|---|---|---|
| AC-001 | REQ-001 | Missing/invalid values show specific errors; valid future-date input passes. | Recorded form checks with fixed test dates. | Developer, test browser |
| AC-002 | REQ-002 | The draft uses the approved address and contains the entered values; special characters are encoded correctly. | Link inspection and real mail-app check. | Developer and owner |
| AC-003 | REQ-003 | Request/manual-send/manual-confirmation language appears before the action; no confirmation claim appears after it. | Page review and captured states. | Owner, preview |
| AC-004 | REQ-004 | Address can be copied without a mail app; opening a draft does not clear the form. | Manual fallback check. | Tester, browser |
| AC-005 | REQ-005 | Keyboard reaches all controls with visible focus; 360px and desktop views have no horizontal overflow. | Keyboard walkthrough and viewport captures. | Tester, browser |
| AC-006 | REQ-006 | Form interactions make no background request and write no persistent storage. | Network and storage inspection. | Developer, browser tools |

### 8. Authority and executor choices

The executor may implement and test the page in the agreed project workspace.
They may choose ordinary local implementation details and the visual choices
within E-001. Deploying publicly and sending any real email require separate
authorization. Form testing uses synthetic details.

### 9. Decision record

| ID | Record | Source |
|---|---|---|
| D-001 | The owner manually confirms requested times. | Example user choice |
| D-002 | Name, email, preferred date and time are the required fields. | Example user choice |
| D-003 | Use the visitor's mail app, with a visible contact fallback. | Example user choice |
| C-001 | No reserved-slot or confirmed-booking claim. | Example user constraint |
| C-002 | Preserve form input during validation and opening a draft. | Example user constraint |
| C-003 | Keyboard access and a readable mobile layout. | Example user constraint |
| C-004 | No background submission or persistent storage of entered data. | Example user constraint |
| N-001 | No payments, accounts, availability calendar or backend. | Example scope choice |
| E-001 | Executor chooses visual details within the stated review rubric. | Example delegation |

### 10. Definition of done

The page and its setup notes are delivered, mandatory checks have actual recorded
evidence, and the owner has reviewed the real content and email destination.
Missing real mail-app validation keeps the implementation pending. No check is
reported as passed solely because this specification names it.

### 11. Open items

None in the product decisions. Owner-supplied release content and real mail-app
validation are explicit execution dependencies, not completed work.

## Example approval and handoff

**Example user:** Approve IW-field-request-01 v1.

**Assistant:** IW-field-request-01 v1 is approved. The execution handoff names
that exact revision, states its authority and evidence requirements, and includes
the full specification above in the copied handoff. The executor now has clear
behavior, exclusions, delegated choices and a way to demonstrate completion.

The approval shown here belongs only to this fictional walkthrough. It does not
approve a real project or authorize publication.
