from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from spec_orch.runtime_core.observability.models import (
    RuntimeBatchSummary,
    RuntimeLiveSummary,
    RuntimeProgressEvent,
    RuntimeRecap,
    RuntimeStepSummary,
)
from spec_orch.services.env_files import resolve_shared_repo_root
from spec_orch.services.io import atomic_write_json

PROGRESS_EVENTS_FILENAME = "progress_events.jsonl"
LIVE_SUMMARY_FILENAME = "live_summary.json"
RECAPS_FILENAME = "recaps.jsonl"
STEP_SUMMARIES_FILENAME = "step_summaries.jsonl"
BATCH_SUMMARIES_FILENAME = "batch_summaries.jsonl"
_ABSOLUTE_PATH_FRAGMENT_RE = re.compile(r"(?:(?<=`)|(?<!\S))/[^\s`]+")


def _resolve_repo_root(start: Path) -> Path:
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
        "tmp",
        "var",
        "opt",
        "etc",
    }


def _sanitize_path_like_string(
    value: str,
    *,
    repo_root: Path,
    shared_root: Path | None,
) -> str:
    repo_root_str = repo_root.as_posix()
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


def _sanitize_observability_value(
    value: Any,
    *,
    repo_root: Path,
    shared_root: Path | None,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_observability_value(
                item,
                repo_root=repo_root,
                shared_root=shared_root,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_observability_value(
                item,
                repo_root=repo_root,
                shared_root=shared_root,
            )
            for item in value
        ]
    if isinstance(value, str):
        return _sanitize_path_like_string(
            value,
            repo_root=repo_root,
            shared_root=shared_root,
        )
    return value


def _sanitized_payload(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    repo_root = _resolve_repo_root(root)
    shared_root = resolve_shared_repo_root(repo_root)
    sanitized = _sanitize_observability_value(
        payload,
        repo_root=repo_root,
        shared_root=shared_root.resolve() if shared_root is not None else None,
    )
    return sanitized if isinstance(sanitized, dict) else {}


def append_progress_event(root: Path, event: RuntimeProgressEvent) -> Path:
    path = Path(root) / PROGRESS_EVENTS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(_sanitized_payload(path.parent, event.to_dict()), ensure_ascii=False) + "\n"
        )
    return path


def read_progress_events(root: Path) -> list[RuntimeProgressEvent]:
    path = Path(root) / PROGRESS_EVENTS_FILENAME
    if not path.exists():
        return []
    events: list[RuntimeProgressEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            events.append(RuntimeProgressEvent.from_dict(payload))
    return events


def write_live_summary(root: Path, summary: RuntimeLiveSummary) -> Path:
    path = Path(root) / LIVE_SUMMARY_FILENAME
    atomic_write_json(path, _sanitized_payload(path.parent, summary.to_dict()))
    return path


def read_live_summary(root: Path) -> RuntimeLiveSummary | None:
    path = Path(root) / LIVE_SUMMARY_FILENAME
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return RuntimeLiveSummary.from_dict(payload)


def append_recap(root: Path, recap: RuntimeRecap) -> Path:
    path = Path(root) / RECAPS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(_sanitized_payload(path.parent, recap.to_dict()), ensure_ascii=False) + "\n"
        )
    return path


def append_step_summary(root: Path, summary: RuntimeStepSummary) -> Path:
    path = Path(root) / STEP_SUMMARIES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(_sanitized_payload(path.parent, summary.to_dict()), ensure_ascii=False)
            + "\n"
        )
    return path


def read_step_summaries(root: Path) -> list[RuntimeStepSummary]:
    path = Path(root) / STEP_SUMMARIES_FILENAME
    if not path.exists():
        return []
    rows: list[RuntimeStepSummary] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(RuntimeStepSummary.from_dict(payload))
    return rows


def append_batch_summary(root: Path, summary: RuntimeBatchSummary) -> Path:
    path = Path(root) / BATCH_SUMMARIES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(_sanitized_payload(path.parent, summary.to_dict()), ensure_ascii=False)
            + "\n"
        )
    return path


def read_batch_summaries(root: Path) -> list[RuntimeBatchSummary]:
    path = Path(root) / BATCH_SUMMARIES_FILENAME
    if not path.exists():
        return []
    rows: list[RuntimeBatchSummary] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(RuntimeBatchSummary.from_dict(payload))
    return rows


def read_recaps(root: Path) -> list[RuntimeRecap]:
    path = Path(root) / RECAPS_FILENAME
    if not path.exists():
        return []
    recaps: list[RuntimeRecap] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            recaps.append(RuntimeRecap.from_dict(payload))
    return recaps


__all__ = [
    "LIVE_SUMMARY_FILENAME",
    "PROGRESS_EVENTS_FILENAME",
    "RECAPS_FILENAME",
    "STEP_SUMMARIES_FILENAME",
    "BATCH_SUMMARIES_FILENAME",
    "append_batch_summary",
    "append_progress_event",
    "append_recap",
    "append_step_summary",
    "read_batch_summaries",
    "read_live_summary",
    "read_progress_events",
    "read_recaps",
    "read_step_summaries",
    "write_live_summary",
]
