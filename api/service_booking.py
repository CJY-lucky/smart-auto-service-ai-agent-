"""预约工单接口。

这是对外提供"确定性排班能力"的地方：即使不经过大模型，
调用方也能拿到可行性判断、冲突原因与备选时段。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from config.time_config import time_config
from services.scheduling_service import SchedulingService
from services.work_order_service import WorkOrderService

from .core.response_models import (
    BookingRequest,
    CompleteRequest,
    DataResponse,
    QuoteRequest,
    RescheduleRequest,
)

router = APIRouter(prefix="/api/service-booking", tags=["预约工单"])


def _service() -> WorkOrderService:
    return WorkOrderService()


@router.post("/quote", response_model=DataResponse, summary="试算工时、金额与可行性")
async def quote(request: QuoteRequest):
    try:
        scheduling = SchedulingService()
        start_time = time_config.parse_datetime(request.start_time)
        if start_time is None:
            raise HTTPException(status_code=400, detail="时间格式无法识别，请使用 YYYY-MM-DD HH:MM")

        technician_id = request.technician_id
        if technician_id is None and request.technician_name:
            technician = scheduling.technician_service.get_by_name(request.technician_name)
            technician_id = technician["id"] if technician else None

        result = scheduling.find_solution(
            request.item_codes,
            start_time,
            technician_id=technician_id,
            preference=request.preference,
        )
        data = {
            "feasible": result.feasible,
            "plan": result.plan.to_dict(),
            "reasons": result.reasons,
            "reason_texts": result.reason_texts,
            "message": SchedulingService.describe(result),
            "solution": result.solution.to_dict() if result.solution else None,
            "suggestions": [solution.to_dict() for solution in result.suggestions],
        }
        return DataResponse(message="试算完成", data=data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/orders", response_model=DataResponse, summary="创建预约工单")
async def create_order(request: BookingRequest):
    try:
        start_time = time_config.parse_datetime(request.start_time)
        if start_time is None:
            raise HTTPException(status_code=400, detail="时间格式无法识别，请使用 YYYY-MM-DD HH:MM")

        outcome = _service().create_work_order(
            request.item_codes,
            start_time,
            owner_ref=request.owner_ref,
            plate_no=request.plate_no,
            vehicle_model=request.vehicle_model,
            mileage=request.mileage,
            oil_spec=request.oil_spec,
            technician_id=request.technician_id,
            bay_id=request.bay_id,
            preference=request.preference,
            notes=request.notes,
            session_id=request.session_id,
        )
        if not outcome.get("success"):
            return DataResponse(
                message=outcome.get("message", "排期失败"),
                success=False,
                data={
                    "reasons": outcome["result"].reasons,
                    "suggestions": [solution.to_dict() for solution in outcome["result"].suggestions],
                },
            )
        return DataResponse(
            message="预约成功",
            data={
                "order": _serialize_order(outcome["order"]),
                "solution": outcome["result"].solution.to_dict(),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/orders", response_model=DataResponse, summary="查询工单列表")
async def list_orders(
    owner_ref: Optional[str] = None,
    status: Optional[str] = Query(default=None),
    day: Optional[str] = None,
    limit: int = 50,
):
    try:
        target_day = time_config.parse_datetime(day) if day else None
        orders = _service().db.work_orders.list_orders(
            status=status, day=target_day, limit=limit
        )
        if owner_ref:
            owner = _service().db.owners.get_by_ref(owner_ref)
            orders = [order for order in orders if owner and order["owner_id"] == owner["id"]]
        return DataResponse(message="ok", data=[_serialize_order(order) for order in orders])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/orders/{order_id}", response_model=DataResponse, summary="查询工单详情")
async def get_order(order_id: int):
    service = _service()
    order = service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    data = _serialize_order(order)
    data["items"] = service.db.work_orders.list_items(order_id)
    return DataResponse(message="ok", data=data)


@router.post("/orders/{order_id}/reschedule", response_model=DataResponse, summary="改约")
async def reschedule_order(order_id: int, request: RescheduleRequest):
    start_time = time_config.parse_datetime(request.start_time)
    if start_time is None:
        raise HTTPException(status_code=400, detail="时间格式无法识别")
    outcome = _service().reschedule(
        order_id, start_time, technician_id=request.technician_id, bay_id=request.bay_id
    )
    if not outcome.get("success"):
        result = outcome.get("result")
        return DataResponse(
            message=outcome.get("message", "改约失败"),
            success=False,
            data={
                "reasons": result.reasons if result else [],
                "suggestions": [solution.to_dict() for solution in result.suggestions] if result else [],
            },
        )
    return DataResponse(message="改约成功", data=_serialize_order(outcome["order"]))


@router.post("/orders/{order_id}/cancel", response_model=DataResponse, summary="取消工单")
async def cancel_order(order_id: int):
    outcome = _service().cancel(order_id)
    if not outcome.get("success"):
        raise HTTPException(status_code=404, detail=outcome.get("message", "工单不存在"))
    return DataResponse(message="已取消", data=_serialize_order(outcome["order"]))


@router.post("/orders/{order_id}/complete", response_model=DataResponse, summary="完成工单")
async def complete_order(order_id: int, request: CompleteRequest):
    outcome = _service().complete(order_id, mileage=request.mileage, amount=request.amount)
    if not outcome.get("success"):
        raise HTTPException(status_code=404, detail=outcome.get("message", "工单不存在"))
    return DataResponse(message="已完成", data=_serialize_order(outcome["order"]))


@router.post("/slots", response_model=DataResponse, summary="推荐可预约时段")
async def suggest_slots(request: QuoteRequest):
    start_time = time_config.parse_datetime(request.start_time)
    if start_time is None:
        raise HTTPException(status_code=400, detail="时间格式无法识别")
    technician_id = request.technician_id
    if technician_id is None and request.technician_name:
        technician = SchedulingService().technician_service.get_by_name(request.technician_name)
        technician_id = technician["id"] if technician else None
    suggestions = SchedulingService().suggest_slots(
        request.item_codes, start_time, technician_id=technician_id, limit=3
    )
    return DataResponse(message="ok", data=[solution.to_dict() for solution in suggestions])


@router.get("/board", response_model=DataResponse, summary="车间排班看板数据")
async def schedule_board(day: Optional[str] = None):
    target_day = time_config.parse_datetime(day) if day else time_config.now()
    board = SchedulingService().day_board(target_day)
    board["orders"] = [_serialize_order(order) for order in board["orders"]]
    return DataResponse(message="ok", data=board)


@router.get("/statistics", response_model=DataResponse, summary="工单统计")
async def statistics():
    return DataResponse(message="ok", data=_service().statistics())


def _serialize_order(order: dict) -> dict:
    """把 datetime 转成字符串，供 JSON 返回。"""

    if not order:
        return {}
    data = dict(order)
    for key in ("start_time", "end_time", "created_at", "updated_at", "completed_at"):
        value = data.get(key)
        if value is not None and hasattr(value, "strftime"):
            data[key] = time_config.format_datetime(value)
    return data