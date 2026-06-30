"""FastAPI：对话 API + 静态 archor 前端。"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from anchor.deepseek_client import DeepSeekClient
from anchor.dialogue_handler import handle_user_message
from anchor.follow_recommendations import build_follow_recommendations
from anchor.plan_builder import build_flipbook_plan, build_plan_shell, is_plan_cached, session_plan_key
from anchor.transport_planner import transport_mode_catalog
from anchor.sanitize import public_error_message, sanitize_meta
from anchor.state_machine import Session

PROJECT_ROOT = ROOT.parent
ARCHOR_DIR = PROJECT_ROOT / "archor"
logger = logging.getLogger("anchor.api")

app = FastAPI(title="Anchor API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_llm: DeepSeekClient | None = None


def get_llm() -> DeepSeekClient | None:
    global _llm
    if _llm is None:
        client = DeepSeekClient()
        _llm = client if client.is_configured else None
    return _llm


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session: dict[str, Any] | None = None
    mode: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session: dict[str, Any]
    meta: dict[str, Any]
    llm_enabled: bool


class PlanRequest(BaseModel):
    session: dict[str, Any] | None = None


class PlanResponse(BaseModel):
    plan: dict[str, Any]
    generation_ms: int | None = None
    cached: bool = False
    build_steps: list[dict[str, Any]] | None = None


class WizardSessionRequest(BaseModel):
    session: dict[str, Any] | None = None


@app.get("/api/transport/modes")
def transport_modes() -> dict[str, Any]:
    return {"modes": transport_mode_catalog()}


@app.post("/api/wizard/follow")
def wizard_follow(body: WizardSessionRequest) -> dict[str, Any]:
    session = body.session or {}
    slots = session.get("slots") or {}
    if not slots.get("destination"):
        raise HTTPException(status_code=400, detail="缺少目的地")
    if not session.get("selected_anchor_pois") and not session.get("selected_anchor_poi"):
        raise HTTPException(status_code=400, detail="请先在锚点页完成选择")
    return build_follow_recommendations(session)


@app.get("/api/health")
def health() -> dict[str, Any]:
    llm = get_llm()
    return {
        "ok": True,
        "llm_enabled": llm is not None,
        "model": llm.model if llm else None,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    session = Session.from_dict(body.session)
    llm = get_llm()
    llm_used = False

    try:
        turn = handle_user_message(session, message, llm=llm, mode=body.mode)
        llm_used = llm is not None
    except Exception as exc:
        if llm is None:
            raise HTTPException(
                status_code=502, detail=public_error_message(exc)
            ) from exc
        logger.warning("DeepSeek call failed, using rule fallback: %s", exc)
        turn = handle_user_message(session, message, llm=None, mode=body.mode)

    payload = turn.to_dict()
    return ChatResponse(
        reply=payload["reply"],
        session=payload["session"],
        meta=sanitize_meta(payload["meta"]),
        llm_enabled=llm_used,
    )


@app.post("/api/plan/shell", response_model=PlanResponse)
def plan_shell(body: PlanRequest) -> PlanResponse:
    session = body.session or {}
    slots = session.get("slots") or {}
    if not slots.get("destination") or not slots.get("days"):
        raise HTTPException(status_code=400, detail="请先完成对话资料收集")
    return PlanResponse(plan=build_plan_shell(session), generation_ms=0, cached=False)


@app.post("/api/plan", response_model=PlanResponse)
def generate_plan(body: PlanRequest) -> PlanResponse:
    session = body.session or {}
    slots = session.get("slots") or {}
    if not slots.get("destination") or not slots.get("days"):
        raise HTTPException(status_code=400, detail="请先完成对话资料收集")
    key = session_plan_key(session)
    cached_hit = is_plan_cached(session)
    started = time.perf_counter()
    try:
        plan = build_flipbook_plan(session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    steps = plan.get("build_steps")
    return PlanResponse(plan=plan, generation_ms=elapsed, cached=cached_hit, build_steps=steps)


if ARCHOR_DIR.is_dir():
    app.mount("/archor", StaticFiles(directory=str(ARCHOR_DIR), html=True), name="archor")


@app.get("/")
def root():
    if ARCHOR_DIR.is_dir():
        return RedirectResponse(url="/archor/")
    return {
        "message": "Anchor API",
        "archor": "/archor/",
        "health": "/api/health",
        "chat": "POST /api/chat",
    }
