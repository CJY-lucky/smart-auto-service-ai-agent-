"""时间基准与项目目录的单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

from config.service_catalog import SERVICE_ITEMS, resolve_item_code
from config.time_config import TimeWindow, time_config
from services.scheduling_service import SchedulingService


def test_time_window_overlap_is_half_open():
    start = datetime(2026, 3, 2, 10, 0)
    first = TimeWindow(start, start + timedelta(minutes=40))
    second = TimeWindow(start + timedelta(minutes=40), start + timedelta(minutes=80))

    # 首尾相接不算冲突，这是排班最容易写错的地方
    assert first.overlaps(second) is False
    assert second.overlaps(first) is False
    assert first.overlaps(TimeWindow(start + timedelta(minutes=39), start + timedelta(minutes=60))) is True


def test_parse_datetime_accepts_common_formats():
    assert time_config.parse_datetime("2026-03-02 10:30") == datetime(2026, 3, 2, 10, 30)
    assert time_config.parse_datetime("2026-03-02 10:30:00") == datetime(2026, 3, 2, 10, 30)
    assert time_config.parse_datetime("2026/03/02 10:30") == datetime(2026, 3, 2, 10, 30)
    assert time_config.parse_datetime("2026-03-02") == datetime(2026, 3, 2, 0, 0)
    assert time_config.parse_datetime("看不懂") is None


def test_ceil_to_slot_aligns_up():
    assert time_config.ceil_to_slot(datetime(2026, 3, 2, 10, 0)) == datetime(2026, 3, 2, 10, 0)
    assert time_config.ceil_to_slot(datetime(2026, 3, 2, 10, 7)) == datetime(2026, 3, 2, 10, 30)


def test_shift_window_is_intersected_with_business_hours():
    day = datetime(2026, 3, 2)
    morning = time_config.shift_window(day, "早班")
    evening = time_config.shift_window(day, "晚班")
    assert (morning.start.hour, morning.end.hour) == (9, 18)
    assert (evening.start.hour, evening.end.hour) == (11, 20)


def test_resolve_item_code_from_口语():
    assert resolve_item_code("换个机油") == "oil_change"
    assert resolve_item_code("四轮定位") == "wheel_alignment"
    assert resolve_item_code("刹车片") == "brake_pad"
    assert resolve_item_code("说不清楚") is None


def test_workload_orders_items_by_dependency():
    service = SchedulingService()
    plan = service.estimate_workload(["wheel_alignment", "tire_change"])

    # 四轮定位依赖换胎，必须先做换胎
    assert plan.item_codes == ["tire_change", "wheel_alignment"]
    assert [segment["item_code"] for segment in plan.segments] == ["tire_change", "wheel_alignment"]

    # 两个项目没有可共用的工位类型，中间要计入挪车转移时间
    assert plan.transfer_minutes == 5
    assert plan.segments[1]["transfer_before"] is True
    assert plan.total_minutes == (
        SERVICE_ITEMS["tire_change"].duration_minutes
        + 5
        + SERVICE_ITEMS["wheel_alignment"].duration_minutes
    )
    assert plan.need_split is False


def test_workload_keeps_no_transfer_when_bays_overlap():
    service = SchedulingService()
    plan = service.estimate_workload(["oil_change", "air_filter"])

    # 机油和空气滤芯都能在举升机/快修工位完成，不需要挪车
    assert plan.transfer_minutes == 0
    assert set(plan.bay_type_options) == {"举升机工位", "快修工位"}