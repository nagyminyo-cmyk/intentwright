#!/usr/bin/env python3
"""Deterministic lifecycle helper for Intentwright packages.

The helper creates and atomically publishes isolated goal packages, verifies
immutable specifications, coordinates exclusive executor claims, and archives
terminal packages without overwriting or merging them.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import textwrap
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator


SCHEMA_VERSION = 2
ROOT_MARKER = ".intentwright-root.json"
WORKSPACE_MARKER = ".intentwright-workspace.json"
LEGACY_ROOT_MARKER = ".goal-forge-root.json"
LEGACY_WORKSPACE_MARKER = ".goal-forge-workspace.json"
LEGACY_COORDINATION_DIRECTORY = ".goal-forge-coordination"
LEGACY_EXCLUSION_KIND = "intentwright-legacy-exclusion"
SEAL_FILE = "package_seal.json"
TERMINAL_SEAL_FILE = "terminal_seal.json"
APPROVED_BODY_FILE = "approved_semantic_spec.md"
PENDING = "goal_pending"
ACHIEVED = "goal_achieved"
NOT_ACHIEVED = "goal_not_achieved"
LOCKS = ".locks"
LOCATION_NAMES = (PENDING, ACHIEVED, NOT_ACHIEVED)
ACTIVE_STATES = {"pending", "in_progress", "validating", "paused", "archive_prepared"}
TERMINAL_STATES = {"achieved", "not_achieved"}
NOT_ACHIEVED_CODES = {
    "blocked",
    "cancelled_by_user",
    "superseded",
    "abandoned_by_user",
}
ADMIN_RETIRE_CODES = {"cancelled_by_user", "superseded", "abandoned_by_user"}
GOAL_ID_RE = re.compile(
    r"^g_\d{8}T\d{9}Z_(?P<slug>[a-z0-9_]+)_(?P<random>[0-9a-f]{8})$"
)
INTERVIEW_ID_RE = re.compile(
    r"^iwi_\d{8}T\d{9}Z_[a-z0-9_]+_[0-9a-f]{4}$"
)
ACCEPTANCE_RE = re.compile(r"\bAC-\d{3,}\b", re.IGNORECASE)
ALL_REQUIREMENT_RE = re.compile(
    r"\b(?:REQ|QUAL|PRES|CON|SEC|PERF|UX|OPS|DATA|CONTENT)-\d{3,}\b",
    re.IGNORECASE,
)
STRETCH_ACCEPTANCE_RE = re.compile(r"\bSAC-\d{3,}\b", re.IGNORECASE)
PORTABLE_BEGIN = "<!-- INTENTWRIGHT_PORTABLE_PAYLOAD_BEGIN -->"
PORTABLE_END = "<!-- INTENTWRIGHT_PORTABLE_PAYLOAD_END -->"
UNIVERSAL_DIMENSIONS = (
    "Outcome and audience",
    "Current state and context",
    "Scope and priority",
    "Inputs, outputs, and interfaces",
    "Golden path and state behavior",
    "Quality and taste",
    "Constraints and dependencies",
    "Compatibility and preservation",
    "Failure, recovery, and operations",
    "Security, privacy, and authority",
    "Performance and reliability",
    "Accessibility, inclusion, and localization",
    "Validation and evidence",
    "Execution authority",
    "Completion and lifecycle",
)
DOMAIN_BRANCHES = (
    "Existing software or repository change",
    "Greenfield software, service, CLI, or API",
    "UI, UX, visual design, or brand",
    "Game",
    "Research, analysis, or recommendation",
    "Writing, documentation, or content",
    "Automation, operations, or agent workflow",
    "Security or defensive engineering",
    "Data, AI, or model-driven system",
    "Product, business, or process",
    "Hardware, physical, or environment-dependent work",
    "Education, tutorial, or learning system",
    "General creative deliverable",
)
WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class LifecycleError(RuntimeError):
    """A safe, user-actionable lifecycle failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def goal_timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def safe_single_line(value: str, label: str, *, maximum: int = 500) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise LifecycleError(f"{label} cannot be empty")
    if cleaned != value:
        raise LifecycleError(f"{label} cannot have leading or trailing whitespace")
    if len(cleaned) > maximum:
        raise LifecycleError(f"{label} exceeds {maximum} characters")
    if any(unicodedata.category(character).startswith("C") for character in cleaned):
        raise LifecycleError(f"{label} cannot contain control or formatting characters")
    return cleaned


def parse_utc_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
        value,
    ) is None:
        raise LifecycleError(f"{label} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LifecycleError(f"{label} is not a valid timestamp") from exc
    return parsed


def is_link_like(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0))
    return (
        stat.S_ISLNK(info.st_mode)
        or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    )


def has_alternate_data_streams(path: Path) -> bool:
    if os.name != "nt" or not path.is_file():
        return False
    import ctypes
    from ctypes import wintypes

    class WIN32_FIND_STREAM_DATA(ctypes.Structure):
        _fields_ = [
            ("StreamSize", ctypes.c_longlong),
            ("cStreamName", wintypes.WCHAR * (260 + 36)),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(WIN32_FIND_STREAM_DATA),
        wintypes.DWORD,
    ]
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(WIN32_FIND_STREAM_DATA),
    ]
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = [wintypes.HANDLE]
    find_close.restype = wintypes.BOOL

    data = WIN32_FIND_STREAM_DATA()
    handle = find_first(str(path), 0, ctypes.byref(data), 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        if error in {2, 38}:
            return False
        raise LifecycleError(
            f"Cannot inspect alternate data streams for {path}: Windows error {error}"
        )
    try:
        stream_names = [data.cStreamName]
        while find_next(handle, ctypes.byref(data)):
            stream_names.append(data.cStreamName)
        error = ctypes.get_last_error()
        if error not in {0, 38}:
            raise LifecycleError(
                f"Cannot finish alternate-stream inspection for {path}: Windows error {error}"
            )
    finally:
        find_close(handle)
    return any(name != "::$DATA" for name in stream_names)


def validate_unique_regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise LifecycleError(f"Cannot inspect {label} {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise LifecycleError(f"{label} must be a regular file: {path}")
    if info.st_nlink != 1:
        raise LifecycleError(f"{label} cannot be hardlinked: {path}")
    if is_link_like(path):
        raise LifecycleError(f"{label} cannot be a link or reparse point: {path}")
    if has_alternate_data_streams(path):
        raise LifecycleError(f"{label} cannot contain NTFS alternate data streams: {path}")


def read_utf8_exact(path: Path) -> str:
    if not path.is_file():
        raise LifecycleError(f"Expected a regular UTF-8 file: {path}")
    validate_unique_regular_file(path, "UTF-8 input")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except (OSError, UnicodeError) as exc:
        raise LifecycleError(f"Cannot read UTF-8 from {path}: {exc}") from exc


def validate_canonical_body_text(text: str) -> None:
    if text.startswith("\ufeff"):
        raise LifecycleError("Approved semantic body must be UTF-8 without a byte-order mark")
    if "\r" in text:
        raise LifecycleError("Approved semantic body must use canonical LF line endings")
    if not text.endswith("\n"):
        raise LifecycleError("Approved semantic body must end with exactly one LF newline")
    if text.endswith("\n\n"):
        raise LifecycleError("Approved semantic body must end with exactly one LF newline")


def validate_canonical_body_file(path: Path, expected_hash: str) -> str:
    text = read_utf8_exact(path)
    validate_canonical_body_text(text)
    actual_hash = sha256_file(path)
    if not secrets.compare_digest(expected_hash, actual_hash):
        raise LifecycleError(
            "Approved semantic body does not match the SHA-256 shown before approval: "
            f"expected {expected_hash}, got {actual_hash}"
        )
    return text


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or is_link_like(path):
        raise LifecycleError(f"Expected a regular JSON file: {path}")
    try:
        value = json.loads(read_utf8_exact(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"Expected a JSON object in {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def create_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise LifecycleError(f"Refusing to overwrite existing file: {path}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise LifecycleError(f"Expected a regular file for hashing: {path}")
    validate_unique_regular_file(path, "Hashed input")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path: Path, parent: Path) -> bool:
    try:
        normalized_path = os.path.normcase(os.path.abspath(str(path)))
        normalized_parent = os.path.normcase(os.path.abspath(str(parent)))
        return os.path.commonpath([normalized_path, normalized_parent]) == normalized_parent
    except ValueError:
        return False


def exact_schema_version(value: Any, label: str) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise LifecycleError(f"{label} has an unsupported schema version")


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def atomic_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def canonical_workspace(workspace_arg: str) -> Path:
    workspace_input = Path(workspace_arg).expanduser()
    if not workspace_input.exists() or not workspace_input.is_dir():
        raise LifecycleError(f"Workspace does not exist or is not a directory: {workspace_input}")
    if is_link_like(workspace_input):
        raise LifecycleError(
            f"Refusing a symlink, junction, or reparse-point workspace: {workspace_input}"
        )
    workspace = workspace_input.resolve(strict=True)
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        git_root_text = completed.stdout.strip()
        if git_root_text:
            git_root = Path(git_root_text).resolve(strict=True)
            if os.path.normcase(str(git_root)) != os.path.normcase(str(workspace)):
                raise LifecycleError(
                    "Use the canonical Git worktree root as --workspace so overlapping nested "
                    f"workspaces cannot acquire independent leases: {git_root}"
                )
    for ancestor in workspace.parents:
        for marker_name in (WORKSPACE_MARKER, LEGACY_WORKSPACE_MARKER):
            marker = ancestor / marker_name
            if marker.exists():
                if is_link_like(marker):
                    raise LifecycleError(f"Unsafe ancestor lifecycle marker: {marker}")
                raise LifecycleError(
                    "This path is nested inside an already registered lifecycle workspace; "
                    f"use its canonical workspace root: {ancestor}"
                )
    return workspace


def find_descendant_workspace_markers(workspace: Path) -> list[Path]:
    found: list[Path] = []
    for directory, dir_names, file_names in os.walk(workspace, followlinks=False):
        base = Path(directory)
        safe_dirs: list[str] = []
        for name in dir_names:
            candidate = base / name
            if name == ".git" or is_link_like(candidate):
                continue
            safe_dirs.append(name)
        dir_names[:] = safe_dirs
        for marker_name in (WORKSPACE_MARKER, LEGACY_WORKSPACE_MARKER):
            marker = base / marker_name
            if marker != workspace / marker_name and marker_name in file_names:
                if is_link_like(marker):
                    raise LifecycleError(f"Unsafe nested lifecycle marker: {marker}")
                found.append(marker)
    return found


def refuse_legacy_workspace(workspace: Path, root: Path | None = None) -> None:
    workspace_marker = workspace / LEGACY_WORKSPACE_MARKER
    root_marker = root / LEGACY_ROOT_MARKER if root is not None else None
    for marker in (workspace_marker, root_marker):
        if marker is None or not marker.exists():
            continue
        if is_link_like(marker):
            raise LifecycleError(f"Unsafe legacy lifecycle marker: {marker}")
        if marker == workspace_marker:
            value = read_json(marker)
            expected_relative = (
                root.resolve(strict=False).relative_to(workspace).as_posix()
                if root is not None
                else value.get("relative_root")
            )
            if (
                type(value.get("schema_version")) is int
                and value.get("schema_version") == SCHEMA_VERSION
                and value.get("kind") == LEGACY_EXCLUSION_KIND
                and value.get("canonical_workspace") == os.path.normcase(str(workspace))
                and value.get("relative_root") == expected_relative
            ):
                continue
        raise LifecycleError(
            "This workspace contains lifecycle state created before Intentwright. "
            "Finish or retire those packages with their original installed helper, then use "
            "Intentwright in a clean workspace or deliberately cleared goal root. Existing "
            "sealed packages must never be renamed in place."
        )


def ensure_legacy_exclusion_marker(workspace: Path, relative_root: Path) -> None:
    marker = workspace / LEGACY_WORKSPACE_MARKER
    expected_root = relative_root.as_posix()
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": LEGACY_EXCLUSION_KIND,
        "canonical_workspace": os.path.normcase(str(workspace)),
        "relative_root": expected_root,
        "created_at": utc_now(),
    }
    if not marker.exists():
        try:
            create_json_exclusive(marker, value)
        except LifecycleError:
            if not marker.exists():
                raise
    registered = read_json(marker)
    if (
        type(registered.get("schema_version")) is not int
        or registered.get("schema_version") != SCHEMA_VERSION
        or registered.get("kind") != LEGACY_EXCLUSION_KIND
        or registered.get("canonical_workspace") != os.path.normcase(str(workspace))
        or registered.get("relative_root") != expected_root
    ):
        raise LifecycleError(
            "This workspace already contains incompatible lifecycle registration state"
        )


def assert_no_link_like(root: Path) -> None:
    if is_link_like(root):
        raise LifecycleError(f"Refusing a symlink, junction, or reparse-point package: {root}")
    for directory, dir_names, file_names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in [*dir_names, *file_names]:
            candidate = base / name
            if is_link_like(candidate):
                raise LifecycleError(
                    f"Goal packages cannot contain symlinks, junctions, or reparse points: {candidate}"
                )
            if candidate.is_file():
                validate_unique_regular_file(candidate, "Goal-package file")


def safe_relative_dir(value: str) -> Path:
    if not isinstance(value, str):
        raise LifecycleError("--goals-dir must be a string")
    if value.strip() != value or any(
        unicodedata.category(character).startswith("C") for character in value
    ):
        raise LifecycleError("--goals-dir cannot contain whitespace padding or control characters")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value) is None:
        raise LifecycleError(
            "--goals-dir must be one envelope-safe directory name using letters, digits, '.', '_', or '-'"
        )
    if value.endswith(".") or value.casefold().split(".", 1)[0] in WINDOWS_RESERVED:
        raise LifecycleError("--goals-dir is not a safe cross-platform directory name")
    candidate = Path(value)
    if candidate.is_absolute() or not candidate.parts:
        raise LifecycleError("--goals-dir must be a non-empty relative path")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise LifecycleError("--goals-dir cannot contain '.', '..', or empty path components")
    if len(candidate.parts) != 1:
        raise LifecycleError("--goals-dir must be one workspace-relative directory name")
    return candidate


def workspace_and_root(
    workspace_arg: str, goals_dir: str, *, create: bool
) -> tuple[Path, Path]:
    workspace = canonical_workspace(workspace_arg)
    relative_root = safe_relative_dir(goals_dir)
    root_input = workspace.joinpath(relative_root)

    current = workspace
    for part in relative_root.parts:
        current = current / part
        if current.exists() and is_link_like(current):
            raise LifecycleError(f"Refusing a link or reparse point in the goal-root path: {current}")

    root = root_input.resolve(strict=False)
    if root == workspace or not is_within(root, workspace):
        raise LifecycleError("Resolved goal root escapes or equals the workspace")

    if create:
        with workspace_registration_lock():
            locked_workspace = canonical_workspace(str(workspace))
            if locked_workspace != workspace:
                raise LifecycleError("Canonical workspace identity changed during registration")
            locked_root = workspace.joinpath(relative_root).resolve(strict=False)
            if locked_root != root:
                raise LifecycleError("Goal-root identity changed during registration")
            refuse_legacy_workspace(workspace, locked_root)
            nested_markers = find_descendant_workspace_markers(workspace)
            if nested_markers:
                raise LifecycleError(
                    "A nested Intentwright workspace is already registered beneath this workspace: "
                    + ", ".join(str(path.parent) for path in nested_markers)
                )
            ensure_root(workspace, root, relative_root)
            register_workspace_root(workspace, relative_root)
            validate_root(workspace, root)
        return workspace, root
    validate_root(workspace, root)
    return workspace, root


def ensure_root(workspace: Path, root: Path, relative_root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if is_link_like(root) or not root.is_dir():
        raise LifecycleError(f"Goal root is not a safe directory: {root}")

    refuse_legacy_workspace(workspace, root)
    expected = {ROOT_MARKER, LOCKS, *LOCATION_NAMES}
    unexpected = [entry.name for entry in root.iterdir() if entry.name not in expected]
    marker = root / ROOT_MARKER
    if not marker.exists() and unexpected:
        raise LifecycleError(
            f"{root} is not an empty or recognized Intentwright root; unexpected entries: "
            + ", ".join(sorted(unexpected))
        )
    if not marker.exists():
        occupied_expected: list[str] = []
        for name in (LOCKS, *LOCATION_NAMES):
            child = root / name
            if child.exists():
                if is_link_like(child) or not child.is_dir():
                    occupied_expected.append(name)
                elif any(child.iterdir()):
                    occupied_expected.append(name)
        if occupied_expected:
            raise LifecycleError(
                f"{root} has no Intentwright marker but contains occupied lifecycle directories: "
                + ", ".join(sorted(occupied_expected))
            )

    for name in (LOCKS, *LOCATION_NAMES):
        child = root / name
        child.mkdir(exist_ok=True)
        if is_link_like(child) or not child.is_dir():
            raise LifecycleError(f"Unsafe Intentwright directory: {child}")

    if not marker.exists():
        marker_value = {
            "schema_version": SCHEMA_VERSION,
            "kind": "intentwright-root",
            "created_at": utc_now(),
            "workspace_hint": str(workspace),
            "relative_root": relative_root.as_posix(),
        }
        try:
            create_json_exclusive(marker, marker_value)
        except LifecycleError:
            if not marker.exists():
                raise
    marker_value = read_json(marker)
    if marker_value.get("relative_root") != relative_root.as_posix():
        raise LifecycleError("Goal-root marker does not match its workspace-relative path")


def register_workspace_root(workspace: Path, relative_root: Path) -> dict[str, Any]:
    committed_workspace = canonical_workspace(str(workspace))
    if committed_workspace != workspace:
        raise LifecycleError("Canonical workspace identity changed before registration commit")
    refuse_legacy_workspace(workspace, workspace / relative_root)
    ensure_legacy_exclusion_marker(workspace, relative_root)
    marker = workspace / WORKSPACE_MARKER
    if marker.exists() and is_link_like(marker):
        raise LifecycleError(f"Unsafe Intentwright workspace marker: {marker}")
    nested_markers = find_descendant_workspace_markers(workspace)
    if nested_markers:
        raise LifecycleError(
            "A nested Intentwright workspace is already registered beneath this workspace; "
            "use that exact workspace or remove the competing registration deliberately: "
            + ", ".join(str(path.parent) for path in nested_markers)
        )
    expected_root = relative_root.as_posix()
    value = {
        "schema_version": SCHEMA_VERSION,
        "kind": "intentwright-workspace",
        "canonical_workspace": os.path.normcase(str(workspace)),
        "relative_root": expected_root,
        "created_at": utc_now(),
    }
    if not marker.exists():
        try:
            create_json_exclusive(marker, value)
        except LifecycleError:
            if not marker.exists():
                raise
    registered = read_json(marker)
    if (
        type(registered.get("schema_version")) is not int
        or registered.get("schema_version") != SCHEMA_VERSION
        or registered.get("kind") != "intentwright-workspace"
        or registered.get("canonical_workspace") != os.path.normcase(str(workspace))
        or registered.get("relative_root") != expected_root
    ):
        raise LifecycleError(
            "This workspace is already registered to a different Intentwright root: "
            f"{registered.get('relative_root')!r}"
        )
    return registered


def validate_root(workspace: Path, root: Path) -> dict[str, Any]:
    if not root.is_dir() or is_link_like(root):
        raise LifecycleError(f"Goal root is missing or unsafe: {root}")
    if not is_within(root.resolve(strict=True), workspace):
        raise LifecycleError(f"Goal root escapes workspace: {root}")
    refuse_legacy_workspace(workspace, root)
    marker = read_json(root / ROOT_MARKER)
    if (
        type(marker.get("schema_version")) is not int
        or marker.get("schema_version") != SCHEMA_VERSION
        or marker.get("kind") != "intentwright-root"
    ):
        raise LifecycleError(f"Unrecognized Intentwright root marker: {root / ROOT_MARKER}")
    expected_relative = root.resolve(strict=True).relative_to(workspace).as_posix()
    if marker.get("relative_root") != expected_relative:
        raise LifecycleError("Goal-root marker path does not match the actual root")
    registration = read_json(workspace / WORKSPACE_MARKER)
    if (
        type(registration.get("schema_version")) is not int
        or registration.get("schema_version") != SCHEMA_VERSION
        or registration.get("kind") != "intentwright-workspace"
        or registration.get("canonical_workspace") != os.path.normcase(str(workspace))
        or registration.get("relative_root") != expected_relative
    ):
        raise LifecycleError(
            "Workspace registration does not authorize this Intentwright root"
        )
    for name in (LOCKS, *LOCATION_NAMES):
        child = root / name
        if not child.is_dir() or is_link_like(child):
            raise LifecycleError(f"Missing or unsafe Intentwright directory: {child}")
        resolved_child = child.resolve(strict=True)
        if resolved_child.parent != root.resolve(strict=True):
            raise LifecycleError(f"Intentwright lifecycle directory escapes its root: {child}")
    return marker


def sanitize_slug(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "goal"
    if slug in WINDOWS_RESERVED:
        slug = f"goal_{slug}"
    slug = slug[:50].rstrip("_") or "goal"
    return slug


def normalize_write_scope(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    if value == ".":
        return "."
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise LifecycleError(f"Write scope contains control characters: {raw!r}")
    if any(character in '`|<>:"?*~' for character in value):
        raise LifecycleError(f"Write scope contains unsafe envelope characters: {raw!r}")
    candidate = PurePosixPath(value)
    if not value or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise LifecycleError(f"Write scope must be a safe project-relative path or '.': {raw}")
    normalized = candidate.as_posix().rstrip("/")
    if normalized.startswith("../") or normalized == "..":
        raise LifecycleError(f"Write scope escapes the workspace: {raw}")
    for part in candidate.parts:
        if part.endswith((" ", ".")):
            raise LifecycleError(
                f"Write scope contains a Windows-aliasing trailing space or dot: {raw!r}"
            )
        if part.casefold().split(".", 1)[0] in WINDOWS_RESERVED:
            raise LifecycleError(
                f"Write scope contains a reserved Windows path component: {raw!r}"
            )
    return normalized


def normalize_write_scopes(values: list[str]) -> list[str]:
    if not values:
        raise LifecycleError("At least one explicit write scope is required")
    normalized = [normalize_write_scope(value) for value in values]
    by_key: dict[str, str] = {}
    for scope in normalized:
        by_key.setdefault(scope.casefold(), scope)
    scopes = sorted(by_key.values(), key=lambda value: (value.casefold(), value))
    if "." in scopes:
        return ["."]
    reduced: list[str] = []
    for scope in scopes:
        parts = tuple(part.casefold() for part in PurePosixPath(scope).parts)
        if any(
            parts[: len(PurePosixPath(existing).parts)]
            == tuple(part.casefold() for part in PurePosixPath(existing).parts)
            for existing in reduced
        ):
            continue
        reduced.append(scope)
    return reduced


def approval_receipt_payload(
    *,
    workspace: Path,
    goals_dir: str,
    title: str,
    slug: str,
    revision: int,
    interview_id: str,
    approved_body_sha256: str,
    write_scopes: list[str],
    retry_of: str | None,
    supersedes: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "intentwright-approval-receipt",
        "workspace_identity": os.path.normcase(str(workspace.resolve(strict=True))),
        "goals_dir": goals_dir,
        "title": title,
        "slug": slug,
        "revision": revision,
        "interview_id": interview_id,
        "approved_body_sha256": approved_body_sha256,
        "write_scopes": write_scopes,
        "retry_of": retry_of,
        "supersedes": supersedes,
    }


def approval_receipt_sha256(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def expected_approval_phrase(revision: int, receipt_sha256: str) -> str:
    return f"Approve spec v{revision} receipt {receipt_sha256}"


def validate_manifest_approval_receipt(
    workspace: Path,
    root: Path,
    manifest: dict[str, Any],
) -> str:
    payload = approval_receipt_payload(
        workspace=workspace,
        goals_dir=root.relative_to(workspace).as_posix(),
        title=manifest["title"],
        slug=manifest["slug"],
        revision=manifest["revision"],
        interview_id=manifest["interview_id"],
        approved_body_sha256=manifest["approval_body_sha256"],
        write_scopes=manifest["write_scopes"],
        retry_of=manifest["retry_of"],
        supersedes=manifest["supersedes"],
    )
    expected_receipt = approval_receipt_sha256(payload)
    if not secrets.compare_digest(
        expected_receipt,
        manifest["approval_receipt_sha256"],
    ):
        raise LifecycleError(
            "Manifest approval receipt does not bind the exact workspace, goal root, title, "
            "slug, revision, interview, body, scopes, and lineage"
        )
    expected_phrase = expected_approval_phrase(manifest["revision"], expected_receipt)
    if manifest["approval_record"] != expected_phrase:
        raise LifecycleError(
            f"Manifest approval_record must be exactly {expected_phrase!r}"
        )
    return expected_receipt


def scopes_overlap(left: list[str], right: list[str]) -> bool:
    if "." in left or "." in right:
        return True
    for first in left:
        first_parts = tuple(part.casefold() for part in PurePosixPath(first).parts)
        for second in right:
            second_parts = tuple(part.casefold() for part in PurePosixPath(second).parts)
            shortest = min(len(first_parts), len(second_parts))
            if first_parts[:shortest] == second_parts[:shortest]:
                return True
    return False


def validate_write_scope_paths(workspace: Path, scopes: list[str]) -> list[str]:
    comparison: list[str] = []
    workspace_resolved = workspace.resolve(strict=True)
    for scope in scopes:
        if scope == ".":
            comparison.append(".")
            continue
        current = workspace_resolved
        for part in PurePosixPath(scope).parts:
            current = current / part
            if current.exists() and is_link_like(current):
                raise LifecycleError(
                    f"Write scope traverses a symlink, junction, or reparse point: {scope}"
                )
            if current.exists() and current.is_file():
                validate_unique_regular_file(current, "Write-scope file")
        resolved = current.resolve(strict=False)
        if not is_within(resolved, workspace_resolved):
            raise LifecycleError(f"Write scope resolves outside the workspace: {scope}")
        comparison.append(resolved.relative_to(workspace_resolved).as_posix())
    return normalize_write_scopes(comparison)


def validate_goal_id(goal_id: str) -> None:
    if not GOAL_ID_RE.fullmatch(goal_id):
        raise LifecycleError(f"Invalid Intentwright goal ID: {goal_id}")


def project_relative(workspace: Path, path: Path) -> str:
    resolved = path.resolve(strict=False)
    if not is_within(resolved, workspace):
        raise LifecycleError(f"Path escapes workspace: {path}")
    return resolved.relative_to(workspace).as_posix()


def render_canonical_spec(
    workspace: Path,
    package: Path,
    manifest: dict[str, Any],
    approved_body: str,
) -> str:
    scopes = ", ".join(f"`{scope}`" for scope in manifest["write_scopes"])
    metadata = (
        f"# Goal specification: {manifest['title']}\n\n"
        "## Metadata\n\n"
        f"- Goal ID: `{manifest['goal_id']}`\n"
        f"- Slug: `{manifest['slug']}`\n"
        f"- Revision: `{manifest['revision']}`\n"
        f"- Interview ID: `{manifest['interview_id']}`\n"
        f"- Approval: {manifest['approval_record']}\n"
        f"- Approval receipt SHA-256: `{manifest['approval_receipt_sha256']}`\n"
        f"- Approval-body SHA-256: `{manifest['approval_body_sha256']}`\n"
        f"- Workspace-relative package: `{project_relative(workspace, package)}`\n"
        f"- Canonical spec: `{project_relative(workspace, package)}/{manifest['spec_file']}`\n"
        f"- Approved semantic body: `{APPROVED_BODY_FILE}`\n"
        f"- Approved semantic SHA-256: `{manifest['approved_body_sha256']}`\n"
        f"- Declared write scopes: {scopes}\n\n"
    )
    return metadata + approved_body


def file_hash_map(package: Path, filenames: list[str]) -> dict[str, str]:
    return {name: sha256_file(package / name) for name in filenames}


def write_package_seal(package: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    filenames = [
        "goal_manifest.json",
        manifest["approved_body_file"],
        manifest["spec_file"],
        manifest["execution_prompt_file"],
        manifest["portable_handoff_file"],
    ]
    seal = {
        "schema_version": SCHEMA_VERSION,
        "goal_id": manifest["goal_id"],
        "sealed_at": utc_now(),
        "files": file_hash_map(package, filenames),
    }
    atomic_write_json(package / SEAL_FILE, seal)
    return seal


def validate_package_seal(package: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    seal = read_json(package / SEAL_FILE)
    if (
        type(seal.get("schema_version")) is not int
        or seal.get("schema_version") != SCHEMA_VERSION
        or seal.get("goal_id") != manifest["goal_id"]
    ):
        raise LifecycleError("Package seal does not match the manifest")
    files = seal.get("files")
    expected_names = {
        "goal_manifest.json",
        manifest["approved_body_file"],
        manifest["spec_file"],
        manifest["execution_prompt_file"],
        manifest["portable_handoff_file"],
    }
    if not isinstance(files, dict) or set(files) != expected_names:
        raise LifecycleError("Package seal file set is invalid")
    for name in sorted(expected_names):
        expected = files.get(name)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise LifecycleError(f"Package seal hash is invalid for {name}")
        actual = sha256_file(package / name)
        if not secrets.compare_digest(expected, actual):
            raise LifecycleError(
                f"Sealed file changed after publication: {name}; expected {expected}, got {actual}"
            )
    return seal


def terminal_file_hashes(
    package: Path,
    overrides: dict[str, bytes] | None = None,
) -> dict[str, str]:
    assert_no_link_like(package)
    override_values = overrides or {}
    files: dict[str, str] = {}
    for candidate in sorted(package.rglob("*"), key=lambda path: path.as_posix()):
        if candidate.is_dir():
            continue
        if not candidate.is_file() or is_link_like(candidate):
            raise LifecycleError(f"Unsafe terminal package entry: {candidate}")
        relative = candidate.relative_to(package).as_posix()
        if relative == TERMINAL_SEAL_FILE:
            continue
        if relative in override_values:
            files[relative] = sha256_bytes(override_values[relative])
        else:
            files[relative] = sha256_file(candidate)
    unknown_overrides = sorted(set(override_values) - set(files))
    if unknown_overrides:
        raise LifecycleError(
            "Terminal-seal override references missing files: "
            + ", ".join(unknown_overrides)
        )
    return files


def write_terminal_seal(
    package: Path,
    goal_id: str,
    outcome: str,
    reason_code: str,
    final_status: dict[str, Any],
) -> dict[str, Any]:
    seal = {
        "schema_version": SCHEMA_VERSION,
        "kind": "intentwright-terminal-seal",
        "goal_id": goal_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "sealed_at": utc_now(),
        "final_status": final_status,
        "files": terminal_file_hashes(
            package,
            {"status.json": atomic_json_bytes(final_status)},
        ),
    }
    atomic_write_json(package / TERMINAL_SEAL_FILE, seal)
    return seal


def validate_terminal_seal(
    package: Path,
    goal_id: str,
    outcome: str,
    reason_code: str,
) -> dict[str, Any]:
    seal = read_json(package / TERMINAL_SEAL_FILE)
    expected_fields = {
        "schema_version",
        "kind",
        "goal_id",
        "outcome",
        "reason_code",
        "sealed_at",
        "final_status",
        "files",
    }
    if set(seal) != expected_fields:
        raise LifecycleError("Terminal seal fields are invalid")
    if (
        type(seal.get("schema_version")) is not int
        or seal.get("schema_version") != SCHEMA_VERSION
        or seal.get("kind") != "intentwright-terminal-seal"
        or seal.get("goal_id") != goal_id
        or seal.get("outcome") != outcome
        or seal.get("reason_code") != reason_code
    ):
        raise LifecycleError("Terminal seal identity does not match the terminal package")
    parse_utc_timestamp(seal.get("sealed_at"), "Terminal seal sealed_at")
    final_status = seal.get("final_status")
    if not isinstance(final_status, dict):
        raise LifecycleError("Terminal seal final_status is invalid")
    if (
        final_status.get("goal_id") != goal_id
        or final_status.get("state") != outcome
        or final_status.get("terminal_reason_code") != reason_code
    ):
        raise LifecycleError("Terminal seal final_status identity is inconsistent")
    actual_status = read_json(package / "status.json")
    if actual_status != final_status:
        raise LifecycleError("Terminal status does not equal the seal's precommitted final status")
    expected_hashes = seal.get("files")
    if not isinstance(expected_hashes, dict) or not expected_hashes:
        raise LifecycleError("Terminal seal file map is invalid")
    actual_hashes = terminal_file_hashes(package)
    if expected_hashes.get("status.json") != sha256_bytes(atomic_json_bytes(final_status)):
        raise LifecycleError("Terminal seal does not bind its embedded final status")
    if set(expected_hashes) != set(actual_hashes):
        missing = sorted(set(expected_hashes) - set(actual_hashes))
        extra = sorted(set(actual_hashes) - set(expected_hashes))
        raise LifecycleError(
            "Terminal package file set changed after sealing; missing="
            + ", ".join(missing or ["none"])
            + "; unexpected="
            + ", ".join(extra or ["none"])
        )
    for relative, actual in actual_hashes.items():
        expected = expected_hashes.get(relative)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise LifecycleError(f"Terminal seal hash is invalid for {relative}")
        if not secrets.compare_digest(expected, actual):
            raise LifecycleError(
                f"Terminal file changed after archival: {relative}; "
                f"expected {expected}, got {actual}"
            )
    return seal


def validate_precommitted_terminal_seal(
    package: Path,
    goal_id: str,
    outcome: str,
    reason_code: str,
) -> dict[str, Any]:
    seal = read_json(package / TERMINAL_SEAL_FILE)
    expected_fields = {
        "schema_version",
        "kind",
        "goal_id",
        "outcome",
        "reason_code",
        "sealed_at",
        "final_status",
        "files",
    }
    if set(seal) != expected_fields:
        raise LifecycleError("Precommitted terminal seal fields are invalid")
    if (
        type(seal.get("schema_version")) is not int
        or seal.get("schema_version") != SCHEMA_VERSION
        or seal.get("kind") != "intentwright-terminal-seal"
        or seal.get("goal_id") != goal_id
        or seal.get("outcome") != outcome
        or seal.get("reason_code") != reason_code
    ):
        raise LifecycleError("Precommitted terminal seal identity is invalid")
    parse_utc_timestamp(seal.get("sealed_at"), "Terminal seal sealed_at")
    final_status = seal.get("final_status")
    if not isinstance(final_status, dict):
        raise LifecycleError("Precommitted terminal seal final_status is invalid")
    if (
        final_status.get("goal_id") != goal_id
        or final_status.get("state") != outcome
        or final_status.get("terminal_reason_code") != reason_code
    ):
        raise LifecycleError("Precommitted terminal status is inconsistent")
    intent = final_status.get("archive_intent")
    if not isinstance(intent, dict) or intent.get("reason_code") != reason_code:
        raise LifecycleError("Precommitted terminal status lacks its exact archive intent")
    expected_hashes = seal.get("files")
    if not isinstance(expected_hashes, dict) or not expected_hashes:
        raise LifecycleError("Precommitted terminal seal file map is invalid")
    if expected_hashes.get("status.json") != sha256_bytes(atomic_json_bytes(final_status)):
        raise LifecycleError("Precommitted terminal seal does not bind its final status")
    actual_hashes = terminal_file_hashes(
        package,
        {"status.json": atomic_json_bytes(final_status)},
    )
    if expected_hashes != actual_hashes:
        raise LifecycleError(
            "Precommitted terminal seal does not match the exact future terminal package"
        )
    return seal


def find_root_from_package(package_arg: str) -> tuple[Path, Path, Path, str]:
    original = Path(package_arg).expanduser()
    if is_link_like(original):
        raise LifecycleError(f"Refusing a linked or reparse-point package: {original}")
    if not original.exists() or not original.is_dir():
        raise LifecycleError(f"Package does not exist or is not a directory: {original}")
    package = original.resolve(strict=True)
    location = package.parent.name
    if location not in LOCATION_NAMES:
        raise LifecycleError(f"Package must be directly beneath a lifecycle folder: {package}")
    root = package.parent.parent
    workspace = root.parent
    validate_root(workspace, root)
    if package.parent != root / location:
        raise LifecycleError(f"Package path is not canonical: {package}")
    return workspace, root, package, location


def find_staging_context(package_arg: str) -> tuple[Path, Path, Path]:
    original = Path(package_arg).expanduser()
    if is_link_like(original):
        raise LifecycleError(f"Refusing a linked or reparse-point staging package: {original}")
    if not original.exists() or not original.is_dir():
        raise LifecycleError(f"Staging package does not exist: {original}")
    package = original.resolve(strict=True)
    if package.parent.name != PENDING or not package.name.startswith(".staging_"):
        raise LifecycleError(f"Not an Intentwright staging package: {package}")
    root = package.parent.parent
    workspace = root.parent
    validate_root(workspace, root)
    return workspace, root, package


def validate_manifest_value(manifest: dict[str, Any]) -> dict[str, Any]:
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != SCHEMA_VERSION:
        raise LifecycleError("Unsupported goal manifest schema")
    expected_fields = {
        "schema_version",
        "goal_id",
        "slug",
        "title",
        "revision",
        "interview_id",
        "approval_record",
        "approval_receipt_sha256",
        "approval_body_sha256",
        "created_at",
        "published_at",
        "project_relative_package",
        "approved_body_file",
        "approved_body_sha256",
        "spec_file",
        "spec_sha256",
        "write_scopes",
        "execution_prompt_file",
        "portable_handoff_file",
        "retry_of",
        "supersedes",
    }
    if set(manifest) != expected_fields:
        missing = sorted(expected_fields - set(manifest))
        extra = sorted(set(manifest) - expected_fields)
        raise LifecycleError(
            "Goal manifest fields are invalid; missing="
            + ", ".join(missing or ["none"])
            + "; unexpected="
            + ", ".join(extra or ["none"])
        )
    goal_id = manifest.get("goal_id")
    if not isinstance(goal_id, str):
        raise LifecycleError("Manifest goal_id is missing")
    validate_goal_id(goal_id)
    slug = manifest.get("slug")
    if (
        not isinstance(slug, str)
        or sanitize_slug(slug) != slug
        or len(slug) > 50
        or GOAL_ID_RE.fullmatch(goal_id).group("slug") != slug
    ):
        raise LifecycleError("Manifest slug is invalid or does not match goal_id")
    title = manifest.get("title")
    if not isinstance(title, str):
        raise LifecycleError("Manifest title is missing")
    safe_single_line(title, "Manifest title", maximum=200)
    if type(manifest.get("revision")) is not int or manifest["revision"] < 1:
        raise LifecycleError("Manifest revision is invalid")
    parse_utc_timestamp(manifest.get("created_at"), "Manifest created_at")
    published_at = manifest.get("published_at")
    if published_at is not None and (
        not isinstance(published_at, str) or not published_at.strip()
    ):
        raise LifecycleError("Manifest published_at is invalid")
    if published_at is not None:
        parse_utc_timestamp(published_at, "Manifest published_at")
    relative_package = manifest.get("project_relative_package")
    if relative_package is not None:
        if not isinstance(relative_package, str) or not relative_package:
            raise LifecycleError("Manifest project_relative_package is invalid")
        relative_parts = PurePosixPath(relative_package)
        if relative_parts.is_absolute() or any(
            part in {"", ".", ".."} for part in relative_parts.parts
        ):
            raise LifecycleError("Manifest project_relative_package is unsafe")
    interview_id = manifest.get("interview_id")
    if not isinstance(interview_id, str) or INTERVIEW_ID_RE.fullmatch(interview_id) is None:
        raise LifecycleError("Manifest interview_id is invalid")
    approval_record = manifest.get("approval_record")
    if not isinstance(approval_record, str):
        raise LifecycleError("Manifest approval_record is invalid")
    approval_receipt_hash = manifest.get("approval_receipt_sha256")
    if not isinstance(approval_receipt_hash, str) or re.fullmatch(
        r"[0-9a-f]{64}", approval_receipt_hash
    ) is None:
        raise LifecycleError("Manifest approval_receipt_sha256 is invalid")
    approval_body_hash = manifest.get("approval_body_sha256")
    if not isinstance(approval_body_hash, str) or re.fullmatch(
        r"[0-9a-f]{64}", approval_body_hash
    ) is None:
        raise LifecycleError("Manifest approval_body_sha256 is invalid")
    approved_body_file = manifest.get("approved_body_file")
    if approved_body_file != APPROVED_BODY_FILE:
        raise LifecycleError(f"Manifest approved_body_file must equal {APPROVED_BODY_FILE}")
    approved_hash = manifest.get("approved_body_sha256")
    if approved_hash is not None and (
        not isinstance(approved_hash, str) or re.fullmatch(r"[0-9a-f]{64}", approved_hash) is None
    ):
        raise LifecycleError("Manifest approved_body_sha256 is invalid")
    spec_hash = manifest.get("spec_sha256")
    if spec_hash is not None and (
        not isinstance(spec_hash, str) or re.fullmatch(r"[0-9a-f]{64}", spec_hash) is None
    ):
        raise LifecycleError("Manifest spec_sha256 is invalid")
    publication_values = (
        published_at,
        relative_package,
        approved_hash,
        spec_hash,
    )
    if any(value is None for value in publication_values) and not all(
        value is None for value in publication_values
    ):
        raise LifecycleError("Manifest publication fields must be either all staged or all published")
    write_scopes = manifest.get("write_scopes")
    if not isinstance(write_scopes, list) or not write_scopes or not all(
        isinstance(item, str) for item in write_scopes
    ):
        raise LifecycleError("Manifest write_scopes must be a non-empty string list")
    if normalize_write_scopes(write_scopes) != write_scopes:
        raise LifecycleError("Manifest write_scopes are not normalized")
    spec_file = manifest.get("spec_file")
    if spec_file != f"goal_spec_{slug}.md":
        raise LifecycleError("Manifest spec_file does not match the canonical slug filename")
    for field, expected in (
        ("execution_prompt_file", "execution_prompt.md"),
        ("portable_handoff_file", "portable_handoff.md"),
    ):
        if manifest.get(field) != expected:
            raise LifecycleError(f"Manifest {field} must equal {expected}")
    for field in ("retry_of", "supersedes"):
        linked = manifest.get(field)
        if linked is not None:
            if not isinstance(linked, str):
                raise LifecycleError(f"Manifest {field} must be a goal ID or null")
            validate_goal_id(linked)
            if linked == goal_id:
                raise LifecycleError(f"Manifest {field} cannot reference itself")
    if manifest.get("retry_of") and manifest.get("supersedes"):
        raise LifecycleError("Manifest cannot contain both retry_of and supersedes lineage")
    return manifest


def load_manifest(package: Path) -> dict[str, Any]:
    return validate_manifest_value(read_json(package / "goal_manifest.json"))


def load_status(package: Path, goal_id: str) -> dict[str, Any]:
    status = read_json(package / "status.json")
    exact_schema_version(status.get("schema_version"), "Status")
    if status.get("goal_id") != goal_id:
        raise LifecycleError("Status does not match the manifest")
    if not isinstance(status.get("state"), str):
        raise LifecycleError("Status state is missing")
    expected_fields = {
        "schema_version",
        "goal_id",
        "state",
        "attempt",
        "claim_epoch",
        "created_at",
        "updated_at",
        "archive_intent",
        "terminal_reason_code",
        "last_action",
    }
    allowed_fields = expected_fields | {"imported_from"}
    if not expected_fields.issubset(status) or not set(status).issubset(allowed_fields):
        raise LifecycleError("Status fields are invalid")
    for field in ("attempt", "claim_epoch"):
        if type(status.get(field)) is not int or status[field] < 0:
            raise LifecycleError(f"Status {field} must be a nonnegative integer")
    parse_utc_timestamp(status.get("created_at"), "Status created_at")
    parse_utc_timestamp(status.get("updated_at"), "Status updated_at")
    if status.get("archive_intent") is not None and not isinstance(
        status["archive_intent"], dict
    ):
        raise LifecycleError("Status archive_intent must be an object or null")
    if status.get("terminal_reason_code") is not None and not isinstance(
        status["terminal_reason_code"], str
    ):
        raise LifecycleError("Status terminal_reason_code must be a string or null")
    if not isinstance(status.get("last_action"), str) or not status["last_action"].strip():
        raise LifecycleError("Status last_action is invalid")
    return status


def section_text(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*\r?$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(markdown)
    if match is None:
        raise LifecycleError(f"Specification is missing required heading: {heading}")
    remainder = markdown[match.end() :]
    next_heading = re.search(r"^##[ \t]+.+?\r?$", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def parse_markdown_table(
    section: str, expected_headers: tuple[str, ...], table_name: str
) -> list[dict[str, str]]:
    lines = section.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip().startswith("|")), None)
    if start is None or start + 1 >= len(lines):
        raise LifecycleError(f"{table_name} table is missing")

    def cells(line: str) -> list[str]:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            raise LifecycleError(f"{table_name} rows must begin and end with '|'")
        return [cell.strip() for cell in stripped[1:-1].split("|")]

    headers = tuple(cells(lines[start]))
    expected = expected_headers
    if headers != expected:
        raise LifecycleError(
            f"{table_name} headers must be exactly: " + " | ".join(expected_headers)
        )
    delimiter = cells(lines[start + 1])
    if len(delimiter) != len(expected) or any(
        re.fullmatch(r":?-{3,}:?", cell) is None for cell in delimiter
    ):
        raise LifecycleError(f"{table_name} delimiter row is invalid")

    rows: list[dict[str, str]] = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            if rows:
                break
            continue
        values = cells(line)
        if len(values) != len(expected):
            raise LifecycleError(f"{table_name} row has the wrong number of columns: {line}")
        if any(not value for value in values):
            raise LifecycleError(f"{table_name} rows cannot contain empty cells: {line}")
        rows.append(dict(zip(expected_headers, values)))
    if not rows:
        raise LifecycleError(f"{table_name} table has no data rows")
    return rows


def unresolved_text(value: str) -> bool:
    return bool(
        "{{" in value
        or "}}" in value
        or re.search(
            r"\bTODO\b|\bTBD\b|\bTO\s+BE\s+DECIDED\b|\bPLACEHOLDER\b",
            value,
            re.IGNORECASE,
        )
        or re.search(r"<[a-z][a-z0-9 _./:-]{2,}>", value, re.IGNORECASE)
        or re.search(
            r"\[(?:insert|replace|describe|specify|choose|decide|todo)[^\]\r\n]*\]",
            value,
            re.IGNORECASE,
        )
    )


def validate_coverage_table(body: str) -> list[dict[str, str]]:
    rows = parse_markdown_table(
        section_text(body, "Decision coverage matrix"),
        ("Dimension", "Status", "Resolution or provenance"),
        "Decision coverage matrix",
    )
    by_name: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["Dimension"] not in UNIVERSAL_DIMENSIONS:
            raise LifecycleError(f"Unexpected coverage dimension: {row['Dimension']}")
        key = row["Dimension"]
        if key in by_name:
            raise LifecycleError(f"Duplicate coverage dimension: {row['Dimension']}")
        if row["Status"] not in {"DECIDED", "DELEGATED", "NOT_APPLICABLE"}:
            raise LifecycleError(f"Invalid coverage status for {row['Dimension']}")
        if len(row["Resolution or provenance"].strip()) < 10:
            raise LifecycleError(
                f"Coverage resolution is too vague for {row['Dimension']}"
            )
        by_name[key] = row
    missing = [name for name in UNIVERSAL_DIMENSIONS if name not in by_name]
    extra = [row["Dimension"] for row in rows if row["Dimension"] not in UNIVERSAL_DIMENSIONS]
    if missing or extra:
        raise LifecycleError(
            "Coverage matrix mismatch; missing="
            + ", ".join(missing or ["none"])
            + "; unexpected="
            + ", ".join(extra or ["none"])
        )
    return rows


def validate_domain_table(body: str) -> list[dict[str, str]]:
    rows = parse_markdown_table(
        section_text(body, "Domain routing"),
        ("Domain branch", "Status", "Rationale"),
        "Domain routing",
    )
    by_name: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["Domain branch"] not in DOMAIN_BRANCHES:
            raise LifecycleError(f"Unexpected domain branch: {row['Domain branch']}")
        key = row["Domain branch"]
        if key in by_name:
            raise LifecycleError(f"Duplicate domain branch: {row['Domain branch']}")
        if row["Status"] not in {"SELECTED", "NOT_APPLICABLE"}:
            raise LifecycleError(f"Invalid domain routing status for {row['Domain branch']}")
        if len(row["Rationale"].strip()) < 10:
            raise LifecycleError(f"Domain routing rationale is too vague for {row['Domain branch']}")
        by_name[key] = row
    missing = [name for name in DOMAIN_BRANCHES if name not in by_name]
    extra = [row["Domain branch"] for row in rows if row["Domain branch"] not in DOMAIN_BRANCHES]
    if missing or extra:
        raise LifecycleError(
            "Domain routing mismatch; missing="
            + ", ".join(missing or ["none"])
            + "; unexpected="
            + ", ".join(extra or ["none"])
        )
    if not any(row["Status"] == "SELECTED" for row in rows):
        raise LifecycleError("At least one domain branch must be selected")
    return rows


def validate_decision_ledger(body: str) -> dict[str, dict[str, str]]:
    rows = parse_markdown_table(
        section_text(body, "Decision ledger"),
        ("ID", "Type", "Status", "Decision or rationale", "Provenance"),
        "Decision ledger",
    )
    expected_status = {
        "D": "CONFIRMED",
        "C": "CONFIRMED",
        "N": "CONFIRMED",
        "A": "BOUNDED",
        "O": "RESOLVED",
        "T": "RESOLVED",
        "R": "REJECTED",
        "E": "DELEGATED",
        "NA": "NOT_APPLICABLE",
    }
    ledger: dict[str, dict[str, str]] = {}
    for row in rows:
        identifier = row["ID"]
        if identifier != identifier.upper():
            raise LifecycleError(f"Requirement ID must use exact uppercase spelling: {identifier}")
        match = re.fullmatch(r"(D|C|N|A|O|T|R|E|NA)-\d{3,}", identifier)
        if match is None:
            raise LifecycleError(f"Decision ledger ID is invalid: {row['ID']}")
        kind = row["Type"]
        if kind != match.group(1):
            raise LifecycleError(f"Decision ledger type does not match {identifier}")
        if identifier in ledger:
            raise LifecycleError(f"Duplicate decision ledger ID: {identifier}")
        status = row["Status"]
        if status != expected_status[kind]:
            raise LifecycleError(
                f"{identifier} status must be exactly {expected_status[kind]}"
            )
        if len(row["Decision or rationale"].strip()) < 10:
            raise LifecycleError(f"{identifier} decision or rationale is too vague")
        if len(row["Provenance"].strip()) < 5:
            raise LifecycleError(f"{identifier} provenance is too vague")
        row["ID"] = identifier
        row["Type"] = kind
        row["Status"] = status
        ledger[identifier] = row
    if not any(row["Type"] == "D" for row in ledger.values()):
        raise LifecycleError("Decision ledger must contain at least one confirmed D entry")
    return ledger


def validate_coverage_ledger_links(
    coverage: list[dict[str, str]],
    domains: list[dict[str, str]],
    ledger: dict[str, dict[str, str]],
) -> None:
    def references(value: str) -> list[str]:
        return [
            match.group(0).upper()
            for match in re.finditer(r"\b(?:D|C|N|A|O|T|R|E|NA)-\d{3,}\b", value)
        ]

    for row in coverage:
        status = row["Status"]
        allowed_types = {
            "DECIDED": {"D", "C", "N", "A"},
            "DELEGATED": {"E"},
            "NOT_APPLICABLE": {"NA"},
        }[status]
        linked = references(row["Resolution or provenance"])
        if not linked:
            raise LifecycleError(
                f"Coverage row {row['Dimension']} must cite a decision-ledger ID"
            )
        for identifier in linked:
            if identifier not in ledger:
                raise LifecycleError(
                    f"Coverage row {row['Dimension']} cites unknown ledger ID {identifier}"
                )
        if not any(ledger[identifier]["Type"] in allowed_types for identifier in linked):
            raise LifecycleError(
                f"Coverage row {row['Dimension']} lacks a status-compatible ledger link"
            )

    for row in domains:
        status = row["Status"]
        allowed_types = {"D", "E"} if status == "SELECTED" else {"NA"}
        linked = references(row["Rationale"])
        if not linked:
            raise LifecycleError(
                f"Domain row {row['Domain branch']} must cite a decision-ledger ID"
            )
        for identifier in linked:
            if identifier not in ledger:
                raise LifecycleError(
                    f"Domain row {row['Domain branch']} cites unknown ledger ID {identifier}"
                )
        if not any(ledger[identifier]["Type"] in allowed_types for identifier in linked):
            raise LifecycleError(
                f"Domain row {row['Domain branch']} lacks a status-compatible ledger link"
            )


def validate_write_scope_table(body: str, write_scopes: list[str]) -> None:
    rows = parse_markdown_table(
        section_text(body, "Execution workspace and write scope"),
        ("Path", "Access", "Rationale"),
        "Execution write scopes",
    )
    paths: list[str] = []
    for row in rows:
        if row["Access"] != "WRITE":
            raise LifecycleError(f"Write scope {row['Path']} access must be exactly WRITE")
        if len(row["Rationale"].strip()) < 10:
            raise LifecycleError(f"Write scope rationale is too vague for {row['Path']}")
        paths.append(normalize_write_scope(row["Path"]))
    normalized = normalize_write_scopes(paths)
    if len(paths) != len(normalized):
        raise LifecycleError("Write-scope table contains duplicate or redundant paths")
    if normalized != write_scopes:
        raise LifecycleError(
            "Write-scope table must exactly equal the immutable manifest scopes; "
            f"table={normalized}, manifest={write_scopes}"
        )


def validate_lineage_table(
    body: str,
    retry_of: str | None,
    supersedes: str | None,
) -> None:
    rows = parse_markdown_table(
        section_text(body, "Goal lifecycle contract"),
        ("Lineage field", "Goal ID or NONE"),
        "Goal lifecycle lineage",
    )
    expected = {
        "retry_of": retry_of or "NONE",
        "supersedes": supersedes or "NONE",
    }
    actual: dict[str, str] = {}
    for row in rows:
        field = row["Lineage field"]
        if field not in expected:
            raise LifecycleError(f"Unexpected lineage field in semantic body: {field}")
        if field in actual:
            raise LifecycleError(f"Duplicate lineage field in semantic body: {field}")
        value = row["Goal ID or NONE"]
        if value != "NONE":
            validate_goal_id(value)
        actual[field] = value
    if actual != expected:
        raise LifecycleError(
            "Goal lifecycle lineage table must exactly match the approved lineage; "
            f"table={actual}, expected={expected}"
        )


def validate_semantic_body(
    body: str,
    write_scopes: list[str] | None = None,
    retry_of: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    if len(body.strip()) < 1000:
        raise LifecycleError("Approved semantic specification is unexpectedly short")
    if not body.lstrip("\ufeff").startswith("## Executive outcome"):
        raise LifecycleError("Approved semantic body must begin with '## Executive outcome'")
    required_headings = (
        "Executive outcome",
        "Context and verified current state",
        "Users and scenarios",
        "Scope and deliverables",
        "Explicit non-goals",
        "Decision coverage matrix",
        "Domain routing",
        "Requirements",
        "Execution workspace and write scope",
        "Detailed behavior and quality bar",
        "Data, interfaces, dependencies, and compatibility",
        "Constraints and prohibited shortcuts",
        "Executor freedoms",
        "Edge cases and failure semantics",
        "Acceptance criteria",
        "Validation plan",
        "Risks and assumptions",
        "Decision ledger",
        "Definition of done",
        "Goal lifecycle contract",
    )
    actual_headings = [
        match.group(1).strip()
        for match in re.finditer(r"^##[ \t]+(.+?)[ \t]*\r?$", body, re.MULTILINE)
    ]
    if actual_headings != list(required_headings):
        raise LifecycleError(
            "Approved semantic body must contain the exact required H2 sections in contract order"
        )
    for heading in required_headings:
        content = section_text(body, heading)
        if not content.strip():
            raise LifecycleError(f"Specification section is empty: {heading}")
    if unresolved_text(body):
        raise LifecycleError("Specification contains unresolved template markers")

    coverage = validate_coverage_table(body)
    domains = validate_domain_table(body)
    ledger = validate_decision_ledger(body)
    validate_coverage_ledger_links(coverage, domains, ledger)
    if write_scopes is None:
        raise LifecycleError("Semantic validation requires explicit immutable write scopes")
    validate_write_scope_table(body, write_scopes)
    validate_lineage_table(body, retry_of, supersedes)
    requirement_rows = parse_markdown_table(
        section_text(body, "Requirements"),
        ("ID", "Requirement", "Rationale or provenance", "Priority"),
        "Requirements",
    )
    requirements: dict[str, dict[str, str]] = {}
    for row in requirement_rows:
        identifier = row["ID"]
        if identifier != identifier.upper():
            raise LifecycleError(
                f"Acceptance criterion ID must use exact uppercase spelling: {identifier}"
            )
        if ALL_REQUIREMENT_RE.fullmatch(identifier) is None:
            raise LifecycleError(f"Invalid requirement ID: {row['ID']}")
        if identifier in requirements:
            raise LifecycleError(f"Duplicate requirement ID: {identifier}")
        priority = row["Priority"]
        if priority not in {"Mandatory", "Stretch"}:
            raise LifecycleError(f"Requirement {identifier} priority must be Mandatory or Stretch")
        if len(row["Requirement"].strip()) < 10 or len(
            row["Rationale or provenance"].strip()
        ) < 10:
            raise LifecycleError(f"Requirement {identifier} is too vague")
        row["ID"] = identifier
        row["Priority"] = priority
        requirements[identifier] = row
    mandatory_requirements = {
        identifier for identifier, row in requirements.items() if row["Priority"] == "Mandatory"
    }
    if not mandatory_requirements:
        raise LifecycleError("At least one mandatory requirement is required")

    acceptance_rows = parse_markdown_table(
        section_text(body, "Acceptance criteria"),
        (
            "ID",
            "Priority",
            "Role",
            "Covers",
            "Pass condition",
            "Evidence method",
            "Required evidence",
        ),
        "Acceptance criteria",
    )
    acceptance: dict[str, dict[str, Any]] = {}
    for row in acceptance_rows:
        identifier = row["ID"]
        mandatory_match = ACCEPTANCE_RE.fullmatch(identifier)
        stretch_match = STRETCH_ACCEPTANCE_RE.fullmatch(identifier)
        if mandatory_match is None and stretch_match is None:
            raise LifecycleError(f"Invalid acceptance criterion ID: {row['ID']}")
        if identifier in acceptance:
            raise LifecycleError(f"Duplicate acceptance criterion ID: {identifier}")
        expected_priority = "Mandatory" if mandatory_match else "Stretch"
        if row["Priority"] != expected_priority:
            raise LifecycleError(
                f"{identifier} must have priority {expected_priority}; use AC- for mandatory and SAC- for stretch"
            )
        role = row["Role"]
        if role not in {
            "DELIVERABLE",
            "BEHAVIOR",
            "QUALITY",
            "SAFETY",
            "VALIDATION",
            "OPERATIONS",
        }:
            raise LifecycleError(f"{identifier} has an invalid acceptance role: {row['Role']}")
        found_covers = [item.upper() for item in ALL_REQUIREMENT_RE.findall(row["Covers"])]
        if not found_covers:
            raise LifecycleError(f"{identifier} does not cover a requirement ID")
        if len(found_covers) != len(set(found_covers)):
            raise LifecycleError(f"{identifier} repeats a requirement in Covers")
        residual = ALL_REQUIREMENT_RE.sub("", row["Covers"])
        if re.fullmatch(r"[\s,;]*", residual) is None:
            raise LifecycleError(
                f"{identifier} Covers must contain only exact requirement IDs separated by commas"
            )
        covers = sorted(found_covers)
        unknown = [item for item in covers if item not in requirements]
        if unknown:
            raise LifecycleError(f"{identifier} covers unknown requirements: {', '.join(unknown)}")
        wrong_priority = [
            item
            for item in covers
            if requirements[item]["Priority"] != expected_priority
        ]
        if wrong_priority:
            raise LifecycleError(
                f"{identifier} may cover only {expected_priority} requirements: "
                + ", ".join(wrong_priority)
            )
        if unresolved_text(row["Pass condition"]) or unresolved_text(row["Required evidence"]):
            raise LifecycleError(f"{identifier} contains unresolved pass or evidence text")
        if len(row["Pass condition"].strip()) < 15 or len(
            row["Required evidence"].strip()
        ) < 10:
            raise LifecycleError(f"{identifier} pass condition or evidence requirement is too vague")
        evidence_method = row["Evidence method"]
        if evidence_method not in {
            "command",
            "interaction",
            "inspection",
            "review",
            "artifact",
        }:
            raise LifecycleError(
                f"{identifier} has an invalid exact Evidence method: {row['Evidence method']}"
            )
        row["ID"] = identifier
        row["Priority"] = expected_priority
        row["Role"] = role
        row["Evidence method"] = evidence_method
        row["Covers IDs"] = covers
        acceptance[identifier] = row
    mandatory_acceptance = {
        identifier for identifier, row in acceptance.items() if row["Priority"] == "Mandatory"
    }
    if not mandatory_acceptance:
        raise LifecycleError("At least one mandatory AC- criterion is required")
    if not any(
        acceptance[identifier]["Role"] == "DELIVERABLE"
        for identifier in mandatory_acceptance
    ):
        raise LifecycleError(
            "At least one mandatory AC- criterion must have role DELIVERABLE"
        )
    mapped_mandatory = {
        covered
        for identifier in mandatory_acceptance
        for covered in acceptance[identifier]["Covers IDs"]
    }
    unmapped = sorted(mandatory_requirements - mapped_mandatory)
    if unmapped:
        raise LifecycleError(
            "Mandatory requirements lack mandatory acceptance mappings: " + ", ".join(unmapped)
        )
    stretch_requirements = {
        identifier for identifier, row in requirements.items() if row["Priority"] == "Stretch"
    }
    mapped_stretch = {
        covered
        for identifier, row in acceptance.items()
        if row["Priority"] == "Stretch"
        for covered in row["Covers IDs"]
    }
    unmapped_stretch = sorted(stretch_requirements - mapped_stretch)
    if unmapped_stretch:
        raise LifecycleError(
            "Stretch requirements lack SAC acceptance mappings: "
            + ", ".join(unmapped_stretch)
        )

    return {
        "requirements": requirements,
        "mandatory_requirements": sorted(mandatory_requirements),
        "acceptance": acceptance,
        "mandatory_acceptance": sorted(mandatory_acceptance),
        "stretch_acceptance": sorted(set(acceptance) - mandatory_acceptance),
        "coverage": coverage,
        "domains": domains,
        "ledger": ledger,
    }


def validate_published_package(
    package_arg: str,
    *,
    allow_unsealed_terminal: bool = False,
    _retry_ancestors: frozenset[str] | None = None,
) -> dict[str, Any]:
    workspace, root, package, location = find_root_from_package(package_arg)
    assert_no_link_like(package)
    manifest = load_manifest(package)
    validate_manifest_approval_receipt(workspace, root, manifest)
    goal_id = manifest["goal_id"]
    retry_ancestors = _retry_ancestors or frozenset()
    if goal_id in retry_ancestors:
        raise LifecycleError("Retry lineage contains a cycle")
    retry_ancestors = retry_ancestors | {goal_id}
    if package.name != goal_id:
        raise LifecycleError("Published package directory must equal manifest goal_id")
    if manifest.get("published_at") in (None, ""):
        raise LifecycleError("Manifest is not published")
    expected_relative = project_relative(workspace, package)
    manifest_relative = manifest.get("project_relative_package")
    canonical_pending_relative = project_relative(workspace, root / PENDING / goal_id)
    if not isinstance(manifest_relative, str):
        raise LifecycleError("Manifest project_relative_package is invalid")
    relative_parts = PurePosixPath(manifest_relative)
    if relative_parts.is_absolute() or ".." in relative_parts.parts:
        raise LifecycleError("Manifest project_relative_package is unsafe")
    # The immutable manifest retains its canonical publication path after archival.
    if manifest_relative != canonical_pending_relative:
        raise LifecycleError("Manifest project_relative_package is not canonical")
    if location == PENDING and expected_relative != canonical_pending_relative:
        raise LifecycleError("Pending package path is not canonical")
    spec_hash = manifest.get("spec_sha256")
    if not isinstance(spec_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", spec_hash):
        raise LifecycleError("Manifest spec_sha256 is invalid")
    if not isinstance(manifest.get("published_at"), str) or not manifest["published_at"]:
        raise LifecycleError("Manifest published_at is missing")
    approved_hash = manifest.get("approved_body_sha256")
    if not isinstance(approved_hash, str) or re.fullmatch(r"[0-9a-f]{64}", approved_hash) is None:
        raise LifecycleError("Published manifest approved_body_sha256 is invalid")
    if approved_hash != manifest["approval_body_sha256"]:
        raise LifecycleError("Published body hash does not match the pre-approval body hash")
    validate_write_scope_paths(workspace, manifest["write_scopes"])
    validate_package_seal(package, manifest)

    approved_body_path = package / manifest["approved_body_file"]
    approved_body = validate_canonical_body_file(
        approved_body_path,
        manifest["approval_body_sha256"],
    )
    actual_approved_hash = sha256_file(approved_body_path)
    if not secrets.compare_digest(approved_hash, actual_approved_hash):
        raise LifecycleError(
            "Approved semantic body hash mismatch: "
            f"expected {approved_hash}, got {actual_approved_hash}"
        )
    spec_analysis = validate_semantic_body(
        approved_body,
        manifest["write_scopes"],
        manifest["retry_of"],
        manifest["supersedes"],
    )
    spec = package / manifest["spec_file"]
    spec_text = read_utf8_exact(spec)
    canonical_pending = root / PENDING / goal_id
    expected_spec = render_canonical_spec(workspace, canonical_pending, manifest, approved_body)
    if spec_text != expected_spec:
        raise LifecycleError(
            "Canonical spec is not the exact approved semantic body plus the mechanical envelope"
        )
    actual_hash = sha256_file(spec)
    if manifest.get("spec_sha256") != actual_hash:
        raise LifecycleError(
            f"Specification hash mismatch: expected {manifest.get('spec_sha256')}, got {actual_hash}"
        )
    status = load_status(package, goal_id)
    if location == PENDING and status["state"] not in ACTIVE_STATES:
        raise LifecycleError(f"Pending package has invalid state: {status['state']}")
    if location == ACHIEVED and status["state"] not in {"archive_prepared", "achieved"}:
        raise LifecycleError(f"Achieved package has invalid state: {status['state']}")
    if location == NOT_ACHIEVED and status["state"] not in {"archive_prepared", "not_achieved"}:
        raise LifecycleError(f"Not-achieved package has invalid state: {status['state']}")
    terminal_seal_path = package / TERMINAL_SEAL_FILE
    if location == PENDING and terminal_seal_path.exists():
        raise LifecycleError("Pending package cannot contain a terminal seal")

    prompt = package / str(manifest.get("execution_prompt_file", "execution_prompt.md"))
    portable = package / str(manifest.get("portable_handoff_file", "portable_handoff.md"))
    if not prompt.is_file() or is_link_like(prompt):
        raise LifecycleError("execution_prompt.md is missing or unsafe")
    if not portable.is_file() or is_link_like(portable):
        raise LifecycleError("portable_handoff.md is missing or unsafe")
    goal_lines = [
        line.strip() for line in read_utf8_exact(prompt).splitlines()
        if line.strip().startswith("/goal ")
    ]
    if len(goal_lines) != 1:
        raise LifecycleError("execution_prompt.md must contain exactly one /goal command")
    if len(goal_lines[0]) > 4000:
        raise LifecycleError("Generated /goal command exceeds 4,000 characters")
    expected_goal_command = make_goal_command(workspace, canonical_pending, manifest)
    if goal_lines[0] != expected_goal_command:
        raise LifecycleError("execution_prompt.md contains a stale or cross-goal /goal command")

    portable_manifest, portable_body, portable_spec = parse_portable(portable)
    if portable_manifest != manifest:
        raise LifecycleError("Portable handoff manifest does not match the canonical manifest")
    if portable_body != approved_body or portable_spec != spec_text:
        raise LifecycleError("Portable handoff specification content does not match the package")

    if location in {ACHIEVED, NOT_ACHIEVED}:
        terminal_outcome = "achieved" if location == ACHIEVED else "not_achieved"
        intent = status.get("archive_intent")
        if not isinstance(intent, dict) or intent.get("outcome") != terminal_outcome:
            raise LifecycleError("Terminal package archive intent is missing or inconsistent")
        expected_destination = project_relative(workspace, root / location / goal_id)
        if intent.get("destination") != expected_destination:
            raise LifecycleError("Terminal package archive destination is inconsistent")
        reason = (
            intent.get("reason_code")
            if status["state"] == "archive_prepared"
            else status.get("terminal_reason_code")
        )
        if not isinstance(reason, str) or not reason:
            raise LifecycleError("Terminal package lacks a terminal reason code")
        if terminal_outcome == "achieved" and reason != "completed":
            raise LifecycleError("Achieved terminal package must use reason code completed")
        if terminal_outcome == "not_achieved" and reason not in NOT_ACHIEVED_CODES:
            raise LifecycleError("Not-achieved terminal package has an invalid reason code")
        if not isinstance(intent.get("administrative"), bool):
            raise LifecycleError("Terminal archive intent lacks an administrative boolean")
        external_goal_disposition = intent.get("external_goal_disposition")
        expected_disposition = expected_external_goal_disposition(
            reason,
            administrative=intent["administrative"],
        )
        if external_goal_disposition != expected_disposition:
            raise LifecycleError(
                "Terminal archive intent has an invalid external-goal disposition"
            )
        threshold_confirmed = intent.get("blocked_threshold_confirmed")
        if not isinstance(threshold_confirmed, bool):
            raise LifecycleError("Terminal archive intent lacks blocked-threshold state")
        if (reason == "blocked") != threshold_confirmed:
            raise LifecycleError("Terminal blocked-threshold state contradicts its reason code")
        outcome_claim: dict[str, Any] | None = None
        if not intent["administrative"]:
            outcome_claim = read_json(package / "claim.json")
            validate_claim_record(outcome_claim, goal_id)
        elif (package / "claim.json").exists():
            raise LifecycleError("Administrative terminal package cannot contain a claim")
        validate_outcome(
            package,
            spec_analysis["acceptance"],
            terminal_outcome,
            reason,
            goal_id,
            intent.get("user_authorization"),
            intent.get("replacement_goal_id"),
            external_goal_disposition,
            outcome_claim,
        )
        if reason == "superseded":
            validate_replacement_lineage_any(
                root,
                goal_id,
                str(intent.get("replacement_goal_id")),
            )
        if status["state"] == "archive_prepared":
            if terminal_seal_path.exists():
                validate_precommitted_terminal_seal(
                    package,
                    goal_id,
                    terminal_outcome,
                    reason,
                )
            if not allow_unsealed_terminal:
                raise LifecycleError(
                    "Terminal move has not committed its final status; use exact-ID recovery"
                )
        elif terminal_seal_path.exists():
            validate_terminal_seal(
                package,
                goal_id,
                terminal_outcome,
                reason,
            )
        else:
            raise LifecycleError(
                "Final terminal package is missing terminal_seal.json and cannot be resealed"
            )

    validate_retry_parent(
        root,
        manifest.get("retry_of"),
        retry_ancestors,
    )

    return {
        "workspace": workspace,
        "root": root,
        "package": package,
        "location": location,
        "manifest": manifest,
        "status": status,
        "spec_sha256": actual_hash,
        "approved_body_sha256": actual_approved_hash,
        "requirements": sorted(spec_analysis["requirements"]),
        "mandatory_requirements": spec_analysis["mandatory_requirements"],
        "acceptance": spec_analysis["mandatory_acceptance"],
        "stretch_acceptance": spec_analysis["stretch_acceptance"],
        "acceptance_details": spec_analysis["acceptance"],
        "goal_command": goal_lines[0],
    }


@contextlib.contextmanager
def windows_named_mutex(root: Path, key: str) -> Iterator[None]:
    import ctypes
    from ctypes import wintypes

    if key == "workspace_registration":
        identity = b"goal-forge-machine-workspace-registration-v1"
        mutex_prefix = "Global\\GoalForge_"
    else:
        identity = (
            os.path.normcase(str(root.resolve(strict=False))) + "\0" + key
        ).encode("utf-8")
        mutex_prefix = "Global\\Intentwright_"
    mutex_name = mutex_prefix + sha256_bytes(identity)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    create_mutex.restype = wintypes.HANDLE
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    release = kernel32.ReleaseMutex
    release.argtypes = [wintypes.HANDLE]
    release.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    handle = create_mutex(None, False, mutex_name)
    if not handle:
        raise LifecycleError(
            f"Cannot create lifecycle mutex for {key}: Windows error {ctypes.get_last_error()}"
        )
    wait_result = wait(handle, 0)
    if wait_result not in {0x00000000, 0x00000080}:
        close(handle)
        if wait_result == 0x00000102:
            raise LifecycleError(f"Another lifecycle operation is active for {key}")
        raise LifecycleError(
            f"Cannot acquire lifecycle mutex for {key}: Windows result {wait_result}"
        )
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            release(handle)
        close(handle)


@contextlib.contextmanager
def named_lock(root: Path, key: str) -> Iterator[None]:
    if re.fullmatch(r"[a-zA-Z0-9_.-]+", key) is None:
        raise LifecycleError(f"Unsafe lifecycle lock key: {key}")
    if os.name == "nt":
        with windows_named_mutex(root, key):
            yield
        return
    lock_path = root / LOCKS / f"{key}.lock"
    lock_directory = lock_path.parent
    lock_directory.mkdir(parents=True, exist_ok=True)
    if is_link_like(lock_directory) or not lock_directory.is_dir():
        raise LifecycleError(f"Unsafe lifecycle lock directory: {lock_directory}")
    if lock_path.exists() and is_link_like(lock_path):
        raise LifecycleError(f"Refusing a linked or reparse-point lifecycle lock: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LifecycleError(f"Cannot safely open lifecycle lock {lock_path}: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        path_info = lock_path.lstat()
    except OSError as exc:
        os.close(descriptor)
        raise LifecycleError(f"Cannot validate lifecycle lock {lock_path}: {exc}") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(path_info.st_mode)
        or opened.st_nlink != 1
        or path_info.st_nlink != 1
        or (opened.st_dev, opened.st_ino) != (path_info.st_dev, path_info.st_ino)
        or is_link_like(lock_path)
    ):
        os.close(descriptor)
        raise LifecycleError(f"Lifecycle lock is not a unique regular file: {lock_path}")
    handle = os.fdopen(descriptor, "r+b", closefd=True)
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LifecycleError(f"Another lifecycle operation is active for {key}") from exc
        yield
    finally:
        with contextlib.suppress(OSError):
            handle.seek(0)
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@contextlib.contextmanager
def goal_lock(root: Path, goal_id: str) -> Iterator[None]:
    validate_goal_id(goal_id)
    with named_lock(root, goal_id):
        yield


@contextlib.contextmanager
def workspace_lease_lock(root: Path) -> Iterator[None]:
    with named_lock(root, "workspace_leases"):
        yield


@contextlib.contextmanager
def workspace_registration_lock() -> Iterator[None]:
    coordination_root = Path.home() / LEGACY_COORDINATION_DIRECTORY
    with named_lock(coordination_root, "workspace_registration"):
        yield


@contextlib.contextmanager
def multiple_goal_locks(root: Path, goal_ids: list[str]) -> Iterator[None]:
    ordered = sorted(set(goal_ids))
    for goal_id in ordered:
        validate_goal_id(goal_id)
    with contextlib.ExitStack() as stack:
        for goal_id in ordered:
            stack.enter_context(goal_lock(root, goal_id))
        yield


def make_goal_command(
    workspace: Path, package: Path, manifest: dict[str, Any]
) -> str:
    goal_id = manifest["goal_id"]
    relative = project_relative(workspace, package)
    spec_file = manifest["spec_file"]
    spec_hash = manifest["spec_sha256"]
    return (
        f'/goal Execute only immutable Intentwright package {goal_id} at "{package}" '
        f'({relative}/{spec_file}). First read execution_prompt.md and {spec_file}, verify '
        f"SHA-256 {spec_hash}, and claim its declared write scopes before changing project files. "
        "Never read sibling goal specs or modify sibling packages. Continue until every mandatory "
        "AC- criterion has structured evidence. Follow execution_prompt.md's reason-specific "
        "terminal ordering exactly: achievement archives before completion, while platform-blocked "
        "or user-cancelled/replaced outcomes transition externally before archival. If the pending "
        "path is absent, recover only this exact goal ID from terminal folders; never recreate or "
        "rerun a terminal goal."
    )


def python_launcher() -> str:
    """Return the conventional Python 3 launcher for the current platform."""
    return "python" if os.name == "nt" else "python3"


def render_execution_prompt(
    workspace: Path, package: Path, manifest: dict[str, Any]
) -> str:
    script = Path(__file__).resolve()
    launcher = python_launcher()
    command = make_goal_command(workspace, package, manifest)
    relative_package = project_relative(workspace, package)
    goal_id = manifest["goal_id"]
    spec_file = manifest["spec_file"]
    spec_hash = manifest["spec_sha256"]
    goals_dir = package.parent.parent.name
    scopes = ", ".join(manifest["write_scopes"])
    return f"""# Intentwright execution handoff

Paste this exact command into a new Codex session that can access the workspace:

{command}

## Immutable target

- Goal ID: `{goal_id}`
- Workspace hint: `{workspace}`
- Package: `{relative_package}`
- Spec: `{relative_package}/{spec_file}`
- Expected SHA-256: `{spec_hash}`
- Declared write scopes: `{scopes}`
- Lifecycle helper: `{script}`

The goal ID and project-relative package are canonical. The absolute paths are convenience hints.
Treat the goal root as potentially sensitive local operational state: specifications,
evidence, host or agent identity, and live or historical claim tokens may appear
there. Do not commit or publish it unless the user deliberately approved that
disclosure.

## Mandatory startup

1. Resolve only the exact package above. Do not select by recency or similarity.
2. Run:

   `{launcher} "{script}" verify --package "{package}"`

3. Confirm the returned goal ID and SHA-256 match this handoff.
4. Atomically claim the package before modifying project files:

   `{launcher} "{script}" claim --package "{package}" --identity "<real thread or agent identity>"`

   Include `--identity` only when a real identity is available; otherwise omit that option. Never fabricate one.

5. Retain the returned `claim_token` and `claim_epoch`. Re-read `claim.json` and confirm both.
6. Treat only `{spec_file}` as the authoritative requirements source. The approved semantic body is an integrity copy, not a second source to reinterpret. Access this package's manifest, seal, status, claim, evidence, and outcome files only for lifecycle work.
7. Exclude the goal root from broad repository searches. Never open sibling specs or modify sibling packages. The lifecycle helper alone may verify sibling lifecycle metadata, sealed integrity, and explicitly linked lineage to enforce leases and replacement ordering.

## During execution

- Heartbeat before and after material phases:

  `{launcher} "{script}" heartbeat --package "{package}" --claim-token "<claim_token>" --action "<phase>"`

- Stop if the claim token or epoch no longer matches.
- If a short lifecycle operation reports that `workspace_leases` is busy, retry that exact operation after the competing lifecycle mutation finishes; this transient lock is not a terminal blocker.
- Keep temporary pauses and recoverable blockers in `goal_pending`.
- Do not modify the frozen spec or immutable manifest.
- Enter `validating` for the final acceptance pass:

  `{launcher} "{script}" state --package "{package}" --claim-token "<claim_token>" --state validating --action "Running final acceptance pass"`

## Terminalization

Write machine-validated `outcome.json`, human-readable `outcome.md`, and all required evidence first. Every mandatory `AC-` must pass; mandatory criteria cannot be waived. If an approved mandatory criterion is no longer appropriate, keep the package pending and obtain a replacement specification. `SAC-` stretch criteria do not block achievement.

Each `pass` or `fail` criterion points to one or more structured JSON evidence records. Every record must quote that criterion's approved `Required evidence` cell exactly, use the current claim epoch, record an RFC3339 UTC observation time, and hash at least one nonempty supporting artifact below `evidence/`. Example:

```json
{{
  "schema_version": 2,
  "goal_id": "{goal_id}",
  "criterion_id": "AC-001",
  "claim_epoch": 1,
  "observed_at": "2026-07-19T12:00:00Z",
  "required_evidence": "Exact text from the approved Required evidence cell.",
  "method": "command",
  "observation": "The command completed and its output demonstrates the pass condition.",
  "command": "{launcher} -m pytest",
  "exit_code": 0,
  "artifacts": [
    {{
      "path": "evidence/ac-001-test-output.txt",
      "sha256": "<64 lowercase hex characters>",
      "description": "Complete captured output from the acceptance command."
    }}
  ]
}}
```

`outcome.json` must use this exact schema (replace the example values and include every mandatory `AC-` exactly once; optional `SAC-` rows may also be included):

```json
{{
  "schema_version": 2,
  "goal_id": "{goal_id}",
  "outcome": "achieved",
  "reason_code": "completed",
  "summary": "A concrete summary of the terminal result.",
  "criteria": [
    {{
      "id": "AC-001",
      "result": "pass",
      "evidence_records": ["evidence/ac-001-record.json"]
    }}
  ],
  "validation": ["Exact commands and checks that were run."],
  "known_limitations": [],
  "remaining_work": [],
  "blocked_threshold_evidence": null,
  "user_authorization": null,
  "replacement_goal_id": null,
  "external_goal_disposition": "complete_after_archive"
}}
```

`pass` and `fail` require structured evidence records; `not_run` requires an empty `evidence_records` list. The helper rejects record or artifact paths outside this package, stale claim epochs, future timestamps, mismatched required-evidence text, missing artifact hashes, and nonzero command exits claimed as passes. For `not_achieved`, record non-empty remaining work; for `achieved`, `remaining_work` must be empty.

For `reason_code: "blocked"`, replace `blocked_threshold_evidence` with an object containing exactly `rule`, `blocker`, `occurrences`, and `no_safe_progress_remaining`. `occurrences` must contain at least three ordered, consecutive objects with exactly `turn`, `observed_at`, and `evidence`. This package record is supporting attestation, not the authority: the platform's threshold-gated `/goal` blocked transition must succeed first.

For `cancelled_by_user`, `abandoned_by_user`, or `superseded`, the user must first cancel or replace the external persistent goal. `user_authorization` and `--authorized-reason` must then be the exact reason-specific phrase emitted by the helper contract: `Cancel goal {goal_id}`, `Abandon goal {goal_id}`, or `Supersede goal {goal_id} with <replacement_goal_id>`. Supersession also requires the exact linked replacement ID. The helper freezes the complete terminal package in `terminal_seal.json`.

Then archive:

`{launcher} "{script}" archive --package "{package}" --claim-token "<claim_token>" --outcome achieved --reason-code completed --external-goal-disposition complete_after_archive`

For a genuinely terminal unsuccessful result, use `--outcome not_achieved`. Executor-driven unsuccessful terminalization is limited to `blocked` or an exact user cancellation, abandonment, or supersession handshake. Validation failure and apparent infeasibility remain pending work unless they mature into the platform's real repeated-blocker terminal condition or the user explicitly cancels/replaces the goal. For `blocked`, call the platform's threshold-gated blocked transition first, then pass `--platform-blocked-confirmed --external-goal-disposition platform_blocked_before_archive`. A turn ending, rate limit, time budget, temporary outage, or retryable dependency is not terminal.

For achievement, only after the archive command verifies the terminal move may the persistent `/goal` be completed. For blocked or user-controlled cancellation/replacement, the external transition happens first and the matching disposition is frozen in the archive. Never mark incomplete work complete. If the pending path is missing, use exact-ID recovery and never rerun terminal work:

`{launcher} "{script}" recover --workspace "{workspace}" --goals-dir "{goals_dir}" --goal-id "{goal_id}" --claim-token "<claim_token when required>"`
"""


def make_portable_payload(
    manifest: dict[str, Any], approved_body: str, spec_text: str
) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "intentwright-portable",
        "manifest": manifest,
        "approved_body_utf8_base64": base64.b64encode(
            approved_body.encode("utf-8")
        ).decode("ascii"),
        "spec_utf8_base64": base64.b64encode(spec_text.encode("utf-8")).decode("ascii"),
    }
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    return "\n".join(textwrap.wrap(encoded, width=100))


def render_portable_handoff(
    workspace: Path,
    package: Path,
    manifest: dict[str, Any],
    approved_body: str,
    spec_text: str,
) -> str:
    command = make_goal_command(workspace, package, manifest)
    payload = make_portable_payload(manifest, approved_body, spec_text)
    goals_dir = package.parent.parent.name
    return f"""# Intentwright portable handoff

Use the short command below when the new session can access the original workspace:

{command}

For a disconnected copy mounted at the exact same receipt-bound canonical absolute workspace identity, copy or attach this entire file first. Use that machine's local Intentwright lifecycle helper to run:

`<python> "<local Intentwright skill>/scripts/intentwright_lifecycle.py" import-portable --workspace "<exact approved absolute workspace path>" --goals-dir "{goals_dir}" --file "<this portable_handoff.md>"`

Use `python` for `<python>` on Windows and normally `python3` on macOS or Linux; it must resolve to Python 3.10 or newer. Resolve `<local Intentwright skill>` on that machine (normally `$HOME/.agents/skills/intentwright`), verify the returned package and hash, then use the newly generated short `/goal`. Any different absolute workspace path or repository requires a new Intentwright readback and approval; the import command will refuse it. Do not truncate the embedded specification.

Important:

- Goal ID: `{manifest['goal_id']}`
- Spec SHA-256: `{manifest['spec_sha256']}`
- A terminal copy of this exact goal ID must never be replayed.
- Packages copied to different filesystems do not share claim state.
- Packages with `retry_of` or `supersedes` lineage are deliberately non-portable without their complete lifecycle history.
- A detached copy cannot prove that another filesystem has since terminalized this ID; confirm provenance before import.
- Never fuzzy-search for a similarly named package.

The machine-readable payload below contains the immutable manifest, exact approved semantic body, and mechanically wrapped UTF-8 specification.

{PORTABLE_BEGIN}
{payload}
{PORTABLE_END}
"""


def locate_exact(root: Path, goal_id: str) -> dict[str, list[Path]]:
    validate_goal_id(goal_id)
    found: dict[str, list[Path]] = {name: [] for name in LOCATION_NAMES}
    for name in LOCATION_NAMES:
        candidate = root / name / goal_id
        if candidate.exists():
            if is_link_like(candidate) or not candidate.is_dir():
                raise LifecycleError(f"Unsafe exact-ID path: {candidate}")
            found[name].append(candidate.resolve(strict=True))
    staging = [
        entry.resolve(strict=True)
        for entry in (root / PENDING).glob(f".staging_{goal_id}_*")
        if entry.is_dir() and not is_link_like(entry)
    ]
    found["staging"] = staging
    return found


def assert_goal_id_absent(root: Path, goal_id: str) -> None:
    found = locate_exact(root, goal_id)
    matches = [str(path) for paths in found.values() for path in paths]
    if matches:
        raise LifecycleError(
            f"Goal ID already exists and will not be overwritten or replayed: {', '.join(matches)}"
        )


def validate_retry_parent(
    root: Path,
    retry_of: str | None,
    ancestors: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    if retry_of is None:
        return None
    validate_goal_id(retry_of)
    retry_ancestors = ancestors or frozenset()
    if retry_of in retry_ancestors:
        raise LifecycleError("Retry lineage contains a cycle")
    located = locate_exact(root, retry_of)
    if len(located[NOT_ACHIEVED]) != 1 or any(
        located[name] for name in (PENDING, ACHIEVED, "staging")
    ):
        raise LifecycleError(
            "retry_of must identify exactly one finalized goal_not_achieved package"
        )
    result = validate_published_package(
        str(located[NOT_ACHIEVED][0]),
        _retry_ancestors=retry_ancestors,
    )
    if (
        result["location"] != NOT_ACHIEVED
        or result["status"]["state"] != "not_achieved"
    ):
        raise LifecycleError(
            "retry_of parent is not a finalized goal_not_achieved package"
        )
    return result


def validate_replacement_link(
    root: Path,
    old_goal_id: str,
    replacement_goal_id: str,
) -> dict[str, Any]:
    validate_goal_id(old_goal_id)
    validate_goal_id(replacement_goal_id)
    if old_goal_id == replacement_goal_id:
        raise LifecycleError("A goal cannot supersede itself")
    located = locate_exact(root, replacement_goal_id)
    replacement_paths = located[PENDING]
    if len(replacement_paths) != 1 or any(
        located[name] for name in (ACHIEVED, NOT_ACHIEVED, "staging")
    ):
        raise LifecycleError(
            "Replacement goal must exist exactly once as a published pending package"
        )
    replacement = replacement_paths[0]
    result = validate_published_package(str(replacement))
    if result["manifest"].get("supersedes") != old_goal_id:
        raise LifecycleError(
            "Replacement manifest does not explicitly supersede the terminalizing goal"
        )
    if result["status"]["state"] != "pending" or (replacement / "claim.json").exists():
        raise LifecycleError(
            "Replacement goal must remain clean and unclaimed until its predecessor is archived"
        )
    old_located = locate_exact(root, old_goal_id)
    if len(old_located[PENDING]) == 1:
        old_result = validate_published_package(str(old_located[PENDING][0]))
        validate_supersession_ready_for_claim(root, old_result["manifest"])
    return result


def validate_replacement_lineage_any(
    root: Path,
    old_goal_id: str,
    replacement_goal_id: str,
) -> dict[str, Any]:
    validate_goal_id(old_goal_id)
    validate_goal_id(replacement_goal_id)
    located = locate_exact(root, replacement_goal_id)
    exact = [
        path
        for location in LOCATION_NAMES
        for path in located[location]
    ]
    if len(exact) != 1 or located["staging"]:
        raise LifecycleError(
            "Superseded terminal package cannot resolve its exact replacement goal"
        )
    result = validate_published_package(str(exact[0]))
    if result["manifest"].get("supersedes") != old_goal_id:
        raise LifecycleError(
            "Replacement manifest does not link back to the superseded goal"
        )
    return result


def validate_supersession_ready_for_claim(
    root: Path,
    manifest: dict[str, Any],
    visited: set[str] | None = None,
) -> None:
    chain = set() if visited is None else set(visited)
    current_goal_id = manifest["goal_id"]
    if current_goal_id in chain:
        raise LifecycleError("Supersession lineage contains a cycle")
    chain.add(current_goal_id)
    predecessor_id = manifest.get("supersedes")
    if predecessor_id is None:
        return
    located = locate_exact(root, predecessor_id)
    if len(located[NOT_ACHIEVED]) != 1 or any(
        located[name] for name in (PENDING, ACHIEVED, "staging")
    ):
        raise LifecycleError(
            "Replacement cannot be claimed until its exact predecessor is terminally superseded"
        )
    predecessor = validate_published_package(str(located[NOT_ACHIEVED][0]))
    status = predecessor["status"]
    intent = status.get("archive_intent")
    if (
        status.get("terminal_reason_code") != "superseded"
        or not isinstance(intent, dict)
        or intent.get("replacement_goal_id") != manifest["goal_id"]
    ):
        raise LifecycleError(
            "Predecessor terminal record does not authorize this exact replacement goal"
        )
    validate_supersession_ready_for_claim(
        root,
        predecessor["manifest"],
        chain,
    )


def write_status(
    package: Path,
    status: dict[str, Any],
    *,
    state: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    updated = dict(status)
    if state is not None:
        updated["state"] = state
    if action is not None:
        updated["last_action"] = action
    updated["updated_at"] = utc_now()
    atomic_write_json(package / "status.json", updated)
    return updated


def check_claim(package: Path, goal_id: str, token: str) -> dict[str, Any]:
    claim = read_json(package / "claim.json")
    validate_claim_record(claim, goal_id)
    manifest = load_manifest(package)
    if claim.get("write_scopes") != manifest.get("write_scopes"):
        raise LifecycleError("Claim write scopes do not match the immutable manifest")
    try:
        uuid.UUID(token)
    except ValueError as exc:
        raise LifecycleError("Claim token is not a valid UUID") from exc
    if not secrets.compare_digest(str(claim.get("claim_token", "")), token):
        raise LifecycleError("Claim token mismatch; this executor is not the current owner")
    return claim


def validate_claim_record(claim: dict[str, Any], goal_id: str) -> None:
    exact_schema_version(claim.get("schema_version"), "Claim record")
    if claim.get("goal_id") != goal_id:
        raise LifecycleError("Claim goal ID does not match the package")
    try:
        parsed = uuid.UUID(str(claim.get("claim_token", "")))
    except ValueError as exc:
        raise LifecycleError("Claim record contains an invalid token") from exc
    if str(parsed) != claim.get("claim_token"):
        raise LifecycleError("Claim record token is not canonical")
    if type(claim.get("claim_epoch")) is not int or claim["claim_epoch"] < 1:
        raise LifecycleError("Claim epoch is invalid")
    parse_utc_timestamp(claim.get("claimed_at"), "Claim claimed_at")
    parse_utc_timestamp(claim.get("heartbeat_at"), "Claim heartbeat_at")
    scopes = claim.get("write_scopes")
    if not isinstance(scopes, list) or normalize_write_scopes(scopes) != scopes:
        raise LifecycleError("Claim write scopes are missing or invalid")


def refresh_claim(package: Path, claim: dict[str, Any], action: str) -> dict[str, Any]:
    updated = dict(claim)
    updated["heartbeat_at"] = utc_now()
    updated["last_action"] = action
    atomic_write_json(package / "claim.json", updated)
    return updated


def validate_manifest_seal_only(package: Path, manifest: dict[str, Any]) -> None:
    seal = read_json(package / SEAL_FILE)
    if (
        type(seal.get("schema_version")) is not int
        or seal.get("schema_version") != SCHEMA_VERSION
        or seal.get("goal_id") != manifest["goal_id"]
    ):
        raise LifecycleError(f"Sibling package seal is invalid: {package}")
    files = seal.get("files")
    if not isinstance(files, dict):
        raise LifecycleError(f"Sibling package seal file map is invalid: {package}")
    expected = files.get("goal_manifest.json")
    actual = sha256_file(package / "goal_manifest.json")
    if not isinstance(expected, str) or not secrets.compare_digest(expected, actual):
        raise LifecycleError(f"Sibling manifest changed after publication: {package}")


def find_scope_conflicts(
    root: Path,
    current_goal_id: str,
    requested_scopes: list[str],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    workspace = root.parent.resolve(strict=True)
    requested_comparison = validate_write_scope_paths(workspace, requested_scopes)
    for candidate in (root / PENDING).iterdir():
        if candidate.name.startswith(".staging_"):
            continue
        if is_link_like(candidate):
            raise LifecycleError(f"Unsafe linked entry in goal_pending: {candidate}")
        if not candidate.is_dir():
            raise LifecycleError(f"Unexpected non-directory entry in goal_pending: {candidate}")
        if GOAL_ID_RE.fullmatch(candidate.name) is None:
            raise LifecycleError(f"Unexpected package name in goal_pending: {candidate.name}")
        if candidate.name == current_goal_id:
            continue
        claim_path = candidate / "claim.json"
        if not claim_path.exists():
            continue
        manifest = load_manifest(candidate)
        if manifest["goal_id"] != candidate.name:
            raise LifecycleError(f"Sibling package name does not match its manifest: {candidate}")
        validate_manifest_seal_only(candidate, manifest)
        claim = read_json(claim_path)
        validate_claim_record(claim, manifest["goal_id"])
        sibling_scopes = manifest["write_scopes"]
        sibling_comparison = validate_write_scope_paths(workspace, sibling_scopes)
        if scopes_overlap(requested_comparison, sibling_comparison):
            conflicts.append(
                {
                    "goal_id": manifest["goal_id"],
                    "write_scopes": sibling_scopes,
                    "agent_identity": claim.get("agent_identity"),
                    "claim_epoch": claim.get("claim_epoch"),
                }
            )
    return conflicts


def command_approval_receipt(args: argparse.Namespace) -> None:
    candidate_input = Path(args.file).expanduser()
    if is_link_like(candidate_input):
        raise LifecycleError(f"Refusing a linked approval draft: {candidate_input}")
    candidate = candidate_input.resolve(strict=True)
    workspace = canonical_workspace(args.workspace)
    goals_dir = safe_relative_dir(args.goals_dir).as_posix()
    title = safe_single_line(args.title, "--title", maximum=200)
    slug = sanitize_slug(args.slug)
    if type(args.revision) is not int or args.revision < 1:
        raise LifecycleError("--revision must be at least 1")
    if INTERVIEW_ID_RE.fullmatch(args.interview_id) is None:
        raise LifecycleError("--interview-id must use the iwi_<UTC>_<slug>_<4hex> format")
    if args.retry_of and args.supersedes:
        raise LifecycleError("A package cannot set both --retry-of and --supersedes")
    for linked in (args.retry_of, args.supersedes):
        if linked is not None:
            validate_goal_id(linked)
    scopes = normalize_write_scopes(args.write_scope)
    validate_write_scope_paths(workspace, scopes)
    text = read_utf8_exact(candidate)
    validate_canonical_body_text(text)
    analysis = validate_semantic_body(
        text,
        scopes,
        args.retry_of,
        args.supersedes,
    )
    body_hash = sha256_file(candidate)
    payload = approval_receipt_payload(
        workspace=workspace,
        goals_dir=goals_dir,
        title=title,
        slug=slug,
        revision=args.revision,
        interview_id=args.interview_id,
        approved_body_sha256=body_hash,
        write_scopes=scopes,
        retry_of=args.retry_of,
        supersedes=args.supersedes,
    )
    receipt_hash = approval_receipt_sha256(payload)
    emit(
        {
            "ok": True,
            "canonical_body": str(candidate),
            "approved_body_sha256": body_hash,
            "approval_receipt_sha256": receipt_hash,
            "approval_phrase": expected_approval_phrase(args.revision, receipt_hash),
            "receipt": payload,
            "requirements": sorted(analysis["requirements"]),
            "mandatory_acceptance_criteria": analysis["mandatory_acceptance"],
            "stretch_acceptance_criteria": analysis["stretch_acceptance"],
            "next": (
                "Show the complete canonical body and this exact receipt before requesting "
                "the emitted approval_phrase verbatim."
            ),
        }
    )


def command_init(args: argparse.Namespace) -> None:
    workspace = canonical_workspace(args.workspace)
    goals_dir = safe_relative_dir(args.goals_dir).as_posix()
    slug = sanitize_slug(args.slug)
    title = safe_single_line(args.title, "--title", maximum=200)
    if type(args.revision) is not int or args.revision < 1:
        raise LifecycleError("--revision must be at least 1")
    if INTERVIEW_ID_RE.fullmatch(args.interview_id) is None:
        raise LifecycleError("--interview-id must use the iwi_<UTC>_<slug>_<4hex> format")
    approval_body_sha256 = args.approved_body_sha256.lower()
    if re.fullmatch(r"[0-9a-f]{64}", approval_body_sha256) is None:
        raise LifecycleError("--approved-body-sha256 must be exactly 64 hexadecimal characters")
    supplied_receipt = args.approval_receipt_sha256.lower()
    if re.fullmatch(r"[0-9a-f]{64}", supplied_receipt) is None:
        raise LifecycleError(
            "--approval-receipt-sha256 must be exactly 64 hexadecimal characters"
        )
    write_scopes = normalize_write_scopes(args.write_scope)
    validate_write_scope_paths(workspace, write_scopes)
    if args.retry_of and args.supersedes:
        raise LifecycleError("A package cannot set both --retry-of and --supersedes")
    for linked in (args.retry_of, args.supersedes):
        if linked is not None:
            validate_goal_id(linked)
    receipt_payload = approval_receipt_payload(
        workspace=workspace,
        goals_dir=goals_dir,
        title=title,
        slug=slug,
        revision=args.revision,
        interview_id=args.interview_id,
        approved_body_sha256=approval_body_sha256,
        write_scopes=write_scopes,
        retry_of=args.retry_of,
        supersedes=args.supersedes,
    )
    expected_receipt = approval_receipt_sha256(receipt_payload)
    if not secrets.compare_digest(supplied_receipt, expected_receipt):
        raise LifecycleError(
            "--approval-receipt-sha256 does not match the exact approved execution envelope"
        )
    approval_record = args.approval_record
    expected_approval = expected_approval_phrase(args.revision, expected_receipt)
    if approval_record != expected_approval:
        raise LifecycleError(f"--approval-record must be exactly {expected_approval!r}")

    workspace, root = workspace_and_root(workspace, goals_dir, create=True)
    if args.retry_of:
        validate_retry_parent(root, args.retry_of)
    if args.supersedes:
        old = locate_exact(root, args.supersedes)
        if len(old[PENDING]) != 1 or any(old[name] for name in (ACHIEVED, NOT_ACHIEVED, "staging")):
            raise LifecycleError("--supersedes must identify exactly one pending goal")
        old_package = old[PENDING][0]
        old_result = validate_published_package(str(old_package))
        if old_result["status"]["state"] == "archive_prepared":
            raise LifecycleError("An archive-prepared goal cannot accept a new replacement")

    for _ in range(16):
        goal_id = f"g_{goal_timestamp()}_{slug}_{secrets.token_hex(4)}"
        if not any(locate_exact(root, goal_id).values()):
            break
    else:
        raise LifecycleError("Could not allocate a unique goal ID")

    staging = root / PENDING / f".staging_{goal_id}_{secrets.token_hex(4)}"
    staging.mkdir(exist_ok=False)
    spec_file = f"goal_spec_{slug}.md"
    created_at = utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "goal_id": goal_id,
        "slug": slug,
        "title": title,
        "revision": args.revision,
        "interview_id": args.interview_id,
        "approval_record": approval_record,
        "approval_receipt_sha256": expected_receipt,
        "approval_body_sha256": approval_body_sha256,
        "created_at": created_at,
        "published_at": None,
        "project_relative_package": None,
        "approved_body_file": APPROVED_BODY_FILE,
        "approved_body_sha256": None,
        "spec_file": spec_file,
        "spec_sha256": None,
        "write_scopes": write_scopes,
        "execution_prompt_file": "execution_prompt.md",
        "portable_handoff_file": "portable_handoff.md",
        "retry_of": args.retry_of,
        "supersedes": args.supersedes,
    }
    status = {
        "schema_version": SCHEMA_VERSION,
        "goal_id": goal_id,
        "state": "draft",
        "attempt": 0,
        "claim_epoch": 0,
        "created_at": created_at,
        "updated_at": created_at,
        "archive_intent": None,
        "terminal_reason_code": None,
        "last_action": "Created unpublished staging package",
    }
    atomic_write_json(staging / "goal_manifest.json", manifest)
    atomic_write_json(staging / "status.json", status)
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "slug": slug,
            "staging_package": str(staging),
            "approved_body_file": APPROVED_BODY_FILE,
            "approved_body_path": str(staging / APPROVED_BODY_FILE),
            "spec_file": spec_file,
            "declared_write_scopes": write_scopes,
            "next": (
                "Write the exact user-approved semantic body byte-for-byte to approved_body_path, "
                "then run publish. The helper will add only the mechanical envelope."
            ),
        }
    )


def command_publish(args: argparse.Namespace) -> None:
    initial_workspace, initial_root, initial_staging = find_staging_context(args.package)
    initial_manifest = load_manifest(initial_staging)
    goal_id = initial_manifest["goal_id"]
    if not initial_staging.name.startswith(f".staging_{goal_id}_"):
        raise LifecycleError("Staging directory name does not match its manifest goal_id")

    with goal_lock(initial_root, goal_id):
        workspace, root, staging = find_staging_context(args.package)
        manifest = load_manifest(staging)
        if (
            workspace != initial_workspace
            or root != initial_root
            or staging != initial_staging
            or manifest["goal_id"] != goal_id
        ):
            raise LifecycleError("Staging identity changed before publication")
        validate_manifest_approval_receipt(workspace, root, manifest)
        final = root / PENDING / goal_id
        approved_body_path = staging / manifest["approved_body_file"]
        if not approved_body_path.is_file() or is_link_like(approved_body_path):
            raise LifecycleError(f"Approved semantic body is missing: {approved_body_path}")
        approved_body = validate_canonical_body_file(
            approved_body_path,
            manifest["approval_body_sha256"],
        )
        analysis = validate_semantic_body(
            approved_body,
            manifest["write_scopes"],
            manifest["retry_of"],
            manifest["supersedes"],
        )
        validate_retry_parent(root, manifest.get("retry_of"), frozenset({goal_id}))

        found = locate_exact(root, goal_id)
        non_staging = [
            path
            for name, paths in found.items()
            if name != "staging"
            for path in paths
        ]
        if non_staging:
            raise LifecycleError(f"Goal ID already published or terminal: {non_staging[0]}")
        if final.exists():
            raise LifecycleError(f"Refusing to overwrite pending destination: {final}")

        published_manifest = dict(manifest)
        published_manifest["published_at"] = utc_now()
        published_manifest["project_relative_package"] = project_relative(workspace, final)
        published_manifest["approved_body_sha256"] = sha256_file(approved_body_path)
        if (
            published_manifest["approved_body_sha256"]
            != published_manifest["approval_body_sha256"]
        ):
            raise LifecycleError("Publication body hash differs from the approved body hash")

        spec = staging / published_manifest["spec_file"]
        spec_text = render_canonical_spec(
            workspace,
            final,
            published_manifest,
            approved_body,
        )
        atomic_write_text(spec, spec_text)
        published_manifest["spec_sha256"] = sha256_file(spec)
        atomic_write_json(staging / "goal_manifest.json", published_manifest)

        execution = render_execution_prompt(workspace, final, published_manifest)
        portable = render_portable_handoff(
            workspace,
            final,
            published_manifest,
            approved_body,
            spec_text,
        )
        atomic_write_text(staging / "execution_prompt.md", execution)
        atomic_write_text(staging / "portable_handoff.md", portable)
        write_package_seal(staging, published_manifest)
        status = load_status(staging, goal_id)
        status["attempt"] = 0
        status["archive_intent"] = None
        write_status(staging, status, state="pending", action="Published approved immutable spec")

        if sha256_file(approved_body_path) != published_manifest["approved_body_sha256"]:
            raise LifecycleError("Approved semantic body changed during publication")
        if sha256_file(spec) != published_manifest["spec_sha256"]:
            raise LifecycleError("Specification changed during publication")
        if len(make_goal_command(workspace, final, published_manifest)) > 4000:
            raise LifecycleError("Generated /goal exceeds 4,000 characters")
        if not (staging / "execution_prompt.md").is_file() or not (
            staging / "portable_handoff.md"
        ).is_file():
            raise LifecycleError("Publication handoffs were not created")
        assert_no_link_like(staging)
        validate_package_seal(staging, published_manifest)
        portable_manifest, portable_body, portable_spec = parse_portable(
            staging / "portable_handoff.md"
        )
        if (
            portable_manifest != published_manifest
            or portable_body != approved_body
            or portable_spec != spec_text
        ):
            raise LifecycleError("Generated portable handoff does not match the approved package")

        os.rename(staging, final)

    result = validate_published_package(str(final))
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "pending_package": str(final),
            "approved_body_path": str(final / published_manifest["approved_body_file"]),
            "approved_body_sha256": result["approved_body_sha256"],
            "spec_path": str(final / published_manifest["spec_file"]),
            "spec_sha256": result["spec_sha256"],
            "requirements": sorted(analysis["requirements"]),
            "mandatory_acceptance_criteria": analysis["mandatory_acceptance"],
            "stretch_acceptance_criteria": analysis["stretch_acceptance"],
            "execution_prompt": str(final / "execution_prompt.md"),
            "portable_handoff": str(final / "portable_handoff.md"),
            "goal_command": result["goal_command"],
        }
    )


def command_discard_staging(args: argparse.Namespace) -> None:
    initial_workspace, initial_root, initial_staging = find_staging_context(args.package)
    initial_manifest = load_manifest(initial_staging)
    goal_id = initial_manifest["goal_id"]
    if not initial_staging.name.startswith(f".staging_{goal_id}_"):
        raise LifecycleError("Staging directory name does not match its manifest goal_id")
    expected_confirmation = f"Discard unpublished staging {goal_id}"
    if args.confirmation != expected_confirmation:
        raise LifecycleError(
            f"--confirmation must be exactly {expected_confirmation!r}"
        )

    with goal_lock(initial_root, goal_id):
        workspace, root, staging = find_staging_context(args.package)
        manifest = load_manifest(staging)
        if (
            workspace != initial_workspace
            or root != initial_root
            or staging != initial_staging
            or manifest["goal_id"] != goal_id
        ):
            raise LifecycleError("Staging identity changed before discard")
        status = load_status(staging, goal_id)
        if status["state"] != "draft":
            raise LifecycleError("Only an unpublished draft staging package can be discarded")
        if any(
            manifest.get(field) is not None
            for field in (
                "published_at",
                "project_relative_package",
                "approved_body_sha256",
                "spec_sha256",
            )
        ):
            raise LifecycleError("Published or partially published staging cannot be discarded")
        prohibited = {
            "claim.json",
            SEAL_FILE,
            TERMINAL_SEAL_FILE,
            "outcome.json",
            "outcome.md",
        }
        present = sorted(name for name in prohibited if (staging / name).exists())
        if present:
            raise LifecycleError(
                "Staging contains execution or publication records and requires inspection: "
                + ", ".join(present)
            )
        assert_no_link_like(staging)
        expected_parent = (root / PENDING).resolve(strict=True)
        if staging.parent != expected_parent or not is_within(staging, expected_parent):
            raise LifecycleError("Staging discard target is not canonical")
        shutil.rmtree(staging)
        if staging.exists():
            raise LifecycleError("Unpublished staging discard could not be verified")
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "discarded_staging": str(staging),
            "workspace": str(workspace),
            "recoverable": False,
            "next": "The exact unpublished draft was removed and cannot be executed.",
        }
    )


def command_verify(args: argparse.Namespace) -> None:
    result = validate_published_package(args.package)
    emit(
        {
            "ok": True,
            "goal_id": result["manifest"]["goal_id"],
            "location": result["location"],
            "state": result["status"]["state"],
            "package": str(result["package"]),
            "spec_file": result["manifest"]["spec_file"],
            "spec_sha256": result["spec_sha256"],
            "approved_body_file": result["manifest"]["approved_body_file"],
            "approved_body_sha256": result["approved_body_sha256"],
            "write_scopes": result["manifest"]["write_scopes"],
            "requirements": result["requirements"],
            "mandatory_acceptance_criteria": result["acceptance"],
            "stretch_acceptance_criteria": result["stretch_acceptance"],
            "terminal_reason_code": result["status"].get("terminal_reason_code"),
            "goal_command": result["goal_command"],
        }
    )


def command_claim(args: argparse.Namespace) -> None:
    identity = (
        safe_single_line(args.identity, "--identity", maximum=200)
        if args.identity is not None
        else None
    )
    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Only a pending package can be claimed")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    root = result["root"]
    with workspace_lease_lock(root):
        with goal_lock(root, goal_id):
            result = validate_published_package(str(package))
            validate_supersession_ready_for_claim(root, result["manifest"])
            claim_path = package / "claim.json"
            if claim_path.exists():
                existing = read_json(claim_path)
                validate_claim_record(existing, goal_id)
                raise LifecycleError(
                    "Package is already claimed by "
                    f"{existing.get('agent_identity') or 'an unidentified executor'} "
                    f"at epoch {existing.get('claim_epoch')}; use takeover only with explicit user authorization"
                )
            status = result["status"]
            if status["state"] != "pending":
                raise LifecycleError(
                    f"Only a clean pending package can be claimed; current state is {status['state']}"
                )
            conflicts = find_scope_conflicts(
                root,
                goal_id,
                result["manifest"]["write_scopes"],
            )
            if conflicts:
                raise LifecycleError(
                    "Declared write scopes overlap active goal claims: "
                    + json.dumps(conflicts, ensure_ascii=False)
                    + ". Use non-overlapping scopes or isolated worktrees."
                )
            epoch = int(status.get("claim_epoch", 0)) + 1
            token = str(uuid.uuid4())
            now = utc_now()
            claim = {
                "schema_version": SCHEMA_VERSION,
                "goal_id": goal_id,
                "claim_token": token,
                "claim_epoch": epoch,
                "agent_identity": identity,
                "host": platform.node() or None,
                "claimed_at": now,
                "heartbeat_at": now,
                "last_action": "Claimed package",
                "write_scopes": result["manifest"]["write_scopes"],
            }
            create_json_exclusive(claim_path, claim)
            confirmed = read_json(claim_path)
            if confirmed.get("claim_token") != token:
                raise LifecycleError("Could not confirm exclusive claim")
            status["claim_epoch"] = epoch
            status["attempt"] = int(status.get("attempt", 0)) + 1
            write_status(package, status, state="in_progress", action="Executor claimed package")
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "package": str(package),
            "claim_token": token,
            "claim_epoch": epoch,
            "agent_identity": identity,
            "write_scopes": result["manifest"]["write_scopes"],
            "warning": "Retain this token, heartbeat before package mutations, and stop if fenced.",
        }
    )


def command_takeover(args: argparse.Namespace) -> None:
    reason = safe_single_line(args.authorized_reason, "--authorized-reason")
    identity = (
        safe_single_line(args.identity, "--identity", maximum=200)
        if args.identity is not None
        else None
    )
    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Only a pending package can be taken over")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    root = result["root"]
    with goal_lock(root, goal_id):
        result = validate_published_package(str(package))
        claim_path = package / "claim.json"
        if not claim_path.exists():
            raise LifecycleError("Package is not claimed; use claim instead of takeover")
        old_claim = read_json(claim_path)
        validate_claim_record(old_claim, goal_id)
        if (
            old_claim.get("takeover_reason") == reason
            and old_claim.get("agent_identity") == identity
        ):
            status = result["status"]
            status["claim_epoch"] = old_claim["claim_epoch"]
            write_status(
                package,
                status,
                state="in_progress",
                action="Confirmed idempotent authorized takeover",
            )
            emit(
                {
                    "ok": True,
                    "idempotent": True,
                    "goal_id": goal_id,
                    "package": str(package),
                    "claim_token": old_claim["claim_token"],
                    "claim_epoch": old_claim["claim_epoch"],
                    "warning": "The prior executor remains fenced.",
                }
            )
            return
        old_epoch = old_claim["claim_epoch"]
        expected_reason = f"Authorize takeover of {goal_id} from claim epoch {old_epoch}"
        if reason != expected_reason:
            raise LifecycleError(
                f"--authorized-reason must be the user's exact phrase {expected_reason!r}"
            )
        history_dir = package / "claim_history"
        history_dir.mkdir(exist_ok=True)
        if is_link_like(history_dir):
            raise LifecycleError("Unsafe claim_history directory")
        historical = dict(old_claim)
        historical["replaced_at"] = utc_now()
        historical["takeover_reason"] = reason
        history_path = history_dir / f"claim_epoch_{old_epoch}_{old_claim.get('claim_token')}.json"
        if history_path.exists():
            existing_history = read_json(history_path)
            if (
                existing_history.get("claim_token") != old_claim.get("claim_token")
                or existing_history.get("claim_epoch") != old_epoch
                or existing_history.get("takeover_reason") != reason
            ):
                raise LifecycleError("Existing takeover history conflicts with this retry")
        else:
            create_json_exclusive(history_path, historical)

        token = str(uuid.uuid4())
        epoch = old_epoch + 1
        now = utc_now()
        new_claim = {
            "schema_version": SCHEMA_VERSION,
            "goal_id": goal_id,
            "claim_token": token,
            "claim_epoch": epoch,
            "agent_identity": identity,
            "host": platform.node() or None,
            "claimed_at": now,
            "heartbeat_at": now,
            "last_action": "Authorized takeover",
            "takeover_reason": reason,
            "write_scopes": result["manifest"]["write_scopes"],
        }
        atomic_write_json(claim_path, new_claim)
        status = result["status"]
        status["claim_epoch"] = epoch
        status["attempt"] = int(status.get("attempt", 0)) + 1
        write_status(package, status, state="in_progress", action="User-authorized claim takeover")
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "package": str(package),
            "claim_token": token,
            "claim_epoch": epoch,
            "prior_claim": str(history_path),
            "warning": "The prior executor is fenced and must stop on its next claim check.",
        }
    )


def command_heartbeat(args: argparse.Namespace) -> None:
    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Cannot heartbeat a terminal package")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    with goal_lock(result["root"], goal_id):
        claim = check_claim(package, goal_id, args.claim_token)
        updated = refresh_claim(package, claim, args.action)
        status = load_status(package, goal_id)
        write_status(package, status, action=args.action)
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "claim_epoch": updated["claim_epoch"],
            "heartbeat_at": updated["heartbeat_at"],
            "action": args.action,
        }
    )


def command_state(args: argparse.Namespace) -> None:
    allowed = {"in_progress", "validating", "paused"}
    if args.state not in allowed:
        raise LifecycleError(f"State must be one of: {', '.join(sorted(allowed))}")
    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Cannot change the active state of a terminal package")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    with goal_lock(result["root"], goal_id):
        claim = check_claim(package, goal_id, args.claim_token)
        refresh_claim(package, claim, args.action)
        status = load_status(package, goal_id)
        if status["state"] == "archive_prepared":
            raise LifecycleError("Package is already prepared for archival; recover it instead")
        updated = write_status(package, status, state=args.state, action=args.action)
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "state": updated["state"],
            "updated_at": updated["updated_at"],
        }
    )


def safe_evidence_path(
    package: Path,
    reference: str,
    *,
    label: str,
) -> tuple[str, Path]:
    normalized = reference.strip().replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or len(relative.parts) < 2
        or relative.parts[0] != "evidence"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise LifecycleError(f"{label} must be a safe path beneath evidence/: {reference}")
    for part in relative.parts:
        if (
            any(
                unicodedata.category(character).startswith("C")
                for character in part
            )
            or any(character in '`|<>:"?*' for character in part)
            or part.endswith((" ", "."))
            or part.casefold().split(".", 1)[0] in WINDOWS_RESERVED
        ):
            raise LifecycleError(
                f"{label} contains a Windows-unsafe or aliasing component: {reference}"
            )
    path = package.joinpath(*relative.parts)
    if (
        not path.is_file()
        or is_link_like(path)
        or not is_within(path.resolve(strict=True), package.resolve(strict=True))
    ):
        raise LifecycleError(f"{label} does not exist safely: {reference}")
    if path.stat().st_size == 0:
        raise LifecycleError(f"{label} is empty: {reference}")
    return normalized, path


def validate_evidence_record(
    package: Path,
    reference: str,
    *,
    goal_id: str,
    criterion_id: str,
    required_evidence: str,
    required_method: str,
    claim: dict[str, Any],
    criterion_result: str,
) -> dict[str, Any]:
    normalized, record_path = safe_evidence_path(
        package,
        reference,
        label=f"{criterion_id} evidence record",
    )
    if record_path.suffix.casefold() != ".json":
        raise LifecycleError(f"{criterion_id} evidence records must be JSON files")
    record = read_json(record_path)
    expected_fields = {
        "schema_version",
        "goal_id",
        "criterion_id",
        "claim_epoch",
        "observed_at",
        "required_evidence",
        "method",
        "observation",
        "command",
        "exit_code",
        "artifacts",
    }
    if set(record) != expected_fields:
        raise LifecycleError(
            f"{criterion_id} evidence record fields are invalid: {normalized}"
        )
    exact_schema_version(record.get("schema_version"), f"{criterion_id} evidence record")
    if record.get("goal_id") != goal_id or record.get("criterion_id") != criterion_id:
        raise LifecycleError(f"{criterion_id} evidence record identity does not match")
    expected_epoch = claim["claim_epoch"]
    if type(record.get("claim_epoch")) is not int or record["claim_epoch"] != expected_epoch:
        raise LifecycleError(f"{criterion_id} evidence record claim epoch does not match")
    observed_at = parse_utc_timestamp(
        record.get("observed_at"),
        f"{criterion_id} evidence observed_at",
    )
    claimed_at = parse_utc_timestamp(
        claim.get("claimed_at"),
        f"{criterion_id} claim claimed_at",
    )
    now = datetime.now(timezone.utc)
    if observed_at < claimed_at:
        raise LifecycleError(f"{criterion_id} evidence predates the current claim")
    if observed_at > now:
        raise LifecycleError(f"{criterion_id} evidence timestamp is in the future")
    if record.get("required_evidence") != required_evidence:
        raise LifecycleError(
            f"{criterion_id} evidence record does not quote its approved Required evidence exactly"
        )
    method = record.get("method")
    if method not in {"command", "interaction", "inspection", "review", "artifact"}:
        raise LifecycleError(f"{criterion_id} evidence method is invalid")
    if method != required_method:
        raise LifecycleError(
            f"{criterion_id} evidence method must be exactly {required_method!r}"
        )
    observation = record.get("observation")
    if not isinstance(observation, str) or len(observation.strip()) < 20:
        raise LifecycleError(f"{criterion_id} evidence observation is too vague")
    command = record.get("command")
    exit_code = record.get("exit_code")
    if method == "command":
        if not isinstance(command, str) or len(command.strip()) < 3:
            raise LifecycleError(f"{criterion_id} command evidence must record the exact command")
        if type(exit_code) is not int:
            raise LifecycleError(f"{criterion_id} command evidence must record an integer exit code")
        if criterion_result == "pass" and exit_code != 0:
            raise LifecycleError(
                f"{criterion_id} cannot pass with a nonzero recorded command exit code"
            )
    elif command is not None or exit_code is not None:
        raise LifecycleError(
            f"{criterion_id} non-command evidence must set command and exit_code to null"
        )
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise LifecycleError(
            f"{criterion_id} evidence record must hash at least one supporting artifact"
        )
    seen_artifacts: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "path",
            "sha256",
            "description",
        }:
            raise LifecycleError(f"{criterion_id} evidence artifact entry is invalid")
        artifact_reference = artifact.get("path")
        if not isinstance(artifact_reference, str):
            raise LifecycleError(f"{criterion_id} evidence artifact path is invalid")
        artifact_normalized, artifact_path = safe_evidence_path(
            package,
            artifact_reference,
            label=f"{criterion_id} supporting artifact",
        )
        if artifact_normalized == normalized:
            raise LifecycleError(
                f"{criterion_id} evidence record cannot hash itself as its supporting artifact"
            )
        key = artifact_normalized.casefold()
        if key in seen_artifacts:
            raise LifecycleError(f"{criterion_id} repeats a supporting artifact")
        seen_artifacts.add(key)
        expected_hash = artifact.get("sha256")
        if not isinstance(expected_hash, str) or re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ) is None:
            raise LifecycleError(f"{criterion_id} supporting artifact hash is invalid")
        actual_hash = sha256_file(artifact_path)
        if not secrets.compare_digest(expected_hash, actual_hash):
            raise LifecycleError(
                f"{criterion_id} supporting artifact hash does not match: {artifact_normalized}"
            )
        description = artifact.get("description")
        if not isinstance(description, str) or len(description.strip()) < 10:
            raise LifecycleError(
                f"{criterion_id} supporting artifact description is too vague"
            )
    return record


def validate_outcome(
    package: Path,
    acceptance_details: dict[str, dict[str, Any]],
    outcome: str,
    reason_code: str,
    goal_id: str,
    user_authorization: str | None,
    replacement_goal_id: str | None,
    external_goal_disposition: str,
    claim: dict[str, Any] | None,
) -> dict[str, Any]:
    json_path = package / "outcome.json"
    markdown_path = package / "outcome.md"
    if not json_path.is_file() or is_link_like(json_path):
        raise LifecycleError("Write a regular outcome.json before terminal archival")
    if not markdown_path.is_file() or is_link_like(markdown_path):
        raise LifecycleError("Write a regular outcome.md before terminal archival")

    report = read_json(json_path)
    expected_fields = {
        "schema_version",
        "goal_id",
        "outcome",
        "reason_code",
        "summary",
        "criteria",
        "validation",
        "known_limitations",
        "remaining_work",
        "blocked_threshold_evidence",
        "user_authorization",
        "replacement_goal_id",
        "external_goal_disposition",
    }
    if set(report) != expected_fields:
        missing = sorted(expected_fields - set(report))
        extra = sorted(set(report) - expected_fields)
        raise LifecycleError(
            "outcome.json fields are invalid; missing="
            + ", ".join(missing or ["none"])
            + "; unexpected="
            + ", ".join(extra or ["none"])
        )
    exact_schema_version(report.get("schema_version"), "outcome.json")
    if report.get("goal_id") != goal_id:
        raise LifecycleError("outcome.json goal_id does not match the package")
    if report.get("outcome") != outcome:
        raise LifecycleError("outcome.json outcome does not match the archive command")
    if report.get("reason_code") != reason_code:
        raise LifecycleError("outcome.json reason_code does not match the archive command")
    summary = report.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        raise LifecycleError("outcome.json summary must be a meaningful non-empty string")
    if report.get("user_authorization") != user_authorization:
        raise LifecycleError(
            "outcome.json user_authorization does not match the terminal command"
        )
    if report.get("replacement_goal_id") != replacement_goal_id:
        raise LifecycleError(
            "outcome.json replacement_goal_id does not match the terminal command"
        )
    if report.get("external_goal_disposition") != external_goal_disposition:
        raise LifecycleError(
            "outcome.json external_goal_disposition does not match the terminal command"
        )
    authorization_reasons = {"cancelled_by_user", "superseded", "abandoned_by_user"}
    if reason_code in authorization_reasons:
        if not isinstance(user_authorization, str):
            raise LifecycleError(f"{reason_code} requires explicit user authorization")
        safe_single_line(user_authorization, "Outcome user authorization")
    elif user_authorization is not None:
        raise LifecycleError(
            f"Outcome reason {reason_code} cannot carry user_authorization"
        )
    if reason_code == "superseded":
        if not isinstance(replacement_goal_id, str):
            raise LifecycleError("Superseded outcome requires replacement_goal_id")
        validate_goal_id(replacement_goal_id)
        if replacement_goal_id == goal_id:
            raise LifecycleError("A superseded goal cannot replace itself")
    elif replacement_goal_id is not None:
        raise LifecycleError(
            "replacement_goal_id must be null unless reason_code is superseded"
        )
    exact_authorization = expected_terminal_authorization(
        reason_code,
        goal_id,
        replacement_goal_id,
    )
    if user_authorization != exact_authorization:
        raise LifecycleError(
            "outcome.json does not contain the exact reason-specific user authorization phrase"
        )

    for field in ("validation", "known_limitations", "remaining_work"):
        values = report.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise LifecycleError(f"outcome.json {field} must be a list of non-empty strings")
    if not report["validation"]:
        raise LifecycleError("outcome.json validation must state what was or was not validated")
    if outcome == "not_achieved" and not report["remaining_work"]:
        raise LifecycleError("A not-achieved outcome must record remaining work")
    if outcome == "achieved" and report["remaining_work"]:
        raise LifecycleError("An achieved outcome must have no remaining work")

    criteria = report.get("criteria")
    if not isinstance(criteria, list):
        raise LifecycleError("outcome.json criteria must be a list")
    mandatory = {
        identifier.upper()
        for identifier, row in acceptance_details.items()
        if row["Priority"] == "Mandatory"
    }
    stretch = {
        identifier.upper()
        for identifier, row in acceptance_details.items()
        if row["Priority"] == "Stretch"
    }
    allowed = mandatory | stretch
    seen: dict[str, dict[str, Any]] = {}
    criterion_fields = {"id", "result", "evidence_records"}
    for entry in criteria:
        if not isinstance(entry, dict) or set(entry) != criterion_fields:
            raise LifecycleError(
                "Each outcome criterion must contain exactly id, result, and evidence_records"
            )
        identifier = entry.get("id")
        if not isinstance(identifier, str):
            raise LifecycleError("Outcome criterion id must be a string")
        identifier = identifier.upper()
        if identifier not in allowed:
            raise LifecycleError(f"Outcome contains an unknown acceptance criterion: {identifier}")
        if identifier in seen:
            raise LifecycleError(f"Outcome contains a duplicate acceptance criterion: {identifier}")
        result = entry.get("result")
        if result not in {"pass", "fail", "not_run"}:
            raise LifecycleError(f"{identifier} has an invalid exact result: {result}")
        evidence_records = entry.get("evidence_records")
        if not isinstance(evidence_records, list) or not all(
            isinstance(value, str) and value.strip() for value in evidence_records
        ):
            raise LifecycleError(
                f"{identifier} evidence_records must be a list of relative JSON paths"
            )
        if result in {"pass", "fail"} and not evidence_records:
            raise LifecycleError(f"{identifier} result {result} requires evidence records")
        if result == "not_run" and evidence_records:
            raise LifecycleError(f"{identifier} result not_run cannot claim evidence")
        if evidence_records and claim is None:
            raise LifecycleError(
                f"{identifier} cannot carry execution evidence without a verified claim"
            )
        seen_record_paths: set[str] = set()
        for reference in evidence_records:
            normalized = reference.strip().replace("\\", "/")
            key = normalized.casefold()
            if key in seen_record_paths:
                raise LifecycleError(f"{identifier} repeats an evidence record path")
            seen_record_paths.add(key)
            assert claim is not None
            validate_evidence_record(
                package,
                reference,
                goal_id=goal_id,
                criterion_id=identifier,
                required_evidence=acceptance_details[identifier]["Required evidence"],
                required_method=acceptance_details[identifier]["Evidence method"],
                claim=claim,
                criterion_result=result,
            )
        entry["id"] = identifier
        seen[identifier] = entry

    missing = sorted(mandatory - set(seen))
    if missing:
        raise LifecycleError(
            "outcome.json must contain every mandatory acceptance criterion exactly once: "
            + ", ".join(missing)
        )
    if outcome == "achieved":
        incomplete = sorted(
            identifier
            for identifier in mandatory
            if seen[identifier]["result"] != "pass"
        )
        if incomplete:
            raise LifecycleError(
                "Achieved outcome has mandatory criteria that are not pass: "
                + ", ".join(incomplete)
            )
    elif reason_code == "blocked" and not any(
        seen[identifier]["result"] in {"fail", "not_run"} for identifier in mandatory
    ):
        raise LifecycleError(
            f"{reason_code} requires at least one incomplete mandatory criterion"
        )

    threshold = report.get("blocked_threshold_evidence")
    if reason_code == "blocked":
        if not isinstance(threshold, dict):
            raise LifecycleError("Blocked outcome requires structured blocked_threshold_evidence")
        expected_threshold_fields = {
            "rule",
            "blocker",
            "occurrences",
            "no_safe_progress_remaining",
        }
        if set(threshold) != expected_threshold_fields:
            raise LifecycleError(
                "blocked_threshold_evidence must contain exactly rule, blocker, occurrences, "
                "and no_safe_progress_remaining"
            )
        for field in ("rule", "blocker", "no_safe_progress_remaining"):
            if not isinstance(threshold.get(field), str) or not threshold[field].strip():
                raise LifecycleError(f"blocked_threshold_evidence {field} cannot be empty")
        occurrences = threshold.get("occurrences")
        if not isinstance(occurrences, list) or len(occurrences) < 3:
            raise LifecycleError(
                "Blocked outcome requires at least three consecutive blocker occurrences"
            )
        turns: list[int] = []
        for occurrence in occurrences:
            if not isinstance(occurrence, dict) or set(occurrence) != {
                "turn",
                "observed_at",
                "evidence",
            }:
                raise LifecycleError(
                    "Each blocker occurrence must contain exactly turn, observed_at, and evidence"
                )
            turn = occurrence.get("turn")
            if type(turn) is not int or turn < 1:
                raise LifecycleError("Blocked occurrence turn must be a positive integer")
            turns.append(turn)
            for field in ("observed_at", "evidence"):
                if not isinstance(occurrence.get(field), str) or not occurrence[field].strip():
                    raise LifecycleError(f"Blocked occurrence {field} cannot be empty")
            parse_utc_timestamp(
                occurrence["observed_at"],
                f"Blocked occurrence turn {turn} observed_at",
            )
        if any(current != previous + 1 for previous, current in zip(turns, turns[1:])):
            raise LifecycleError("Blocked occurrence turn numbers must be consecutive and ordered")
        observed_times = [
            parse_utc_timestamp(
                occurrence["observed_at"],
                f"Blocked occurrence turn {occurrence['turn']} observed_at",
            )
            for occurrence in occurrences
        ]
        now = datetime.now(timezone.utc)
        if any(observed > now for observed in observed_times):
            raise LifecycleError("Blocked occurrence timestamps cannot be in the future")
        if any(
            current <= previous
            for previous, current in zip(observed_times, observed_times[1:])
        ):
            raise LifecycleError("Blocked occurrence timestamps must be strictly increasing")
    elif threshold is not None:
        raise LifecycleError(
            "blocked_threshold_evidence must be null when reason_code is not blocked"
        )

    text = read_utf8_exact(markdown_path)
    if len(text.strip()) < 100:
        raise LifecycleError("outcome.md is unexpectedly short")
    for label, value in (
        ("Goal ID", goal_id),
        ("Outcome", outcome),
        ("Reason code", reason_code),
    ):
        if re.search(
            rf"(?im)^[ \t]*[-*]?[ \t]*{re.escape(label)}[ \t]*:[ \t]*`?{re.escape(value)}`?[ \t]*$",
            text,
        ) is None:
            raise LifecycleError(f"outcome.md must exactly identify {label}: {value}")
    if outcome == "not_achieved" and re.search(
        r"^##[ \t]+Remaining work[ \t]*\r?$", text, re.MULTILINE | re.IGNORECASE
    ) is None:
        raise LifecycleError("Unsuccessful outcome.md must contain a Remaining work section")
    return report


def terminal_next_action(outcome: str, reason_code: str) -> str:
    if outcome == "achieved":
        return "Only now mark the external persistent goal complete."
    if reason_code == "blocked":
        return (
            "The platform-blocked transition was required before archival; confirm it remains "
            "blocked and take no second terminal action."
        )
    if reason_code == "superseded":
        return (
            "Do not rerun this goal. Continue only through the explicitly linked replacement goal."
        )
    if reason_code in {"cancelled_by_user", "abandoned_by_user"}:
        return (
            "Do not mark the work complete or rerun it; the user-authorized retirement is terminal."
        )
    return "Do not mark incomplete work complete; preserve this terminal outcome."


def expected_terminal_authorization(
    reason_code: str,
    goal_id: str,
    replacement_goal_id: str | None,
) -> str | None:
    if reason_code == "cancelled_by_user":
        return f"Cancel goal {goal_id}"
    if reason_code == "abandoned_by_user":
        return f"Abandon goal {goal_id}"
    if reason_code == "superseded":
        if replacement_goal_id is None:
            raise LifecycleError("Supersession authorization requires a replacement goal ID")
        return f"Supersede goal {goal_id} with {replacement_goal_id}"
    return None


def expected_external_goal_disposition(
    reason_code: str,
    *,
    administrative: bool,
) -> str:
    if administrative:
        return "not_started"
    if reason_code == "completed":
        return "complete_after_archive"
    if reason_code == "blocked":
        return "platform_blocked_before_archive"
    return "user_cancelled_or_replaced_before_archive"


def build_terminal_status(package: Path, terminal_state: str) -> dict[str, Any]:
    manifest = load_manifest(package)
    status = load_status(package, manifest["goal_id"])
    if status["state"] != "archive_prepared":
        raise LifecycleError("Only archive_prepared status can be terminally committed")
    intent = status.get("archive_intent")
    if not isinstance(intent, dict) or intent.get("outcome") != terminal_state:
        raise LifecycleError("Archive intent is missing or inconsistent")
    reason = intent.get("reason_code")
    if terminal_state == "achieved":
        if reason != "completed":
            raise LifecycleError("Achieved archive intent must use reason code completed")
    elif reason not in NOT_ACHIEVED_CODES:
        raise LifecycleError("Not-achieved archive intent has an invalid reason code")
    finalized = dict(status)
    finalized["terminal_reason_code"] = reason
    finalized["state"] = terminal_state
    finalized["last_action"] = f"Archived as {terminal_state}"
    finalized["updated_at"] = utc_now()
    return finalized


def finalize_and_seal_terminal(package: Path, terminal_state: str) -> dict[str, Any]:
    manifest = load_manifest(package)
    status = load_status(package, manifest["goal_id"])
    if status["state"] == "archive_prepared":
        if (package / TERMINAL_SEAL_FILE).exists():
            seal = validate_precommitted_terminal_seal(
                package,
                manifest["goal_id"],
                terminal_state,
                str(status.get("archive_intent", {}).get("reason_code")),
            )
            finalized = seal["final_status"]
        else:
            finalized = build_terminal_status(package, terminal_state)
            reason = finalized.get("terminal_reason_code")
            write_terminal_seal(
                package,
                manifest["goal_id"],
                terminal_state,
                str(reason),
                finalized,
            )
        atomic_write_json(package / "status.json", finalized)
        validate_terminal_seal(
            package,
            manifest["goal_id"],
            terminal_state,
            str(finalized.get("terminal_reason_code")),
        )
    elif status["state"] == terminal_state:
        finalized = status
        if not (package / TERMINAL_SEAL_FILE).is_file():
            raise LifecycleError(
                "Final terminal status without terminal_seal.json is corruption, not a "
                "recoverable precommit; do not reseal it"
            )
        validate_terminal_seal(
            package,
            manifest["goal_id"],
            terminal_state,
            str(finalized.get("terminal_reason_code")),
        )
    else:
        raise LifecycleError("Terminal package is not ready to finalize and seal")
    intent = finalized.get("archive_intent")
    if not isinstance(intent, dict):
        raise LifecycleError("Finalized terminal package lacks archive intent")
    reason = finalized.get("terminal_reason_code")
    if reason != intent.get("reason_code"):
        raise LifecycleError("Finalized terminal reason contradicts archive intent")
    return finalized


def command_archive(args: argparse.Namespace) -> None:
    if args.outcome == "achieved":
        if args.reason_code != "completed":
            raise LifecycleError("Achieved archival requires --reason-code completed")
        destination_name = ACHIEVED
        terminal_state = "achieved"
    else:
        if args.reason_code not in NOT_ACHIEVED_CODES:
            raise LifecycleError(
                "Not-achieved reason must be one of: " + ", ".join(sorted(NOT_ACHIEVED_CODES))
            )
        destination_name = NOT_ACHIEVED
        terminal_state = "not_achieved"
    if args.reason_code == "blocked" and not args.platform_blocked_confirmed:
        raise LifecycleError(
            "Blocked archival requires --platform-blocked-confirmed only after the platform "
            "accepted the persistent goal's threshold-gated blocked transition"
        )
    if args.reason_code != "blocked" and args.platform_blocked_confirmed:
        raise LifecycleError(
            "--platform-blocked-confirmed is valid only with --reason-code blocked"
        )
    authorization_reasons = {"cancelled_by_user", "superseded", "abandoned_by_user"}
    user_authorization = args.authorized_reason
    if args.reason_code in authorization_reasons:
        if user_authorization is None:
            raise LifecycleError(
                f"{args.reason_code} archival requires --authorized-reason"
            )
        user_authorization = safe_single_line(
            user_authorization,
            "--authorized-reason",
        )
    elif user_authorization is not None:
        raise LifecycleError(
            "--authorized-reason is valid only for user-authorized terminal reasons"
        )
    replacement_goal_id = args.replacement_goal_id
    if args.reason_code == "superseded":
        if replacement_goal_id is None:
            raise LifecycleError("Superseded archival requires --replacement-goal-id")
        validate_goal_id(replacement_goal_id)
    elif replacement_goal_id is not None:
        raise LifecycleError(
            "--replacement-goal-id is valid only with --reason-code superseded"
        )

    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Archive source must be an exact pending package")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    expected_authorization = expected_terminal_authorization(
        args.reason_code,
        goal_id,
        replacement_goal_id,
    )
    if user_authorization != expected_authorization:
        if expected_authorization is None:
            raise LifecycleError("This terminal reason cannot carry user authorization")
        raise LifecycleError(
            f"--authorized-reason must be the user's exact phrase {expected_authorization!r}"
        )
    external_goal_disposition = args.external_goal_disposition
    expected_disposition = expected_external_goal_disposition(
        args.reason_code,
        administrative=False,
    )
    if external_goal_disposition != expected_disposition:
        raise LifecycleError(
            f"--external-goal-disposition must be exactly {expected_disposition!r}"
        )
    root = result["root"]
    destination = root / destination_name / goal_id
    lock_ids = [goal_id]
    if replacement_goal_id is not None:
        lock_ids.append(replacement_goal_id)

    with workspace_lease_lock(root):
        with multiple_goal_locks(root, lock_ids):
            result = validate_published_package(str(package))
            claim = check_claim(package, goal_id, args.claim_token)
            status = result["status"]
            if terminal_state == "achieved" and status["state"] != "validating":
                raise LifecycleError("Enter validating state before achieved archival")
            if status["state"] == "archive_prepared":
                raise LifecycleError("Archive is already prepared; use recover")
            if replacement_goal_id is not None:
                validate_replacement_link(root, goal_id, replacement_goal_id)
            validate_outcome(
                package,
                result["acceptance_details"],
                terminal_state,
                args.reason_code,
                goal_id,
                user_authorization,
                replacement_goal_id,
                external_goal_disposition,
                claim,
            )
            refresh_claim(package, claim, "Preparing terminal archive")
            if destination.exists():
                raise LifecycleError(
                    f"Refusing to overwrite or merge terminal destination: {destination}"
                )
            status["archive_intent"] = {
                "outcome": terminal_state,
                "reason_code": args.reason_code,
                "destination": project_relative(result["workspace"], destination),
                "prepared_at": utc_now(),
                "administrative": False,
                "blocked_threshold_confirmed": bool(args.platform_blocked_confirmed),
                "user_authorization": user_authorization,
                "replacement_goal_id": replacement_goal_id,
                "external_goal_disposition": external_goal_disposition,
            }
            write_status(
                package,
                status,
                state="archive_prepared",
                action=f"Prepared archive to {destination_name}",
            )
            os.rename(package, destination)
            if package.exists() or not destination.is_dir():
                raise LifecycleError("Terminal move verification failed")
            validate_published_package(
                str(destination),
                allow_unsealed_terminal=True,
            )
            finalized = finalize_and_seal_terminal(destination, terminal_state)
            verified = validate_published_package(str(destination))
            if verified["manifest"]["goal_id"] != goal_id:
                raise LifecycleError("Terminal manifest verification failed")

    next_action = terminal_next_action(terminal_state, args.reason_code)
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "outcome": terminal_state,
            "reason_code": args.reason_code,
            "replacement_goal_id": replacement_goal_id,
            "terminal_package": str(destination),
            "state": finalized["state"],
            "next": next_action,
        }
    )


def command_recover(args: argparse.Namespace) -> None:
    workspace, root = workspace_and_root(args.workspace, args.goals_dir, create=False)
    validate_goal_id(args.goal_id)
    with workspace_lease_lock(root):
        with goal_lock(root, args.goal_id):
            found = locate_exact(root, args.goal_id)
            exact = [path for name in LOCATION_NAMES for path in found[name]]
            if len(exact) > 1:
                raise LifecycleError(
                    "Exact goal ID exists in multiple lifecycle folders; do not merge or delete: "
                    + ", ".join(str(path) for path in exact)
                )
            if not exact:
                if found["staging"]:
                    raise LifecycleError(
                        "Goal exists only as unpublished staging and is not executable: "
                        + ", ".join(str(path) for path in found["staging"])
                    )
                raise LifecycleError(f"Exact goal ID was not found: {args.goal_id}")

            package = exact[0]
            location = package.parent.name
            result = validate_published_package(
                str(package),
                allow_unsealed_terminal=location in {ACHIEVED, NOT_ACHIEVED},
            )
            status = result["status"]
            if location in {ACHIEVED, NOT_ACHIEVED}:
                expected_state = "achieved" if location == ACHIEVED else "not_achieved"
                intent = status.get("archive_intent")
                if not isinstance(intent, dict):
                    raise LifecycleError("Terminal package lacks archive intent")
                reason = intent.get("reason_code")
                if not isinstance(reason, str) or not reason:
                    raise LifecycleError("Terminal package lacks a reason code")
                if status["state"] == "archive_prepared":
                    finalized = finalize_and_seal_terminal(package, expected_state)
                    validate_published_package(str(package))
                elif status["state"] == expected_state:
                    if not (package / TERMINAL_SEAL_FILE).is_file():
                        raise LifecycleError(
                            "Terminal package has final status but no terminal seal; refuse to "
                            "trust or reseal potentially changed contents"
                        )
                    finalized = status
                    validate_published_package(str(package))
                    if finalized.get("terminal_reason_code") != reason:
                        raise LifecycleError("Terminal reason does not match archive intent")
                else:
                    raise LifecycleError("Terminal folder and state are inconsistent")
                emit(
                    {
                        "ok": True,
                        "goal_id": args.goal_id,
                        "already_terminal": True,
                        "terminal_package": str(package),
                        "state": finalized["state"],
                        "terminal_reason_code": reason,
                        "replacement_goal_id": intent.get("replacement_goal_id"),
                        "next": terminal_next_action(expected_state, reason),
                    }
                )
                return

            if status["state"] != "archive_prepared":
                claim_path = package / "claim.json"
                if claim_path.exists():
                    claim = read_json(claim_path)
                    validate_claim_record(claim, args.goal_id)
                    if args.claim_token:
                        check_claim(package, args.goal_id, args.claim_token)
                    claimed = True
                    owner = claim.get("agent_identity")
                    epoch = claim.get("claim_epoch")
                    next_action = (
                        "Resume only if you hold the current claim token. Any non-owner must "
                        "stop or obtain explicit user-authorized takeover."
                    )
                else:
                    if status["state"] != "pending":
                        raise LifecycleError(
                            f"Active state {status['state']} is missing its executor claim"
                        )
                    claimed = False
                    owner = None
                    epoch = None
                    next_action = (
                        "This package is unclaimed; claim this exact goal before project work."
                    )
                emit(
                    {
                        "ok": True,
                        "goal_id": args.goal_id,
                        "already_terminal": False,
                        "pending_package": str(package),
                        "state": status["state"],
                        "claimed": claimed,
                        "agent_identity": owner,
                        "claim_epoch": epoch,
                        "terminal_reason_code": None,
                        "next": next_action,
                    }
                )
                return

            intent = status.get("archive_intent")
            if not isinstance(intent, dict):
                raise LifecycleError("archive_prepared status lacks archive intent")
            outcome = intent.get("outcome")
            reason = intent.get("reason_code")
            if outcome not in {"achieved", "not_achieved"} or not isinstance(reason, str):
                raise LifecycleError("archive_prepared status has an invalid outcome or reason")
            if outcome == "achieved" and reason != "completed":
                raise LifecycleError("Achieved recovery requires reason code completed")
            if outcome == "not_achieved" and reason not in NOT_ACHIEVED_CODES:
                raise LifecycleError("Not-achieved recovery has an invalid reason code")
            if reason == "blocked" and intent.get("blocked_threshold_confirmed") is not True:
                raise LifecycleError("Blocked archive intent lacks threshold confirmation")
            user_authorization = intent.get("user_authorization")
            replacement_goal_id = intent.get("replacement_goal_id")
            if reason == "superseded":
                if not isinstance(replacement_goal_id, str):
                    raise LifecycleError("Superseded archive intent lacks replacement_goal_id")
                validate_replacement_link(root, args.goal_id, replacement_goal_id)

            administrative = intent.get("administrative")
            if not isinstance(administrative, bool):
                raise LifecycleError("Archive intent lacks an administrative boolean")
            external_goal_disposition = intent.get("external_goal_disposition")
            expected_disposition = expected_external_goal_disposition(
                reason,
                administrative=administrative,
            )
            if external_goal_disposition != expected_disposition:
                raise LifecycleError(
                    "Archive intent has an invalid external-goal disposition"
                )
            outcome_claim: dict[str, Any] | None = None
            if administrative:
                if (package / "claim.json").exists():
                    raise LifecycleError("Administrative archive recovery cannot bypass a claim")
            else:
                if not args.claim_token:
                    raise LifecycleError("Claimed archive recovery requires --claim-token")
                outcome_claim = check_claim(package, args.goal_id, args.claim_token)

            validate_outcome(
                package,
                result["acceptance_details"],
                outcome,
                reason,
                args.goal_id,
                user_authorization,
                replacement_goal_id,
                external_goal_disposition,
                outcome_claim,
            )
            destination_name = ACHIEVED if outcome == "achieved" else NOT_ACHIEVED
            destination = root / destination_name / args.goal_id
            expected_destination = project_relative(workspace, destination)
            if intent.get("destination") != expected_destination:
                raise LifecycleError("Archive intent destination is inconsistent")
            if destination.exists():
                raise LifecycleError("Both pending source and terminal destination exist; stop")
            os.rename(package, destination)
            if package.exists() or not destination.is_dir():
                raise LifecycleError("Recovered terminal move verification failed")
            validate_published_package(
                str(destination),
                allow_unsealed_terminal=True,
            )
            finalized = finalize_and_seal_terminal(destination, outcome)
            validate_published_package(str(destination))
    emit(
        {
            "ok": True,
            "goal_id": args.goal_id,
            "recovered": True,
            "terminal_package": str(destination),
            "state": finalized["state"],
            "terminal_reason_code": reason,
            "replacement_goal_id": replacement_goal_id,
            "next": terminal_next_action(outcome, reason),
        }
    )


def command_retire(args: argparse.Namespace) -> None:
    if args.reason_code not in ADMIN_RETIRE_CODES:
        raise LifecycleError(
            "Administrative retirement reason must be one of: "
            + ", ".join(sorted(ADMIN_RETIRE_CODES))
        )
    reason = safe_single_line(args.authorized_reason, "--authorized-reason")
    if args.reason_code == "superseded":
        if not args.replacement_goal_id:
            raise LifecycleError("Superseded retirement requires --replacement-goal-id")
        validate_goal_id(args.replacement_goal_id)
    elif args.replacement_goal_id:
        raise LifecycleError("--replacement-goal-id is valid only with --reason-code superseded")

    result = validate_published_package(args.package)
    if result["location"] != PENDING:
        raise LifecycleError("Only an unclaimed pending package can be retired")
    package = result["package"]
    goal_id = result["manifest"]["goal_id"]
    expected_authorization = expected_terminal_authorization(
        args.reason_code,
        goal_id,
        args.replacement_goal_id,
    )
    if reason != expected_authorization:
        raise LifecycleError(
            f"--authorized-reason must be the user's exact phrase {expected_authorization!r}"
        )
    destination = result["root"] / NOT_ACHIEVED / goal_id
    if args.replacement_goal_id == goal_id:
        raise LifecycleError("A goal cannot supersede itself")
    lock_ids = [goal_id]
    if args.replacement_goal_id:
        lock_ids.append(args.replacement_goal_id)
    with workspace_lease_lock(result["root"]):
        with multiple_goal_locks(result["root"], lock_ids):
            result = validate_published_package(str(package))
            if result["status"]["state"] != "pending" or (package / "claim.json").exists():
                raise LifecycleError(
                    "Only a clean, unclaimed pending package can be administratively retired"
                )
            if args.replacement_goal_id:
                validate_replacement_link(
                    result["root"],
                    goal_id,
                    args.replacement_goal_id,
                )
            if destination.exists():
                raise LifecycleError(f"Refusing to overwrite terminal destination: {destination}")

            remaining = (
                f"Continue only through replacement goal {args.replacement_goal_id}."
                if args.replacement_goal_id
                else "Create a new separately approved package only if the user later resumes the work."
            )
            outcome_json = {
                "schema_version": SCHEMA_VERSION,
                "goal_id": goal_id,
                "outcome": "not_achieved",
                "reason_code": args.reason_code,
                "summary": f"User-authorized administrative retirement: {reason}",
                "criteria": [
                    {
                        "id": criterion,
                        "result": "not_run",
                        "evidence_records": [],
                    }
                    for criterion in result["acceptance"]
                ],
                "validation": [
                    "No execution attempt was started; mandatory acceptance criteria were not run."
                ],
                "known_limitations": [],
                "remaining_work": [remaining],
                "blocked_threshold_evidence": None,
                "user_authorization": reason,
                "replacement_goal_id": args.replacement_goal_id,
                "external_goal_disposition": "not_started",
            }
            replacement_line = (
                f"- Replacement goal ID: `{args.replacement_goal_id}`\n"
                if args.replacement_goal_id
                else ""
            )
            outcome_text = f"""# Goal outcome

- Goal ID: `{goal_id}`
- Outcome: `not_achieved`
- Reason code: `{args.reason_code}`
- Summary: {reason}
{replacement_line}
## Acceptance results

No execution attempt was started. Every mandatory acceptance criterion is recorded as `not_run` in `outcome.json`.

## Validation performed

The lifecycle helper verified that the package was clean and unclaimed before the user-authorized administrative retirement.

## Known limitations and waivers

None.

## Remaining work

{remaining}
"""
            atomic_write_json(package / "outcome.json", outcome_json)
            atomic_write_text(package / "outcome.md", outcome_text)
            validate_outcome(
                package,
                result["acceptance_details"],
                "not_achieved",
                args.reason_code,
                goal_id,
                reason,
                args.replacement_goal_id,
                "not_started",
                None,
            )
            status = result["status"]
            status["archive_intent"] = {
                "outcome": "not_achieved",
                "reason_code": args.reason_code,
                "destination": project_relative(result["workspace"], destination),
                "prepared_at": utc_now(),
                "administrative": True,
                "blocked_threshold_confirmed": False,
                "user_authorization": reason,
                "replacement_goal_id": args.replacement_goal_id,
                "external_goal_disposition": "not_started",
            }
            write_status(
                package,
                status,
                state="archive_prepared",
                action=f"Administratively retired as {args.reason_code}",
            )
            os.rename(package, destination)
            if package.exists() or not destination.is_dir():
                raise LifecycleError("Administrative retirement move verification failed")
            validate_published_package(
                str(destination),
                allow_unsealed_terminal=True,
            )
            finalized = finalize_and_seal_terminal(destination, "not_achieved")
            validate_published_package(str(destination))
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "outcome": "not_achieved",
            "reason_code": args.reason_code,
            "replacement_goal_id": args.replacement_goal_id,
            "terminal_package": str(destination),
            "state": finalized["state"],
            "next": terminal_next_action("not_achieved", args.reason_code),
        }
    )


def parse_portable(path: Path) -> tuple[dict[str, Any], str, str]:
    if not path.is_file() or is_link_like(path):
        raise LifecycleError(f"Portable handoff is missing or unsafe: {path}")
    text = read_utf8_exact(path)
    if text.count(PORTABLE_BEGIN) != 1 or text.count(PORTABLE_END) != 1:
        raise LifecycleError("Portable handoff must contain exactly one payload")
    start = text.find(PORTABLE_BEGIN)
    end = text.find(PORTABLE_END)
    if start < 0 or end < 0 or end <= start:
        raise LifecycleError("Portable handoff payload markers are missing or malformed")
    encoded = "".join(text[start + len(PORTABLE_BEGIN) : end].split())
    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"Portable handoff payload is invalid: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != "intentwright-portable"
        or not isinstance(payload.get("manifest"), dict)
    ):
        raise LifecycleError("Portable handoff schema is unsupported")
    expected_fields = {
        "schema_version",
        "kind",
        "manifest",
        "approved_body_utf8_base64",
        "spec_utf8_base64",
    }
    if set(payload) != expected_fields:
        raise LifecycleError("Portable handoff payload fields are invalid")
    try:
        approved_body = base64.b64decode(
            payload["approved_body_utf8_base64"], validate=True
        ).decode("utf-8")
        spec_text = base64.b64decode(payload["spec_utf8_base64"], validate=True).decode("utf-8")
    except (KeyError, TypeError, binascii.Error, ValueError, UnicodeError) as exc:
        raise LifecycleError(f"Portable specification payload is invalid: {exc}") from exc
    manifest = validate_manifest_value(payload["manifest"])
    validate_canonical_body_text(approved_body)
    approved_hash = sha256_bytes(approved_body.encode("utf-8"))
    if (
        manifest.get("approved_body_sha256") != approved_hash
        or manifest.get("approval_body_sha256") != approved_hash
    ):
        raise LifecycleError(
            "Portable approved semantic body hash does not match the immutable manifest"
        )
    spec_hash = sha256_bytes(spec_text.encode("utf-8"))
    if manifest.get("spec_sha256") != spec_hash:
        raise LifecycleError("Portable specification hash does not match the immutable manifest")
    validate_semantic_body(
        approved_body,
        manifest["write_scopes"],
        manifest["retry_of"],
        manifest["supersedes"],
    )
    return manifest, approved_body, spec_text


def command_import_portable(args: argparse.Namespace) -> None:
    portable_input = Path(args.file).expanduser()
    if is_link_like(portable_input):
        raise LifecycleError(f"Refusing a linked or reparse-point portable handoff: {portable_input}")
    portable_path = portable_input.resolve(strict=True)
    manifest, approved_body, spec_text = parse_portable(portable_path)
    if manifest.get("retry_of") or manifest.get("supersedes"):
        raise LifecycleError(
            "Lineage-bearing goal packages are not portable; import the full lifecycle history "
            "or obtain a newly approved destination-workspace package"
        )
    goal_id = manifest["goal_id"]
    expected_hash = manifest["spec_sha256"]
    source_package = portable_path.parent
    if (
        source_package.name == goal_id
        and source_package.parent.name in {ACHIEVED, NOT_ACHIEVED}
    ):
        raise LifecycleError(
            "Refusing to import a handoff directly from a terminal package; terminal goals "
            "must never be replayed"
        )

    workspace, root = workspace_and_root(args.workspace, args.goals_dir, create=True)
    validate_manifest_approval_receipt(workspace, root, manifest)
    with goal_lock(root, goal_id):
        assert_goal_id_absent(root, goal_id)
        staging = root / PENDING / f".staging_{goal_id}_import_{secrets.token_hex(4)}"
        staging.mkdir(exist_ok=False)
        final = root / PENDING / goal_id
        imported_manifest = dict(manifest)
        expected_relative = project_relative(workspace, final)
        if imported_manifest.get("project_relative_package") != expected_relative:
            raise LifecycleError(
                "Portable package must be imported under the same project-relative goal root "
                f"recorded by its immutable manifest ({imported_manifest.get('project_relative_package')})"
            )
        expected_spec = render_canonical_spec(workspace, final, imported_manifest, approved_body)
        if spec_text != expected_spec:
            raise LifecycleError(
                "Portable canonical spec is not the exact approved body plus its mechanical envelope"
            )
        spec_file = imported_manifest["spec_file"]
        created_at = utc_now()
        status = {
            "schema_version": SCHEMA_VERSION,
            "goal_id": goal_id,
            "state": "pending",
            "attempt": 0,
            "claim_epoch": 0,
            "created_at": created_at,
            "updated_at": created_at,
            "archive_intent": None,
            "terminal_reason_code": None,
            "last_action": "Imported portable immutable spec",
            "imported_from": str(portable_path),
        }
        try:
            atomic_write_json(staging / "goal_manifest.json", imported_manifest)
            atomic_write_text(staging / imported_manifest["approved_body_file"], approved_body)
            atomic_write_text(staging / spec_file, spec_text)
            atomic_write_json(staging / "status.json", status)
            atomic_write_text(
                staging / "execution_prompt.md",
                render_execution_prompt(workspace, final, imported_manifest),
            )
            atomic_write_text(
                staging / "portable_handoff.md",
                render_portable_handoff(
                    workspace,
                    final,
                    imported_manifest,
                    approved_body,
                    spec_text,
                ),
            )
            write_package_seal(staging, imported_manifest)
            assert_no_link_like(staging)
            loaded_manifest = load_manifest(staging)
            if loaded_manifest != imported_manifest:
                raise LifecycleError("Imported manifest changed while staging")
            if loaded_manifest.get("published_at") in (None, ""):
                raise LifecycleError("Portable manifest is not published")
            if sha256_file(staging / spec_file) != expected_hash:
                raise LifecycleError("Imported specification changed while staging")
            if (
                sha256_file(staging / imported_manifest["approved_body_file"])
                != imported_manifest["approved_body_sha256"]
            ):
                raise LifecycleError("Imported approved semantic body changed while staging")
            validate_package_seal(staging, imported_manifest)
            regenerated_manifest, regenerated_body, regenerated_spec = parse_portable(
                staging / "portable_handoff.md"
            )
            if (
                regenerated_manifest != imported_manifest
                or regenerated_body != approved_body
                or regenerated_spec != spec_text
            ):
                raise LifecycleError("Regenerated portable handoff changed the immutable payload")
            os.rename(staging, final)
        except Exception:
            # Preserve any crash-left staging package for explicit inspection.
            raise
    result = validate_published_package(str(final))
    emit(
        {
            "ok": True,
            "goal_id": goal_id,
            "pending_package": str(final),
            "spec_path": str(final / spec_file),
            "spec_sha256": result["spec_sha256"],
            "goal_command": result["goal_command"],
            "warning": "This filesystem copy has independent claim state.",
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, publish, claim, verify, recover, and archive Intentwright packages."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    approval_receipt = sub.add_parser(
        "approval-receipt",
        help="Validate the exact semantic body and bind its complete execution envelope.",
    )
    approval_receipt.add_argument("--file", required=True)
    approval_receipt.add_argument("--workspace", required=True)
    approval_receipt.add_argument("--goals-dir", default="goals")
    approval_receipt.add_argument("--title", required=True)
    approval_receipt.add_argument("--slug", required=True)
    approval_receipt.add_argument("--revision", type=int, required=True)
    approval_receipt.add_argument("--interview-id", required=True)
    approval_receipt.add_argument("--write-scope", action="append", required=True)
    approval_receipt.add_argument("--retry-of")
    approval_receipt.add_argument("--supersedes")
    approval_receipt.set_defaults(func=command_approval_receipt)

    init = sub.add_parser("init", help="Create a unique unpublished staging package.")
    init.add_argument("--workspace", required=True)
    init.add_argument("--goals-dir", default="goals")
    init.add_argument("--slug", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--revision", type=int, default=1)
    init.add_argument("--interview-id", required=True)
    init.add_argument("--approval-record", required=True)
    init.add_argument("--approval-receipt-sha256", required=True)
    init.add_argument("--approved-body-sha256", required=True)
    init.add_argument(
        "--write-scope",
        action="append",
        required=True,
        help="Repeat for each explicitly approved project-relative implementation scope.",
    )
    init.add_argument("--retry-of")
    init.add_argument("--supersedes")
    init.set_defaults(func=command_init)

    publish = sub.add_parser("publish", help="Validate and atomically publish an approved spec.")
    publish.add_argument("--package", required=True)
    publish.set_defaults(func=command_publish)

    discard_staging = sub.add_parser(
        "discard-staging",
        help="Delete one exact unpublished draft staging package after explicit confirmation.",
    )
    discard_staging.add_argument("--package", required=True)
    discard_staging.add_argument("--confirmation", required=True)
    discard_staging.set_defaults(func=command_discard_staging)

    verify = sub.add_parser("verify", help="Verify one exact published package and spec hash.")
    verify.add_argument("--package", required=True)
    verify.set_defaults(func=command_verify)

    claim = sub.add_parser("claim", help="Atomically claim one exact pending package.")
    claim.add_argument("--package", required=True)
    claim.add_argument("--identity")
    claim.set_defaults(func=command_claim)

    takeover = sub.add_parser(
        "takeover", help="Replace an existing claim with explicit user authorization."
    )
    takeover.add_argument("--package", required=True)
    takeover.add_argument("--authorized-reason", required=True)
    takeover.add_argument("--identity")
    takeover.set_defaults(func=command_takeover)

    heartbeat = sub.add_parser("heartbeat", help="Verify ownership and refresh a claim heartbeat.")
    heartbeat.add_argument("--package", required=True)
    heartbeat.add_argument("--claim-token", required=True)
    heartbeat.add_argument("--action", required=True)
    heartbeat.set_defaults(func=command_heartbeat)

    state = sub.add_parser("state", help="Change active package state after claim verification.")
    state.add_argument("--package", required=True)
    state.add_argument("--claim-token", required=True)
    state.add_argument("--state", required=True, choices=("in_progress", "validating", "paused"))
    state.add_argument("--action", required=True)
    state.set_defaults(func=command_state)

    archive = sub.add_parser("archive", help="Validate evidence and atomically archive a package.")
    archive.add_argument("--package", required=True)
    archive.add_argument("--claim-token", required=True)
    archive.add_argument("--outcome", required=True, choices=("achieved", "not_achieved"))
    archive.add_argument("--reason-code", required=True)
    archive.add_argument(
        "--platform-blocked-confirmed",
        action="store_true",
        help="Attest that the platform accepted its threshold-gated blocked transition.",
    )
    archive.add_argument(
        "--external-goal-disposition",
        required=True,
        choices=(
            "complete_after_archive",
            "platform_blocked_before_archive",
            "user_cancelled_or_replaced_before_archive",
        ),
    )
    archive.add_argument("--authorized-reason")
    archive.add_argument("--replacement-goal-id")
    archive.set_defaults(func=command_archive)

    recover = sub.add_parser("recover", help="Recover or locate one exact goal ID idempotently.")
    recover.add_argument("--workspace", required=True)
    recover.add_argument("--goals-dir", default="goals")
    recover.add_argument("--goal-id", required=True)
    recover.add_argument("--claim-token")
    recover.set_defaults(func=command_recover)

    retire = sub.add_parser(
        "retire", help="Archive an unclaimed package after explicit cancellation or supersession."
    )
    retire.add_argument("--package", required=True)
    retire.add_argument("--reason-code", required=True, choices=tuple(sorted(ADMIN_RETIRE_CODES)))
    retire.add_argument("--authorized-reason", required=True)
    retire.add_argument("--replacement-goal-id")
    retire.set_defaults(func=command_retire)

    import_portable = sub.add_parser(
        "import-portable",
        help="Restore a verified non-lineage handoff in its receipt-bound canonical workspace.",
    )
    import_portable.add_argument("--workspace", required=True)
    import_portable.add_argument("--goals-dir", default="goals")
    import_portable.add_argument("--file", required=True)
    import_portable.set_defaults(func=command_import_portable)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except LifecycleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: Interrupted; inspect staging or pending state before retrying.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
