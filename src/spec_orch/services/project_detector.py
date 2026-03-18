"""Detect project type from marker files and generate spec-orch.toml."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectProfile:
    language: str
    framework: str | None = None
    verification: dict[str, list[str]] = field(default_factory=dict)
    builder_adapter: str = "codex_exec"
    extra_notes: str = ""
    base_branch: str = "main"


_PROFILES: dict[str, dict] = {
    "python": {
        "markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
        "language": "python",
        "verification": {
            "lint": ["{python}", "-m", "ruff", "check", "src/"],
            "typecheck": ["{python}", "-m", "mypy", "src/"],
            "test": ["{python}", "-m", "pytest", "-q"],
            "build": ["{python}", "-c", "print('build ok')"],
        },
    },
    "node": {
        "markers": ["package.json"],
        "language": "node",
        "verification": {
            "lint": ["npx", "eslint", "."],
            "typecheck": ["npx", "tsc", "--noEmit"],
            "test": ["npm", "test"],
            "build": ["npm", "run", "build"],
        },
    },
    "rust": {
        "markers": ["Cargo.toml"],
        "language": "rust",
        "verification": {
            "lint": ["cargo", "clippy", "--", "-D", "warnings"],
            "typecheck": ["cargo", "check"],
            "test": ["cargo", "test"],
            "build": ["cargo", "build"],
        },
    },
    "go": {
        "markers": ["go.mod"],
        "language": "go",
        "verification": {
            "lint": ["golangci-lint", "run"],
            "typecheck": ["go", "vet", "./..."],
            "test": ["go", "test", "./..."],
            "build": ["go", "build", "./..."],
        },
    },
    "java": {
        "markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "language": "java",
        "verification": {
            "lint": ["./gradlew", "checkstyleMain"],
            "test": ["./gradlew", "test"],
            "build": ["./gradlew", "build"],
        },
    },
    "swift": {
        "markers": ["Package.swift", "*.xcodeproj", "*.xcworkspace"],
        "language": "swift",
        "verification": {
            "lint": ["swiftlint"],
            "test": ["swift", "test"],
            "build": ["swift", "build"],
        },
    },
    "dotnet": {
        "markers": ["*.csproj", "*.sln", "*.fsproj"],
        "language": "dotnet",
        "verification": {
            "lint": ["dotnet", "format", "--verify-no-changes"],
            "test": ["dotnet", "test"],
            "build": ["dotnet", "build"],
        },
    },
}

_FRAMEWORK_HINTS: dict[str, str] = {
    "next.config.js": "nextjs",
    "next.config.ts": "nextjs",
    "next.config.mjs": "nextjs",
    "vite.config.ts": "vite",
    "vite.config.js": "vite",
    "angular.json": "angular",
    "vue.config.js": "vue",
    "nuxt.config.ts": "nuxt",
    "remix.config.js": "remix",
    "astro.config.mjs": "astro",
    "svelte.config.js": "svelte",
    "Podfile": "ios-cocoapods",
    "Fastfile": "fastlane",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
    "Makefile": "make",
    "Justfile": "just",
    "Taskfile.yml": "taskfile",
    "turbo.json": "turborepo",
    "nx.json": "nx",
    "lerna.json": "lerna",
}


def _detect_base_branch(root: Path) -> str:
    """Detect the default branch from git (main or master)."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            return ref.split("/")[-1]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    for branch in ("main", "master"):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return branch
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    return "main"


def _detect_framework(root: Path) -> str | None:
    for marker, framework in _FRAMEWORK_HINTS.items():
        if "*" in marker:
            if list(root.glob(marker)):
                return framework
        elif (root / marker).exists():
            return framework
    return None


def _refine_node_verification(root: Path, profile: ProjectProfile) -> None:
    """Adjust Node.js verification based on package.json contents."""
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return
    try:
        import json

        pkg = json.loads(pkg_path.read_text())
    except Exception:
        return

    scripts = pkg.get("scripts", {})
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    if "lint" in scripts:
        profile.verification["lint"] = ["npm", "run", "lint"]
    elif "biome" in deps:
        profile.verification["lint"] = ["npx", "biome", "check", "."]

    if "typecheck" in scripts:
        profile.verification["typecheck"] = ["npm", "run", "typecheck"]
    elif "typescript" not in deps:
        profile.verification.pop("typecheck", None)

    if "test" in scripts:
        profile.verification["test"] = ["npm", "test"]
    elif "vitest" in deps:
        profile.verification["test"] = ["npx", "vitest", "run"]
    elif "jest" in deps:
        profile.verification["test"] = ["npx", "jest"]

    if "build" in scripts:
        profile.verification["build"] = ["npm", "run", "build"]


def detect_project(root: Path) -> ProjectProfile:
    """Detect project type from marker files in the given directory."""
    for _profile_name, spec in _PROFILES.items():
        for marker in spec["markers"]:
            if "*" in marker:
                if list(root.glob(marker)):
                    matched = True
                    break
            elif (root / marker).exists():
                matched = True
                break
        else:
            matched = False

        if matched:
            framework = _detect_framework(root)
            base_branch = _detect_base_branch(root)
            profile = ProjectProfile(
                language=spec["language"],
                framework=framework,
                verification=dict(spec["verification"]),
                base_branch=base_branch,
            )
            if profile.language == "node":
                _refine_node_verification(root, profile)
            return profile

    framework = _detect_framework(root)
    base_branch = _detect_base_branch(root)
    return ProjectProfile(
        language="unknown",
        framework=framework,
        verification={},
        extra_notes="Could not detect project type. Configure [verification] manually.",
        base_branch=base_branch,
    )


def generate_toml_config(profile: ProjectProfile) -> str:
    """Generate spec-orch.toml content from a ProjectProfile."""
    lines: list[str] = []

    lines.append("# Generated by: spec-orch init")
    lines.append(
        f"# Detected: {profile.language}" + (f" ({profile.framework})" if profile.framework else "")
    )
    lines.append("")

    lines.append("[issue]")
    lines.append('source = "fixture"  # fixture | linear | github | jira')
    lines.append("")

    lines.append("# [linear]")
    lines.append('# token_env = "SPEC_ORCH_LINEAR_TOKEN"')
    lines.append('# team_key = "YOUR_TEAM"')
    lines.append("")

    lines.append("[builder]")
    lines.append('adapter = "codex_exec"')
    lines.append("timeout_seconds = 1800")
    lines.append("")

    lines.append("[reviewer]")
    lines.append('adapter = "local"')
    lines.append("")

    if profile.verification:
        lines.append("[verification]")
        for step, cmd in profile.verification.items():
            quoted = [f'"{c}"' for c in cmd]
            lines.append(f"{step} = [{', '.join(quoted)}]")
        lines.append("")

    lines.append("[github]")
    lines.append(f'base_branch = "{profile.base_branch}"')
    lines.append("")

    lines.append("[daemon]")
    lines.append("max_concurrent = 1")
    lines.append("")

    lines.append("[evolution]")
    lines.append("enabled = false")

    if profile.extra_notes:
        lines.append("")
        lines.append(f"# NOTE: {profile.extra_notes}")

    lines.append("")
    return "\n".join(lines)
