"""车主行为分析与提醒接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.recommendation_service import RecommendationService
from services.vehicle_behavior_service import VehicleBehaviorService

from .core.response_models import DataResponse, ReminderRequest, VehicleRequest

router = APIRouter(prefix="/api/vehicle-behavior", tags=["车主行为分析"])
router_underscore = APIRouter(prefix="/api/vehicle_behavior", tags=["车主行为分析"])


async def _analysis(owner_ref: str) -> dict:
    service = VehicleBehaviorService()
    analysis = service.analyze(owner_ref)
    analysis.pop("behaviors", None)
    return analysis


@router.get("/analysis", response_model=DataResponse, summary="车主行为分析")
async def get_analysis(owner_ref: str = "default_owner"):
    try:
        return DataResponse(message="ok", data=await _analysis(owner_ref))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/dashboard_data", response_model=DataResponse, summary="行为分析看板数据")
async def dashboard_data(owner_ref: str = "default_owner"):
    return DataResponse(message="ok", data=await _analysis(owner_ref))


@router.get("/behaviors", response_model=DataResponse, summary="行为流水")
async def behaviors(owner_ref: str = "default_owner", limit: int = 100):
    return DataResponse(message="ok", data=VehicleBehaviorService().get_behaviors(owner_ref, limit=limit))


@router.get("/preferences", response_model=DataResponse, summary="车主偏好")
async def preferences(owner_ref: str = "default_owner"):
    return DataResponse(message="ok", data=VehicleBehaviorService().db.behaviors.get_preferences(owner_ref))


@router.get("/reminders", response_model=DataResponse, summary="提醒列表")
async def reminders(owner_ref: str = "default_owner", pending_only: bool = False):
    return DataResponse(
        message="ok",
        data=VehicleBehaviorService().db.behaviors.get_reminders(owner_ref, pending_only=pending_only),
    )


@router.post("/send-reminder", response_model=DataResponse, summary="生成带档期的回访提醒")
async def send_reminder(request: ReminderRequest):
    try:
        result = VehicleBehaviorService().get_reminder_with_schedule(
            request.owner_ref, include_weather=request.include_weather
        )
        return DataResponse(message="ok", data=result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate-reminders", response_model=DataResponse, summary="立即生成提醒（不发送）")
async def generate_reminders(force: bool = False):
    created = RecommendationService().generate_reminders(force=force)
    return DataResponse(message=f"生成 {len(created)} 条提醒", data=created)


@router_underscore.get("/dashboard_data", response_model=DataResponse, summary="行为分析看板数据（下划线兼容）")
async def dashboard_data_underscore(owner_ref: str = "default_owner"):
    return DataResponse(message="ok", data=await _analysis(owner_ref))