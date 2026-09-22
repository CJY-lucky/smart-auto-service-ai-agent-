"""任务分类接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agents.task_classification_agent import TaskClassificationAgent

from .chat_handler import get_agents
from .core.response_models import DataResponse, TaskClassificationRequest

router = APIRouter(prefix="/api/task", tags=["任务分类"])


@router.post("/classify", response_model=DataResponse, summary="判断车主意图类别")
async def classify_task(request: TaskClassificationRequest):
    try:
        agents = get_agents()
        agent: TaskClassificationAgent = agents["task"]
        result = await agent.classify_task(request.text)
        return DataResponse(message="分类完成", data=result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/state", response_model=DataResponse, summary="查看当前对话状态")
async def get_state():
    agents = get_agents()
    return DataResponse(message="ok", data=agents["task"].get_classification_info())