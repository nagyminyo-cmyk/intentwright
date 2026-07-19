from __future__ import annotations

import argparse
import importlib.util
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "goal_lifecycle.py"
MODULE_SPEC = importlib.util.spec_from_file_location("goal_forge_lifecycle", HELPER)
assert MODULE_SPEC and MODULE_SPEC.loader
LIFECYCLE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(LIFECYCLE)


class LifecycleContractTests(unittest.TestCase):
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
