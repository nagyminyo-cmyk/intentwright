# Goal Forge interview playbook

## Contents

1. Governing principle
2. Interview state machine
3. Question selection and pacing
4. Universal decision matrix
5. High-value probes
6. Ambiguity and contradiction handling
7. Domain branches
8. Decision ledger
9. Readiness and integrity checks
10. Failure modes

## 1. Governing principle

Interrogate until every consequential choice is decided, verified, explicitly delegated with boundaries, or proven not applicable. Do not micromanage harmless implementation details merely to increase the question count.

The desired output is a specification from which a capable executor can act without inventing product intent. “Detailed” means decision-complete, traceable, and testable—not simply long.

## 2. Interview state machine

### Discover

- Inspect available workspace facts before questioning.
- Identify whether this is greenfield, an existing system change, a replacement, or a mixed task.
- Distinguish confirmed repository facts, user claims, inferences, and unknowns.
- Inspect only goal-root metadata when concurrent goal packages exist. Never open sibling specs.
- Resolve the canonical workspace first: use the Git worktree root when present,
  and reject nested workspace aliases. Confirm its single registered
  project-relative goal root and preserve the exact `--goals-dir` value.
- Determine whether this is a fresh goal, a replacement with `supersedes`, or a
  retry of one exact terminal not-achieved package with `retry_of`.

### Anchor

Establish:

- the exact end result;
- the people or systems it serves;
- the concrete scenario in which it is used;
- the problem or opportunity;
- why it matters now;
- what a convincing five-minute demonstration looks like;
- hard constraints and preservation requirements;
- explicit non-goals;
- who decides ambiguous trade-offs.

### Route

Select every relevant domain branch. A multiplayer desktop game may require game, UI/design, software, networking, security, and operations branches. Do not force a mixed task into one category.

### Breadth pass

Classify every universal dimension as:

- `DECIDED`: the user or verified context resolved it;
- `DELEGATED`: the executor may decide within a recorded boundary and rubric;
- `OPEN`: a material answer is still needed;
- `NOT_APPLICABLE`: it does not affect this task, with a brief reason.

Assign a conversational interview ID before the first question using exactly
`gfi_YYYYMMDDTHHMMSSmmmZ_<lowercase_snake_slug>_<4 lowercase hex>`. Keep one
active interview per thread; explicitly park or switch by exact ID instead of
mixing ideas.

### Adaptive deep dive

Prioritize questions using:

`priority = impact × uncertainty × irreversibility × downstream dependency`

Resolve high-branching choices before leaf details. Every follow-up must be caused by an answer, missing fact, contradiction, or risk—not by a canned quota.

### Adversarial completeness pass

Review the draft as:

- a skeptical owner looking for technically compliant disappointment;
- an implementer looking for decisions still left to invent;
- a QA reviewer looking for unverifiable claims;
- an operator looking for hidden dependencies and recovery gaps;
- an adversary looking for unsafe authority or trust assumptions where relevant.

Turn material findings into further questions.

### Approval

Canonicalize the exact semantic body as UTF-8 without BOM, LF-only, with exactly
one final LF. Generate an approval receipt that binds the body hash, canonical
workspace, goal root, title, slug, revision, interview ID, scopes, and lineage.
Present the entire numbered revision plus that receipt. Require the emitted exact
phrase `Approve spec v<N> receipt <SHA-256>`. Any material body or envelope
change increments the revision, changes the receipt, and requires approval again.

## 3. Question selection and pacing

### Ask one at a time when

- the answer changes the entire branch;
- the user must make a real trade-off;
- the question could invalidate earlier assumptions;
- examples or options depend on the answer;
- the issue is emotional, aesthetic, strategic, or hard to answer.

### Ask a small batch when

- questions are independent leaf decisions;
- answering one cannot invalidate the others;
- all belong to the same narrow topic;
- three to five answers can be given compactly.

### Help without leading

- Explain why a question matters when it is not obvious.
- Offer two or three realistic choices when the user lacks vocabulary.
- Mark a recommendation as a recommendation and explain its trade-off.
- Allow “I delegate this” only after defining the executor’s boundaries and quality test.
- Do not convert uncertainty into a default invisibly.

### Preserve momentum

- Show only ledger deltas after ordinary rounds.
- Summarize remaining areas periodically.
- Do not repeat settled questions unless new information creates a tension.
- Stop probing a detail when alternative answers cannot materially change delivery, validation, risk, or user experience.

## 4. Universal decision matrix

### Outcome and audience

- What exact artifact, behavior, decision, or changed state must exist?
- Who uses, reviews, receives, or is affected by it?
- What can they do afterward that they cannot do now?
- What is the primary use case? Which secondary cases are required?
- What would be technically correct but still disappoint?
- What does a compelling demonstration show from beginning to end?

### Current state and context

- What exists today, and what evidence confirms it?
- What is broken, missing, slow, confusing, risky, or unwanted?
- What previous attempts, constraints, or decisions matter?
- What must remain unchanged?
- Is the stated mechanism itself required, or only the outcome?

### Scope and priority

- What are the concrete deliverables?
- Where does the goal begin and end?
- What is explicitly outside scope?
- Which items are mandatory, optional, or stretch?
- Which requirement wins when schedule, quality, simplicity, compatibility, and completeness conflict?
- May stretch work ever delay completion? Default to no.

### Inputs, outputs, and interfaces

- What enters the system or process, from where, in what form, and under whose control?
- What exact outputs are produced, where do they go, and who consumes them?
- What schemas, formats, protocols, dimensions, lengths, or quality constraints apply?
- What happens with missing, malformed, stale, duplicate, partial, or hostile input?
- What interfaces must remain compatible?

### Golden path and state behavior

- Walk through the exact path from start to success.
- What does the user or system see or do at each step?
- What state persists between steps, sessions, devices, or failures?
- What happens in empty, loading, partial, success, invalid, unauthorized, offline, timeout, retry, cancelled, and unrecoverable states?
- What can be undone, resumed, retried, or recovered?

### Quality and taste

- What does “great” mean here in observable terms?
- What references demonstrate the desired bar, and which qualities should be borrowed?
- What anti-references show what to avoid?
- Which subjective choices are non-negotiable?
- If exact metrics are inappropriate, what bounded review rubric determines acceptance?
- Which details create delight, trust, clarity, tension, speed, or polish?

### Constraints and dependencies

- Which platforms, versions, devices, languages, formats, libraries, budgets, dates, or environments are fixed?
- Which dependencies, credentials, subscriptions, accounts, people, services, hardware, or networks are required?
- Who owns each dependency?
- What happens when a dependency is unavailable?
- Which assumptions must be verified before irreversible work?
- What may the executor install, download, purchase, or replace?

### Compatibility and preservation

- Which current behaviors, routes, data, visuals, files, APIs, shortcuts, saves, or workflows must survive?
- Is backward compatibility required? For whom and for how long?
- Are migration, import, export, rollback, or coexistence paths required?
- What regression evidence proves preservation?
- Which legacy behavior may intentionally change?

### Failure, recovery, and operations

- What failures are expected, and what should users or operators observe?
- Which operations must be idempotent?
- What are the retry, timeout, fallback, cancellation, and rollback semantics?
- What must be logged, measured, alerted, or audited?
- How is corrupted or partial state detected and repaired?
- What is the safe degraded mode?

### Security, privacy, and authority

- What assets, identities, secrets, personal data, money, or external systems are involved?
- Who may read, change, delete, publish, deploy, send, approve, or spend?
- Where are trust boundaries and untrusted inputs?
- What abuse cases or invariants matter?
- What data retention, deletion, redaction, or provenance rules apply?
- Separate authority to edit local files from authority to deploy, message others, alter external systems, delete data, transfer funds, or incur cost.

### Performance and reliability

- Which workloads, sizes, concurrency levels, latency expectations, and resource limits are realistic?
- What must work offline or under poor connectivity?
- What uptime, durability, determinism, or reproducibility is needed?
- Which benchmark environment and evidence make a performance claim honest?
- What behavior is acceptable when the target cannot be met?

### Accessibility, inclusion, and localization

- Which accessibility baseline applies?
- What keyboard, screen-reader, contrast, motion, caption, input, or cognitive needs matter?
- Which locales, languages, time zones, number/date formats, or text expansion cases apply?
- Which audience assumptions could exclude intended users?

### Validation and evidence

- What observable fact proves each requirement?
- Which unit, integration, end-to-end, rendered, device, human-review, benchmark, or source-verification evidence is needed?
- Is the required environment actually available?
- What may be simulated, and how must simulation be labeled?
- What must never be claimed as verified without real hardware, accounts, people, network, or external state?
- If a mandatory criterion becomes inappropriate or impossible, what replacement
  specification or user-controlled cancellation path applies? Mandatory criteria
  cannot be waived during execution.
- If real validation must happen later, who owns it, when will it run, what keeps the package pending, and what result makes it terminal?

### Execution authority

- What may the executor decide without asking again?
- What actions require explicit user confirmation?
- May it modify configuration, dependencies, schemas, migrations, or external services?
- May it create subagents, browse, use connectors, or run long validation?
- What must it preserve in a dirty worktree?
- When should it pause rather than assume?
- Which exact project-relative paths may it modify?
- Does parallel execution require an isolated Git worktree?
- Which external actions or shared resources cannot be protected by filesystem scope leases?

### Completion and lifecycle

- Which criteria are mandatory for achievement?
- What evidence must be recorded?
- What temporary conditions leave the package pending?
- Which genuinely terminal outcomes count as not achieved?
- If `blocked` is permitted, what is the concrete repeated blocker, what evidence
  records each occurrence, and what proves there is no safe in-scope progress?
- What cleanup, packaging, documentation, handoff, or archival is part of “done”?

## 5. High-value probes

### Operationalize adjectives

For words such as `fast`, `polished`, `modern`, `secure`, `robust`, `easy`, `smart`, `complete`, and `production-ready`, ask for:

- an observable behavior;
- a reference and anti-reference;
- a threshold when defensible;
- a bounded judgment rubric otherwise;
- evidence the executor can realistically collect.

### Counterexample probe

Ask: “What might look compliant or impressive but would still feel wrong?” Convert the answer into a non-goal, constraint, or acceptance criterion.

### Negative requirement probe

Ask: “What must this never do?” Distinguish taste preferences from safety or correctness invariants.

### Boundary probe

Ask where the responsibility starts, ends, and hands off. Name neighboring systems or work that must remain untouched.

### Failure simulation

Simulate unavailable dependencies, malformed data, interruption halfway through, concurrent execution, stale state, unauthorized access, and failed validation.

### Trade-off probe

Present only real conflicts. Do not make the user choose between compatible virtues merely to manufacture specificity.

### Preservation probe

Enumerate current user-visible and machine-visible contracts. Map each preserved contract to a regression check.

### Executor-discretion probe

Ask which decisions the agent may make, then define the boundaries, priorities, examples, anti-examples, and review test for those decisions.

## 6. Ambiguity and contradiction handling

Automatically challenge:

- unbounded words such as `everything`, `fully`, `all`, `never`, and `etc.`;
- requirements missing an actor, trigger, target, environment, or owner;
- pronouns or references with multiple possible meanings;
- conflicting `must`, `should`, and optional language;
- a technology choice without an outcome or rationale;
- success defined only as code or files existing;
- acceptance criteria that require unavailable hardware, credentials, people, or accounts;
- hidden reliance on subscriptions, current web facts, or external access;
- requirements whose result cannot be observed;
- multiple unrelated goals disguised as one;
- an assumption presented as a confirmed fact.

When two answers conflict:

1. Quote or tightly paraphrase both.
2. Explain the practical consequence.
3. Record a `T` entry.
4. Offer realistic resolution paths when helpful.
5. Require resolution or explicit bounded delegation.
6. Preserve the superseded choice as `R`; never erase the history.

Do not force false precision. “Feels immediate under ordinary local use, with a measured benchmark reported rather than a fabricated target” can be more honest than an invented millisecond requirement.

## 7. Domain branches

Use all applicable branches.

### Existing software or repository change

- Which exact surfaces, modules, routes, commands, workflows, and data are affected?
- What current behavior is authoritative?
- What architecture is fixed versus open?
- What user changes or dirty-worktree edits must be preserved?
- What compatibility, migration, rollback, packaging, and release paths apply?
- Which tests exist, and which real rendered or runtime checks are missing?
- What counts as a complete rework versus a narrow patch?

### Greenfield software, service, CLI, or API

- What platforms, runtimes, deployment targets, and supported versions apply?
- What components own state and decisions?
- What are the interface contracts, schemas, authentication, authorization, and error semantics?
- What data lifecycle, migrations, observability, and support model are required?
- What is the expected workload and scaling boundary?
- What packaging, installation, upgrade, rollback, and documentation are needed?

### UI, UX, visual design, or brand

- What is the visual hierarchy and primary action on each surface?
- What content density, layout, color, typography, imagery, texture, motion, and interaction feedback are desired?
- Which references and anti-references define the taste?
- What should empty, loading, error, disabled, success, hover, focus, and pressed states look and feel like?
- Which breakpoints, input modes, window sizes, and accessibility needs apply?
- Which old elements are retained, replaced, or preserved behind another route?
- What real rendered review proves quality beyond code correctness?

### Game

- What is the core loop, moment-to-moment action, win/loss condition, and session length?
- What are the controls, movement, camera, responsiveness, feedback, and desired feel?
- What progression, economy, difficulty curve, content volume, onboarding, and replayability are required?
- What visual, animation, sound, music, humor, narrative, and anti-reference direction applies?
- What save, pause, accessibility, settings, and input-device behavior is required?
- For multiplayer: topology, authority, hosting, discovery, latency, synchronization, disconnect, rejoin, cheating, and version mismatch behavior?
- Which gameplay claims require a real second player, machine, controller, or network?

### Research, analysis, or recommendation

- What decision must the work support?
- What questions, hypotheses, comparison dimensions, and exclusions apply?
- Which sources are authoritative, current enough, and independent?
- What methodology, confidence, uncertainty, and conflicting evidence treatment is required?
- What calculations or datasets must be reproducible?
- What output format, audience level, citations, and recommendation threshold apply?

### Writing, documentation, or content

- Who is the audience, and what should they understand, feel, or do?
- What thesis, facts, claims, structure, length, voice, terminology, and examples are required?
- What sources and citation standard apply?
- Which claims, tones, phrases, or implications are forbidden?
- What is editable versus verbatim?
- What editorial review proves clarity, accuracy, consistency, and usefulness?

### Automation, operations, or agent workflow

- What triggers the workflow, and what inputs and outputs exist?
- What schedule, concurrency, idempotency, deduplication, retries, backoff, timeout, and cancellation behavior applies?
- What permissions, secrets, external actions, and approval gates exist?
- What logs, alerts, audit trail, recovery, rollback, and runbook are required?
- How are partial execution, duplicate delivery, stale state, and takeover handled?
- What keeps one agent or job from contaminating another?

### Security or defensive engineering

- What assets, actors, adversaries, trust boundaries, and attack surfaces matter?
- What abuse cases and security invariants must hold?
- What data sensitivity, key custody, access control, retention, and provenance rules apply?
- Which validations are safe and authorized?
- What mitigations, residual risks, logging, and incident recovery are required?
- What is explicitly out of scope or prohibited?

### Data, AI, or model-driven system

- What data sources, rights, schemas, quality, drift, leakage, and retention concerns apply?
- What ground truth, baseline, evaluation set, and failure taxonomy exist?
- What latency, cost, determinism, explainability, and human oversight are required?
- What happens on low confidence, refusal, hallucination, model outage, or provider change?
- Which decisions may the model make, and which require deterministic or human control?
- How will evaluation avoid contamination and cherry-picking?

### Product, business, or process

- Who has the problem, how often, and what current workaround exists?
- What evidence supports the need?
- What is the smallest valid outcome versus the long-term vision?
- What adoption, trust, compliance, operational, and stakeholder constraints apply?
- What metric indicates value without creating harmful incentives?
- Which assumptions should be validated before monetization, scaling, or irreversible investment?

### Hardware, physical, or environment-dependent work

- What exact components, dimensions, tolerances, interfaces, tools, and safety limits apply?
- What environment, power, connectivity, mounting, transport, durability, and maintenance conditions exist?
- Which parts are available and testable locally?
- What simulations or prototypes are valid, and what requires real hardware certification?
- What failure modes could damage property or harm people?

### Education, tutorial, or learning system

- What does the learner already know?
- What exact capability should they demonstrate afterward?
- What teaching pace, explanation style, examples, practice, feedback, and assessment apply?
- Which misconceptions should be surfaced?
- What accessibility, motivation, and progression needs matter?
- How will mastery be observed rather than inferred from completion?

### General creative deliverable

- What emotional effect, message, audience, medium, duration, and context matter?
- What references, anti-references, motifs, palette, rhythm, texture, voice, and originality boundary apply?
- Which components are fixed and which may be explored?
- What variants or iteration process are desired?
- What review rubric distinguishes intentional work from generic output?

## 8. Decision ledger

Use the exact table `ID | Type | Status | Decision or rationale | Provenance`
and stable identifiers. An approvable ledger uses only these type/status pairs:

- `D`, `C`, `N` with `CONFIRMED`;
- `A` with `BOUNDED`;
- `O`, `T` with `RESOLVED`;
- `R` with `REJECTED`;
- `E` with `DELEGATED`;
- `NA` with `NOT_APPLICABLE`.

Record provenance: user answer, verified workspace fact, cited external fact, or explicit recommendation accepted by the user.

Never delete history. Preserve former questions and tensions as resolved `O` and
`T` rows. Include at least one real `D`. Include `NA` only when a coverage or
domain row is genuinely not applicable; never invent it to satisfy a quota.
Coverage and domain rows must cite status-compatible ledger IDs.

## 9. Readiness and integrity checks

Before requesting approval, verify:

- Every deliverable has uniquely identified requirements.
- Every required behavior maps to at least one acceptance criterion.
- Every acceptance criterion names concrete evidence.
- Every dependency has an owner and unavailable-dependency behavior.
- Every assumption states when and how it will be verified.
- Every preservation requirement has regression evidence.
- Every subjective quality requirement has references, anti-references, examples, or a review rubric.
- Mandatory and stretch work are explicit; stretch work cannot block achievement.
- Mandatory criteria use `AC-`; non-blocking stretch criteria use `SAC-`.
- Every mandatory `AC-` can produce a criterion-specific structured JSON evidence
  record plus at least one hashed supporting artifact beneath `evidence/`.
- At least one mandatory `AC-` has role `DELIVERABLE`; mandatory criteria cannot
  be waived.
- No unresolved material contradiction remains.
- No consequential product choice is left to executor invention unless explicitly delegated.
- Mandatory validation is executable now or has an explicitly approved future owner, environment, timing, pending rule, and terminal rule.
- External actions and destructive authority are explicit.
- Every universal dimension and domain branch appears in the final coverage matrices.
- Declared project write scopes are sufficient and do not falsely promise implementation isolation; use an isolated worktree when overlap is plausible.
- The canonical workspace identity and one custom goal-root name are frozen in
  the approval receipt and every workspace-resolving lifecycle command.
- Any `retry_of` or `supersedes` lineage is exact, mutually exclusive, and
  present in both the semantic-body lineage table and approval receipt. Every
  retry ancestor is finalized under `goal_not_achieved` and passes recursive
  publication-seal and terminal-seal verification.
- A replacement chain cannot skip a pending ancestor; every predecessor must
  terminally authorize the next exact goal ID in order.
- A possible blocked outcome defines how at least three ordered consecutive
  occurrences will be recorded, while recognizing that the platform's
  threshold-gated blocked transition is authoritative.
- Apparent infeasibility and validation failure remain pending unless the
  platform accepts `blocked` or the user explicitly cancels/replaces the goal.
- “Done” includes evidence, terminal sealing, package archival, and the
  reason-specific external goal transition in the correct order.
- The short `/goal` can remain below 4,000 characters because full detail lives in the frozen spec.
- The temporary approval candidate has an exact cleanup point after verified
  publication, and any abandoned unpublished staging draft has an explicit
  `discard-staging` decision rather than indefinite accumulation.

## 10. Failure modes

Guard against:

- questionnaire theater;
- asking discoverable facts;
- leading the user toward the interviewer’s preferred implementation;
- overwhelming the user with dozens of simultaneous questions;
- infinite interrogation of inconsequential detail;
- false precision;
- silent contradiction resolution;
- premature architecture lock-in;
- subjective or circular acceptance criteria;
- “tests pass” as the only evidence for visual, interactive, networked, or hardware behavior;
- calling unavailable real-world validation complete;
- allowing stretch work to prevent completion;
- publishing before the exact receipt-bound approval phrase;
- spec drift after publication;
- abandoned candidate drafts or hidden staging packages accumulating without an
  explicit recovery or discard decision;
- reading all pending specs;
- treating a pause, rate limit, one-turn end, or recoverable outage as terminal failure;
- marking an achieved persistent goal complete before package archival;
- archiving `blocked` before the platform accepts its threshold-gated transition;
- resealing a final terminal package merely because its terminal seal disappeared;
- claiming cross-workspace or lineage portability that the approval receipt and
  lifecycle history cannot support.
