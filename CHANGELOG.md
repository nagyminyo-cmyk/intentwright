# Changelog

All notable changes to Goal Forge will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

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
