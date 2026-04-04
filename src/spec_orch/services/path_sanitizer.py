from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from spec_orch.services.env_files import resolve_shared_repo_root

# Only Unix-style absolute filesystem paths are normalized from free-form text.
# Windows drive-letter paths are left unchanged unless they are parsed from
# structured payload values elsewhere.
_ABSOLUTE_PATH_FRAGMENT_RE = re.compile(r"(?<!://)/[^\s\"`]+")
_TEXT_SUFFIXES = {
    "",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".py",
    ".spec",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def resolve_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _collapse_external_path(path: Path) -> str:
    parts = [part for part in path.parts if part and part != path.anchor]
    if not parts:
        return "<external-path>"
    if parts[0] in {"Users", "home"} and len(parts) >= 2:
        parts = parts[2:]
    elif parts[0] == "root":
        parts = parts[1:]
    tail = "/".join((parts or [path.name])[-3:])
    return f"<external-path>/{tail}"


def _looks_like_filesystem_path(path: Path) -> bool:
    parts = [part for part in path.parts if part and part != path.anchor]
    if not parts:
        return False
    return parts[0] in {
        "Users",
        "home",
        "root",
        "private",
        "workspace",
        "workspaces",
        "mnt",
        "media",
        "srv",
        "data",
        "Volumes",
        "tmp",
        "var",
        "opt",
        "etc",
    }


def sanitize_path_like_string(
    value: str,
    *,
    repo_root: Path,
    shared_root: Path | None = None,
) -> str:
    repo_root_str = repo_root.resolve().as_posix()
    if value == repo_root_str:
        return "."

    sanitized = value.replace(f"{repo_root_str}/", "")
    if shared_root is not None:
        shared_root_str = shared_root.resolve().as_posix()
        if sanitized == shared_root_str:
            sanitized = "<shared-repo>"
        sanitized = sanitized.replace(f"{shared_root_str}/", "<shared-repo>/")

    def _replace_external_fragment(match: re.Match[str]) -> str:
        fragment = match.group(0)
        candidate = Path(fragment)
        if not (candidate.is_absolute() and _looks_like_filesystem_path(candidate)):
            return fragment
        return _collapse_external_path(candidate)

    sanitized = _ABSOLUTE_PATH_FRAGMENT_RE.sub(_replace_external_fragment, sanitized)

    stripped = sanitized.strip()
    if stripped and stripped == sanitized:
        candidate = Path(stripped)
        if candidate.is_absolute() and _looks_like_filesystem_path(candidate):
            return _collapse_external_path(candidate)
    return sanitized


def sanitize_value(
    value: Any,
    *,
    repo_root: Path,
    shared_root: Path | None = None,
) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        duplicate_counts: dict[str, int] = {}
        for key, item in value.items():
            sanitized_key = str(key)
            if isinstance(key, str):
                sanitized_key = sanitize_path_like_string(
                    key,
                    repo_root=repo_root,
                    shared_root=shared_root,
                )
            count = duplicate_counts.get(sanitized_key, 0)
            duplicate_counts[sanitized_key] = count + 1
            if count:
                sanitized_key = f"{sanitized_key}#{count + 1}"
            sanitized[sanitized_key] = sanitize_value(
                item,
                repo_root=repo_root,
                shared_root=shared_root,
            )
        return sanitized
    if isinstance(value, list):
        return [
            sanitize_value(item, repo_root=repo_root, shared_root=shared_root) for item in value
        ]
    if isinstance(value, str):
        return sanitize_path_like_string(
            value,
            repo_root=repo_root,
            shared_root=shared_root,
        )
    return value


def sanitize_text_artifact_tree(root: Path, *, repo_root: Path | None = None) -> list[Path]:
    resolved_root = root.resolve()
    resolved_repo_root = resolve_repo_root(repo_root or resolved_root)
    shared_root = resolve_shared_repo_root(resolved_repo_root)
    changed: list[Path] = []
    for path in resolved_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        sanitized = sanitize_path_like_string(
            original,
            repo_root=resolved_repo_root,
            shared_root=shared_root.resolve() if shared_root is not None else None,
        )
        if sanitized == original:
            continue
        path.write_text(sanitized, encoding="utf-8")
        changed.append(path)
    return changed
