# Changelog

All notable changes to Intentwright will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-10-12

### Added

- Separate Intentwright Spec 1.0.0 marketplace edition with all essential
  interview instructions in one file and an explicit approval text handoff.
- Reproducible, standard-library-only release builder with explicit file
  allowlists, version checks, symlink/reparse rejection, per-file manifests and
  archive SHA-256 checksums.
- Complete Codex install ZIP, marketplace upload ZIP with `SKILL.md` at its
  root, and optional clean source archive.
- Packaging extraction/CLI smoke tests, determinism and payload-integrity tests,
  and release-artifact CI with draft GitHub release creation on matching tags.
- Illustrative interview walkthrough and clearer installation, edition and
  update guidance.
- Regression coverage for concurrent claims, takeover fencing, cancellation,
  retry/replacement lineage, portable imports and interrupted archival.

### Fixed

- Recover terminal archival interrupted immediately before final status
  replacement when the leftover atomic status file exactly matches the
  precommitted seal. Changed contents, unsafe links, lookalike filenames,
  missing seals and unexpected files remain rejected and preserved.

### Changed

- Distinguish full local lifecycle functionality from the Spec edition's
  conversation-only interview and approval behavior.
- Clarify that cooperating-executor hashes, claims and evidence checks do not
  prove authorship or independently establish subjective acceptance.
- Lifecycle schema remains 2; existing schema-2 package identifiers and
  compatibility boundaries are preserved.

## [2.0.0] - 2026-07-19

### Changed

- Established the complete Intentwright public identity: `$intentwright`, `iwi_` interview
  IDs, Intentwright marker and payload namespaces, and the renamed lifecycle
  helper.
- Advanced the lifecycle schema to version 2. Packages created by another
  lifecycle identity remain bound to the helper that created them and are
  rejected rather than silently rewritten.

### Added

- Bidirectional workspace-registration fencing between schema 1 helpers and
  Intentwright, including a compatibility exclusion sentinel and regression
  coverage.

## [1.0.0] - 2026-07-19

### Added

- Adaptive, decision-complete pre-goal interview workflow.
- Universal coverage matrix and domain-specific interview branches.
- Exact revision approval bound to the semantic body, workspace, write scopes,
  and lineage through SHA-256 receipts.
- Isolated `goal_pending`, `goal_achieved`, and `goal_not_achieved` packages.
- Specifically named `goal_spec_<slug>.md` specifications.
- Exclusive claims, scope-overlap fencing, heartbeats, takeovers, and claim
  epochs for concurrent agents.
- Structured acceptance evidence and immutable terminal seals.
- Crash-safe archival and exact-ID recovery.
- Replacement and recursively verified retry lineage.
- Windows cross-session mutexes and hardened Unix lock files.
- Portable handoffs for eligible non-lineage goals.
