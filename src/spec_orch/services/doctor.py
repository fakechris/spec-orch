from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from spec_orch.services.config_checker import CheckResult, ConfigChecker


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    fix_hint: str | None = None


def _from_config_result(result: CheckResult) -> DoctorCheck:
    return DoctorCheck(
        name=f"config:{result.name}",
        status=result.status,
        message=result.message,
    )


class Doctor:
    def __init__(self, config_path: Path = Path("spec-orch.toml")) -> None:
        self._config_path = config_path
        self._checker = ConfigChecker()

    def _check_git(self) -> DoctorCheck:
        git = shutil.which("git")
        if not git:
            return DoctorCheck(
                name="env:git",
                status="fail",
                message="git not found on PATH",
                fix_hint="brew install git",
            )
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            version = result.stdout.strip()
            return DoctorCheck(name="env:git", status="pass", message=version)
        except Exception as exc:
            return DoctorCheck(
                name="env:git",
                status="fail",
                message=f"git --version failed: {exc}",
            )

    def _check_python_version(self) -> DoctorCheck:
        major, minor = sys.version_info[:2]
        if (major, minor) >= (3, 11):
            return DoctorCheck(
                name="env:python",
                status="pass",
                message=f"Python {major}.{minor}.{sys.version_info[2]}",
            )
        return DoctorCheck(
            name="env:python",
            status="fail",
            message=f"Python {major}.{minor} < 3.11",
            fix_hint="pyenv install 3.11 && pyenv local 3.11",
        )

    def _check_env_file(self) -> DoctorCheck:
        env_path = Path(".env")
        if not env_path.exists():
            return DoctorCheck(
                name="env:dotenv",
                status="warn",
                message=".env file not found",
                fix_hint="cp .env.example .env",
            )
        content = env_path.read_text(encoding="utf-8")
        required_keys = ("SPEC_ORCH_LLM_API_KEY", "SPEC_ORCH_LINEAR_TOKEN")
        missing = [k for k in required_keys if k not in content]
        if missing:
            return DoctorCheck(
                name="env:dotenv",
                status="warn",
                message=f".env missing keys: {', '.join(missing)}",
                fix_hint=f"echo '{missing[0]}=' >> .env",
            )
        return DoctorCheck(
            name="env:dotenv",
            status="pass",
            message=".env present with required keys",
        )

    def _check_environment(self) -> list[DoctorCheck]:
        return [
            self._check_git(),
            self._check_python_version(),
            self._check_env_file(),
        ]

    def _check_configuration(self) -> list[DoctorCheck]:
        config_results = self._checker.check_toml(self._config_path)
        return [_from_config_result(r) for r in config_results]

    def _load_raw(self) -> dict[str, object]:
        try:
            return self._checker.load_toml(self._config_path)
        except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
            return {}

    def _resolve_executable(self, token: str) -> str:
        if token == "{python}":
            return sys.executable
        return token

    def _check_verification(self) -> list[DoctorCheck]:
        raw = self._load_raw()
        verification = raw.get("verification")
        if not isinstance(verification, dict):
            return [
                DoctorCheck(
                    name="verify:section",
                    status="warn",
                    message="No [verification] section in config",
                )
            ]
        checks: list[DoctorCheck] = []
        for step_name, cmd_list in verification.items():
            if not isinstance(cmd_list, list) or not cmd_list:
                checks.append(
                    DoctorCheck(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Invalid command definition for {step_name}",
                    )
                )
                continue
            base_token = cmd_list[0]
            exe = self._resolve_executable(base_token)
            found = shutil.which(exe)
            if found:
                checks.append(
                    DoctorCheck(
                        name=f"verify:{step_name}",
                        status="pass",
                        message=f"executable found: {found}",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name=f"verify:{step_name}",
                        status="fail",
                        message=f"executable not found: {exe}",
                        fix_hint=f"pip install {base_token}" if base_token != "{python}" else None,
                    )
                )
        return checks

    def _check_builder(self) -> list[DoctorCheck]:
        raw = self._load_raw()
        builder = raw.get("builder")
        if not isinstance(builder, dict):
            return [
                DoctorCheck(
                    name="builder:executable",
                    status="warn",
                    message="No [builder] section in config",
                )
            ]
        adapter = builder.get("adapter", "codex_exec")
        executable = builder.get("executable") or builder.get("codex_executable")
        agent = builder.get("agent")

        if not executable and isinstance(agent, str):
            executable = agent

        if not executable:
            executable = "codex"

        if not isinstance(executable, str):
            executable = str(executable)

        found = shutil.which(executable)
        if found:
            return [
                DoctorCheck(
                    name="builder:executable",
                    status="pass",
                    message=f"{executable} found at {found} (adapter={adapter})",
                )
            ]
        return [
            DoctorCheck(
                name="builder:executable",
                status="fail",
                message=f"{executable} not found on PATH (adapter={adapter})",
                fix_hint=f"npm install -g {executable}",
            )
        ]

    def run_all(self) -> list[DoctorCheck]:
        results: list[DoctorCheck] = []
        results.extend(self._check_environment())
        results.extend(self._check_configuration())
        results.extend(self._check_verification())
        results.extend(self._check_builder())
        return results

    def to_json(self) -> dict[str, object]:
        checks = self.run_all()
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for c in checks:
            counts[c.status] += 1
        return {
            "checks": [asdict(c) for c in checks],
            "summary": counts,
        }
