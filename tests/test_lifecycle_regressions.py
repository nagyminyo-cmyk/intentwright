"""Exercise ownership, lineage, import, and crash boundaries through the public CLI."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from test_end_to_end import HELPER, INTERVIEW_ID, REVISION, SEMANTIC_BODY, TITLE


@dataclass(frozen=True)
class PublishedGoal:
    goal_id: str
    package: Path
    manifest: dict[str, Any]


# Abruptly stop a real CLI process at filesystem commit boundaries. No lifecycle
# state is fabricated: the helper writes every receipt, claim, outcome, and seal.
CRASH_RUNNER = r"""
import json
import os
import runpy
import sys
from pathlib import Path

helper, source, point = sys.argv[1:4]
source = Path(source).resolve()
real_rename, real_replace = os.rename, os.replace

def rename(before, after, *args, **kwargs):
    if Path(before).resolve() == source:
        if point == 'before_move':
            os._exit(73)
        result = real_rename(before, after, *args, **kwargs)
        if point == 'after_move':
            os._exit(73)
        return result
    return real_rename(before, after, *args, **kwargs)

def replace(before, after, *args, **kwargs):
    destination = Path(after)
    if destination.name == 'terminal_seal.json' and point == 'after_seal':
        result = real_replace(before, after, *args, **kwargs)
        os._exit(73)
        return result
    if destination.name == 'status.json' and point == 'before_final_status':
        content = json.loads(Path(before).read_text(encoding='utf-8'))
        if content.get('state') in {'achieved', 'not_achieved'}:
            os._exit(73)
    return real_replace(before, after, *args, **kwargs)

os.rename, os.replace = rename, replace
sys.argv = [helper, *sys.argv[4:]]
runpy.run_path(helper, run_name='__main__')
"""


class PublicLifecycleRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="intentwright-regression-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def _invoke(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), *arguments],
            cwd=self.workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def _ok(self, *arguments: str) -> dict[str, Any]:
        result = self._invoke(*arguments)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"{arguments!r}\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        payload = json.loads(result.stdout)
        self.assertIs(payload.get("ok"), True)
        return payload

    def _rejected(self, *arguments: str, pattern: str) -> None:
        result = self._invoke(*arguments)
        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
        self.assertIn("ERROR:", result.stderr)
        self.assertRegex(result.stderr, pattern)

    def _prepare(
        self,
        slug: str,
        scope: str = "src",
        *,
        retry_of: str | None = None,
        supersedes: str | None = None,
    ) -> tuple[Path, list[str]]:
        (self.workspace / scope).mkdir(parents=True, exist_ok=True)
        body = SEMANTIC_BODY.replace("| src | WRITE |", f"| {scope} | WRITE |")
        for field, linked in (("retry_of", retry_of), ("supersedes", supersedes)):
            if linked:
                body = body.replace(f"| {field} | NONE |", f"| {field} | {linked} |")
        candidate = self.workspace / f"candidate_{slug}.md"
        candidate.write_bytes(body.encode("utf-8"))
        envelope = [
            "--workspace", str(self.workspace),
            "--goals-dir", "goals",
            "--title", TITLE,
            "--slug", slug,
            "--revision", str(REVISION),
            "--interview-id", INTERVIEW_ID,
            "--write-scope", scope,
        ]
        for flag, linked in (("--retry-of", retry_of), ("--supersedes", supersedes)):
            if linked:
                envelope.extend([flag, linked])
        receipt = self._ok("approval-receipt", "--file", str(candidate), *envelope)
        initialization = [
            "init", *envelope,
            "--approval-record", receipt["approval_phrase"],
            "--approval-receipt-sha256", receipt["approval_receipt_sha256"],
            "--approved-body-sha256", receipt["approved_body_sha256"],
        ]
        return candidate, initialization

    def _publish(self, slug: str, scope: str = "src", **lineage: str) -> PublishedGoal:
        candidate, initialization = self._prepare(slug, scope, **lineage)
        initialized = self._ok(*initialization)
        Path(initialized["approved_body_path"]).write_bytes(candidate.read_bytes())
        published = self._ok("publish", "--package", initialized["staging_package"])
        package = Path(published["pending_package"])
        manifest = json.loads((package / "goal_manifest.json").read_text(encoding="utf-8"))
        return PublishedGoal(published["goal_id"], package, manifest)

    def _claim(self, goal: PublishedGoal) -> dict[str, Any]:
        return self._ok("claim", "--package", str(goal.package), "--identity", "test-owner")

    def _retire(self, goal: PublishedGoal, replacement: PublishedGoal | None = None) -> Path:
        reason = "superseded" if replacement else "cancelled_by_user"
        authorization = (
            f"Supersede goal {goal.goal_id} with {replacement.goal_id}"
            if replacement else f"Cancel goal {goal.goal_id}"
        )
        arguments = [
            "retire", "--package", str(goal.package), "--reason-code", reason,
            "--authorized-reason", authorization,
        ]
        if replacement:
            arguments.extend(["--replacement-goal-id", replacement.goal_id])
        retired = self._ok(*arguments)
        return Path(retired["terminal_package"])

    @staticmethod
    def _json(path: Path, value: dict[str, Any]) -> None:
        path.write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))

    def _cancel_arguments(self, goal: PublishedGoal, token: str) -> list[str]:
        authorization = f"Cancel goal {goal.goal_id}"
        self._json(goal.package / "outcome.json", {
            "schema_version": goal.manifest["schema_version"],
            "goal_id": goal.goal_id,
            "outcome": "not_achieved",
            "reason_code": "cancelled_by_user",
            "summary": "The user explicitly cancelled this isolated test execution.",
            "criteria": [{"id": "AC-001", "result": "not_run", "evidence_records": []}],
            "validation": ["No deliverable was completed before the explicit cancellation."],
            "known_limitations": [],
            "remaining_work": ["The requested deliverable remains unimplemented."],
            "blocked_threshold_evidence": None,
            "user_authorization": authorization,
            "replacement_goal_id": None,
            "external_goal_disposition": "user_cancelled_or_replaced_before_archive",
        })
        (goal.package / "outcome.md").write_bytes((
            f"# Goal outcome\n\n- Goal ID: `{goal.goal_id}`\n"
            "- Outcome: `not_achieved`\n- Reason code: `cancelled_by_user`\n\n"
            "## Validation performed\n\nThe user cancellation was recorded before archival.\n\n"
            "## Remaining work\n\nThe requested deliverable remains unimplemented.\n"
        ).encode("utf-8"))
        return [
            "archive", "--package", str(goal.package), "--claim-token", token,
            "--outcome", "not_achieved", "--reason-code", "cancelled_by_user",
            "--authorized-reason", authorization,
            "--external-goal-disposition", "user_cancelled_or_replaced_before_archive",
        ]

    def _recover(self, goal: PublishedGoal, token: str | None = None) -> dict[str, Any]:
        arguments = [
            "recover", "--workspace", str(self.workspace), "--goals-dir", "goals",
            "--goal-id", goal.goal_id,
        ]
        if token:
            arguments.extend(["--claim-token", token])
        return self._ok(*arguments)

    def _crash_cancellation(
        self, goal: PublishedGoal, point: str,
    ) -> tuple[Path, str]:
        owner = self._claim(goal)
        token = owner["claim_token"]
        arguments = self._cancel_arguments(goal, token)
        crashed = subprocess.run(
            [sys.executable, "-c", CRASH_RUNNER, str(HELPER), str(goal.package),
             point, *arguments],
            cwd=self.workspace, env=self.environment, capture_output=True,
            text=True, encoding="utf-8", timeout=30, check=False,
        )
        self.assertEqual(crashed.returncode, 73, msg=crashed.stdout + crashed.stderr)
        location = (goal.package if point == "before_move" else
                    self.workspace / "goals" / "goal_not_achieved" / goal.goal_id)
        return location, token

    def _assert_recovery_preserves_invalid_temporary(
        self, goal: PublishedGoal, temporary: Path,
    ) -> None:
        before = temporary.lstat()
        self._rejected("recover", "--workspace", str(self.workspace),
                       "--goal-id", goal.goal_id,
                       pattern="(?i)(temporary|seal|link|regular|reparse)")
        after = temporary.lstat()
        for field in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns"):
            self.assertEqual(getattr(after, field), getattr(before, field))
        status = json.loads((temporary.parent / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "archive_prepared")

    def _concurrent_claims(
        self, goals: list[PublishedGoal], *, retry_busy: bool = False,
    ) -> list[subprocess.CompletedProcess[str]]:
        barrier = threading.Barrier(len(goals))

        def claim(goal: PublishedGoal) -> subprocess.CompletedProcess[str]:
            barrier.wait(timeout=10)
            for _ in range(30):
                result = self._invoke("claim", "--package", str(goal.package))
                if not retry_busy or "Another lifecycle operation is active" not in result.stderr:
                    return result
                time.sleep(0.02)
            return result

        with ThreadPoolExecutor(max_workers=len(goals)) as executor:
            return list(executor.map(claim, goals))

    def test_concurrent_claims_of_one_goal_have_one_owner(self) -> None:
        goal = self._publish("same_goal")
        results = self._concurrent_claims([goal, goal], retry_busy=True)
        self.assertEqual(sorted(result.returncode for result in results), [0, 2])
        winner = json.loads(next(result.stdout for result in results if result.returncode == 0))
        claim = json.loads((goal.package / "claim.json").read_text(encoding="utf-8"))
        self.assertEqual(claim["claim_token"], winner["claim_token"])
        self.assertEqual(self._recover(goal)["claim_epoch"], 1)

    def test_concurrent_overlapping_scopes_cannot_both_be_claimed(self) -> None:
        parent = self._publish("parent_scope", "src")
        descendant = self._publish("child_scope", "src/maps")
        results = self._concurrent_claims([parent, descendant], retry_busy=True)
        self.assertEqual(sorted(result.returncode for result in results), [0, 2])
        loser = next(result for result in results if result.returncode == 2)
        self.assertIn("overlap active goal claims", loser.stderr)
        self.assertEqual(sum((goal.package / "claim.json").exists()
                             for goal in (parent, descendant)), 1)

    def test_concurrent_disjoint_scopes_can_both_be_claimed(self) -> None:
        goals = [self._publish("map_scope", "src/map"),
                 self._publish("maps_scope", "src/maps")]
        results = self._concurrent_claims(goals, retry_busy=True)
        for result in results:
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertNotEqual(*(json.loads(result.stdout)["claim_token"] for result in results))
        for goal in goals:
            self.assertTrue(self._recover(goal)["claimed"])

    def test_takeover_fences_old_token_and_is_idempotent(self) -> None:
        goal = self._publish("takeover")
        old = self._claim(goal)
        phrase = f"Authorize takeover of {goal.goal_id} from claim epoch 1"
        arguments = ["takeover", "--package", str(goal.package),
                     "--authorized-reason", phrase, "--identity", "new-owner"]
        new = self._ok(*arguments)
        repeated = self._ok(*arguments)
        self.assertEqual(new["claim_epoch"], 2)
        self.assertNotEqual(new["claim_token"], old["claim_token"])
        self.assertEqual(repeated["claim_token"], new["claim_token"])
        self.assertEqual(repeated["claim_epoch"], 2)
        self.assertIs(repeated["idempotent"], True)
        historical = json.loads(Path(new["prior_claim"]).read_text(encoding="utf-8"))
        self.assertEqual(historical["claim_token"], old["claim_token"])
        frozen_claim = (goal.package / "claim.json").read_bytes()
        frozen_status = (goal.package / "status.json").read_bytes()
        for command in (
            ["heartbeat", "--action", "Old owner still running"],
            ["state", "--state", "validating", "--action", "Old owner tries validation"],
            ["archive", "--outcome", "achieved", "--reason-code", "completed",
             "--external-goal-disposition", "complete_after_archive"],
        ):
            with self.subTest(command=command[0]):
                self._rejected(command[0], "--package", str(goal.package),
                               "--claim-token", old["claim_token"], *command[1:],
                               pattern="Claim token mismatch")
                self.assertEqual((goal.package / "claim.json").read_bytes(), frozen_claim)
                self.assertEqual((goal.package / "status.json").read_bytes(), frozen_status)
        self._ok("heartbeat", "--package", str(goal.package),
                 "--claim-token", new["claim_token"], "--action", "New owner continues")

    def test_takeover_requires_the_current_epoch_authorization(self) -> None:
        goal = self._publish("wrong_takeover")
        owner = self._claim(goal)
        self._rejected("takeover", "--package", str(goal.package), "--authorized-reason",
                       f"Authorize takeover of {goal.goal_id} from claim epoch 2",
                       pattern="exact phrase")
        self.assertFalse((goal.package / "claim_history").exists())
        self.assertEqual(self._recover(goal, owner["claim_token"])["claim_epoch"], 1)

    def test_administrative_cancellation_requires_exact_phrase_and_is_terminal(self) -> None:
        goal = self._publish("retirement")
        self._rejected("retire", "--package", str(goal.package),
                       "--reason-code", "cancelled_by_user", "--authorized-reason", "Cancel it",
                       pattern="exact phrase")
        self.assertFalse((goal.package / "outcome.json").exists())
        terminal = self._retire(goal)
        verified = self._ok("verify", "--package", str(terminal))
        self.assertEqual(verified["terminal_reason_code"], "cancelled_by_user")
        self.assertIs(self._recover(goal)["already_terminal"], True)
        self._rejected("claim", "--package", str(terminal), pattern="pending package")

    def test_administrative_retirement_cannot_bypass_a_claim(self) -> None:
        goal = self._publish("claimed_retirement")
        owner = self._claim(goal)
        self._rejected("retire", "--package", str(goal.package),
                       "--reason-code", "cancelled_by_user",
                       "--authorized-reason", f"Cancel goal {goal.goal_id}",
                       pattern="clean, unclaimed")
        self.assertEqual(self._recover(goal, owner["claim_token"])["state"], "in_progress")

    def test_claimed_cancellation_preserves_unfinished_work(self) -> None:
        goal = self._publish("claimed_cancel")
        owner = self._claim(goal)
        arguments = self._cancel_arguments(goal, owner["claim_token"])
        wrong = list(arguments)
        wrong[wrong.index("--external-goal-disposition") + 1] = "complete_after_archive"
        self._rejected(*wrong, pattern="external-goal-disposition")
        archived = self._ok(*arguments)
        terminal = Path(archived["terminal_package"])
        outcome = json.loads((terminal / "outcome.json").read_text(encoding="utf-8"))
        self.assertEqual(archived["state"], "not_achieved")
        self.assertEqual(outcome["criteria"][0]["result"], "not_run")
        self.assertTrue(outcome["remaining_work"])
        self._ok("verify", "--package", str(terminal))

    def test_replacement_waits_for_its_exact_predecessor(self) -> None:
        predecessor = self._publish("predecessor")
        replacement = self._publish("replacement", supersedes=predecessor.goal_id)
        self._rejected("claim", "--package", str(replacement.package), pattern="supersed")
        self._retire(predecessor, replacement)
        self.assertEqual(self._claim(replacement)["claim_epoch"], 1)

    def test_replacement_chain_cannot_skip_a_pending_ancestor(self) -> None:
        first = self._publish("chain_first")
        second = self._publish("chain_second", supersedes=first.goal_id)
        third = self._publish("chain_third", supersedes=second.goal_id)
        self._rejected("claim", "--package", str(third.package), pattern="supersed")
        self._retire(first, second)
        self._rejected("claim", "--package", str(third.package), pattern="supersed")
        self._retire(second, third)
        self.assertEqual(self._claim(third)["claim_epoch"], 1)

    def test_retry_revalidates_terminal_ancestor_integrity(self) -> None:
        predecessor = self._publish("retry_parent")
        terminal = self._retire(predecessor)
        retry = self._publish("retry_child", retry_of=predecessor.goal_id)
        report = terminal / "outcome.md"
        original = report.read_bytes()
        report.write_bytes(original + b"\nChanged terminal evidence.\n")
        self._rejected("verify", "--package", str(retry.package), pattern="(?i)(seal|hash|changed)")
        self._rejected("claim", "--package", str(retry.package), pattern="(?i)(seal|hash|changed)")
        self.assertFalse((retry.package / "claim.json").exists())
        report.write_bytes(original)
        self.assertEqual(self._claim(retry)["claim_epoch"], 1)

    def test_retry_cannot_reference_a_pending_goal(self) -> None:
        predecessor = self._publish("pending_parent")
        _, initialization = self._prepare("invalid_retry", retry_of=predecessor.goal_id)
        self._rejected(*initialization, pattern="(?i)(terminal|not.achieved)")
        self.assertEqual(len(list((self.workspace / "goals" / "goal_pending").iterdir())), 1)

    def test_tampered_portable_body_is_rejected_before_import(self) -> None:
        goal = self._publish("tampered_portable")
        portable = (goal.package / "portable_handoff.md").read_text(encoding="utf-8")
        begin = "<!-- INTENTWRIGHT_PORTABLE_PAYLOAD_BEGIN -->"
        end = "<!-- INTENTWRIGHT_PORTABLE_PAYLOAD_END -->"
        encoded = portable.split(begin, 1)[1].split(end, 1)[0]
        payload = json.loads(base64.b64decode("".join(encoded.split())))
        body = base64.b64decode(payload["approved_body_utf8_base64"])
        payload["approved_body_utf8_base64"] = base64.b64encode(body + b"Injected change.\n").decode()
        tampered = self.workspace / "tampered_portable.md"
        tampered.write_text(begin + "\n" + base64.b64encode(json.dumps(payload).encode()).decode()
                            + "\n" + end + "\n", encoding="utf-8")
        self._rejected("import-portable", "--workspace", str(self.workspace),
                       "--file", str(tampered), pattern="body hash")
        self._ok("verify", "--package", str(goal.package))
        self.assertEqual(len(list(goal.package.parent.iterdir())), 1)

    def test_portable_import_requires_the_receipt_bound_workspace(self) -> None:
        goal = self._publish("workspace_portable")
        detached_workspace = self.workspace / "different_workspace"
        detached_workspace.mkdir()
        self._rejected("import-portable", "--workspace", str(detached_workspace),
                       "--file", str(goal.package / "portable_handoff.md"),
                       pattern="(?i)(workspace|receipt)")
        self.assertFalse(list(detached_workspace.glob("**/goal_manifest.json")))

    def test_portable_import_restores_the_exact_approved_identity(self) -> None:
        goal = self._publish("valid_portable")
        detached = self.workspace / "detached_source"
        shutil.move(str(goal.package), str(detached))
        imported = self._ok("import-portable", "--workspace", str(self.workspace),
                            "--file", str(detached / "portable_handoff.md"))
        self.assertEqual(imported["goal_id"], goal.goal_id)
        self.assertEqual(imported["spec_sha256"], goal.manifest["spec_sha256"])
        self.assertEqual((goal.package / "approved_semantic_spec.md").read_bytes(),
                         (detached / "approved_semantic_spec.md").read_bytes())
        self.assertEqual(self._ok("verify", "--package", str(goal.package))["state"], "pending")

    def test_lineage_bearing_portable_import_is_rejected(self) -> None:
        predecessor = self._publish("portable_parent")
        self._retire(predecessor)
        retry = self._publish("portable_retry", retry_of=predecessor.goal_id)
        self._rejected("import-portable", "--workspace", str(self.workspace),
                       "--file", str(retry.package / "portable_handoff.md"), pattern="Lineage-bearing")

    def test_interrupted_archival_recovers_at_each_commit_boundary(self) -> None:
        for point in ("before_move", "after_move", "after_seal", "before_final_status"):
            with self.subTest(point=point):
                goal = self._publish(f"crash_{point}")
                location, token = self._crash_cancellation(goal, point)
                status = json.loads((location / "status.json").read_text(encoding="utf-8"))
                self.assertEqual(status["state"], "archive_prepared")
                if point in {"after_seal", "before_final_status"}:
                    temporaries = list(location.glob(".status.json.*.tmp"))
                    self._rejected("verify", "--package", str(location), pattern="exact-ID recovery")
                    self.assertEqual(list(location.glob(".status.json.*.tmp")), temporaries)
                recovered = self._recover(goal, token)
                terminal = Path(recovered["terminal_package"])
                self.assertEqual(recovered["state"], "not_achieved")
                self.assertFalse(goal.package.exists())
                self.assertFalse(list(terminal.glob(".status.json.*.tmp")))
                self._ok("verify", "--package", str(terminal))
                self.assertIs(self._recover(goal)["already_terminal"], True)

    def test_precommitted_status_temporary_with_wrong_bytes_is_preserved(self) -> None:
        goal = self._publish("corrupt_status_temporary")
        terminal, _ = self._crash_cancellation(goal, "before_final_status")
        temporary, = terminal.glob(".status.json.*.tmp")
        temporary.write_bytes(temporary.read_bytes() + b"\nChanged atomic write.\n")
        self._assert_recovery_preserves_invalid_temporary(goal, temporary)

    def test_precommitted_status_lookalike_filename_is_preserved(self) -> None:
        goal = self._publish("lookalike_status_temporary")
        terminal, _ = self._crash_cancellation(goal, "before_final_status")
        temporary, = terminal.glob(".status.json.*.tmp")
        lookalike = terminal / ".status.json.not_a_helper_uuid.tmp"
        temporary.rename(lookalike)
        self._assert_recovery_preserves_invalid_temporary(goal, lookalike)

    def test_precommitted_status_hardlink_is_preserved(self) -> None:
        goal = self._publish("hardlinked_status_temporary")
        terminal, _ = self._crash_cancellation(goal, "before_final_status")
        temporary, = terminal.glob(".status.json.*.tmp")
        retained = self.workspace / "retained_final_status.json"
        retained.write_bytes(temporary.read_bytes())
        temporary.unlink()
        os.link(retained, temporary)
        self._assert_recovery_preserves_invalid_temporary(goal, temporary)
        self.assertTrue(retained.is_file())

    def test_precommitted_status_symlink_is_preserved(self) -> None:
        goal = self._publish("symlinked_status_temporary")
        terminal, _ = self._crash_cancellation(goal, "before_final_status")
        temporary, = terminal.glob(".status.json.*.tmp")
        retained = self.workspace / "retained_symlink_status.json"
        retained.write_bytes(temporary.read_bytes())
        temporary.unlink()
        try:
            temporary.symlink_to(retained)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows account lacks permission to create symlinks")
            raise
        self._assert_recovery_preserves_invalid_temporary(goal, temporary)
        self.assertTrue(retained.is_file())

    def test_final_terminal_package_does_not_ignore_status_temporaries(self) -> None:
        goal = self._publish("extra_terminal_status")
        terminal = self._retire(goal)
        extra = terminal / (".status.json." + "a" * 32 + ".tmp")
        extra.write_bytes((terminal / "status.json").read_bytes())
        self._rejected("recover", "--workspace", str(self.workspace),
                       "--goal-id", goal.goal_id, pattern="(?i)(file set|seal)")
        self.assertTrue(extra.is_file())

    def test_terminal_recovery_refuses_a_missing_seal(self) -> None:
        goal = self._publish("missing_terminal_seal")
        terminal = self._retire(goal)
        (terminal / "terminal_seal.json").unlink()
        self._rejected("recover", "--workspace", str(self.workspace), "--goal-id", goal.goal_id,
                       pattern="(?i)(seal|corruption)")
        self.assertFalse((terminal / "terminal_seal.json").exists())


if __name__ == "__main__":
    unittest.main()
