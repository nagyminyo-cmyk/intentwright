from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("intentwright_release", ROOT / "scripts/build_release.py")
assert SPEC and SPEC.loader
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


def fixture(root: Path) -> None:
    """A complete small skill fixture makes exclusion and corruption tests isolated."""
    for relative in (*RELEASE.CORE_FILES, *RELEASE.SOURCE_FILES):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Fixture documentation.\n", encoding="utf-8")
    (root / "VERSION").write_text("2.1.0\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "intentwright"\nversion = "2.1.0"\n', encoding="utf-8"
    )
    (root / "SKILL.md").write_text(
        "---\nname: intentwright\ndescription: Fixture skill\n---\n"
        "Read [playbook](references/interview-playbook.md).\n", encoding="utf-8"
    )
    (root / "scripts/intentwright_lifecycle.py").write_text(
        "SCHEMA_VERSION = 2\n", encoding="utf-8"
    )
    spec = root / "marketplace/intentwright-spec"
    spec.mkdir(parents=True)
    for name in RELEASE.SPEC_FILES:
        (spec / name).write_text("Fixture documentation.\n", encoding="utf-8")
    (spec / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (spec / "SKILL.md").write_text(
        "---\nname: intentwright-spec\ndescription: Self-contained fixture\n---\n"
        "Interview, read back the specification, and wait for explicit approval.\n",
        encoding="utf-8",
    )


class ReleasePackagingTests(unittest.TestCase):
    def test_archives_are_reproducible_and_have_complete_hash_manifests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-packaging-") as temporary:
            directory = Path(temporary)
            root = directory / "source"
            root.mkdir()
            fixture(root)
            first = directory / "first"
            second = directory / "second"
            RELEASE.build(root, first, include_source=True)
            # Checkout mtimes and platform line endings must not affect release bytes.
            for path in root.rglob("*"):
                if path.is_file():
                    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                    path.write_bytes(data.replace(b"\n", b"\r\n"))
                    os.utime(path, (1700000000, 1700000000))
            RELEASE.build(root, second, include_source=True)
            self.assertEqual(sorted(p.name for p in first.iterdir()),
                             sorted(p.name for p in second.iterdir()))
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            index = json.loads((first / "RELEASES.json").read_text())
            self.assertEqual(len(index["archives"]), 3)
            for package in index["archives"]:
                path = first / package["filename"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), package["sha256"])
                with zipfile.ZipFile(path) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                    manifest_name = next(n for n in archive.namelist() if n.endswith("MANIFEST.json"))
                    manifest = json.loads(archive.read(manifest_name))
                    self.assertEqual(manifest["files"], package["files"])
                    self.assertEqual(set(archive.namelist()), set(manifest["files"]) | {manifest_name})
                    for name, metadata in manifest["files"].items():
                        data = archive.read(name)
                        self.assertEqual(hashlib.sha256(data).hexdigest(), metadata["sha256"])
                        self.assertEqual(len(data), metadata["size"])
                    for info in archive.infolist():
                        self.assertEqual(info.date_time, RELEASE.ZIP_TIMESTAMP)
                        self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                        self.assertNotIn("..", Path(info.filename).parts)
                        self.assertFalse(info.filename.startswith("/"))
            for line in (first / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256((first / name).read_bytes()).hexdigest())

    def test_upload_skill_is_at_zip_root_and_private_files_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-exclusions-") as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            fixture(root)
            optional_files = {
                "marketplace/intentwright-spec/agents/openai.yaml": "interface: {}\n",
                "docs/skill-evaluation.md": "Source-only evaluation guidance.\n",
                "tests/fixtures/skill-prompts.json": "[]\n",
            }
            for name, content in optional_files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            forbidden = (".env", ".git/config", "goals/goal_pending/private.md",
                         ".intentwright-workspace.json", "examples/secret.env",
                         "examples/.git/private.md", "examples/goals/private.md",
                         "scripts/private_credentials.txt", "tests/__pycache__/private.py")
            for name in forbidden:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("PRIVATE_MARKER", encoding="utf-8")
            output = Path(temporary) / "out"
            RELEASE.build(root, output, include_source=True)
            with zipfile.ZipFile(output / "intentwright-spec-1.0.0-agensi.zip") as archive:
                self.assertIn("SKILL.md", archive.namelist())
                self.assertIn("LICENSE", archive.namelist())
                self.assertIn("agents/openai.yaml", archive.namelist())
                self.assertNotIn("intentwright-spec/SKILL.md", archive.namelist())
            for path in output.glob("*.zip"):
                with zipfile.ZipFile(path) as archive:
                    for name in archive.namelist():
                        self.assertNotIn(b"PRIVATE_MARKER", archive.read(name))
                    self.assertFalse(any(".git/" in n or "__pycache__/" in n or "goals/" in n
                                         for n in archive.namelist()))
                    for name in ("docs/skill-evaluation.md", "tests/fixtures/skill-prompts.json"):
                        included = any(n.endswith("/" + name) for n in archive.namelist())
                        self.assertEqual(included, "source" in path.name, name)

    def test_builder_rejects_version_mismatch_and_missing_dependency(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-invalid-") as temporary:
            root = Path(temporary)
            fixture(root)
            (root / "VERSION").write_text("2.9.0\n", encoding="utf-8")
            with self.assertRaisesRegex(RELEASE.BuildError, "version differ"):
                RELEASE.collect_codex(root)
            (root / "VERSION").write_text("2.1.0\n", encoding="utf-8")
            (root / "references/interview-playbook.md").unlink()
            with self.assertRaisesRegex(RELEASE.BuildError, "missing"):
                RELEASE.collect_codex(root)

    def test_spec_rejects_an_external_file_dependency(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-spec-dependency-") as temporary:
            root = Path(temporary)
            fixture(root)
            skill = root / "marketplace/intentwright-spec/SKILL.md"
            skill.write_text(skill.read_text() + "\nRead [notes](README.md).\n", encoding="utf-8")
            with self.assertRaisesRegex(RELEASE.BuildError, "self-contained"):
                RELEASE.collect_spec(root)

    def test_builder_rejects_symlink_in_an_allowed_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-links-") as temporary:
            root = Path(temporary)
            fixture(root)
            target = root / "examples/private.md"
            target.parent.mkdir()
            outside = root / "outside.md"
            outside.write_text("PRIVATE_MARKER", encoding="utf-8")
            try:
                target.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"Creating symlinks is unavailable on this host: {error}")
            with self.assertRaisesRegex(RELEASE.BuildError, "links"):
                RELEASE.collect_codex(root)

    def test_actual_codex_archive_extracts_and_helper_runs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="intentwright-install-smoke-") as temporary:
            output = Path(temporary) / "release"
            releases = RELEASE.build(ROOT, output, edition="codex")
            extracted = Path(temporary) / "installed"
            with zipfile.ZipFile(output / str(releases[0]["filename"])) as archive:
                archive.extractall(extracted)
            skill_root = extracted / "intentwright"
            for name in RELEASE.CORE_FILES:
                self.assertTrue((skill_root / name).is_file(), name)
            result = subprocess.run(
                [sys.executable, str(skill_root / "scripts/intentwright_lifecycle.py"), "--help"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("approval-receipt", result.stdout)
            self.assertIn("publish", result.stdout)


if __name__ == "__main__":
    unittest.main()
