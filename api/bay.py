"""工位管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from config.constants import SERVICE_BAY_TYPES
from config.time_config import time_config
from services.bay_service import BayService

from .core.response_models import BayRequest, DataResponse

router = APIRouter(prefix="/api/bays", tags=["工位管理"])


@router.get("", response_model=DataResponse, summary="工位列表")
async def list_bays(bay_type: str | None = None, active_only: bool = True):
    service = BayService()
    service.initialize_default_bays()
    return DataResponse(message="ok", data=service.list_bays(bay_type=bay_type, active_only=active_only))


@router.get("/types", response_model=DataResponse, summary="工位类型可选项")
async def bay_types():
    return DataResponse(message="ok", data=SERVICE_BAY_TYPES)


@router.get("/schedules/today", response_model=DataResponse, summary="今日工位占用")
async def schedules_today():
    service = BayService()
    service.initialize_default_bays()
    today = time_config.now()
    result = []
    for bay in service.list_bays():
        result.append(
            {
                **bay,
                "busy_periods": [
                    {
                        "start": item["start"].strftime("%H:%M"),
                        "end": item["end"].strftime("%H:%M"),
                        "order_no": item["order_no"],
                    }
                    for item in service.busy_periods(bay["id"], today)
                ],
            }
        )
    return DataResponse(message="ok", data=result)


@router.get("/{bay_id}", response_model=DataResponse, summary="工位详情")
async def get_bay(bay_id: int):
    bay = BayService().get_bay(bay_id)
    if not bay:
        raise HTTPException(status_code=404, detail="工位不存在")
    return DataResponse(message="ok", data=bay)


@router.post("", response_model=DataResponse, summary="新增工位")
async def create_bay(request: BayRequest):
    service = BayService()
    bay_id = service.add_bay(request.name, request.bay_type, request.equipment)
    return DataResponse(message="已新增", data={"id": bay_id})


@router.put("/{bay_id}", response_model=DataResponse, summary="更新工位")
async def update_bay(bay_id: int, request: BayRequest):
    service = BayService()
    success = service.update_bay(bay_id, **request.model_dump(exclude_none=True))
    if not success:
        raise HTTPException(status_code=404, detail="工位不存在")
    return DataResponse(message="已更新", data=service.get_bay(bay_id))


@router.delete("/{bay_id}", response_model=DataResponse, summary="停用工位")
async def delete_bay(bay_id: int):
    success = BayService().remove_bay(bay_id)
    if not success:
        raise HTTPException(status_code=404, detail="工位不存在")
    return DataResponse(message="已停用", data={"id": bay_id})