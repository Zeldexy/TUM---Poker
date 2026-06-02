"""FastAPI app: lobby + table management (REST) and realtime play (WebSocket).

Run from the repo root:  uvicorn backend.app:app --reload

Flow: POST /api/tables (host creates a lobby) -> friends POST /api/tables/{code}/join
-> host adds bots / kicks / sets chips -> host POST .../start -> host POST .../hands
to deal each hand. Gameplay actions go over the WebSocket.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.schemas import (
    AddBotRequest,
    CreateTableRequest,
    HostActionRequest,
    JoinTableRequest,
    KickRequest,
    LeaveRequest,
    StartingChipsRequest,
)
from backend.sessions import Table, registry
from stats import StatsDashboard

app = FastAPI(title="Texas Hold'em")

# Allowed browser origins for REST calls. Defaults to "*" (open, dev-friendly;
# safe because we never use cookies — auth is a token in the URL/body). Lock it
# down in production via POKER_CORS_ORIGINS, e.g.
#   POKER_CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
_origins_env = os.environ.get("POKER_CORS_ORIGINS", "*").strip()
_allow_origins = (
    ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require(game_id: str) -> Table:
    table = registry.get(game_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


def _require_code(code: str) -> Table:
    table = registry.get_by_code(code)
    if table is None:
        raise HTTPException(status_code=404, detail="No table with that code")
    return table


@app.post("/api/tables")
async def create_table(request: CreateTableRequest) -> dict:
    table = registry.create(
        request.host_name,
        request.starting_chips,
        request.small_blind,
        request.big_blind,
    )
    host = table.members[0]
    return {
        "game_id": table.game_id,
        "code": table.code,
        "token": table.host_token,
        "member_id": host.member_id,
        "is_host": True,
        "lobby": table.lobby_snapshot(),
    }


@app.post("/api/tables/{code}/join")
async def join_table(code: str, request: JoinTableRequest) -> dict:
    table = _require_code(code)
    try:
        member = table.join(request.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    await table.broadcast_after_lobby_change()
    return {
        "game_id": table.game_id,
        "code": table.code,
        "token": member.token,
        "member_id": member.member_id,
        "is_host": False,
        "pending": member.pending,
        "lobby": table.lobby_snapshot(),
    }


@app.post("/api/tables/{game_id}/bots")
async def add_bot(game_id: str, request: AddBotRequest) -> dict:
    table = _require(game_id)
    try:
        table.add_bot(request.host_token, request.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    await table.broadcast_after_lobby_change()
    return table.lobby_snapshot()


@app.post("/api/tables/{game_id}/kick")
async def kick(game_id: str, request: KickRequest) -> dict:
    table = _require(game_id)
    try:
        table.kick(request.host_token, request.member_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    await table.broadcast_after_lobby_change()
    return table.lobby_snapshot()


@app.post("/api/tables/{game_id}/starting-chips")
async def set_starting_chips(game_id: str, request: StartingChipsRequest) -> dict:
    table = _require(game_id)
    try:
        table.set_starting_chips(request.host_token, request.starting_chips)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    await table.broadcast_after_lobby_change()
    return table.lobby_snapshot()


@app.post("/api/tables/{game_id}/start")
async def start_game(game_id: str, request: HostActionRequest) -> dict:
    table = _require(game_id)
    try:
        await table.start_game(request.host_token)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True, "status": table.status}


@app.post("/api/tables/{game_id}/hands")
async def deal_hand(game_id: str, request: HostActionRequest) -> dict:
    table = _require(game_id)
    try:
        await table.deal_hand(request.host_token)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {
        "ok": True,
        "status": table.status,
        "hand_in_progress": table.runner is not None,
    }


@app.get("/api/tables/{game_id}")
def get_table(game_id: str) -> dict:
    table = _require(game_id)
    if table.status == "lobby":
        return table.lobby_snapshot()
    return table._state_msg(token=None)


@app.delete("/api/tables/{game_id}")
def delete_table(game_id: str) -> dict:
    registry.remove(game_id)
    return {"ok": True}


@app.post("/api/tables/{game_id}/leave")
async def leave_table(game_id: str, request: LeaveRequest) -> dict:
    table = _require(game_id)
    await table.leave(request.token)
    return {"ok": True}


@app.get("/api/stats")
def stats() -> dict:
    return StatsDashboard().to_dict()


@app.websocket("/api/tables/{game_id}/ws")
async def table_socket(
    websocket: WebSocket, game_id: str, token: str | None = None
) -> None:
    table = registry.get(game_id)
    if table is None:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    await table.connect(websocket, token)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "leave":
                await table.leave(token)
                try:
                    await websocket.send_json({"type": "left"})
                except Exception:
                    pass
                break
            await _handle(table, websocket, token, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Always drop the connection and close from the server side so the
        # client's onclose fires reliably (and any lingering socket goes away).
        table.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


async def _handle(table: Table, websocket: WebSocket, token, message: dict) -> None:
    kind = message.get("type")
    if kind == "action":
        try:
            await table.submit_action(
                token, message.get("action", ""), int(message.get("amount", 0) or 0)
            )
        except ValueError as error:
            await websocket.send_json({"type": "error", "message": str(error)})
    elif kind == "start_game":
        try:
            await table.start_game(token)
        except ValueError as error:
            await websocket.send_json({"type": "error", "message": str(error)})
    elif kind == "deal_hand":
        try:
            await table.deal_hand(token)
        except ValueError as error:
            await websocket.send_json({"type": "error", "message": str(error)})
    # Unknown message types are ignored.


# ── Static SPA serving ────────────────────────────────────────────────────────
# Must be registered LAST so every /api/ route and the WebSocket are matched
# first. FastAPI resolves routes in registration order; the mount below would
# intercept /api/ calls if it appeared earlier.

# Use your exact absolute path here:
frontend_path = (
    r"D:\Microsoft VS Code Projects\TUM--Poker--Frontend\Poker---Front-End\dist"
)

_dist = Path(frontend_path)

if _dist.is_dir():
    # Vite puts compiled JS/CSS/images under dist/assets/ — serve that subtree
    # as a proper static mount so large files stream efficiently.
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static-assets")

    @app.get("/")
    def serve_react_app() -> FileResponse:
        return FileResponse(str(_dist / "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        # Return any file that actually exists in dist (favicon.ico, robots.txt…)
        # For everything else — including all React Router paths — return the
        # SPA shell so the client-side router can take over.
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_dist / "index.html"))
