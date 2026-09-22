"""咨询服务接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .chat_handler import get_agents
from .core.response_models import ConsultationRequest, DataResponse

router = APIRouter(prefix="/api/consultation", tags=["知识咨询"])


@router.post("/ask", response_model=DataResponse, summary="提问保养相关问题")
async def ask_consultation(request: ConsultationRequest):
    try:
        agents = get_agents()
        answer = await agents["consultant"].consult(request.question, owner_ref=request.owner_ref)
        return DataResponse(
            message="咨询完成",
            data={"question": request.question, "answer": answer},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/search", response_model=DataResponse, summary="直接检索知识库")
async def search_knowledge(request: ConsultationRequest):
    from services.knowledge_service import KnowledgeService

    try:
        service = KnowledgeService()
        await service.initialize()
        documents = await service.search(request.question, top_k=3)
        return DataResponse(message="检索完成", data=documents)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))