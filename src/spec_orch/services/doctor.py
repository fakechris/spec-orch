from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from spec_orch.services.config_checker import CheckResult, ConfigChecker
from spec_orch.services.io import atomic_write_json


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

    def _required_env_keys(self) -> list[str]:
        """Derive required env keys from active config sections."""
        raw = self._load_raw()
        keys: list[str] = []
        planner = raw.get("planner") or raw.get("conversation")
        if isinstance(planner, dict) and planner:
            key_env = planner.get("api_key_env")
            if key_env:
                keys.append(key_env)
        linear = raw.get("linear")
        if isinstance(linear, dict) and linear:
            token_env = linear.get("token_env")
            if token_env:
                keys.append(token_env)
        return keys

    def _check_env_file(self) -> DoctorCheck:
        required_keys = self._required_env_keys()
        if not required_keys:
            return DoctorCheck(
                name="env:dotenv",
                status="pass",
                message="No env keys required by active config",
            )

        env_path = Path(".env")
        defined_keys: set[str] = set()
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key = stripped.split("=", 1)[0].strip()
                if key:
                    defined_keys.add(key)

        missing = [k for k in required_keys if k not in defined_keys and k not in os.environ]
        if missing:
            return DoctorCheck(
                name="env:dotenv",
                status="warn",
                message=f"Missing env keys: {', '.join(missing)}",
                fix_hint=f"echo '{missing[0]}=' >> .env  (or export {missing[0]}=...)",
            )
        return DoctorCheck(
            name="env:dotenv",
            status="pass",
            message="Required env keys present",
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
            if not isinstance(base_token, str):
                checks.append(
                    DoctorCheck(
                        name=f"verify:{step_name}",
                        status="warn",
                        message=f"Non-string executable in {step_name}: {base_token!r}",
                    )
                )
                continue
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

        if not isinstance(executable, str):
            executable = None
        if not executable and isinstance(agent, str):
            executable = agent
        if not executable:
            executable = "codex"

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

    def _check_reviewer(self) -> list[DoctorCheck]:
        raw = self._load_raw()
        reviewer = raw.get("reviewer")
        if not isinstance(reviewer, dict):
            return [
                DoctorCheck(
                    name="reviewer:adapter",
                    status="warn",
                    message="No [reviewer] section in config; defaulting to local (JSON-only)",
                    fix_hint='Add [reviewer] adapter = "llm" to spec-orch.toml',
                )
            ]
        adapter = reviewer.get("adapter", "local")
        if adapter == "local":
            has_llm_key = bool(os.environ.get("SPEC_ORCH_LLM_API_KEY"))
            if has_llm_key:
                return [
                    DoctorCheck(
                        name="reviewer:adapter",
                        status="warn",
                        message="Reviewer is 'local' (JSON-only) but LLM API key is available",
                        fix_hint='Set [reviewer] adapter = "llm" for automated LLM review',
                    )
                ]
            return [
                DoctorCheck(
                    name="reviewer:adapter",
                    status="pass",
                    message=(
                        "Reviewer adapter: local (set SPEC_ORCH_LLM_API_KEY to enable LLM review)"
                    ),
                )
            ]
        return [
            DoctorCheck(
                name="reviewer:adapter",
                status="pass",
                message=f"Reviewer adapter: {adapter}",
            )
        ]

    def run_all(self) -> list[DoctorCheck]:
        results: list[DoctorCheck] = []
        results.extend(self._check_environment())
        results.extend(self._check_configuration())
        results.extend(self._check_verification())
        results.extend(self._check_builder())
        results.extend(self._check_reviewer())
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

    def write_health_file(self, output_dir: Path | None = None) -> Path:
        """Write structured health report to .spec_orch/health.json."""
        report = self.to_json()
        target_dir = output_dir or Path(".spec_orch")
        target_dir.mkdir(parents=True, exist_ok=True)
        health_path = target_dir / "health.json"
        atomic_write_json(health_path, report)
        return health_path
