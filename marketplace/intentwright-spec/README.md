# Intentwright Spec

**Clear intent. Better builds.**

Turn a rough idea into a specification you can review, approve, and hand to
a person or AI agent. Intentwright asks the questions that affect the outcome,
tracks your decisions, surfaces contradictions, and defines observable
acceptance checks before implementation starts.

## Start here

Ask your compatible assistant to use Intentwright Spec, then describe the idea:

> Use Intentwright Spec. I want a booking page for my dog park. Interview me
> until the scope, behavior, and acceptance criteria are clear.

In a host with explicit skill selection, select `intentwright-spec`. How a
marketplace loads skills depends on that platform. The entire workflow is
contained in `SKILL.md`; supporting examples are optional.

## What you get

- An adaptive interview that starts with consequential choices.
- A compact record of decisions, constraints, assumptions, and delegated choices.
- A specification with scope, behavior, quality, dependencies, and acceptance checks.
- A clear approval step tied to the exact revision.
- A self-contained handoff you can give to an executor in another conversation.

Use it for a software feature, a game, research, writing, design, or an
automation. It is most useful when the idea has enough ambiguity that building
immediately would force important guesses. A simple edit rarely needs it.

## Requirements and limits

A compatible assistant must be able to load and follow Markdown skill
instructions. There are no required scripts, APIs, paid services, local file
access, or account connections for the interview itself. Your assistant or
marketplace may have its own subscription or access requirements.

This edition produces project-specific text. It does not build the project,
validate an implementation, issue cryptographic approval receipts, claim
filesystem locks, or manage persistent goals. External facts and project files
remain unverified unless the assistant has access and actually checks them.
Good results still depend on your answers and the assistant following the
workflow. No fixed interview length or quality guarantee is promised.

The optional [worked example](examples/booking-page.md) is an illustrative
scenario, not a customer testimonial or evidence that a website was built.

## Full Codex edition

The same repository also contains Intentwright for Codex, with a Python helper,
immutable goal packages, and a guarded execution lifecycle. It has additional
requirements and is a separate installation; this text-only edition does not
inherit those guarantees.

Source and issue tracker: https://github.com/nagyminyo-cmyk/intentwright

## Version and licence

Version 1.0.0. MIT licensed; see `LICENSE`. Paid marketplace access is a
distribution option for open-source work. This package does not promise
exclusivity or remove the permissions granted by its MIT licence.
