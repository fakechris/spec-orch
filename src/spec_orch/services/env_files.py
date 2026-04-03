from __future__ import annotations

import os
import subprocess
from pathlib import Path

_LEGACY_ENV_ALIASES = {
    "MINIMAX_API_KEY": "SPEC_ORCH_LLM_API_KEY",
    "MINIMAX_ANTHROPIC_BASE_URL": "SPEC_ORCH_LLM_API_BASE",
}


def resolve_git_common_dir(start: Path | None = None) -> Path | None:
    cwd = (start or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (cwd / path).resolve()
    return path.resolve()


def resolve_shared_repo_root(
    start: Path | None = None,
    *,
    git_common_dir: Path | None = None,
) -> Path | None:
    common_dir: Path | None
    if git_common_dir is not None:
        common_dir = git_common_dir.resolve()
    else:
        common_dir = resolve_git_common_dir(start)
    if common_dir is None:
        return None
    return common_dir.parent.resolve()


def iter_dotenv_candidates(
    start: Path | None = None,
    *,
    git_common_dir: Path | None = None,
) -> list[Path]:
    cwd = (start or Path.cwd()).resolve()
    candidates: list[Path] = []
    seen: set[Path] = set()
    current = cwd
    while True:
        env_path = current / ".env"
        resolved = env_path.resolve(strict=False)
        if resolved not in seen:
            candidates.append(env_path)
            seen.add(resolved)
        if current.parent == current:
            break
        current = current.parent

    shared_root = resolve_shared_repo_root(cwd, git_common_dir=git_common_dir)
    if shared_root is not None:
        shared_env = shared_root / ".env"
        resolved = shared_env.resolve(strict=False)
        if resolved not in seen:
            candidates.append(shared_env)

    return candidates


def find_dotenv_path(
    start: Path | None = None,
    *,
    git_common_dir: Path | None = None,
) -> Path | None:
    for candidate in iter_dotenv_candidates(start, git_common_dir=git_common_dir):
        if candidate.is_file():
            return candidate.resolve()
    return None


def bridge_legacy_llm_env_aliases() -> None:
    for target, source in _LEGACY_ENV_ALIASES.items():
        if os.environ.get(target):
            continue
        value = os.environ.get(source, "").strip()
        if value:
            os.environ[target] = value


def load_dotenv(
    start: Path | None = None,
    *,
    git_common_dir: Path | None = None,
) -> Path | None:
    env_path = find_dotenv_path(start, git_common_dir=git_common_dir)
    if env_path is not None:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value
    bridge_legacy_llm_env_aliases()
    return env_path
