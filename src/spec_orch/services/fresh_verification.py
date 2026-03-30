from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

_PYTHON_PREFIX: Final[list[str]] = ["{python}", "-c"]


def _normalize_scope(files_in_scope: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in files_in_scope:
        text = str(raw_path).strip().replace("\\", "/")
        if not text:
            continue
        path = PurePosixPath(text)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Invalid files_in_scope path: {raw_path!r}")
        normalized_path = path.as_posix()
        if normalized_path not in normalized:
            normalized.append(normalized_path)
    return normalized


def _python_check(script: str) -> list[str]:
    return [*_PYTHON_PREFIX, script]


def _build_exists_script(scoped_files: list[str]) -> str:
    return (
        "from pathlib import Path\n"
        "import sys\n"
        f"paths = {scoped_files!r}\n"
        "missing = [rel for rel in paths if not Path(rel).is_file()]\n"
        "if missing:\n"
        "    sys.stderr.write(f'missing={missing}\\n')\n"
        "    raise SystemExit(1)\n"
    )


def _build_contract_tokens_script(ts_files: list[str]) -> str:
    return (
        "from pathlib import Path\n"
        "import sys\n"
        f"paths = {ts_files!r}\n"
        "required = ('export ', 'interface ', 'type ', 'enum ')\n"
        "invalid = []\n"
        "for rel in paths:\n"
        "    text = Path(rel).read_text(encoding='utf-8')\n"
        "    if not any(token in text for token in required):\n"
        "        invalid.append(rel)\n"
        "if invalid:\n"
        "    sys.stderr.write(f'missing_contract_tokens={invalid}\\n')\n"
        "    raise SystemExit(1)\n"
    )


def _build_schema_surface_script(ts_files: list[str]) -> str:
    return (
        "from pathlib import Path\n"
        "import sys\n"
        f"paths = {ts_files!r}\n"
        "surface_tokens = (\n"
        "    'Schema',\n"
        "    'schema',\n"
        "    'export interface ',\n"
        "    'export type ',\n"
        "    'export const ',\n"
        ")\n"
        "invalid = []\n"
        "for rel in paths:\n"
        "    text = Path(rel).read_text(encoding='utf-8')\n"
        "    if not any(token in text for token in surface_tokens):\n"
        "        invalid.append(rel)\n"
        "if invalid:\n"
        "    sys.stderr.write(f'missing_schema_surface={invalid}\\n')\n"
        "    raise SystemExit(1)\n"
    )


def build_fresh_verification_commands(files_in_scope: list[str]) -> dict[str, list[str]]:
    scoped_files = _normalize_scope(files_in_scope)
    if not scoped_files:
        return {}

    commands = {
        "scaffold_exists": _python_check(_build_exists_script(scoped_files)),
    }

    ts_files = [path for path in scoped_files if path.endswith((".ts", ".tsx"))]
    if ts_files:
        commands["typescript_contract_tokens"] = _python_check(
            _build_contract_tokens_script(ts_files)
        )
        commands["typescript_schema_surface"] = _python_check(
            _build_schema_surface_script(ts_files)
        )

    return commands
