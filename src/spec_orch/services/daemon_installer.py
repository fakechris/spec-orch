"""Generate and install systemd / launchd service definitions for the daemon."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

_LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>spec_orch</string>
    <string>daemon</string>
    <string>start</string>
    <string>--config</string>
    <string>{config}</string>
    <string>--repo-root</string>
    <string>{repo_root}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{repo_root}</string>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{log_dir}/spec-orch-daemon.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>{log_dir}/spec-orch-daemon.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{path_env}</string>
  </dict>
</dict>
</plist>
"""

_SYSTEMD_UNIT = """\
[Unit]
Description=SpecOrch Daemon — polls Linear and executes issues
After=network.target

[Service]
Type=simple
ExecStart={python} -m spec_orch daemon start --config {config} --repo-root {repo_root}
WorkingDirectory={repo_root}
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""


def _detect_platform() -> str:
    return "darwin" if platform.system() == "Darwin" else "linux"


def generate_service_file(
    *,
    repo_root: Path,
    config_path: Path,
    label: str = "com.specorch.daemon",
) -> tuple[str, str]:
    """Return (content, target_path) for the service definition."""
    plat = _detect_platform()
    python = sys.executable
    config_abs = str(config_path.resolve())
    repo_abs = str(repo_root.resolve())

    if plat == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "spec-orch"
        content = _LAUNCHD_PLIST.format(
            label=label,
            python=python,
            config=config_abs,
            repo_root=repo_abs,
            log_dir=str(log_dir),
            path_env=os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        )
        target = str(Path.home() / "Library" / "LaunchAgents" / f"{label}.plist")
        return content, target
    else:
        content = _SYSTEMD_UNIT.format(
            python=python,
            config=config_abs,
            repo_root=repo_abs,
        )
        user_dir = Path.home() / ".config" / "systemd" / "user"
        target = str(user_dir / "spec-orch-daemon.service")
        return content, target


def install_service(
    *,
    repo_root: Path,
    config_path: Path,
    label: str = "com.specorch.daemon",
) -> str:
    """Write the service file and return the install path."""
    content, target = generate_service_file(
        repo_root=repo_root,
        config_path=config_path,
        label=label,
    )
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    plat = _detect_platform()
    if plat == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "spec-orch"
        log_dir.mkdir(parents=True, exist_ok=True)

    target_path.write_text(content)
    return target


def start_service(label: str = "com.specorch.daemon") -> bool:
    """Start the installed service. Returns True on success."""
    plat = _detect_platform()
    try:
        if plat == "darwin":
            plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            subprocess.run(
                ["launchctl", "load", str(plist)],
                check=True, capture_output=True,
            )
        else:
            subprocess.run(
                ["systemctl", "--user", "start", "spec-orch-daemon"],
                check=True, capture_output=True,
            )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def stop_service(label: str = "com.specorch.daemon") -> bool:
    """Stop the running service. Returns True on success."""
    plat = _detect_platform()
    try:
        if plat == "darwin":
            plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            subprocess.run(
                ["launchctl", "unload", str(plist)],
                check=True, capture_output=True,
            )
        else:
            subprocess.run(
                ["systemctl", "--user", "stop", "spec-orch-daemon"],
                check=True, capture_output=True,
            )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def service_status(label: str = "com.specorch.daemon") -> dict[str, str]:
    """Return service status info."""
    plat = _detect_platform()
    result: dict[str, str] = {"platform": plat, "installed": "no", "running": "unknown"}

    if plat == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        result["installed"] = "yes" if plist.exists() else "no"
        try:
            proc = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True, text=True,
            )
            result["running"] = "yes" if proc.returncode == 0 else "no"
        except FileNotFoundError:
            result["running"] = "unknown"
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "spec-orch-daemon.service"
        result["installed"] = "yes" if unit.exists() else "no"
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", "spec-orch-daemon"],
                capture_output=True, text=True,
            )
            result["running"] = "yes" if proc.stdout.strip() == "active" else "no"
        except FileNotFoundError:
            result["running"] = "unknown"

    return result
