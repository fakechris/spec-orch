from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

from . import app as dashboard_app
from . import shell as dashboard_shell

MISSION_IDS_BODY = Body(..., embed=True)
ACTION_KEY_BODY = Body(..., embed=True)


def register_routes(app: FastAPI, root: Path) -> None:
    def _apply_approval_action(
        mission_id: str,
        action_key: str,
        *,
        channel: str = "web-dashboard",
    ) -> tuple[int, dict[str, Any]]:
        mgr = dashboard_app._get_lifecycle_manager(root)
        if mgr is None:
            return 503, {"error": "Mission lifecycle unavailable"}

        action = dashboard_app._resolve_approval_action(root, mission_id, action_key)
        if action is None:
            return 404, {"error": "Approval action unavailable"}

        try:
            ok = mgr.inject_btw(mission_id, action["message"], channel=channel)
            action_record = dashboard_app._record_approval_action(
                root,
                mission_id,
                action_key=action_key,
                label=action["label"],
                message=action["message"],
                channel=channel,
                status="applied" if ok else "not_applied",
            )
            return 200, {
                "ok": ok,
                "action_key": action_key,
                "message": action["message"],
                "action": action_record,
            }
        except Exception:
            action_record = dashboard_app._record_approval_action(
                root,
                mission_id,
                action_key=action_key,
                label=action["label"],
                message=action["message"],
                channel=channel,
                status="failed",
            )
            return 500, {
                "error": "Approval action failed",
                "action": action_record,
            }

    def _approval_redirect_for(mission_id: str) -> str:
        return f"/?mission={mission_id}&mode=missions&tab=approvals"

    def _approval_result_summary(mission_id: str, action_status: str) -> str:
        if action_status == "applied":
            return f"Applied guidance to {mission_id}"
        if action_status == "not_applied":
            return f"Recorded guidance only for {mission_id}"
        if action_status == "failed":
            return f"Approval action failed for {mission_id}"
        return f"Processed approval action for {mission_id}"

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return dashboard_shell.build_dashboard_html()

    @app.get("/favicon.ico")
    async def favicon() -> PlainTextResponse:
        return PlainTextResponse("", status_code=204)

    @app.get("/api/missions")
    async def api_missions() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_missions(root))

    @app.get("/api/inbox")
    async def api_inbox() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_inbox(root))

    @app.get("/api/approvals")
    async def api_approvals() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_approval_queue(root))

    @app.get("/api/missions/{mission_id}")
    async def api_mission(mission_id: str) -> JSONResponse:
        missions = dashboard_app._gather_missions(root)
        for mission in missions:
            if mission["mission_id"] == mission_id:
                return JSONResponse(mission)
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/missions/{mission_id}/detail")
    async def api_mission_detail(mission_id: str) -> JSONResponse:
        detail = dashboard_app._gather_mission_detail(root, mission_id)
        if detail is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse(detail)

    @app.get("/api/missions/{mission_id}/visual-qa")
    async def api_mission_visual_qa(mission_id: str) -> JSONResponse:
        return JSONResponse(dashboard_app._gather_mission_visual_qa(root, mission_id))

    @app.get("/api/missions/{mission_id}/costs")
    async def api_mission_costs(mission_id: str) -> JSONResponse:
        return JSONResponse(dashboard_app._gather_mission_costs(root, mission_id))

    @app.get("/api/missions/{mission_id}/packets/{packet_id}/transcript")
    async def api_packet_transcript(mission_id: str, packet_id: str) -> JSONResponse:
        transcript = dashboard_app._gather_packet_transcript(root, mission_id, packet_id)
        return JSONResponse(transcript)

    @app.get("/artifacts/{artifact_path:path}")
    async def artifact_file(artifact_path: str):
        candidate = (root / artifact_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return PlainTextResponse("not found", status_code=404)
        if not candidate.exists() or not candidate.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(candidate)

    @app.get("/api/missions/{mission_id}/spec")
    async def api_mission_spec(mission_id: str) -> PlainTextResponse:
        content = dashboard_app._get_spec_content(root, mission_id)
        if content is None:
            return PlainTextResponse("not found", status_code=404)
        return PlainTextResponse(content)

    @app.get("/api/runs")
    async def api_runs() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_run_history(root))

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "repo_root": str(root),
                "missions": len(dashboard_app._gather_missions(root)),
            }
        )

    @app.get("/api/events")
    async def api_events(
        issue_id: str | None = None,
        run_id: str | None = None,
        topic: str | None = None,
        limit: int = 100,
    ) -> JSONResponse:
        bus = dashboard_app._get_event_bus()
        if bus is None:
            return JSONResponse([])
        parsed_topic = None
        if topic:
            try:
                from spec_orch.services.event_bus import EventTopic

                parsed_topic = EventTopic(topic)
            except ValueError:
                parsed_topic = None
        events = bus.query_history(
            topic=parsed_topic,
            issue_id=issue_id,
            run_id=run_id,
            limit=limit,
        )
        return JSONResponse(
            [
                {
                    "topic": (
                        event.topic.value
                        if hasattr(event.topic, "value")
                        else str(event.topic)
                    ),
                    "payload": event.payload,
                    "timestamp": event.timestamp,
                    "source": event.source,
                }
                for event in events
            ]
        )

    @app.get("/api/lifecycle")
    async def api_lifecycle() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_lifecycle_states(root))

    @app.get("/api/evolution")
    async def api_evolution() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_evolution_metrics(root))

    @app.get("/api/control/overview")
    async def api_control_overview() -> JSONResponse:
        return JSONResponse(dashboard_app._control_overview(root))

    @app.get("/api/control/skills")
    async def api_control_skills() -> JSONResponse:
        return JSONResponse(dashboard_app._control_skills(root))

    @app.get("/api/control/eval")
    async def api_control_eval() -> JSONResponse:
        return JSONResponse(dashboard_app._control_eval(root))

    @app.post("/api/control/eval/run")
    async def api_control_eval_run() -> JSONResponse:
        return JSONResponse(dashboard_app._control_eval_trigger(root))

    @app.get("/api/control/reactions")
    async def api_control_reactions() -> JSONResponse:
        return JSONResponse(dashboard_app._control_reactions(root))

    @app.get("/api/control/degradation")
    async def api_control_degradation() -> JSONResponse:
        return JSONResponse(dashboard_app._control_degradation(root))

    @app.post("/api/missions/{mission_id}/approve")
    async def api_approve(mission_id: str) -> JSONResponse:
        mgr = dashboard_app._get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Mission lifecycle unavailable"}, status_code=503)
        if dashboard_app._gather_mission_detail(root, mission_id) is None:
            return JSONResponse({"error": "Mission not found"}, status_code=200)
        try:
            state = mgr.approve_and_start(mission_id)
            return JSONResponse({"ok": True, "state": state.to_dict()})
        except FileNotFoundError:
            return JSONResponse({"error": "Mission not found"}, status_code=200)
        except Exception:
            return JSONResponse({"error": "Mission approval failed"}, status_code=500)

    @app.post("/api/missions/{mission_id}/retry")
    async def api_retry(mission_id: str) -> JSONResponse:
        mgr = dashboard_app._get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Mission lifecycle unavailable"}, status_code=503)
        try:
            state = mgr.retry(mission_id)
            return JSONResponse({"ok": True, "state": state.to_dict()})
        except Exception:
            return JSONResponse({"error": "Mission retry failed"}, status_code=500)

    @app.post("/api/discuss")
    async def api_discuss(
        thread_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        svc = dashboard_app._get_conversation_service(root)
        if svc is None:
            return JSONResponse({"error": "ConversationService unavailable"}, status_code=503)
        try:
            from spec_orch.domain.models import ConversationMessage

            msg = ConversationMessage(
                message_id=f"web-{uuid.uuid4().hex[:8]}",
                thread_id=thread_id,
                sender="user",
                content=message,
                timestamp=dashboard_app.datetime.now(dashboard_app.UTC).isoformat(),
                channel="web-dashboard",
            )
            reply = svc.handle_message(msg)
            return JSONResponse({"reply": reply})
        except Exception:
            return JSONResponse({"error": "Discussion failed"}, status_code=503)

    @app.post("/api/missions/{mission_id}/approval-action")
    async def api_approval_action(
        mission_id: str,
        action_key: str = Body(..., embed=True),
    ) -> JSONResponse:
        status_code, payload = _apply_approval_action(mission_id, action_key)
        return JSONResponse(payload, status_code=status_code)

    @app.post("/api/approvals/batch-action")
    async def api_approval_batch_action(
        mission_ids: list[str] = MISSION_IDS_BODY,
        action_key: str = ACTION_KEY_BODY,
    ) -> JSONResponse:
        results: list[dict[str, Any]] = []
        focus_mission_id: str | None = None
        for mission_id in mission_ids:
            status_code, payload = _apply_approval_action(mission_id, action_key)
            action_status = payload.get("action", {}).get("status")
            if focus_mission_id is None and action_status in {"failed", "not_applied"}:
                focus_mission_id = mission_id
            results.append(
                {
                    "mission_id": mission_id,
                    "redirect_to": _approval_redirect_for(mission_id),
                    "result_summary": _approval_result_summary(
                        mission_id,
                        str(action_status or ""),
                    ),
                    "status_code": status_code,
                    **payload,
                }
            )
        summary = {
            "requested": len(mission_ids),
            "processed": len(results),
            "applied": sum(
                1 for item in results if item.get("action", {}).get("status") == "applied"
            ),
            "not_applied": sum(
                1
                for item in results
                if item.get("action", {}).get("status") == "not_applied"
            ),
            "failed": sum(
                1 for item in results if item.get("action", {}).get("status") == "failed"
            ),
        }
        if focus_mission_id is None and results:
            focus_mission_id = results[0]["mission_id"]
        next_pending_mission_id = next(
            (
                item["mission_id"]
                for item in results
                if item.get("action", {}).get("status") in {"failed", "not_applied"}
            ),
            None,
        )
        return JSONResponse(
            {
                "summary": summary,
                "results": results,
                "focus_mission_id": focus_mission_id,
                "next_pending_mission_id": next_pending_mission_id,
            }
        )

    @app.post("/api/btw")
    async def api_btw(
        issue_id: str = Body(...),
        message: str = Body(...),
    ) -> JSONResponse:
        mgr = dashboard_app._get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Mission lifecycle unavailable"}, status_code=503)
        try:
            ok = mgr.inject_btw(issue_id, message, channel="web-dashboard")
            return JSONResponse({"ok": ok})
        except Exception:
            return JSONResponse({"error": "BTW injection failed"}, status_code=500)

    @app.websocket("/ws")
    async def _ws_handler(websocket: WebSocket) -> None:
        await websocket.accept()
        bus = dashboard_app._get_event_bus()
        if bus is None:
            await websocket.send_text(
                json.dumps(
                    {
                        "topic": "system.error",
                        "payload": {"message": "EventBus unavailable"},
                        "timestamp": dashboard_app.datetime.now(dashboard_app.UTC).isoformat(),
                    }
                )
            )
            await websocket.close()
            return

        async def _push(event: Any) -> None:
            payload = {
                "topic": event.topic.value if hasattr(event.topic, "value") else str(event.topic),
                "payload": event.payload,
                "timestamp": event.timestamp,
                "source": event.source,
            }
            await websocket.send_text(json.dumps(payload))

        unsubscribe = bus.subscribe(_push)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()
