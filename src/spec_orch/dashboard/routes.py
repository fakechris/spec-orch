from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import app as dashboard_app


def register_routes(app: FastAPI, root: Path) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return dashboard_app.DASHBOARD_HTML

    @app.get("/favicon.ico")
    async def favicon() -> PlainTextResponse:
        return PlainTextResponse("", status_code=204)

    @app.get("/api/missions")
    async def api_missions() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_missions(root))

    @app.get("/api/inbox")
    async def api_inbox() -> JSONResponse:
        return JSONResponse(dashboard_app._gather_inbox(root))

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

    @app.get("/api/missions/{mission_id}/packets/{packet_id}/transcript")
    async def api_packet_transcript(mission_id: str, packet_id: str) -> JSONResponse:
        transcript = dashboard_app._gather_packet_transcript(root, mission_id, packet_id)
        return JSONResponse(transcript)

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
            return JSONResponse({"error": "Discussion failed"}, status_code=500)

    @app.post("/api/missions/{mission_id}/approval-action")
    async def api_approval_action(
        mission_id: str,
        action_key: str = Body(..., embed=True),
    ) -> JSONResponse:
        mgr = dashboard_app._get_lifecycle_manager(root)
        if mgr is None:
            return JSONResponse({"error": "Mission lifecycle unavailable"}, status_code=503)

        action = dashboard_app._resolve_approval_action(root, mission_id, action_key)
        if action is None:
            return JSONResponse({"error": "Approval action unavailable"}, status_code=404)

        try:
            ok = mgr.inject_btw(mission_id, action["message"], channel="web-dashboard")
            action_record = dashboard_app._record_approval_action(
                root,
                mission_id,
                action_key=action_key,
                label=action["label"],
                message=action["message"],
                channel="web-dashboard",
                status="applied" if ok else "not_applied",
            )
            return JSONResponse(
                {
                    "ok": ok,
                    "action_key": action_key,
                    "message": action["message"],
                    "action": action_record,
                }
            )
        except Exception:
            action_record = dashboard_app._record_approval_action(
                root,
                mission_id,
                action_key=action_key,
                label=action["label"],
                message=action["message"],
                channel="web-dashboard",
                status="failed",
            )
            return JSONResponse(
                {"error": "Approval action failed", "action": action_record},
                status_code=500,
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
