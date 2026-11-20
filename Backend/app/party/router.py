import asyncio
import json
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlmodel import Session

from app.auth.deps import get_optional_user, user_from_token
from app.config import get_settings
from app.db import get_session, session_scope
from app.models import User
from app.party.manager import manager
from app.party.party import (
    CLOSE_BAD_REQUEST,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHORIZED,
    Party,
    PartyError,
    message,
)
from app.party.results import save_party_results_async
from app.quiz.sample import get_sample_questions
from app.quiz.store import load_questions

router = APIRouter()


# ---------- REST ----------

class CreatePartyRequest(BaseModel):
    quiz_id: Optional[str] = None


class CreatePartyResponse(BaseModel):
    code: str
    host_token: str
    join_url: str


@router.post("/api/parties", response_model=CreatePartyResponse, status_code=201)
def create_party(
    body: Optional[CreatePartyRequest] = None,
    host: Optional[User] = Depends(get_optional_user),
    session: Session = Depends(get_session),
) -> CreatePartyResponse:
    """Host może być gościem; zalogowanemu gra zapisuje się w historii."""
    quiz_id = body.quiz_id if body is not None else None
    if quiz_id is not None:
        questions = load_questions(session, quiz_id)
        if questions is None:
            raise HTTPException(404, "Quiz not found")
    else:
        questions = get_sample_questions()
    party = manager.create(
        questions,
        quiz_id=quiz_id,
        host_user_id=host.id if host else None,
        on_finish=save_party_results_async,
    )
    join_url = f"{get_settings().frontend_url.rstrip('/')}/join/{party.code}"
    return CreatePartyResponse(code=party.code, host_token=party.host_token, join_url=join_url)


@router.get("/api/parties/{code}")
async def get_party(code: str) -> Dict[str, Any]:
    party = manager.get(code)
    if party is None:
        raise HTTPException(404, "Party not found")
    return party.summary()


# ---------- WebSocket ----------

async def _reject(ws: WebSocket, code: int, reason: str) -> None:
    await ws.send_json(message("error", message=reason))
    await ws.close(code=code, reason=reason)


async def _message_loop(ws: WebSocket, handle: Callable[[str, Dict[str, Any]], Awaitable[None]]) -> None:
    """Read {"type", "data"} messages until disconnect; report bad input back to the client."""
    while True:
        raw = await ws.receive_text()
        try:
            msg = json.loads(raw)
            type_ = msg["type"]
            data = msg.get("data") or {}
            if not isinstance(type_, str) or not isinstance(data, dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            await ws.send_json(message("error", message='Expected JSON {"type": str, "data": object}'))
            continue
        try:
            await handle(type_, data)
        except PartyError as e:
            await ws.send_json(message("error", message=str(e), request=type_))


@router.websocket("/ws/party/{code}/host")
async def host_ws(ws: WebSocket, code: str, token: str = "") -> None:
    await ws.accept()
    party = manager.get(code)
    if party is None:
        return await _reject(ws, CLOSE_NOT_FOUND, "Party not found")
    if not secrets.compare_digest(token, party.host_token):
        return await _reject(ws, CLOSE_UNAUTHORIZED, "Invalid host token")

    async def handle(type_: str, data: Dict[str, Any]) -> None:
        if type_ == "start_game":
            await party.start()
        elif type_ == "next_question":
            await party.next()
        elif type_ == "kick_player":
            await party.kick(str(data.get("player_id", "")))
        else:
            raise PartyError(f"Unknown message type: {type_}")

    await party.attach_host(ws)
    try:
        await _message_loop(ws, handle)
    except WebSocketDisconnect:
        pass
    finally:
        await party.detach_host(ws)


def _user_id_from_token(token: str) -> Optional[int]:
    with session_scope() as session:
        user = user_from_token(session, token)
        return user.id if user else None


@router.websocket("/ws/party/{code}/player")
async def player_ws(
    ws: WebSocket, code: str, nick: str = "", reconnect_token: str = "", access_token: str = ""
) -> None:
    """access_token (opcjonalny) = token z logowania; wtedy wynik trafia do historii gracza."""
    await ws.accept()
    party: Optional[Party] = manager.get(code)
    if party is None:
        return await _reject(ws, CLOSE_NOT_FOUND, "Party not found")
    user_id: Optional[int] = None
    if access_token:
        user_id = await asyncio.to_thread(_user_id_from_token, access_token)
        if user_id is None:
            return await _reject(ws, CLOSE_UNAUTHORIZED, "Invalid or expired access token")
    try:
        player = party.join(nick, reconnect_token or None, user_id)
    except PartyError as e:
        return await _reject(ws, CLOSE_BAD_REQUEST, str(e))

    async def handle(type_: str, data: Dict[str, Any]) -> None:
        if type_ == "answer":
            await party.submit_answer(player, data.get("question_id"), data.get("choice"))
        else:
            raise PartyError(f"Unknown message type: {type_}")

    await party.attach_player(player, ws)
    try:
        await _message_loop(ws, handle)
    except WebSocketDisconnect:
        pass
    finally:
        await party.detach_player(player, ws)
