"""Format codex and orchestrator events into human-readable terminal lines."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

_SUPPORTS_COLOR = hasattr(os, "isatty") and os.isatty(2)

# ANSI helpers — only emit codes when stderr is a tty.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"


def _c(code: str, text: str, *, color: bool = True) -> str:
    if not color:
        return text
    return f"{code}{text}{_RESET}"


# Tag width for alignment
_TAG_WIDTH = 8


class EventFormatter:
    """Converts raw codex / orchestrator events into formatted terminal lines.

    ``format()`` returns a colored string (ANSI) suitable for stderr.
    ``format_plain()`` returns the same content without ANSI codes.
    """

    def __init__(self, *, color: bool | None = None, verbose: bool = False) -> None:
        self._color = color if color is not None else _SUPPORTS_COLOR
        self._verbose = verbose
        self._max_output_lines = 0 if verbose else 5

    def format(self, event: dict[str, Any]) -> str | None:
        """Return a formatted line for *event*, or ``None`` to skip."""
        return self._dispatch(event, color=self._color)

    def format_plain(self, event: dict[str, Any]) -> str | None:
        """Return a formatted line **without** ANSI codes."""
        return self._dispatch(event, color=False)

    # ------------------------------------------------------------------

    def _dispatch(self, event: dict[str, Any], *, color: bool) -> str | None:
        ts = self._timestamp(event)
        etype: str = event.get("event_type", "") or event.get("type", "")
        data: dict = event.get("data", event)

        # Builder / codex events (forwarded via event_logger)
        item = data.get("item", {})
        itype = item.get("type", "")

        if etype in ("item.started", "item.completed", "item.updated"):
            return self._format_item(ts, etype, item, itype, color=color)

        if etype == "turn.plan.updated":
            items = data.get("items", [])
            tag = _c(_MAGENTA, "PLAN".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Updated ({len(items)} items)"

        if etype == "turn.completed":
            usage = data.get("usage", {})
            tag = _c(_GREEN + _BOLD, "TURN".ljust(_TAG_WIDTH), color=color)
            if usage:
                return (
                    f"{ts} {tag} Completed "
                    f"({usage.get('input_tokens', 0):,} in"
                    f" / {usage.get('output_tokens', 0):,} out)"
                )
            return f"{ts} {tag} Completed"

        if etype == "turn.failed":
            tag = _c(_RED + _BOLD, "TURN".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Failed"

        # Orchestrator events (from run_controller / telemetry)
        return self._format_orchestrator(ts, event, color=color)

    # ---- item events ---------------------------------------------------

    def _format_item(
        self,
        ts: str,
        etype: str,
        item: dict,
        itype: str,
        *,
        color: bool,
    ) -> str | None:
        if etype == "item.started" and itype == "command_execution":
            tag = _c(_CYAN, "COMMAND".ljust(_TAG_WIDTH), color=color)
            cmd = item.get("command", "")
            return f"{ts} {tag} {cmd}"

        if etype == "item.completed":
            if itype == "command_execution":
                return self._format_command_completed(ts, item, color=color)
            if itype == "agent_message":
                tag = _c(_BLUE, "MESSAGE".ljust(_TAG_WIDTH), color=color)
                text = item.get("text", "")
                if len(text) > 120:
                    text = text[:117] + "..."
                return f"{ts} {tag} {text}"
            if itype == "file_change":
                tag = _c(_YELLOW, "FILE".ljust(_TAG_WIDTH), color=color)
                return f"{ts} {tag} {item.get('file', '?')}"
            if itype == "reasoning":
                tag = _c(_DIM, "REASON".ljust(_TAG_WIDTH), color=color)
                text = item.get("text", "")
                if len(text) > 100:
                    text = text[:97] + "..."
                return f"{ts} {tag} {text}"

        return None

    def _format_command_completed(self, ts: str, item: dict, *, color: bool) -> str:
        exit_code = item.get("exit_code", "?")
        output = item.get("aggregated_output", "")
        lines = output.splitlines() if output else []
        line_count = len(lines)

        if exit_code == 0:
            tag = _c(_DIM, "OUTPUT".ljust(_TAG_WIDTH), color=color)
            status = _c(_GREEN, f"exit {exit_code}", color=color)
        else:
            tag = _c(_RED, "OUTPUT".ljust(_TAG_WIDTH), color=color)
            status = _c(_RED, f"exit {exit_code}", color=color)

        summary = f"{ts} {tag} ({status}, {line_count} lines)"

        if self._max_output_lines > 0 and lines:
            shown = lines[: self._max_output_lines]
            preview = "\n".join(f"         {_c(_DIM, '| ', color=color)}{ln}" for ln in shown)
            if line_count > self._max_output_lines:
                preview += (
                    f"\n         {_c(_DIM, '| ', color=color)}"
                    f"... ({line_count - self._max_output_lines} more lines)"
                )
            return f"{summary}\n{preview}"
        elif self._max_output_lines == 0 and self._verbose and lines:
            preview = "\n".join(f"         {_c(_DIM, '| ', color=color)}{ln}" for ln in lines)
            return f"{summary}\n{preview}"

        return summary

    # ---- orchestrator events -------------------------------------------

    def _format_orchestrator(self, ts: str, event: dict[str, Any], *, color: bool) -> str | None:
        etype: str = event.get("event_type", "")
        component: str = event.get("component", "")
        data: dict = event.get("data", {})

        if etype == "builder_started":
            tag = _c(_CYAN + _BOLD, "BUILDER".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Started"

        if etype == "builder_completed":
            ok = data.get("succeeded", False)
            skipped = data.get("skipped", False)
            if skipped:
                tag = _c(_DIM, "BUILDER".ljust(_TAG_WIDTH), color=color)
                return f"{ts} {tag} Skipped (no builder_prompt)"
            if ok:
                tag = _c(_GREEN + _BOLD, "BUILDER".ljust(_TAG_WIDTH), color=color)
                return f"{ts} {tag} Succeeded"
            tag = _c(_RED + _BOLD, "BUILDER".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Failed"

        if etype in ("verification_started", "rerun_verification_started"):
            tag = _c(_MAGENTA, "VERIFY".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Running verification..."

        if etype == "verification_step_completed":
            step = data.get("step", "?")
            exit_code = data.get("exit_code", 1)
            if exit_code == 0:
                tag = _c(_GREEN, "VERIFY".ljust(_TAG_WIDTH), color=color)
                status = _c(_GREEN, "passed", color=color)
            else:
                tag = _c(_RED, "VERIFY".ljust(_TAG_WIDTH), color=color)
                status = _c(_RED, "FAILED", color=color)
            return f"{ts} {tag} {step}: {status}"

        if etype == "verification_completed":
            all_ok = data.get("all_passed", False)
            if all_ok:
                tag = _c(_GREEN + _BOLD, "VERIFY".ljust(_TAG_WIDTH), color=color)
                return f"{ts} {tag} All checks passed"
            tag = _c(_RED + _BOLD, "VERIFY".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Some checks failed"

        if etype == "gate_evaluated":
            mergeable = data.get("mergeable", False)
            failed = data.get("failed_conditions", [])
            flow = data.get("flow_control", {})
            if mergeable:
                tag = _c(_GREEN + _BOLD, "GATE".ljust(_TAG_WIDTH), color=color)
                success_details: list[str] = []
                if isinstance(flow, dict) and flow.get("promotion_required"):
                    success_details.append(f"promote={flow.get('promotion_target') or 'required'}")
                if success_details:
                    return f"{ts} {tag} MERGEABLE ({', '.join(success_details)})"
                return f"{ts} {tag} MERGEABLE"
            tag = _c(_RED + _BOLD, "GATE".ljust(_TAG_WIDTH), color=color)
            blocked = ", ".join(failed) if failed else "unknown"
            blocked_details: list[str] = []
            if isinstance(flow, dict):
                if flow.get("retry_recommended"):
                    blocked_details.append("retry")
                if flow.get("escalation_required"):
                    blocked_details.append("escalate")
                if flow.get("demotion_suggested"):
                    blocked_details.append(
                        f"demote={flow.get('demotion_target') or 'suggested'}"
                    )
                if flow.get("backtrack_reason"):
                    blocked_details.append(f"backtrack={flow.get('backtrack_reason')}")
            suffix = f"; {', '.join(blocked_details)}" if blocked_details else ""
            return f"{ts} {tag} BLOCKED ({blocked}{suffix})"

        if etype == "review_initialized":
            tag = _c(_BLUE, "REVIEW".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Initialized (verdict: {data.get('verdict', '?')})"

        if etype == "run_started":
            tag = _c(_BOLD, "RUN".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Started"

        if etype == "rerun_completed":
            tag = _c(_BOLD, "RUN".ljust(_TAG_WIDTH), color=color)
            return f"{ts} {tag} Re-run completed"

        if component and etype:
            tag = _c(_DIM, component.upper()[:_TAG_WIDTH].ljust(_TAG_WIDTH), color=color)
            msg = event.get("message", etype)
            return f"{ts} {tag} {msg}"

        return None

    # ---- helpers -------------------------------------------------------

    @staticmethod
    def _timestamp(event: dict[str, Any]) -> str:
        ts = event.get("timestamp")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                return f"[{dt.strftime('%H:%M:%S')}]"
            except (ValueError, TypeError):
                pass
        return f"[{datetime.now(UTC).strftime('%H:%M:%S')}]"
