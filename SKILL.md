---
name: goal-forge
description: Exhaustively interview the user before a persistent /goal, turn rough intent into an explicitly approved execution-ready specification, publish an isolated concurrency-coordinated goal package, and generate a pasteable new-session /goal handoff with verified terminal archival. Use when the user invokes $goal-forge, asks to be grilled before building, wants a highly detailed plan/specification for an ambitious task, or answers, corrects, resumes, revises, or approves an active Goal Forge interview. Do not use for ordinary quick questions, simple well-scoped changes, or execution of an already approved goal package.
---

# Goal Forge

Turn fuzzy intent into a frozen, testable execution contract before implementation. Optimize for consequential clarity, not a theatrical question count.

## Non-negotiable rules

1. Stay in discovery and specification mode. Do not implement the requested project, set `/goal`, deploy, publish externally, or change project files during the interview.
2. Inspect safely discoverable workspace facts read-only before asking the user for them.
3. Resolve every material decision through an explicit user choice, a verified fact, or conscious delegation with boundaries and a quality rubric.
4. Never silently convert an assumption into a requirement, choose between contradictory answers, or operationalize a subjective adjective without showing the interpretation.
5. Ask foundational branching questions individually. Group only independent leaf questions, normally three to five at a time.
6. Continue until the readiness gate passes. Do not stop at a fixed question count, and do not probe details that cannot affect the outcome.
7. Do not create a goal package before the user approves the exact numbered revision and its complete approval receipt.
8. Treat a published specification as immutable. Material change requires a separately approved replacement; never edit an executing specification in place.
9. Use `scripts/goal_lifecycle.py` for approval receipts, publication, claims, recovery, and archival. Do not improvise weaker file moves.
10. Address goals only by exact immutable goal ID and exact package path. Never select “latest” or “most similar.”
11. The conversational interviewer must not open sibling goal specifications. The lifecycle helper may machine-verify sibling lifecycle metadata, sealed integrity, and explicitly linked lineage.
12. Use a Python 3.10-or-newer launcher for lifecycle commands: `python` on Windows and normally `python3` on macOS or Linux. In instructions below, `<python>` means that platform-appropriate launcher.
13. Treat the goal root as potentially sensitive local operational state. It may contain full specifications, evidence, host or agent identity, and live or historical claim tokens. Warn the user before publication and do not commit or publish it unless they deliberately approve that disclosure.

## Start or resume

1. Read [references/interview-playbook.md](references/interview-playbook.md) completely.
2. Resolve the canonical workspace. In a Git worktree, use its top-level root. Goal Forge refuses nested workspace aliases that could bypass shared leases.
3. Select one project-relative goal-root directory, normally `goals`. If that path already contains unrelated data, obtain another one-directory name. One canonical workspace may register only one Goal Forge root.
4. Inspect the target repository's ignore rules read-only. State whether the selected goal root and `.goal-forge-workspace.json` are ignored, and recommend ignoring both unless the user consciously wants lifecycle data in version control. Never edit ignore rules without authorization.
5. Assign an interview ID using exactly
   `gfi_YYYYMMDDTHHMMSSmmmZ_<lowercase_snake_slug>_<4 lowercase hex>`, for
   example `gfi_20260719T143522123Z_game_rebuild_map_7f3a`. Show it in the first
   response and every full readback. It is not a goal ID and creates no files.
6. Keep one active interview per thread. Park or switch by exact interview ID; never merge decision ledgers.
7. Inspect relevant `AGENTS.md`, README files, manifests, documentation, selected source, Git status, and goal-root metadata read-only. Exclude sibling goal packages from content discovery.
8. State your current understanding in one paragraph and ask the highest-leverage unresolved question.

When there is no repository yet, establish the artifact, target environment, canonical future workspace, and package location before deeper design.

## Run the adaptive interview

Follow the state machine and applicable domain branches in the playbook.

- Anchor the exact outcome, audience, use scenario, convincing demonstration, hard constraints, preservation rules, authority boundaries, and non-goals.
- Classify every universal dimension as `DECIDED`, `DELEGATED`, `OPEN`, or `NOT_APPLICABLE`.
- Prioritize by impact, uncertainty, irreversibility, and downstream dependency.
- Challenge words such as “polished,” “fast,” “secure,” “complete,” “production-ready,” “smart,” “intuitive,” “everything,” and “etc.”
- Ask for examples, anti-examples, state behavior, edge cases, failure behavior, trade-offs, and feasible evidence.
- Route into every applicable domain branch. Mixed work often needs several.
- Label recommendations and expose their material trade-offs.
- Delegate only consciously chosen decisions. Record boundaries, priorities, examples, anti-examples, and the review rubric.
- Prefer observable behavior or a bounded review rubric over invented numerical precision.

Maintain this typed ledger:

- `D`: confirmed decision, status `CONFIRMED`
- `C`: hard constraint, status `CONFIRMED`
- `N`: explicit non-goal, status `CONFIRMED`
- `A`: bounded assumption with verification plan, status `BOUNDED`
- `O`: resolved former open question, status `RESOLVED`
- `T`: resolved former contradiction, status `RESOLVED`
- `R`: rejected or superseded option with rationale, status `REJECTED`
- `E`: delegated executor choice with boundaries and rubric, status `DELEGATED`
- `NA`: proven non-applicability with rationale, status `NOT_APPLICABLE`

During questioning, an item may be open. An approvable ledger may not contain unresolved items or invented `NA` rows. After each round, show only meaningful ledger changes and the next question or small batch.

## Apply the readiness gate

Before drafting, read [references/goal-package-contract.md](references/goal-package-contract.md) completely. Use its exact semantic-body headings and machine-validated tables.

Run five adversarial reviews:

1. Skeptical owner: could an executor technically comply and still disappoint?
2. Implementer: what consequential product decision would still need invention?
3. QA reviewer: what requirement cannot be honestly demonstrated?
4. Operator: what dependency, interruption, concurrency, recovery, or lifecycle state is undefined?
5. Adversary, when relevant: what authority, untrusted input, abuse path, or trust boundary is unsafe?

Continue interviewing while any material open question, unresolved contradiction, unbounded delegation, unavailable mandatory validation, hidden authority question, or ambiguous terminal behavior remains. Temporarily unavailable validation is acceptable only when its owner, environment, timing, pending behavior, and terminal condition are explicit.

## Produce and approve an exact revision

1. Draft the complete semantic body with the exact contract topology.
2. Choose the exact title, sanitized goal slug, revision, interview ID, canonical workspace, goal root, write scopes, and lineage (`retry_of`, `supersedes`, or neither).
3. Write the candidate body to a temporary file outside the goal root as UTF-8 without BOM, LF-only, with exactly one final LF. This temporary draft is not a package.
4. Run `approval-receipt` with the candidate file and every envelope field:

   ```text
   <python> "<skill>/scripts/goal_lifecycle.py" approval-receipt --file "<candidate>" --workspace "<canonical workspace>" --goals-dir "<goal root>" --title "<exact title>" --slug "<slug>" --revision <N> --interview-id "<gfi_...>" --write-scope "<scope>"
   ```

   Repeat `--write-scope` for every scope. Pass the exact `--retry-of` or `--supersedes` ID when applicable.

5. Present the complete semantic body and a compact receipt readback containing the exact workspace identity, goal root, title, slug, revision, interview ID, body SHA-256, normalized scopes, lineage, receipt SHA-256, and emitted approval phrase.
6. State that no material unresolved items remain, or enumerate consciously delegated items.
7. Ask the user to type the emitted phrase verbatim, for example:

   `Approve spec v3 receipt <64-character SHA-256>`

8. Anything else—including “looks good,” silence, a typo, or approval plus a change request—is not approval.
9. Any material change to body or envelope increments the revision, regenerates the receipt, and requires a new exact phrase.

The receipt cryptographically binds the approved body to the workspace, goal root, title, slug, revision, interview, write scopes, and lineage. Do not create a package until the exact phrase is present in the conversation.

## Publish the approved package

After approval, re-read the contract’s publication and lifecycle sections.

1. Run `init` with the exact same envelope fields, `--approved-body-sha256`, `--approval-receipt-sha256`, and exact `--approval-record`.
2. Write the approved semantic body byte-for-byte to the returned `approved_body_path`.
3. Run `publish`. It validates the exact body, scope table, lineage table, coverage, ledger, requirements, acceptance mapping, and receipt; adds only the mechanical envelope; creates both handoffs; seals publication files; and atomically moves the package into `<goal-root>/goal_pending/<goal-id>`.
4. Run `verify` on the exact published package.
5. Remove the exact temporary candidate only after verified publication; its
   approved bytes now exist in the sealed package. Report that this temporary
   file was removed and is recoverable only from the package.
6. Report the goal ID, pending package path, specifically named `goal_spec_<slug>.md`, both hashes, portable handoff path, and exact generated `/goal`.
7. Do not execute the new goal in the interview session. The user pastes the generated command into a new session with access to the same canonical workspace.

## Multiple goals and replacements

- Every goal has its own uniquely named directory under `goal_pending`; several agents may run non-overlapping goals concurrently.
- Claims are exclusive. The helper refuses overlapping declared write scopes, including case variants and resolved path aliases. On Windows, `Global\` named mutexes serialize lifecycle mutations across logon sessions. Prefer separate Git worktrees when goals may touch related files.
- A replacement may be approved and published while its predecessor is claimed, but it cannot be claimed until the predecessor is terminally archived as `superseded` with the exact replacement ID.
- For a replacement chain, every ancestor must already be terminally superseded in order. Do not skip a still-pending ancestor.
- Before an unclaimed package is retired, require the exact user phrase emitted by the contract, such as `Supersede goal <old> with <new>`, `Cancel goal <id>`, or `Abandon goal <id>`.
- If `init` created a draft that will never be published, inspect its exact path,
  then use `discard-staging` only with
  `Discard unpublished staging <goal-id>`. Report that the unpublished draft
  was permanently removed. Publication and discard share the same per-goal
  lock and revalidate the staging identity after acquisition. Never delete a
  published or partially published package this way.
- A takeover requires the exact phrase `Authorize takeover of <goal-id> from claim epoch <N>`.
- `retry_of` must identify one exact finalized terminal not-achieved package. The helper recursively revalidates that package and every retry ancestor, including publication and terminal seals, at initialization, immediately before publication, on verification, and before claiming. `supersedes` identifies one exact pending predecessor. Never combine them.
- Lineage-bearing handoffs are not portable without the full lifecycle history.

## Honest terminal lifecycle

- Temporary pauses, failed checks, apparent infeasibility, rate limits, missing credentials, and retryable outages stay in `goal_pending`.
- Achievement requires every mandatory `AC-` to pass with criterion-specific structured evidence bound to the current claim epoch and hashed supporting artifacts. Mandatory criteria cannot be waived.
- Executor-driven not-achieved archival is limited to:
  - `blocked`, only after the platform accepts its own threshold-gated blocked transition; or
  - exact user cancellation, abandonment, or supersession after the external persistent goal is cancelled or replaced.
- An unclaimed package that never started may be administratively retired with exact user authorization.
- The helper moves the entire package to `goal_achieved` or `goal_not_achieved`, commits the final status, and seals every terminal file. Missing or changed terminal seals are treated as corruption except for a distinguishable `archive_prepared` recovery state.
- Recover only by exact goal ID. Never recreate, replay, merge, or automatically delete terminal history.

## Completion standard

Finish this skill only when either:

- the interview is waiting for the user’s next material answer or exact approval phrase; or
- an approved package has passed publication and verification and the exact pasteable handoff has been delivered.

Never claim that Goal Forge built the requested project. It produces the decision-complete contract and safe execution handoff; the new `/goal` session performs the work.
