# Security policy

## Reporting a vulnerability

Please use GitHub's private **Report a vulnerability** flow in the repository's
Security tab. Do not open a public issue containing an exploit, sensitive local
paths, credentials, or unreleased vulnerability details.

For non-sensitive hardening ideas, a normal GitHub issue is welcome.

## Scope and expectations

Goal Forge handles local specifications, lifecycle state, claim tokens, hashes,
and filesystem paths. Security-relevant areas include:

- path traversal, symlink, junction, reparse-point, hardlink, or alias bypasses;
- concurrent publication, claim, takeover, archive, or recovery races;
- integrity-check bypasses;
- cross-goal scope or lineage confusion;
- unsafe portable import behavior;
- accidental exposure of secrets in generated handoffs or evidence.

Goal Forge is not an OS sandbox. A process that already has permission to alter
the workspace can bypass cooperative write-scope rules or rewrite both content
and unhashed trust roots. Reports should distinguish coordination guarantees
from operating-system access control.

## Supported versions

Security fixes are applied to the latest released version.
