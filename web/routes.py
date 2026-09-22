"""Web 界面路由。

页面本身是薄壳，数据统一由 JS 调用 /api/* 获取，
这样接口和页面不会出现两套逻辑。
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from api.chat_handler import ProcessUserInput_stream
from config.time_config import time_config

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="web/templates")
router = APIRouter(tags=["Web 界面"])


def _context(request: Request, **extra) -> dict:
    context = {
        "request": request,
        "today": time_config.current_date_str(),
        "weekday": time_config.current_weekday_str(),
        "now": time_config.current_datetime_str(),
        "business_hours": "9:00-20:00",
    }
    context.update(extra)
    return context


@router.get("/", response_class=HTMLResponse, summary="首页：对话式预约")
async def index(request: Request):
    return templates.TemplateResponse("index.html", _context(request, active="chat"))


@router.post("/chat/stream", summary="流式对话")
async def chat_stream(payload: dict):
    message = (payload or {}).get("message", "")
    owner_ref = (payload or {}).get("owner_ref", "default_owner")

    async def token_generator() -> AsyncGenerator[str, None]:
        async for token in ProcessUserInput_stream(message, owner_ref):
            yield token

    return StreamingResponse(token_generator(), media_type="text/plain; charset=utf-8")


@router.get("/knowledge", response_class=HTMLResponse, summary="知识库管理")
async def knowledge_page(request: Request):
    return templates.TemplateResponse("knowledge_management.html", _context(request, active="knowledge"))


@router.get("/technician", response_class=HTMLResponse, summary="技师管理")
async def technician_page(request: Request):
    return templates.TemplateResponse("technician.html", _context(request, active="technician"))


@router.get("/bay", response_class=HTMLResponse, summary="工位管理")
async def bay_page(request: Request):
    return templates.TemplateResponse("bay_management.html", _context(request, active="bay"))


@router.get("/schedule", response_class=HTMLResponse, summary="车间排班看板")
async def schedule_page(request: Request):
    return templates.TemplateResponse("schedule_board.html", _context(request, active="schedule"))


@router.get("/vehicle", response_class=HTMLResponse, summary="车辆档案")
async def vehicle_page(request: Request):
    return templates.TemplateResponse("vehicle_archive.html", _context(request, active="vehicle"))


@router.get("/behavior", response_class=HTMLResponse, summary="车主行为分析")
async def behavior_page(request: Request):
    return templates.TemplateResponse(
        "vehicle_behavior_analysis.html", _context(request, active="behavior")
    )