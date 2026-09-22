"""知识库管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.knowledge_service import KnowledgeService

from .core.response_models import DataResponse, KnowledgeRequest, KnowledgeSearchRequest

router = APIRouter(prefix="/api/knowledge", tags=["知识库管理"])


async def _service() -> KnowledgeService:
    service = KnowledgeService()
    await service.initialize()
    return service


@router.get("", response_model=DataResponse, summary="知识库列表")
async def list_knowledge():
    service = await _service()
    documents = service.get_all_documents()
    return DataResponse(
        message="ok",
        data={
            "documents": documents,
            "categories": service.get_all_categories(),
            "total_count": len(documents),
        },
    )


@router.get("/categories", response_model=DataResponse, summary="知识分类")
async def list_categories():
    service = await _service()
    return DataResponse(message="ok", data=service.get_all_categories())


@router.get("/{doc_id}", response_model=DataResponse, summary="知识详情")
async def get_knowledge(doc_id: int):
    service = await _service()
    document = service.get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return DataResponse(message="ok", data=document)


@router.post("", response_model=DataResponse, summary="新增知识")
async def create_knowledge(request: KnowledgeRequest):
    service = await _service()
    doc_id = await service.add_document(request.content, request.category, request.keywords)
    return DataResponse(message="已新增", data={"id": doc_id})


@router.put("/{doc_id}", response_model=DataResponse, summary="更新知识")
async def update_knowledge(doc_id: int, request: KnowledgeRequest):
    service = await _service()
    success = await service.update_document(
        doc_id, content=request.content, category=request.category, keywords=request.keywords
    )
    if not success:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return DataResponse(message="已更新", data=service.get_document(doc_id))


@router.delete("/{doc_id}", response_model=DataResponse, summary="删除知识")
async def delete_knowledge(doc_id: int):
    service = await _service()
    success = await service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return DataResponse(message="已删除", data={"id": doc_id})


@router.post("/search", response_model=DataResponse, summary="检索知识库")
async def search_knowledge(request: KnowledgeSearchRequest):
    service = await _service()
    documents = await service.search(request.query, top_k=request.top_k)
    return DataResponse(message="ok", data=documents)