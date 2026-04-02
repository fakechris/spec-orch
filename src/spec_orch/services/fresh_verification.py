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


def _build_lint_smoke_script(ts_files: list[str]) -> str:
    return (
        "from pathlib import Path\n"
        "import sys\n"
        f"paths = {ts_files!r}\n"
        "issues = []\n"
        "for rel in paths:\n"
        "    text = Path(rel).read_text(encoding='utf-8')\n"
        "    lines = text.splitlines()\n"
        "    trailing = [idx + 1 for idx, line in enumerate(lines) if line.rstrip() != line]\n"
        "    tabs = [idx + 1 for idx, line in enumerate(lines) if '\\t' in line]\n"
        "    if trailing:\n"
        "        issues.append(f'{rel}:trailing_whitespace={trailing}')\n"
        "    if tabs:\n"
        "        issues.append(f'{rel}:tabs={tabs}')\n"
        "    if text and not text.endswith('\\n'):\n"
        "        issues.append(f'{rel}:missing_terminal_newline')\n"
        "if issues:\n"
        "    sys.stderr.write('lint_smoke_failed=' + ';'.join(issues) + '\\n')\n"
        "    raise SystemExit(1)\n"
    )


def _build_import_smoke_module(ts_files: list[str]) -> str:
    imports = []
    for index, rel in enumerate(ts_files, start=1):
        stem = PurePosixPath(rel).with_suffix("").name
        alias = f"contract_{index}"
        imports.append(f"import * as {alias} from './{stem}';")
    aliases = ", ".join(f"contract_{i}" for i in range(1, len(ts_files) + 1))
    imports.append(f"void [{aliases}];")
    return "\n".join(imports) + "\n"


def _build_import_smoke_script(ts_files: list[str], import_smoke_path: str) -> str:
    import_module = _build_import_smoke_module(ts_files)
    return (
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n"
        f"targets = {ts_files!r}\n"
        f"import_smoke_path = Path({import_smoke_path!r})\n"
        f"import_smoke_path.write_text({import_module!r}, encoding='utf-8')\n"
        "command = [\n"
        "    'tsc',\n"
        "    '--noEmit',\n"
        "    '--target', 'es2022',\n"
        "    '--module', 'esnext',\n"
        "    '--moduleResolution', 'bundler',\n"
        "    '--skipLibCheck',\n"
        "    *targets,\n"
        "    import_smoke_path.as_posix(),\n"
        "]\n"
        "raise SystemExit(subprocess.run(command, check=False).returncode)\n"
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
        commands["typescript_typecheck"] = [
            "tsc",
            "--noEmit",
            "--target",
            "es2022",
            "--module",
            "esnext",
            "--moduleResolution",
            "bundler",
            "--skipLibCheck",
            *ts_files,
        ]
        commands["typescript_lint_smoke"] = _python_check(_build_lint_smoke_script(ts_files))
        import_smoke_path = PurePosixPath(ts_files[0]).with_name("import_smoke.ts").as_posix()
        commands["typescript_import_smoke"] = _python_check(
            _build_import_smoke_script(ts_files, import_smoke_path)
        )

    return commands
