from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "goal_lifecycle.py"
TITLE = "Validate the public Goal Forge lifecycle"
SLUG = "public_e2e"
REVISION = 1
INTERVIEW_ID = "gfi_20260719T120000000Z_public_e2e_1a2b"
REQUIRED_EVIDENCE = (
    "A JSON command transcript containing successful approval, initialization, "
    "publication, verification, and claim results."
)

SEMANTIC_BODY = f"""## Executive outcome

Validate that the public Goal Forge helper can turn one approved specification into an
isolated package, execute its guarded lifecycle, and preserve a verifiable achieved
archive. The audience is maintainers and contributors running the repository test suite.
The convincing demonstration is a clean end-to-end command sequence in a temporary
workspace followed by successful terminal verification and exact-ID recovery.

## Context and verified current state

The test starts with an empty temporary directory created by Python. The lifecycle helper
is loaded from this repository, and the fixture creates only its approved `src` write
scope. No credentials, network services, user repositories, or persistent machine data
are required. The temporary workspace is removed by the test harness after execution.

## Users and scenarios

A contributor runs the standard unittest suite. The fixture requests an approval
receipt, initializes staging, supplies the exact approved bytes, publishes, verifies,
claims, records evidence and outcome, enters validation, archives as achieved, verifies
the terminal package, and recovers it by exact goal ID. Any failed command fails the test.

## Scope and deliverables

The mandatory deliverable is one deterministic integration test of the public command
line lifecycle using only the Python standard library. It must retain criterion-specific
evidence inside the package and assert both active and terminal responses. There is no
stretch work in this fixture.

## Explicit non-goals

The fixture does not test user interviewing quality, external persistent-goal APIs,
network behavior, repository hosting, graphical interfaces, or destructive operations
against a real project. It does not mock lifecycle internals or bypass command validation.

## Decision coverage matrix

| Dimension | Status | Resolution or provenance |
|---|---|---|
| Outcome and audience | DECIDED | D-001 defines the maintainer-facing lifecycle result. |
| Current state and context | DECIDED | D-002 fixes an empty temporary workspace as the starting state. |
| Scope and priority | DECIDED | D-001 limits mandatory work to the complete command sequence. |
| Inputs, outputs, and interfaces | DECIDED | D-001 fixes CLI JSON as the exercised interface and output. |
| Golden path and state behavior | DECIDED | D-001 defines publication through achieved recovery in order. |
| Quality and taste | DECIDED | D-001 requires compact readable assertions and deterministic fixture data. |
| Constraints and dependencies | DECIDED | C-001 permits only Python standard-library dependencies. |
| Compatibility and preservation | DECIDED | C-001 keeps all writes inside the temporary workspace and package. |
| Failure, recovery, and operations | DECIDED | D-001 requires command failures to fail the test and recovery to succeed. |
| Security, privacy, and authority | DECIDED | C-001 prohibits credentials, network access, and writes to user projects. |
| Performance and reliability | DECIDED | D-002 bounds the fixture to one small package and local subprocesses. |
| Accessibility, inclusion, and localization | NOT_APPLICABLE | NA-001 records that no human-facing product surface is delivered. |
| Validation and evidence | DECIDED | D-001 requires structured evidence plus active and terminal verification. |
| Execution authority | DECIDED | C-001 authorizes writes only under the temporary workspace. |
| Completion and lifecycle | DECIDED | D-001 requires achieved archival, terminal verification, and recovery. |

## Domain routing

| Domain branch | Status | Rationale |
|---|---|---|
| Existing software or repository change | SELECTED | D-001 adds integration coverage to this existing helper repository. |
| Greenfield software, service, CLI, or API | NOT_APPLICABLE | NA-001 confirms no standalone system is created. |
| UI, UX, visual design, or brand | NOT_APPLICABLE | NA-001 confirms no visual or interactive interface is delivered. |
| Game | NOT_APPLICABLE | NA-001 confirms the fixture contains no game behavior. |
| Research, analysis, or recommendation | NOT_APPLICABLE | NA-001 confirms research is not the deliverable. |
| Writing, documentation, or content | NOT_APPLICABLE | NA-001 confirms prose exists only as lifecycle fixture data. |
| Automation, operations, or agent workflow | SELECTED | D-001 defines an automated lifecycle workflow as the test target. |
| Security or defensive engineering | NOT_APPLICABLE | NA-001 confirms ordinary isolation checks are sufficient for this fixture. |
| Data, AI, or model-driven system | NOT_APPLICABLE | NA-001 confirms no data pipeline or model is involved. |
| Product, business, or process | NOT_APPLICABLE | NA-001 confirms no business process is being designed. |
| Hardware, physical, or environment-dependent work | NOT_APPLICABLE | NA-001 confirms no special hardware or physical setup is needed. |
| Education, tutorial, or learning system | NOT_APPLICABLE | NA-001 confirms teaching is not the target outcome. |
| General creative deliverable | NOT_APPLICABLE | NA-001 confirms no general creative artifact is requested. |

## Requirements

| ID | Requirement | Rationale or provenance | Priority |
|---|---|---|---|
| REQ-001 | The public helper completes the approved lifecycle from receipt through an exclusively claimed package without validation errors. | D-001 defines the command sequence that proves the public workflow remains executable. | Mandatory |

## Execution workspace and write scope

The fixture uses one newly created non-Git temporary workspace and no external shared
resources. The single scope exists only to exercise exact scope binding and is sufficient
because the test never performs implementation writes elsewhere.

| Path | Access | Rationale |
|---|---|---|
| src | WRITE | Contains the only implementation scope approved for this isolated fixture. |

## Detailed behavior and quality bar

Every CLI command must run as a fresh subprocess and return parseable JSON with `ok`
equal to true. The approved body is copied byte-for-byte into staging. Publication
tampering must be rejected, after which restoring the exact sealed bytes must restore
verification. Assertions use exact IDs, paths, hashes, states, and claim epochs rather
than selecting packages by recency or similarity.

## Data, interfaces, dependencies, and compatibility

Inputs are this canonical UTF-8 semantic body and explicit envelope arguments. Outputs
are CLI JSON records and package files defined by the lifecycle contract. Python 3.10 or
newer and the standard library are the only dependencies. All JSON evidence uses stable
field names, all package references are relative, and cleanup is owned by TemporaryDirectory.

## Constraints and prohibited shortcuts

The test may not import lifecycle internals to mutate state, skip approval, forge seals,
disable validation, access a sibling package, use a real user workspace, or depend on
network access. It must invoke the public CLI with the same ordering required of an
executor and must provide exact receipt, claim, evidence, and disposition values.

## Executor freedoms

There are no delegated product decisions. Test maintainers may refactor assertion
helpers while preserving the exact public lifecycle, isolation boundary, semantic
contract, tamper check, and terminal verification behavior recorded by D-001 and C-001.

## Edge cases and failure semantics

A changed sealed specification must make verification return a nonzero status and an
explicit lifecycle error. The fixture restores the original bytes before continuing.
Any malformed JSON, missing path, stale token, wrong epoch, failed evidence hash, invalid
state transition, archive rejection, or failed recovery is an immediate unittest failure.
Temporary files remain isolated even when a subprocess fails.

## Acceptance criteria

| ID | Priority | Role | Covers | Pass condition | Evidence method | Required evidence |
|---|---|---|---|---|---|---|
| AC-001 | Mandatory | DELIVERABLE | REQ-001 | The helper publishes, verifies, and exclusively claims one approved package in the isolated workspace. | command | {REQUIRED_EVIDENCE} |

## Validation plan

Run `python -m unittest discover -s tests -v` on each supported operating system. The
fixture captures JSON from each successful CLI subprocess, verifies a deliberate sealed
file mutation is rejected, restores the immutable bytes, then checks achieved archival,
terminal package verification, and idempotent exact-ID recovery.

## Risks and assumptions

The test assumes the current Python executable can launch child Python processes; this
is verified by the first receipt command. Filesystem timestamp granularity is mitigated
by recording evidence only after a confirmed claim. A command failure preserves stdout
and stderr in the unittest assertion so contributors can diagnose the exact phase.

## Decision ledger

| ID | Type | Status | Decision or rationale | Provenance |
|---|---|---|---|---|
| D-001 | D | CONFIRMED | Exercise the complete public CLI lifecycle and assert exact active and terminal results. | Public integration-test requirement. |
| D-002 | D | CONFIRMED | Use one fresh temporary workspace containing only the explicit source scope. | Public integration-test isolation requirement. |
| C-001 | C | CONFIRMED | Use only standard-library code and keep every fixture write within temporary storage. | Public portability and safety boundary. |
| NA-001 | NA | NOT_APPLICABLE | Product domains unrelated to a local lifecycle CLI fixture have no delivered surface. | Verified integration-test scope. |

## Definition of done

The receipt, staging initialization, exact-body publication, active verification, tamper
rejection, exclusive claim, structured criterion evidence, achieved outcome, validating
transition, terminal archive, terminal verification, and exact-ID recovery all pass.
The terminal package contains a valid terminal seal and no mandatory work remains.

## Goal lifecycle contract

| Lineage field | Goal ID or NONE |
|---|---|
| retry_of | NONE |
| supersedes | NONE |

Execute only this generated goal ID, verify before claiming, retain the claim token and
epoch, bind all evidence to that epoch, and archive only after the mandatory criterion
passes. The achieved archive is final and may be located again only by exact-ID recovery.
"""


class PublicLifecycleEndToEndTests(unittest.TestCase):
    maxDiff = None

    def _run(self, workspace: Path, *arguments: str) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, str(HELPER), *arguments],
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f"Command failed: {' '.join(arguments)}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            ),
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"CLI did not emit JSON: {exc}\nstdout:\n{completed.stdout}")
        self.assertIs(payload.get("ok"), True)
        return payload

    def _run_rejected(self, workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [sys.executable, str(HELPER), *arguments],
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ERROR:", completed.stderr)
        return completed

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))

    def test_full_public_lifecycle_with_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="goal-forge-e2e-") as temporary:
            workspace = Path(temporary).resolve()
            (workspace / "src").mkdir()
            candidate = workspace / "approved_candidate.md"
            candidate.write_bytes(SEMANTIC_BODY.encode("utf-8"))

            envelope = [
                "--workspace",
                str(workspace),
                "--goals-dir",
                "goals",
                "--title",
                TITLE,
                "--slug",
                SLUG,
                "--revision",
                str(REVISION),
                "--interview-id",
                INTERVIEW_ID,
                "--write-scope",
                "src",
            ]
            receipt = self._run(
                workspace,
                "approval-receipt",
                "--file",
                str(candidate),
                *envelope,
            )
            self.assertEqual(receipt["requirements"], ["REQ-001"])
            self.assertEqual(receipt["mandatory_acceptance_criteria"], ["AC-001"])

            initialized = self._run(
                workspace,
                "init",
                *envelope,
                "--approval-record",
                receipt["approval_phrase"],
                "--approval-receipt-sha256",
                receipt["approval_receipt_sha256"],
                "--approved-body-sha256",
                receipt["approved_body_sha256"],
            )
            staging = Path(initialized["staging_package"])
            approved_body_path = Path(initialized["approved_body_path"])
            approved_body_path.write_bytes(candidate.read_bytes())

            published = self._run(
                workspace,
                "publish",
                "--package",
                str(staging),
            )
            goal_id = published["goal_id"]
            package = Path(published["pending_package"])
            self.assertEqual(package.name, goal_id)
            self.assertTrue(package.is_dir())

            verified = self._run(
                workspace,
                "verify",
                "--package",
                str(package),
            )
            self.assertEqual(verified["state"], "pending")
            self.assertEqual(verified["location"], "goal_pending")

            spec_path = Path(published["spec_path"])
            sealed_spec = spec_path.read_bytes()
            spec_path.write_bytes(sealed_spec + b"\nunauthorized mutation\n")
            rejected = self._run_rejected(
                workspace,
                "verify",
                "--package",
                str(package),
            )
            self.assertRegex(rejected.stderr, r"(?i)(changed|hash|seal|mismatch)")
            spec_path.write_bytes(sealed_spec)
            self._run(workspace, "verify", "--package", str(package))

            claimed = self._run(
                workspace,
                "claim",
                "--package",
                str(package),
                "--identity",
                "public-test-runner",
            )
            token = claimed["claim_token"]
            epoch = claimed["claim_epoch"]
            self.assertEqual(epoch, 1)

            evidence_dir = package / "evidence"
            evidence_dir.mkdir()
            transcript_path = evidence_dir / "ac-001-transcript.json"
            transcript = {
                "approval": receipt["ok"],
                "initialization": initialized["ok"],
                "publication": published["ok"],
                "verification": verified["ok"],
                "claim": claimed["ok"],
                "goal_id": goal_id,
            }
            self._write_json(transcript_path, transcript)
            transcript_hash = hashlib.sha256(transcript_path.read_bytes()).hexdigest()
            observed_at = (
                datetime.now(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            evidence_record_path = evidence_dir / "ac-001-record.json"
            evidence_record = {
                "schema_version": 1,
                "goal_id": goal_id,
                "criterion_id": "AC-001",
                "claim_epoch": epoch,
                "observed_at": observed_at,
                "required_evidence": REQUIRED_EVIDENCE,
                "method": "command",
                "observation": (
                    "The isolated CLI sequence returned successful JSON for every active "
                    "lifecycle phase required by AC-001."
                ),
                "command": "python -m unittest discover -s tests -v",
                "exit_code": 0,
                "artifacts": [
                    {
                        "path": "evidence/ac-001-transcript.json",
                        "sha256": transcript_hash,
                        "description": (
                            "Structured transcript of successful active lifecycle commands."
                        ),
                    }
                ],
            }
            self._write_json(evidence_record_path, evidence_record)

            outcome = {
                "schema_version": 1,
                "goal_id": goal_id,
                "outcome": "achieved",
                "reason_code": "completed",
                "summary": (
                    "The public lifecycle fixture completed its mandatory acceptance path."
                ),
                "criteria": [
                    {
                        "id": "AC-001",
                        "result": "pass",
                        "evidence_records": ["evidence/ac-001-record.json"],
                    }
                ],
                "validation": [
                    "Verified publication, tamper rejection, restoration, and exclusive claim."
                ],
                "known_limitations": [],
                "remaining_work": [],
                "blocked_threshold_evidence": None,
                "user_authorization": None,
                "replacement_goal_id": None,
                "external_goal_disposition": "complete_after_archive",
            }
            self._write_json(package / "outcome.json", outcome)
            (package / "outcome.md").write_bytes(
                (
                    "# Goal outcome\n\n"
                    f"- Goal ID: `{goal_id}`\n"
                    "- Outcome: `achieved`\n"
                    "- Reason code: `completed`\n\n"
                    "## Acceptance results\n\n"
                    "AC-001 passed with a claim-bound command record and hashed transcript.\n\n"
                    "## Validation performed\n\n"
                    "Publication, tamper rejection, restored verification, and claim ownership "
                    "were validated before archival.\n"
                ).encode("utf-8")
            )

            validating = self._run(
                workspace,
                "state",
                "--package",
                str(package),
                "--claim-token",
                token,
                "--state",
                "validating",
                "--action",
                "Validate public integration fixture",
            )
            self.assertEqual(validating["state"], "validating")

            archived = self._run(
                workspace,
                "archive",
                "--package",
                str(package),
                "--claim-token",
                token,
                "--outcome",
                "achieved",
                "--reason-code",
                "completed",
                "--external-goal-disposition",
                "complete_after_archive",
            )
            terminal = Path(archived["terminal_package"])
            self.assertEqual(archived["state"], "achieved")
            self.assertFalse(package.exists())
            self.assertTrue((terminal / "terminal_seal.json").is_file())

            terminal_verified = self._run(
                workspace,
                "verify",
                "--package",
                str(terminal),
            )
            self.assertEqual(terminal_verified["location"], "goal_achieved")
            self.assertEqual(terminal_verified["state"], "achieved")

            recovered = self._run(
                workspace,
                "recover",
                "--workspace",
                str(workspace),
                "--goals-dir",
                "goals",
                "--goal-id",
                goal_id,
            )
            self.assertIs(recovered["already_terminal"], True)
            self.assertEqual(recovered["state"], "achieved")
            self.assertEqual(Path(recovered["terminal_package"]), terminal)


if __name__ == "__main__":
    unittest.main()
