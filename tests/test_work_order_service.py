"""工单生命周期测试：创建、并发保护、取消、完成回写档案。"""

from __future__ import annotations

from datetime import timedelta

from config.time_config import time_config
from services.scheduling_service import SchedulingService
from services.technician_service import TechnicianService
from services.vehicle_service import VehicleService
from services.work_order_service import WorkOrderService


def tomorrow_at(hour: int, minute: int = 0):
    base = time_config.now() + timedelta(days=1)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_create_work_order_creates_vehicle_profile():
    service = WorkOrderService()
    start = tomorrow_at(10)

    outcome = service.create_work_order(
        ["oil_change"], start, plate_no="京C10001", vehicle_model="卡罗拉", mileage=32000
    )

    assert outcome["success"] is True
    order = outcome["order"]
    assert order["status"] == "created"
    assert order["item_codes"] == ["oil_change"]
    assert order["start_time"] == start

    vehicle = VehicleService().get_by_plate("京C10001")
    assert vehicle is not None
    assert vehicle["mileage"] == 32000
    assert vehicle["model"] == "卡罗拉"


def test_double_booking_same_resources_is_rejected():
    service = WorkOrderService()
    scheduling = SchedulingService()
    technician = TechnicianService().get_by_name("张伟")
    start = tomorrow_at(11)
    bay_id = scheduling.find_solution(
        ["oil_change"], start, technician_id=technician["id"]
    ).solution.bay["id"]

    first = service.create_work_order(
        ["oil_change"], start, plate_no="京C10002", technician_id=technician["id"], bay_id=bay_id
    )
    second = service.create_work_order(
        ["oil_change"], start, plate_no="京C10003", technician_id=technician["id"], bay_id=bay_id
    )

    assert first["success"] is True
    assert second["success"] is False
    assert second["order"] is None
    assert service.db.work_orders.count_active() == 1


def test_cancel_releases_resources():
    service = WorkOrderService()
    start = tomorrow_at(15)
    created = service.create_work_order(["oil_change"], start, plate_no="京C10004")
    order_id = created["order"]["id"]

    assert service.db.work_orders.count_active() == 1
    service.cancel(order_id)

    assert service.db.work_orders.count_active() == 0
    assert service.db.work_orders.is_technician_available(
        created["order"]["technician_id"], start, start + timedelta(minutes=40)
    )


def test_reschedule_moves_order_to_new_slot():
    service = WorkOrderService()
    start = tomorrow_at(9)
    created = service.create_work_order(["oil_change"], start, plate_no="京C10005")

    new_start = tomorrow_at(16)
    outcome = service.reschedule(created["order"]["id"], new_start)

    assert outcome["success"] is True
    assert outcome["order"]["start_time"] == new_start


def test_complete_writes_back_to_vehicle_archive():
    service = WorkOrderService()
    start = tomorrow_at(9, 30)
    created = service.create_work_order(
        ["oil_change"], start, plate_no="京C10006", mileage=40000
    )

    outcome = service.complete(created["order"]["id"], mileage=40500)
    assert outcome["success"] is True

    vehicle = VehicleService().get_by_plate("京C10006")
    assert vehicle["mileage"] == 40500
    assert vehicle["last_service_mileage"] == 40500
    assert vehicle["last_service_date"] is not None


def test_order_no_is_unique():
    service = WorkOrderService()
    numbers = {service.generate_order_no() for _ in range(20)}
    assert len(numbers) == 20