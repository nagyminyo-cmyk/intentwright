from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "intentwright_lifecycle.py"
MODULE_SPEC = importlib.util.spec_from_file_location("intentwright_lifecycle", HELPER)
assert MODULE_SPEC and MODULE_SPEC.loader
LIFECYCLE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(LIFECYCLE)


class LifecycleContractTests(unittest.TestCase):
    def test_public_surface_has_no_stale_identity(self) -> None:
        banned = (
            "Goal " + "Forge",
            "$goal" + "-forge",
            "nagyminyo-cmyk/goal" + "-forge",
            "scripts/goal" + "_lifecycle.py",
            "references/goal" + "-package-contract.md",
            "goal" + "_forge_lifecycle",
            "goal" + "-forge-e2e",
        )
        ignored_directories = {".git", ".venv", ".ruff_cache", "__pycache__"}
        text_suffixes = {".md", ".py", ".toml", ".yaml", ".yml", ".txt"}
        text_names = {".gitignore", ".gitattributes", "VERSION"}
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or any(part in ignored_directories for part in path.parts)
                or (path.suffix not in text_suffixes and path.name not in text_names)
            ):
                continue
            content = path.read_text(encoding="utf-8")
            for token in banned:
                with self.subTest(path=path.relative_to(ROOT), token=token):
                    self.assertNotIn(token, content)

    def test_public_identity_is_intentwright(self) -> None:
        self.assertEqual(LIFECYCLE.ROOT_MARKER, ".intentwright-root.json")
        self.assertEqual(LIFECYCLE.WORKSPACE_MARKER, ".intentwright-workspace.json")
        self.assertEqual(
            LIFECYCLE.PORTABLE_BEGIN,
            "<!-- INTENTWRIGHT_PORTABLE_PAYLOAD_BEGIN -->",
        )
        self.assertIsNotNone(
            LIFECYCLE.INTERVIEW_ID_RE.fullmatch(
                "iwi_20260719T120000000Z_public_identity_1a2b"
            )
        )
        self.assertIsNone(
            LIFECYCLE.INTERVIEW_ID_RE.fullmatch(
                "gfi_20260719T120000000Z_public_identity_1a2b"
            )
        )

    def test_legacy_workspace_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-legacy-guard-") as temporary:
            workspace = Path(temporary).resolve()
            legacy_marker = workspace / LIFECYCLE.LEGACY_WORKSPACE_MARKER
            legacy_marker.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                LIFECYCLE.LifecycleError,
                "before Intentwright",
            ):
                LIFECYCLE.workspace_and_root(
                    str(workspace),
                    "goals",
                    create=True,
                )
            self.assertFalse((workspace / LIFECYCLE.WORKSPACE_MARKER).exists())

    def test_legacy_root_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-legacy-root-") as temporary:
            workspace = Path(temporary).resolve()
            root = workspace / "goals"
            root.mkdir()
            (root / LIFECYCLE.LEGACY_ROOT_MARKER).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                LIFECYCLE.LifecycleError,
                "before Intentwright",
            ):
                LIFECYCLE.workspace_and_root(
                    str(workspace),
                    "goals",
                    create=True,
                )

    def test_exclusion_sentinel_rejects_the_legacy_registration_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-exclusion-") as temporary:
            workspace = Path(temporary).resolve()
            _, root = LIFECYCLE.workspace_and_root(
                str(workspace),
                "intent_goals",
                create=True,
            )
            sentinel = json.loads(
                (workspace / LIFECYCLE.LEGACY_WORKSPACE_MARKER).read_text(encoding="utf-8")
            )
            self.assertEqual(sentinel["schema_version"], 2)
            self.assertEqual(sentinel["kind"], LIFECYCLE.LEGACY_EXCLUSION_KIND)
            legacy_contract_accepts = (
                sentinel["schema_version"] == 1
                and sentinel["kind"] == "goal" + "-forge-workspace"
                and sentinel["relative_root"] == root.name
            )
            self.assertFalse(legacy_contract_accepts)

    def test_slug_normalization_is_stable(self) -> None:
        self.assertEqual(
            LIFECYCLE.sanitize_slug("  Rebuild: Café Map!  "),
            "rebuild_cafe_map",
        )
        self.assertEqual(LIFECYCLE.sanitize_slug("CON"), "goal_con")

    def test_goal_root_is_one_safe_relative_directory(self) -> None:
        self.assertEqual(LIFECYCLE.safe_relative_dir("goals"), Path("goals"))
        for invalid in ("../goals", "nested/goals", "goals.", "CON", " goals"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(LIFECYCLE.LifecycleError):
                    LIFECYCLE.safe_relative_dir(invalid)

    def test_scope_normalization_reduces_descendants(self) -> None:
        self.assertEqual(
            LIFECYCLE.normalize_write_scopes(
                ["src/maps", "docs", "src", "docs"],
            ),
            ["docs", "src"],
        )
        self.assertEqual(LIFECYCLE.normalize_write_scopes([".", "src"]), ["."])

    def test_scope_overlap_uses_path_components(self) -> None:
        self.assertTrue(
            LIFECYCLE.scopes_overlap(["src/maps"], ["src/maps/runtime"]),
        )
        self.assertTrue(LIFECYCLE.scopes_overlap(["."], ["docs"]))
        self.assertFalse(
            LIFECYCLE.scopes_overlap(["src/map"], ["src/maps"]),
        )

    def test_approval_phrase_binds_revision_and_receipt(self) -> None:
        receipt = "a" * 64
        self.assertEqual(
            LIFECYCLE.expected_approval_phrase(3, receipt),
            f"Approve spec v3 receipt {receipt}",
        )

    def test_generated_handoffs_use_the_platform_python_launcher(self) -> None:
        expected = "python" if os.name == "nt" else "python3"
        self.assertEqual(LIFECYCLE.python_launcher(), expected)

    def test_cli_exposes_the_complete_lifecycle(self) -> None:
        parser = LIFECYCLE.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(
            set(subparsers.choices),
            {
                "approval-receipt",
                "init",
                "publish",
                "discard-staging",
                "verify",
                "claim",
                "takeover",
                "heartbeat",
                "state",
                "archive",
                "recover",
                "retire",
                "import-portable",
            },
        )


if __name__ == "__main__":
    unittest.main()
