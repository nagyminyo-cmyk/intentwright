# Goal Forge package contract

This is the machine-facing contract for an approved Goal Forge specification. Follow it exactly; `scripts/goal_lifecycle.py` rejects drift.

## 1. Canonical workspace and layout

Use the canonical Git worktree root when the workspace is in Git. A non-Git workspace is identified by its resolved absolute path. Nested workspaces may not register independent Goal Forge roots.

```text
<workspace>/
├── .goal-forge-workspace.json
└── goals/
    ├── .goal-forge-root.json
    ├── .locks/
    ├── goal_pending/
    │   └── g_20260719T143522123Z_game_rebuild_map_7f3a9c2e/
    │       ├── goal_manifest.json
    │       ├── approved_semantic_spec.md
    │       ├── goal_spec_game_rebuild_map.md
    │       ├── execution_prompt.md
    │       ├── portable_handoff.md
    │       ├── package_seal.json
    │       ├── status.json
    │       ├── claim.json
    │       ├── claim_history/
    │       ├── evidence/
    │       ├── outcome.json
    │       └── outcome.md
    ├── goal_achieved/
    │   └── <terminal package including terminal_seal.json>
    └── goal_not_achieved/
        └── <terminal package including terminal_seal.json>
```

The goal root may use a different one-directory workspace-relative name, but one canonical workspace may register only one root. Do not adopt an unrelated existing `goals` directory.

Each goal has one exact package. Never put several spec files directly in `goal_pending`, reuse a goal ID, fuzzy-match a package, merge packages, or automatically delete terminal history.

## 2. Identity, scope, and publication

Goal IDs use:

```text
g_<UTC timestamp with milliseconds>_<sanitized snake slug>_<8 random hex>
```

Publication uses an unpublished `.staging_<goal-id>_<nonce>` directory and an atomic rename into `goal_pending/<goal-id>`. A staging directory is never executable.

The helper:

- sanitizes the slug to `[a-z0-9_]+` and caps it at 50 characters;
- validates all paths below the canonical workspace;
- rejects symlinks, junctions, reparse points, hardlinked files, NTFS alternate
  data streams, Windows path aliases, path escapes, overwrites, and merges;
- permits one registered Goal Forge root per canonical workspace;
- rejects nested workspace aliases and overlapping claimed scopes;
- stores normalized explicit project-relative write scopes; there is no implicit default;
- hashes the approved body and wrapped canonical spec;
- seals every immutable publication file in `package_seal.json`;
- atomically publishes only after the exact receipt and package validate.

Use `.` as a write scope only when the user deliberately grants whole-worktree authority. A scope lease protects filesystem overlap in one canonical workspace; it does not protect shared external services. Prefer separate Git worktrees for related parallel goals.

## 3. Exact approval receipt

The semantic body is UTF-8 without BOM, LF-only, and ends with exactly one LF. Before any package exists, run `approval-receipt` on a temporary candidate outside the goal root.

The receipt digest binds this canonical JSON information:

- schema and receipt kind;
- canonical workspace identity;
- exact goal-root directory;
- exact title and sanitized slug;
- numbered revision and interview ID;
- approved-body SHA-256;
- normalized write scopes;
- exact `retry_of` and `supersedes` values.

The exact approval phrase is:

```text
Approve spec v<N> receipt <64-character lowercase SHA-256>
```

The user must type that phrase verbatim after seeing the full body and receipt readback. Any change to any bound field creates a different receipt and requires a new numbered approval.

## 4. Canonical semantic body

The approved body begins at `## Executive outcome`; it excludes the title and generated Metadata section. It must contain exactly the following H2 headings, once each and in this order. Do not add other H2 headings.

### Exact topology

```markdown
## Executive outcome

State the concrete end state, audience, use scenario, value, and convincing demonstration in task-specific language.

## Context and verified current state

Separate verified workspace facts, user-provided facts, inferences, and facts still scheduled for verification.

## Users and scenarios

Define actors, golden paths, state transitions, and outcomes.

## Scope and deliverables

List mandatory deliverables separately from stretch work. Stretch work never blocks achievement.

## Explicit non-goals

Name plausible adjacent work and prohibited expansion.

## Decision coverage matrix

| Dimension | Status | Resolution or provenance |
|---|---|---|
| Outcome and audience | DECIDED | D-001 defines the target users, scenario, and demonstrated outcome. |
| Current state and context | DECIDED | D-002 records the verified starting state and evidence source. |
| Scope and priority | DECIDED | D-003 separates mandatory work from non-blocking stretch work. |
| Inputs, outputs, and interfaces | DECIDED | D-004 defines controlled inputs and observable outputs. |
| Golden path and state behavior | DECIDED | D-005 defines the normal flow and state transitions. |
| Quality and taste | DELEGATED | E-001 delegates minor presentation choices within an explicit rubric. |
| Constraints and dependencies | DECIDED | C-001 fixes the supported environment and dependency boundary. |
| Compatibility and preservation | DECIDED | C-002 identifies behavior and files that must remain unchanged. |
| Failure, recovery, and operations | DECIDED | D-006 specifies retryable, recoverable, and terminal behavior. |
| Security, privacy, and authority | DECIDED | C-003 limits authority and identifies untrusted inputs. |
| Performance and reliability | DECIDED | D-007 defines realistic workloads and evidence. |
| Accessibility, inclusion, and localization | NOT_APPLICABLE | NA-001 explains why no human-facing or locale-sensitive surface exists. |
| Validation and evidence | DECIDED | D-008 defines executable checks and retained evidence. |
| Execution authority | DECIDED | C-004 defines allowed writes and confirmation boundaries. |
| Completion and lifecycle | DECIDED | D-009 defines pending, achieved, blocked, and user-controlled retirement. |

Use exactly these 15 dimension names. Status is exactly `DECIDED`, `DELEGATED`, or `NOT_APPLICABLE`. Every row must contain a substantive explanation and cite at least one compatible ledger ID:

- `DECIDED`: `D`, `C`, `N`, or `A`
- `DELEGATED`: `E`
- `NOT_APPLICABLE`: `NA`

Do not manufacture a `NOT_APPLICABLE` row. If all dimensions apply, no `NA` coverage status is required.

## Domain routing

| Domain branch | Status | Rationale |
|---|---|---|
| Existing software or repository change | SELECTED | D-010 confirms this changes an existing repository. |
| Greenfield software, service, CLI, or API | NOT_APPLICABLE | NA-002 explains that no new standalone system is in scope. |
| UI, UX, visual design, or brand | NOT_APPLICABLE | NA-003 explains that no user interface changes. |
| Game | SELECTED | D-011 defines the required game-specific behavior. |
| Research, analysis, or recommendation | NOT_APPLICABLE | NA-004 explains that research is supporting work, not the deliverable. |
| Writing, documentation, or content | NOT_APPLICABLE | NA-005 explains that documentation is incidental only. |
| Automation, operations, or agent workflow | NOT_APPLICABLE | NA-006 explains that no recurring automation is delivered. |
| Security or defensive engineering | NOT_APPLICABLE | NA-007 explains that only ordinary safety boundaries apply. |
| Data, AI, or model-driven system | NOT_APPLICABLE | NA-008 explains that no model or data pipeline is used. |
| Product, business, or process | NOT_APPLICABLE | NA-009 explains that no business-process deliverable is requested. |
| Hardware, physical, or environment-dependent work | NOT_APPLICABLE | NA-010 explains that no special hardware is required. |
| Education, tutorial, or learning system | NOT_APPLICABLE | NA-011 explains that teaching is not the outcome. |
| General creative deliverable | NOT_APPLICABLE | NA-012 explains that creative work is contained within the selected game branch. |

Use exactly these 13 branch names and select at least one. Status is exactly `SELECTED` or `NOT_APPLICABLE`. A selected row cites `D` or `E`; a non-applicable row cites `NA`. Only include `NA` ledger rows that are genuinely needed.

## Requirements

| ID | Requirement | Rationale or provenance | Priority |
|---|---|---|---|
| REQ-001 | The implementation produces the exact observable primary behavior. | D-001 and D-005 define the required outcome and flow. | Mandatory |
| UX-001 | The implementation adds a bounded optional delight detail. | E-001 permits it when mandatory work already passes. | Stretch |

Use unique IDs beginning `REQ-`, `QUAL-`, `PRES-`, `CON-`, `SEC-`, `PERF-`, `UX-`, `OPS-`, `DATA-`, or `CONTENT-`. Priority is exactly `Mandatory` or `Stretch`.

## Execution workspace and write scope

State the worktree strategy, external shared resources, and why each scope is sufficient. Include this exact table:

| Path | Access | Rationale |
|---|---|---|
| src/game | WRITE | Contains the implementation files explicitly approved for this goal. |

Every `Path` must exactly match one normalized `--write-scope`; every access value is `WRITE`. The table and receipt scopes must be identical.

## Detailed behavior and quality bar

Specify workflows, state/event behavior, examples, anti-examples, visual or editorial direction, failure semantics, and bounded subjective rubrics.

## Data, interfaces, dependencies, and compatibility

Define inputs, outputs, contracts, ownership, dependency loss, migration, preservation, and regression behavior.

## Constraints and prohibited shortcuts

State hard limits, safety boundaries, environment requirements, confirmation gates, and technically passing shortcuts that violate intent.

## Executor freedoms

List only explicit delegations. For each, give boundaries, priorities, examples, anti-examples, and a review rubric. Cite its `E` ledger ID.

## Edge cases and failure semantics

Cover every relevant empty, loading, partial, invalid, unauthorized, offline, timeout, retry, interrupted, concurrent, corrupt, and unrecoverable state.

## Acceptance criteria

| ID | Priority | Role | Covers | Pass condition | Evidence method | Required evidence |
|---|---|---|---|---|---|---|
| AC-001 | Mandatory | DELIVERABLE | REQ-001 | A task-specific observable end-to-end condition holds in the approved environment. | command | Exact command output and a runtime artifact demonstrating the stated condition. |
| SAC-001 | Stretch | QUALITY | UX-001 | The optional detail satisfies the bounded review rubric without regressions. | review | A review artifact showing the optional detail and regression result. |

`AC-` means mandatory; `SAC-` means non-blocking stretch. Allowed roles are `DELIVERABLE`, `BEHAVIOR`, `QUALITY`, `SAFETY`, `VALIDATION`, and `OPERATIONS`. At least one mandatory criterion must be `DELIVERABLE`.

An `AC-` may cover only mandatory requirements. A `SAC-` may cover only stretch requirements. `Covers` contains only exact comma-separated requirement IDs. Every requirement must be mapped at its matching priority.

Evidence method is exactly `command`, `interaction`, `inspection`, `review`, or
`artifact`; each outcome record must use the approved method. Pass conditions
must be concrete. Required evidence must name evidence the environment can
actually produce. Mandatory criteria cannot be waived.

## Validation plan

Name exact feasible commands, environments, devices, accounts, people, review rubrics, and evidence locations. Mark unavailable real-world validation honestly and keep the goal pending until its approved terminal condition is reached.

## Risks and assumptions

Give every bounded assumption a verification point. Give every risk a mitigation and pending/terminal behavior.

## Decision ledger

| ID | Type | Status | Decision or rationale | Provenance |
|---|---|---|---|---|
| D-001 | D | CONFIRMED | The primary user completes the named scenario and observes the defined result. | User answer in interview round 1. |
| C-001 | C | CONFIRMED | Work remains within the approved environment and authority boundary. | User answer and verified workspace context. |
| A-001 | A | BOUNDED | A dependency is assumed available and will be checked before implementation. | Explicit user-approved assumption and verification plan. |
| O-001 | O | RESOLVED | The former open question was resolved with the selected behavior. | User answer in interview round 3. |
| T-001 | T | RESOLVED | The conflicting requirements were reconciled with the recorded priority. | User resolution in interview round 4. |
| R-001 | R | REJECTED | The alternative was rejected because it violates a named constraint. | User decision in interview round 4. |
| E-001 | E | DELEGATED | The executor may choose minor presentation details within the named rubric. | Explicit delegation in interview round 5. |
| NA-001 | NA | NOT_APPLICABLE | This dimension has no human-facing or locale-sensitive surface. | Verified scope and user confirmation. |

Use only these exact type/status pairs:

- `D`, `C`, `N` → `CONFIRMED`
- `A` → `BOUNDED`
- `O`, `T` → `RESOLVED`
- `R` → `REJECTED`
- `E` → `DELEGATED`
- `NA` → `NOT_APPLICABLE`

Include at least one `D`. Include only entry types that have real decisions or history; there is no requirement to invent `NA`, `A`, `O`, `T`, `R`, or `E` rows.

## Definition of done

Require the deliverables, every mandatory requirement, every mandatory `AC-`, criterion-specific evidence records, supporting artifact hashes, final verification, outcome report, correct package archival, terminal seal verification, and the matching external `/goal` transition.

## Goal lifecycle contract

| Lineage field | Goal ID or NONE |
|---|---|
| retry_of | NONE |
| supersedes | NONE |

The table must exactly equal the approved receipt and manifest. Use a concrete goal ID instead of `NONE` only for the applicable lineage field; the other remains `NONE`.

- Execute only this exact goal ID and spec.
- Verify the receipt, manifest, package seal, and spec hash before work.
- Claim before changing project files and retain the current token/epoch.
- Exclude sibling packages from content discovery and modification.
- Keep temporary or remediable problems pending.
- Write evidence, `outcome.json`, and `outcome.md` before archival.
- Follow the external-goal ordering for the chosen terminal reason.
- Move and terminal-seal the whole package.
- Never rerun a terminal package; recover only by exact ID.
```

Replace every instructional sentence and example row with task-specific content. The body must be at least 1,000 characters and contain no `TODO`, `TBD`, “to be decided,” placeholder text, unresolved double-brace template markers, or angle-bracket template markers.

## 5. Generated mechanical envelope

After exact approval, the helper prepends only:

```markdown
# Goal specification: <exact title>

## Metadata

- Goal ID: `<goal-id>`
- Slug: `<slug>`
- Revision: `<revision>`
- Interview ID: `<interview-id>`
- Approval: Approve spec v<N> receipt <receipt SHA-256>
- Approval receipt SHA-256: `<receipt SHA-256>`
- Approval-body SHA-256: `<body SHA-256 shown before approval>`
- Workspace-relative package: `<path>`
- Canonical spec: `<path>`
- Approved semantic body: `approved_semantic_spec.md`
- Approved semantic SHA-256: `<published body SHA-256>`
- Declared write scopes: `<normalized scopes>`
```

`approved_semantic_spec.md` remains byte-for-byte identical to the approved body. The canonical spec equals this envelope plus that exact body.

## 6. Manifest and publication seal

`goal_manifest.json` has exactly:

```json
{
  "schema_version": 1,
  "goal_id": "g_...",
  "slug": "game_rebuild_map",
  "title": "Rebuild the game map",
  "revision": 3,
  "interview_id": "gfi_...",
  "approval_record": "Approve spec v3 receipt <64 hex>",
  "approval_receipt_sha256": "<64 hex>",
  "approval_body_sha256": "<64 hex>",
  "created_at": "RFC3339 UTC",
  "published_at": "RFC3339 UTC",
  "project_relative_package": "goals/goal_pending/g_...",
  "approved_body_file": "approved_semantic_spec.md",
  "approved_body_sha256": "<64 hex>",
  "spec_file": "goal_spec_game_rebuild_map.md",
  "spec_sha256": "<64 hex>",
  "write_scopes": ["src/game"],
  "execution_prompt_file": "execution_prompt.md",
  "portable_handoff_file": "portable_handoff.md",
  "retry_of": null,
  "supersedes": null
}
```

The manifest is immutable after publication. `package_seal.json` hashes the manifest, approved body, canonical spec, execution prompt, and portable handoff.

## 7. Claims and concurrent goals

`claim` atomically creates `claim.json` containing the exact goal ID, UUID token, monotonically increasing epoch, real agent identity when available, host, timestamps, action, and frozen scopes.

Before any project write:

1. verify the exact package;
2. claim it;
3. retain the token and epoch;
4. heartbeat before and after material phases;
5. stop immediately if fenced.

On Windows, `Global\` named OS mutexes serialize registration, publication,
discard, claim, takeover, state, and archival mutations across logon sessions
without following filesystem lock paths. The registration mutex uses one
machine-stable identity so parent/child workspace registration is atomic.
Failure to acquire or access the global mutex fails closed. Other platforms use
hardened regular lock files. Publication and draft discard share the same
per-goal lock and revalidate the exact staging identity after acquisition. A
claim fails if any claimed pending package has an overlapping resolved scope.
Scope comparison is case-insensitive and rejects link, reparse, hardlink,
reserved-name, trailing-dot/space, and short-name alias risks.

Takeover requires the user to type:

```text
Authorize takeover of <goal-id> from claim epoch <current epoch>
```

The old claim is preserved in `claim_history`.

## 8. Structured evidence and outcome

A `pass` or `fail` criterion references one or more JSON files below `evidence/`. Each record has exactly:

```json
{
  "schema_version": 1,
  "goal_id": "g_...",
  "criterion_id": "AC-001",
  "claim_epoch": 1,
  "observed_at": "RFC3339 UTC",
  "required_evidence": "Exact text from the approved criterion cell.",
  "method": "command",
  "observation": "A specific statement of what was observed and why it supports the result.",
  "command": "python -m pytest",
  "exit_code": 0,
  "artifacts": [
    {
      "path": "evidence/ac-001-output.txt",
      "sha256": "<64 lowercase hex>",
      "description": "Complete output captured from the acceptance command."
    }
  ]
}
```

Allowed methods: `command`, `interaction`, `inspection`, `review`, `artifact`. Non-command methods set `command` and `exit_code` to `null`. Every record needs at least one distinct nonempty supporting artifact and its exact SHA-256. A passing command record must have exit code zero.

`outcome.json` has exactly:

```json
{
  "schema_version": 1,
  "goal_id": "g_...",
  "outcome": "achieved",
  "reason_code": "completed",
  "summary": "Meaningful terminal summary.",
  "criteria": [
    {
      "id": "AC-001",
      "result": "pass",
      "evidence_records": ["evidence/ac-001-record.json"]
    }
  ],
  "validation": ["Exact checks and review performed."],
  "known_limitations": [],
  "remaining_work": [],
  "blocked_threshold_evidence": null,
  "user_authorization": null,
  "replacement_goal_id": null,
  "external_goal_disposition": "complete_after_archive"
}
```

Results are exactly `pass`, `fail`, or `not_run`. `pass` and `fail` need records; `not_run` has none. Every mandatory `AC-` appears exactly once. Achievement requires all mandatory criteria to pass and no remaining work.

`outcome.md` is a substantive human-readable report and exactly identifies the goal ID, outcome, and reason code. Not-achieved reports contain `## Remaining work`.

## 9. Terminal reasons and external `/goal` ordering

Allowed terminal combinations:

| Outcome | Reason | External disposition | Ordering |
|---|---|---|---|
| `achieved` | `completed` | `complete_after_archive` | Archive and verify first; then mark persistent `/goal` complete. |
| `not_achieved` | `blocked` | `platform_blocked_before_archive` | The platform must first accept its threshold-gated blocked update; then archive with `--platform-blocked-confirmed`. |
| `not_achieved` | `cancelled_by_user` | `user_cancelled_or_replaced_before_archive` | User cancels/clears the persistent goal first, then authorizes exact archival. |
| `not_achieved` | `abandoned_by_user` | `user_cancelled_or_replaced_before_archive` | User abandons/clears the persistent goal first, then authorizes exact archival. |
| `not_achieved` | `superseded` | `user_cancelled_or_replaced_before_archive` | User replaces the persistent goal first; archive with exact replacement linkage. |

An unclaimed package that never started uses administrative disposition `not_started`.

Validation failure, apparent infeasibility, a turn ending, a budget limit, missing credentials, or a temporary outage is not a helper terminal reason. Keep the package pending, remediate, or obtain user-controlled cancellation/replacement. A blocker becomes terminal only when the platform’s own repeated-turn rule accepts `blocked`.

Exact user authorization phrases:

```text
Cancel goal <goal-id>
Abandon goal <goal-id>
Supersede goal <old-goal-id> with <replacement-goal-id>
```

For blocked reports, `blocked_threshold_evidence` contains exactly `rule`, `blocker`, `occurrences`, and `no_safe_progress_remaining`. Occurrences contain exact `turn`, `observed_at`, and `evidence`, use positive consecutive turn numbers and strictly increasing non-future UTC times, and number at least three. This is retained attestation; the platform transition is authoritative.

## 10. Terminal commit, seal, and recovery

Archival first records `archive_prepared`, then atomically moves the whole package. The helper precommits `terminal_seal.json` over the exact future final `status.json` and every other terminal file, then installs that final status.

This distinguishes safe crash recovery:

- `archive_prepared`, no terminal seal: safe to finish;
- `archive_prepared`, valid precommitted terminal seal: safe to install its exact final status;
- final status plus valid seal: terminal and immutable;
- final status with a missing or changed seal: corruption; never reseal automatically.

`terminal_seal.json` binds the goal ID, outcome, reason, embedded final status, timestamp, exact file set, and every SHA-256. A terminal package cannot be rerun.

## 11. Replacement and retry lineage

- `supersedes` points to one exact pending predecessor.
- A replacement may publish while its predecessor is claimed, but remains unclaimable until the predecessor is terminally superseded to that exact ID.
- Replacement chains are recursive: every earlier ancestor must already be terminally superseded in order.
- `retry_of` points to one exact finalized terminal not-achieved package.
- Retry lineage is recursively revalidated at initialization, immediately before publication, on every verification, and before claiming. Missing, duplicated, relocated, archive-prepared, or seal-corrupted ancestors block the operation.
- A package cannot use both fields.
- Lineage is part of the approved body, receipt, manifest, and terminal records.
- Lineage-bearing packages are non-portable unless the complete lifecycle history is present.

## 12. Lifecycle commands

These examples are copyable as single Windows PowerShell lines. They require
Python 3.10 or newer. On macOS or Linux, replace the `python` launcher with
`python3`. Repeat `--write-scope` when needed and add the exact approved lineage
flag when applicable.

Pre-approval:

```powershell
python "<skill>/scripts/goal_lifecycle.py" approval-receipt --file "<candidate>" --workspace "<workspace>" --goals-dir "goals" --title "<title>" --slug "<slug>" --revision 3 --interview-id "<gfi_YYYYMMDDTHHMMSSmmmZ_slug_4hex>" --write-scope "src/game"
```

After the exact approval phrase:

```powershell
python "<skill>/scripts/goal_lifecycle.py" init --workspace "<workspace>" --goals-dir "goals" --title "<title>" --slug "<slug>" --revision 3 --interview-id "<gfi_YYYYMMDDTHHMMSSmmmZ_slug_4hex>" --approval-record "Approve spec v3 receipt <receipt hash>" --approval-receipt-sha256 "<receipt hash>" --approved-body-sha256 "<body hash>" --write-scope "src/game"
python "<skill>/scripts/goal_lifecycle.py" publish --package "<staging package>"
python "<skill>/scripts/goal_lifecycle.py" verify --package "<pending package>"
python "<skill>/scripts/goal_lifecycle.py" claim --package "<pending package>"
python "<skill>/scripts/goal_lifecycle.py" heartbeat --package "<package>" --claim-token "<token>" --action "<phase>"
python "<skill>/scripts/goal_lifecycle.py" state --package "<package>" --claim-token "<token>" --state validating --action "Running final acceptance pass"
```

Achievement:

```powershell
python "<skill>/scripts/goal_lifecycle.py" archive --package "<package>" --claim-token "<token>" --outcome achieved --reason-code completed --external-goal-disposition complete_after_archive
```

Blocked, only after the platform accepted `blocked`:

```powershell
python "<skill>/scripts/goal_lifecycle.py" archive --package "<package>" --claim-token "<token>" --outcome not_achieved --reason-code blocked --platform-blocked-confirmed --external-goal-disposition platform_blocked_before_archive
```

Claimed cancellation or abandonment, after the user clears the persistent goal
and the outcome JSON contains the same exact authorization:

```powershell
python "<skill>/scripts/goal_lifecycle.py" archive --package "<package>" --claim-token "<token>" --outcome not_achieved --reason-code cancelled_by_user --authorized-reason "Cancel goal <goal-id>" --external-goal-disposition user_cancelled_or_replaced_before_archive
python "<skill>/scripts/goal_lifecycle.py" archive --package "<package>" --claim-token "<token>" --outcome not_achieved --reason-code abandoned_by_user --authorized-reason "Abandon goal <goal-id>" --external-goal-disposition user_cancelled_or_replaced_before_archive
```

Claimed supersession, after the external replacement and with matching outcome
JSON linkage:

```powershell
python "<skill>/scripts/goal_lifecycle.py" archive --package "<old package>" --claim-token "<token>" --outcome not_achieved --reason-code superseded --authorized-reason "Supersede goal <old-goal-id> with <replacement-goal-id>" --replacement-goal-id "<replacement-goal-id>" --external-goal-disposition user_cancelled_or_replaced_before_archive
```

Takeover requires the exact current epoch:

```powershell
python "<skill>/scripts/goal_lifecycle.py" takeover --package "<package>" --authorized-reason "Authorize takeover of <goal-id> from claim epoch <N>" --identity "<real new executor identity>"
```

Administrative retirement applies only to a clean unclaimed package:

```powershell
python "<skill>/scripts/goal_lifecycle.py" retire --package "<package>" --reason-code cancelled_by_user --authorized-reason "Cancel goal <goal-id>"
python "<skill>/scripts/goal_lifecycle.py" retire --package "<package>" --reason-code abandoned_by_user --authorized-reason "Abandon goal <goal-id>"
python "<skill>/scripts/goal_lifecycle.py" retire --package "<old package>" --reason-code superseded --authorized-reason "Supersede goal <old-goal-id> with <replacement-goal-id>" --replacement-goal-id "<replacement-goal-id>"
```

An exact unpublished draft may be permanently removed only after inspection:

```powershell
python "<skill>/scripts/goal_lifecycle.py" discard-staging --package "<exact .staging package>" --confirmation "Discard unpublished staging <goal-id>"
```

Publication and discard use the same per-goal lifecycle lock. If another
operation owns that lock, discard fails without deleting anything; after
acquisition it revalidates the canonical staging path, manifest identity, draft
state, and absence of publication or execution records before removal.

Remove the separate temporary candidate only after the published package
verifies, and report that cleanup. If publication is abandoned, retain the
candidate until the exact staging draft is either recovered or explicitly
discarded.

Exact recovery:

```powershell
python "<skill>/scripts/goal_lifecycle.py" recover --workspace "<workspace>" --goals-dir "goals" --goal-id "<exact goal ID>" --claim-token "<token when required>"
```

Portable restoration is deliberately narrow:

```powershell
python "<local skill>/scripts/goal_lifecycle.py" import-portable --workspace "<exact same receipt-bound absolute workspace path>" --goals-dir "goals" --file "<portable_handoff.md>"
```

`import-portable` rejects a different absolute workspace identity, lineage-bearing
handoffs, terminal-source handoffs, and goal-ID collisions. A different path or
repository requires a new readback, receipt, and user approval.
