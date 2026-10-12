#!/usr/bin/env python3
"""Build clean, reproducible Intentwright release archives using only the stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
CORE_FILES = (
    "SKILL.md",
    "README.md",
    "LICENSE",
    "VERSION",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "agents/openai.yaml",
    "references/interview-playbook.md",
    "references/intentwright-package-contract.md",
    "scripts/intentwright_lifecycle.py",
)
SPEC_FILES = ("SKILL.md", "README.md", "LICENSE", "VERSION")
SOURCE_FILES = (
    ".gitattributes",
    ".gitignore",
    "pyproject.toml",
    "scripts/build_release.py",
    ".github/workflows/validate.yml",
    ".github/workflows/release.yml",
)
OPTIONAL_SOURCE_FILES = ("docs/skill-evaluation.md", "tests/fixtures/skill-prompts.json")
IGNORED_DIRECTORIES = {
    ".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", "dist",
    "goals", "goal_pending", "goal_achieved", "goal_not_achieved",
}


class BuildError(ValueError):
    """The source tree cannot produce a valid release."""


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_plain_path(path: Path, root: Path) -> None:
    """Reject links/reparse points anywhere between the source root and a file."""
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise BuildError(f"Source path escapes its root: {path}") from error
    current = root
    for part in (None, *relative.parts):
        if part is not None:
            current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError as error:
            raise BuildError(f"Required source path is missing: {current}") from error
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise BuildError(f"Symbolic links and reparse points are not allowed: {current}")


def text_file(root: Path, relative: str) -> bytes:
    path = root.joinpath(*PurePosixPath(relative).parts)
    assert_plain_path(path, root)
    if not path.is_file():
        raise BuildError(f"Expected a regular file: {path}")
    try:
        content = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise BuildError(f"Release files must be UTF-8 text: {path}") from error
    if content.startswith("\ufeff"):
        raise BuildError(f"Release files must not have a UTF-8 BOM: {path}")
    # Canonical bytes make Windows/macOS/Linux checkouts produce the same archive.
    return content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def optional_tree(root: Path, relative: str, suffixes: set[str]) -> list[str]:
    directory = root / relative
    if not directory.exists() and not directory.is_symlink():
        return []
    assert_plain_path(directory, root)
    if not directory.is_dir():
        raise BuildError(f"Expected a directory: {directory}")
    result = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith(".") or child.name in IGNORED_DIRECTORIES:
            continue
        assert_plain_path(child, root)
        child_relative = child.relative_to(root).as_posix()
        if child.is_dir():
            result.extend(optional_tree(root, child_relative, suffixes))
        elif child.suffix in suffixes:
            result.append(child_relative)
    return result


def optional_files(root: Path, relatives: tuple[str, ...]) -> list[str]:
    result = []
    for relative in relatives:
        path = root / relative
        if path.exists() or path.is_symlink():
            assert_plain_path(path, root)
            result.append(relative)
    return result


def version(root: Path) -> str:
    value = text_file(root, "VERSION").decode().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise BuildError(f"VERSION must contain one semantic release version: {root}")
    return value


def validate_skill(payload: dict[str, bytes], expected_name: str) -> None:
    text = payload["SKILL.md"].decode()
    frontmatter = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not frontmatter:
        raise BuildError(f"{expected_name}: SKILL.md has no YAML frontmatter")
    if not re.search(rf"^name: {re.escape(expected_name)}$", frontmatter[1], re.MULTILINE):
        raise BuildError(f"{expected_name}: SKILL.md has the wrong skill name")
    if not re.search(r"^description: \S", frontmatter[1], re.MULTILINE):
        raise BuildError(f"{expected_name}: SKILL.md needs a non-empty description")
    for target in re.findall(r"\]\(([^\s)]+)\)", text):
        if ":" in target or target.startswith("#"):
            continue
        target = target.split("#", 1)[0]
        if target and target not in payload:
            raise BuildError(f"{expected_name}: SKILL.md references a missing file: {target}")
    if expected_name == "intentwright-spec":
        if re.search(r"(?:scripts/[\w.-]+\.py|references/[\w.-]+\.md|"
                     r"\$intentwright\b(?!-spec))", text):
            raise BuildError("The specification edition must not depend on full-edition files")
        if re.search(r"\]\((?![a-z]+:|#)[^\s)]+\)", text):
            raise BuildError("The marketplace SKILL.md must be self-contained")


def collect_codex(root: Path) -> tuple[str, dict[str, bytes]]:
    release_version = version(root)
    project = text_file(root, "pyproject.toml").decode()
    project_section = re.search(r"(?ms)^\[project\]\n(.*?)(?=^\[|\Z)", project)
    declared = re.search(r'^version = "([^"]+)"$', project_section[1], re.MULTILINE) \
        if project_section else None
    if not declared or declared[1] != release_version:
        raise BuildError("VERSION and pyproject.toml project version differ")
    paths = (*CORE_FILES, *optional_tree(root, "examples", {".md", ".json", ".txt"}))
    payload = {path: text_file(root, path) for path in paths}
    validate_skill(payload, "intentwright")
    if not re.search(rb"^SCHEMA_VERSION = 2$", payload["scripts/intentwright_lifecycle.py"], re.M):
        raise BuildError("This release builder expects the unchanged lifecycle schema 2")
    return release_version, payload


def collect_spec(root: Path) -> tuple[str, dict[str, bytes]]:
    spec_root = root / "marketplace" / "intentwright-spec"
    assert_plain_path(spec_root, root)
    release_version = version(spec_root)
    paths = (*SPEC_FILES, *optional_tree(spec_root, "examples", {".md", ".json", ".txt"}))
    payload = {path: text_file(spec_root, path) for path in paths}
    payload.update({path: text_file(spec_root, path)
                    for path in optional_files(spec_root, ("agents/openai.yaml",))})
    validate_skill(payload, "intentwright-spec")
    if payload["LICENSE"] != text_file(root, "LICENSE"):
        raise BuildError("The Spec edition must preserve the repository's MIT license")
    return release_version, payload


def collect_source(root: Path, codex: dict[str, bytes], spec: dict[str, bytes]) -> dict[str, bytes]:
    payload = dict(codex)
    extra = (*SOURCE_FILES, *optional_tree(root, "tests", {".py"}),
             *optional_files(root, OPTIONAL_SOURCE_FILES))
    payload.update({path: text_file(root, path) for path in extra})
    payload.update({f"marketplace/intentwright-spec/{path}": data for path, data in spec.items()})
    return payload


def check_output_file(output: Path) -> None:
    if output.exists() or output.is_symlink():
        metadata = output.lstat()
        if (not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & 0x400):
            raise BuildError(f"Refusing to replace a non-regular release output: {output}")


def atomic_write(output: Path, data: bytes) -> None:
    check_output_file(output)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_archive(output: Path, edition: str, release_version: str,
                  prefix: str, payload: dict[str, bytes]) -> dict[str, object]:
    files = {prefix + path: {"sha256": sha256(data), "size": len(data)}
             for path, data in sorted(payload.items())}
    manifest = {"manifest_version": 1, "edition": edition, "version": release_version,
                "files": files}
    contents = {prefix + path: data for path, data in payload.items()}
    contents[prefix + "MANIFEST.json"] = json_bytes(manifest)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        # Stored entries avoid cross-zlib differences; these small text bundles remain small.
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in sorted(contents.items()):
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, data)
        check_output_file(output)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)
    data = output.read_bytes()
    return {"filename": output.name, "edition": edition, "version": release_version,
            "sha256": sha256(data), "size": len(data), "files": files}


def build(source_dir: Path, output_dir: Path, edition: str = "all",
          include_source: bool = False) -> list[dict[str, object]]:
    root = source_dir.absolute()
    assert_plain_path(root, root)
    codex_version, codex = collect_codex(root) if edition in {"all", "codex"} else ("", {})
    spec_version, spec = collect_spec(root) if edition in {"all", "spec"} else ("", {})
    if include_source and edition != "all":
        raise BuildError("--include-source requires --edition all")
    source = collect_source(root, codex, spec) if include_source else None
    output_dir = output_dir.absolute()
    if output_dir.is_symlink():
        raise BuildError("The release output directory must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    assert_plain_path(output_dir, output_dir)
    releases = []
    if codex:
        releases.append(write_archive(output_dir / f"intentwright-codex-{codex_version}.zip",
                                      "codex", codex_version, "intentwright/", codex))
    if spec:
        releases.append(write_archive(output_dir / f"intentwright-spec-{spec_version}-agensi.zip",
                                      "spec", spec_version, "", spec))
    if source is not None:
        releases.append(write_archive(output_dir / f"intentwright-source-{codex_version}.zip",
                                      "source", codex_version,
                                      f"intentwright-source-{codex_version}/", source))
    index = json_bytes({"manifest_version": 1, "archives": releases})
    atomic_write(output_dir / "RELEASES.json", index)
    checksums = {str(release["filename"]): str(release["sha256"]) for release in releases}
    checksums["RELEASES.json"] = sha256(index)
    checksum_text = "".join(f"{digest}  {name}\n" for name, digest in sorted(checksums.items()))
    atomic_write(output_dir / "SHA256SUMS", checksum_text.encode("utf-8"))
    return releases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--edition", choices=("all", "codex", "spec"), default="all")
    parser.add_argument("--include-source", action="store_true")
    args = parser.parse_args()
    try:
        releases = build(args.source_dir, args.output_dir, args.edition, args.include_source)
    except (BuildError, OSError) as error:
        parser.exit(1, f"Release build failed: {error}\n")
    for release in releases:
        print(f"{release['filename']}  {release['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
