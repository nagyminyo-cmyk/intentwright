# Contributing to Goal Forge

Thank you for helping make ambitious agent goals less ambiguous.

## Good contributions

- A missing high-leverage interview question or domain branch.
- A concrete example where an executor could satisfy the spec but still
  disappoint the user.
- A lifecycle race, integrity problem, recovery failure, or platform mismatch.
- A deterministic regression test for an existing rule.
- Documentation that makes installation or approval behavior clearer.

Avoid adding questions merely to make the interview longer. Every question
should be capable of changing scope, behavior, quality, validation, authority,
or lifecycle decisions.

## Development setup

The examples below use the Windows launcher `python`. On macOS or Linux, use
`python3` unless `python` already resolves to Python 3.10 or newer.

```bash
git clone https://github.com/nagyminyo-cmyk/goal-forge.git
cd goal-forge
python scripts/goal_lifecycle.py --help
python -m unittest discover -s tests -v
```

Run Ruff before submitting:

```bash
python -m pip install ruff==0.15.22
ruff check .
```

## Pull requests

Keep each pull request focused. Explain:

- the failure or ambiguity being addressed;
- why the change belongs in the interviewer, contract, or lifecycle helper;
- what behavior changes for users and execution agents;
- how the change was validated;
- any compatibility or migration impact.

Contract changes should update `SKILL.md`, the relevant reference document,
the lifecycle helper when applicable, and tests together.

## Compatibility

The helper supports Python 3.10 and newer. Keep the standard-library-only
runtime unless a dependency has a compelling, documented lifecycle benefit.

Test platform-sensitive changes on Windows and at least one Unix-like platform.
