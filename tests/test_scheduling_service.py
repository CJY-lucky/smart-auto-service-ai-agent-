"""双资源排班内核的测试——这是整个项目最需要被测试保护的部分。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config.time_config import time_config
from services.scheduling_service import ConflictReason, SchedulingService
from services.technician_service import TechnicianService
from services.work_order_service import WorkOrderService


def tomorrow_at(hour: int, minute: int = 0):
    base = time_config.now() + timedelta(days=1)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


@pytest.fixture()
def technicians():
    service = TechnicianService()
    return {item["name"]: item for item in service.list_technicians()}


def test_solution_locks_technician_and_bay(technicians):
    scheduling = SchedulingService()
    start = tomorrow_at(10)

    result = scheduling.find_solution(["oil_change"], start)

    assert result.feasible is True
    assert result.solution is not None
    assert result.solution.technician["id"]
    assert result.solution.bay["bay_type"] in ("举升机工位", "快修工位")
    assert result.solution.duration_minutes == 40


def test_occupied_technician_is_reported_as_conflict(technicians):
    scheduling = SchedulingService()
    orders = WorkOrderService()
    start = tomorrow_at(10)
    technician = technicians["张伟"]

    outcome = orders.create_work_order(
        ["oil_change"], start, plate_no="京A00001", technician_id=technician["id"], owner_ref="test_owner"
    )
    assert outcome["success"] is True

    result = scheduling.find_solution(["oil_change"], start, technician_id=technician["id"])
    assert result.feasible is False
    assert ConflictReason.TECHNICIAN_BUSY.value in result.reasons
    # 必须给出备选时段，而不是只说"不行"
    assert result.suggestions
    assert all(slot.technician["id"] == technician["id"] for slot in result.suggestions)


def test_occupied_bay_is_reported_as_conflict(technicians):
    scheduling = SchedulingService()
    orders = WorkOrderService()
    start = tomorrow_at(10)
    first = scheduling.find_solution(["oil_change"], start)
    bay_id = first.solution.bay["id"]

    orders.create_work_order(
        ["oil_change"], start, plate_no="京A00002", bay_id=bay_id, technician_id=first.solution.technician["id"]
    )

    other_technician = technicians["王强"]
    result = scheduling.find_solution(
        ["oil_change"], start, bay_id=bay_id, technician_id=other_technician["id"]
    )
    assert result.feasible is False
    assert ConflictReason.BAY_BUSY.value in result.reasons


def test_adjacent_slots_do_not_conflict(technicians):
    scheduling = SchedulingService()
    orders = WorkOrderService()
    start = tomorrow_at(10)
    technician = technicians["张伟"]
    bay_id = scheduling.find_solution(["oil_change"], start, technician_id=technician["id"]).solution.bay["id"]

    orders.create_work_order(
        ["oil_change"], start, plate_no="京A00003", technician_id=technician["id"], bay_id=bay_id
    )

    # 10:40 开始正好接上 10:00-10:40 的工单
    result = scheduling.find_solution(
        ["oil_change"], start + timedelta(minutes=40), technician_id=technician["id"], bay_id=bay_id
    )
    assert result.feasible is True


def test_technician_without_certification_is_rejected(technicians):
    scheduling = SchedulingService()
    result = scheduling.find_solution(["paint"], tomorrow_at(10), technician_id=technicians["孙丽"]["id"])

    assert result.feasible is False
    assert ConflictReason.TECHNICIAN_NOT_QUALIFIED.value in result.reasons


def test_paint_requires_paint_bay(technicians):
    scheduling = SchedulingService()
    result = scheduling.find_solution(["paint"], tomorrow_at(10))

    assert result.feasible is True
    assert result.solution.bay["bay_type"] == "钣喷房"
    assert result.solution.technician["name"] == "郑斌"


def test_outside_business_hours_is_rejected(technicians):
    scheduling = SchedulingService()
    result = scheduling.find_solution(["oil_change"], tomorrow_at(21, 30))

    assert result.feasible is False
    assert ConflictReason.OUTSIDE_BUSINESS_HOURS.value in result.reasons


def test_multi_bay_order_assigns_each_segment_its_own_bay():
    scheduling = SchedulingService()
    start = tomorrow_at(10)

    result = scheduling.find_solution(["tire_change", "wheel_alignment"], start)

    assert result.feasible is True
    solution = result.solution
    assert [segment["bay"]["bay_type"] for segment in solution.segments] == ["举升机工位", "四轮定位工位"]
    # 换胎 60 分钟 + 转移 5 分钟 + 四轮定位 60 分钟
    assert solution.duration_minutes == 125
    assert set(solution.bay_names) == {"举升机工位A", "四轮定位工位"}


def test_day_board_lists_technicians_bays_and_orders():
    scheduling = SchedulingService()
    start = tomorrow_at(14)
    WorkOrderService().create_work_order(["oil_change"], start, plate_no="京A00009", owner_ref="test_owner")

    board = scheduling.day_board(start)

    assert board["technicians"]
    assert board["bays"]
    assert len(board["orders"]) == 1
    assert board["orders"][0]["plate_no"] == "京A00009"