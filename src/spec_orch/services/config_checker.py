from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from spec_orch.services.linear_client import LinearClient


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str


class ConfigChecker:
    _SECTIONS: tuple[str, ...] = ("linear", "builder", "planner", "daemon")
    _REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
        "linear": ("token_env", "team_key"),
        "builder": ("codex_executable",),
        "planner": ("model",),
        "daemon": (),
    }

    def load_toml(self, path: Path) -> dict[str, object]:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        return raw

    def check_toml(self, path: Path) -> list[CheckResult]:
        try:
            raw = self.load_toml(path)
        except FileNotFoundError:
            return [
                CheckResult(
                    name=section,
                    status="fail",
                    message=f"Config file not found: {path}",
                )
                for section in self._SECTIONS
            ]
        except tomllib.TOMLDecodeError as exc:
            return [
                CheckResult(
                    name=section,
                    status="fail",
                    message=f"Invalid TOML: {exc}",
                )
                for section in self._SECTIONS
            ]

        results: list[CheckResult] = []
        for section in self._SECTIONS:
            section_data = raw.get(section)
            required_fields = self._REQUIRED_FIELDS[section]

            if not isinstance(section_data, dict):
                status: Literal["pass", "warn", "fail"]
                message: str
                if required_fields:
                    status = "fail"
                    message = f"Missing section: [{section}]"
                else:
                    status = "warn"
                    message = f"Missing section: [{section}]"
                results.append(CheckResult(name=section, status=status, message=message))
                continue

            missing = [field for field in required_fields if not section_data.get(field)]
            if missing:
                results.append(
                    CheckResult(
                        name=section,
                        status="fail",
                        message=f"Missing required fields: {', '.join(missing)}",
                    )
                )
                continue

            results.append(CheckResult(name=section, status="pass", message="Section present."))
        return results

    def check_linear(self, token: str, team_key: str) -> list[CheckResult]:
        if not token:
            return [
                CheckResult(
                    name="linear_api",
                    status="fail",
                    message="Linear API token is not configured.",
                )
            ]
        if not team_key:
            return [
                CheckResult(
                    name="linear_api",
                    status="fail",
                    message="Linear team_key is not configured.",
                )
            ]

        client: LinearClient | None = None
        try:
            client = LinearClient(token=token)
            data = client.query(
                """
                query {
                  teams {
                    nodes {
                      key
                      name
                      states {
                        nodes {
                          name
                        }
                      }
                    }
                  }
                }
                """
            )
            teams = data.get("teams", {}).get("nodes", [])
            team = next((item for item in teams if item.get("key") == team_key), None)
            if not team:
                available = ", ".join(item.get("key", "") for item in teams if item.get("key"))
                available = available or "none"
                return [
                    CheckResult(
                        name="linear_api",
                        status="fail",
                        message=f"Team key {team_key} not found. Available teams: {available}",
                    )
                ]

            states = [
                state.get("name", "")
                for state in team.get("states", {}).get("nodes", [])
                if state.get("name")
            ]
            state_text = ", ".join(states) if states else "none"
            status: Literal["pass", "warn"] = "pass" if states else "warn"
            return [
                CheckResult(
                    name="linear_api",
                    status=status,
                    message=(
                        f"Connected to Linear team {team_key}. Workflow states: {state_text}"
                    ),
                )
            ]
        except Exception as exc:
            return [
                CheckResult(
                    name="linear_api",
                    status="fail",
                    message=f"Linear API check failed: {exc}",
                )
            ]
        finally:
            if client is not None:
                client.close()

    def check_codex(self, executable: str) -> CheckResult:
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return CheckResult(
                name="codex",
                status="fail",
                message=f"Executable not found: {executable}",
            )

        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
            return CheckResult(
                name="codex",
                status="fail",
                message=f"{executable} --version failed: {details}",
            )

        version = result.stdout.strip() or f"{executable} is available"
        return CheckResult(name="codex", status="pass", message=version)

    def check_planner(
        self, model: str | None, api_key_env: str | None
    ) -> list[CheckResult]:
        results: list[CheckResult] = []

        if model:
            results.append(
                CheckResult(
                    name="planner_model",
                    status="pass",
                    message=f"Planner model configured: {model}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="planner_model",
                    status="warn",
                    message="Planner model is not configured.",
                )
            )

        if not api_key_env:
            results.append(
                CheckResult(
                    name="planner_api_key",
                    status="warn",
                    message="Planner API key env var is not configured.",
                )
            )
            return results

        if os.environ.get(api_key_env):
            results.append(
                CheckResult(
                    name="planner_api_key",
                    status="pass",
                    message=f"Environment variable {api_key_env} is set.",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="planner_api_key",
                    status="fail",
                    message=f"Environment variable {api_key_env} is not set.",
                )
            )
        return results
