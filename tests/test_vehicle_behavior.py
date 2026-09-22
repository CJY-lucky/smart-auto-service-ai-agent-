"""车辆档案周期推理与车主行为分析测试。"""

from __future__ import annotations

from datetime import timedelta

from config.time_config import time_config
from services.vehicle_behavior_service import VehicleBehaviorService
from services.vehicle_service import VehicleService
from services.work_order_service import WorkOrderService
from agents.vehicle_behavior_agent import VehicleBehaviorAgent


def make_vehicle(plate: str = "京E30001", owner_ref: str = "default_owner"):
    service = VehicleService()
    owner_id = service.ensure_owner(owner_ref)
    now = time_config.now()
    vehicle_id = service.ensure_vehicle(
        owner_id,
        plate,
        model="卡罗拉",
        year=2020,
        mileage=42000,
        last_service_mileage=32000,
        last_service_date=now - timedelta(days=300),
        purchase_date=now - timedelta(days=1500),
    )
    return service.get_vehicle(vehicle_id)


def test_due_items_by_mileage_and_time():
    vehicle = make_vehicle("京E30002")
    service = VehicleService()

    due = service.due_items(vehicle)
    codes = [item["item_code"] for item in due]

    assert "oil_change" in codes
    assert all(item["reasons"] for item in due)


def test_next_service_estimate():
    vehicle = make_vehicle("京E30003")
    estimate = VehicleService().next_service_estimate(vehicle)

    assert estimate["next_mileage"] == 42000
    assert estimate["remaining_km"] == 0
    assert estimate["next_date"] is not None


def test_cycle_trigger_points_include_inspection_and_brake():
    vehicle = make_vehicle("京E30004")
    triggers = VehicleService().cycle_trigger_points(vehicle)
    types = {item["type"] for item in triggers}

    assert "inspection" in types
    assert "brake_pad" in types


def test_behavior_analysis_finds_favorite_technician():
    vehicle = make_vehicle("京E30005")
    service = WorkOrderService()
    start = (time_config.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)

    outcome = service.create_work_order(
        ["oil_change"], start, plate_no=vehicle["plate_no"], owner_ref="default_owner"
    )
    assert outcome["success"] is True

    analysis = VehicleBehaviorService().analyze("default_owner")
    assert analysis["total_appointments"] == 1
    assert analysis["favorite_technician_id"] == outcome["order"]["technician_id"]
    assert analysis["favorite_service"] == "oil_change"
    assert analysis["due_reminders"]


def test_reminder_message_contains_slots():
    vehicle = make_vehicle("京E30006", owner_ref="behavior_test_owner")
    agent = VehicleBehaviorAgent()

    result = agent.get_reminder_with_schedule("behavior_test_owner")

    assert result["vehicle"]["plate_no"] == vehicle["plate_no"]
    assert vehicle["plate_no"] in result["message"]
    assert result["due_items"]
    assert isinstance(result["available_slots"], list)