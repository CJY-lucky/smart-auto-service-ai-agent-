"""车辆档案接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from config.time_config import time_config
from services.vehicle_service import VehicleService

from .core.response_models import DataResponse, VehicleRequest

router = APIRouter(prefix="/api/vehicles", tags=["车辆档案"])


def _serialize_vehicle(vehicle: dict) -> dict:
    data = dict(vehicle)
    for key in ("last_service_date", "purchase_date", "created_at", "updated_at"):
        value = data.get(key)
        if value is not None and hasattr(value, "strftime"):
            data[key] = time_config.format_datetime(value)
    return data


@router.get("", response_model=DataResponse, summary="车辆档案列表")
async def list_vehicles(owner_ref: Optional[str] = None):
    service = VehicleService()
    if owner_ref:
        owner = service.db.owners.get_by_ref(owner_ref)
        vehicles = service.list_by_owner(owner["id"]) if owner else []
    else:
        vehicles = service.list_vehicles()
    return DataResponse(message="ok", data=[_serialize_vehicle(item) for item in vehicles])


@router.get("/owners", response_model=DataResponse, summary="车主列表")
async def list_owners():
    return DataResponse(message="ok", data=VehicleService().db.owners.list_owners())


@router.get("/{vehicle_id}", response_model=DataResponse, summary="车辆详情")
async def get_vehicle(vehicle_id: int):
    service = VehicleService()
    vehicle = service.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")
    data = _serialize_vehicle(vehicle)
    data["due_items"] = service.due_items(vehicle)
    estimate = service.next_service_estimate(vehicle)
    if estimate and estimate.get("next_date") is not None:
        estimate["next_date"] = time_config.format_datetime(estimate["next_date"], "%Y-%m-%d")
    data["next_service"] = estimate
    data["cycle_triggers"] = service.cycle_trigger_points(vehicle)
    return DataResponse(message="ok", data=data)


@router.post("", response_model=DataResponse, summary="新增/更新车辆档案")
async def create_vehicle(request: VehicleRequest):
    service = VehicleService()
    owner_id = service.ensure_owner(request.owner_ref, request.owner_name)
    payload = request.model_dump(exclude={"owner_ref", "owner_name", "plate_no"}, exclude_none=True)
    for key in ("last_service_date", "purchase_date"):
        if payload.get(key):
            payload[key] = time_config.parse_datetime(payload[key])
    vehicle_id = service.ensure_vehicle(owner_id, request.plate_no, **payload)
    return DataResponse(
        message="已保存",
        data=_serialize_vehicle(service.get_vehicle(vehicle_id)),
    )


@router.put("/{vehicle_id}", response_model=DataResponse, summary="更新车辆档案")
async def update_vehicle(vehicle_id: int, request: VehicleRequest):
    service = VehicleService()
    payload = request.model_dump(exclude={"owner_ref", "owner_name", "plate_no"}, exclude_none=True)
    for key in ("last_service_date", "purchase_date"):
        if payload.get(key):
            payload[key] = time_config.parse_datetime(payload[key])
    if request.plate_no:
        payload["plate_no"] = request.plate_no
    success = service.update_vehicle(vehicle_id, **payload)
    if not success:
        raise HTTPException(status_code=404, detail="车辆不存在")
    return DataResponse(message="已更新", data=_serialize_vehicle(service.get_vehicle(vehicle_id)))


@router.get("/{vehicle_id}/reminders", response_model=DataResponse, summary="车辆到期项目与提醒")
async def vehicle_reminders(vehicle_id: int):
    service = VehicleService()
    vehicle = service.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="车辆不存在")
    return DataResponse(
        message="ok",
        data={
            "due_items": service.due_items(vehicle),
            "next_service": service.next_service_estimate(vehicle),
            "triggers": service.cycle_trigger_points(vehicle),
        },
    )