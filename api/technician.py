"""技师管理接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from config.constants import CERTIFICATIONS, SHIFT_NAMES
from config.time_config import time_config
from services.technician_service import TechnicianService

from .core.response_models import DataResponse, TechnicianRequest

router = APIRouter(prefix="/api/technicians", tags=["技师管理"])


@router.get("", response_model=DataResponse, summary="技师列表")
async def list_technicians(active_only: bool = True):
    service = TechnicianService()
    service.initialize_default_technicians()
    return DataResponse(message="ok", data=service.list_technicians(active_only=active_only))


@router.get("/options", response_model=DataResponse, summary="资质与班次可选项")
async def options():
    return DataResponse(message="ok", data={"certifications": CERTIFICATIONS, "shifts": SHIFT_NAMES})


@router.get("/schedules/today", response_model=DataResponse, summary="今日技师排班")
async def schedules_today():
    service = TechnicianService()
    service.initialize_default_technicians()
    today = time_config.now()
    result = []
    for technician in service.list_technicians():
        result.append(
            {
                "technician_id": technician["id"],
                "technician_name": technician["name"],
                "shift": technician["shift"],
                "busy_periods": [
                    {
                        "start": item["start"].strftime("%H:%M"),
                        "end": item["end"].strftime("%H:%M"),
                        "order_no": item["order_no"],
                    }
                    for item in service.busy_periods(technician["id"], today)
                ],
            }
        )
    return DataResponse(message="ok", data=result)


@router.get("/{technician_id}", response_model=DataResponse, summary="技师详情")
async def get_technician(technician_id: int):
    technician = TechnicianService().get_technician(technician_id)
    if not technician:
        raise HTTPException(status_code=404, detail="技师不存在")
    return DataResponse(message="ok", data=technician)


@router.post("", response_model=DataResponse, summary="新增技师")
async def create_technician(request: TechnicianRequest):
    service = TechnicianService()
    technician_id = service.add_technician(request.name, **request.model_dump(exclude={"name"}, exclude_none=True))
    return DataResponse(message="已新增", data={"id": technician_id})


@router.put("/{technician_id}", response_model=DataResponse, summary="更新技师")
async def update_technician(technician_id: int, request: TechnicianRequest):
    service = TechnicianService()
    success = service.update_technician(
        technician_id, **request.model_dump(exclude_none=True)
    )
    if not success:
        raise HTTPException(status_code=404, detail="技师不存在")
    return DataResponse(message="已更新", data=service.get_technician(technician_id))


@router.delete("/{technician_id}", response_model=DataResponse, summary="停用技师")
async def delete_technician(technician_id: int):
    success = TechnicianService().remove_technician(technician_id)
    if not success:
        raise HTTPException(status_code=404, detail="技师不存在")
    return DataResponse(message="已停用", data={"id": technician_id})