"""预约 Agent 的端到端测试（全程不调用大模型，走规则兜底）。"""

from __future__ import annotations

from datetime import timedelta

from agents.service_booking import InputParser
from agents.service_booking_agent import ServiceBookingAgent
from config.time_config import time_config
from services.scheduling_service import SchedulingService
from services.technician_service import TechnicianService
from services.work_order_service import WorkOrderService


def collect(agent, message: str) -> str:
    import asyncio

    async def run() -> str:
        chunks = []
        async for token in agent.run_stream(message):
            chunks.append(token)
        return "".join(chunks)

    return asyncio.run(run())


def tomorrow_text(hour: int = 10) -> str:
    return time_config.now() + timedelta(days=1), hour


def test_input_parser_rules_extract_booking_fields():
    parser = InputParser(None)
    parsed = parser.parse_rules("明天上午10点，京A12345，换机油，我的车跑了4万公里")

    assert parsed["plate_no"] == "京A12345"
    assert parsed["item_codes"] == ["oil_change"]
    assert parsed["mileage"] == 40000
    assert parsed["start_time"].endswith("10:00")


async def test_booking_flow_creates_order():
    agent = ServiceBookingAgent()
    chunks = []
    async for token in agent.run_stream("明天上午10点，京A12345，换机油"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "预约成功" in reply
    assert "工单号" in reply

    orders = WorkOrderService().db.work_orders.list_orders(limit=10)
    assert len(orders) == 1
    assert orders[0]["item_codes"] == ["oil_change"]


async def test_booking_asks_for_missing_time_then_books():
    agent = ServiceBookingAgent()

    first = []
    async for token in agent.run_stream("京A12346 想换个机油"):
        first.append(token)
    assert "什么时候" in "".join(first)
    assert WorkOrderService().db.work_orders.count_active() == 0

    second = []
    async for token in agent.run_stream("明天下午3点"):
        second.append(token)
    assert "预约成功" in "".join(second)


async def test_booking_offers_alternatives_when_technician_busy():
    service = WorkOrderService()
    technician = TechnicianService().get_by_name("张伟")
    start = (time_config.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    service.create_work_order(
        ["oil_change"], start, plate_no="京A12347", technician_id=technician["id"], owner_ref="default_owner"
    )

    agent = ServiceBookingAgent()
    chunks = []
    async for token in agent.run_stream("明天上午10点，京A12347，找张伟技师换机油"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "预约成功" not in reply
    assert "空档" in reply or "可以安排" in reply


async def test_agent_books_multi_bay_order_across_two_bays():
    agent = ServiceBookingAgent()
    chunks = []
    async for token in agent.run_stream("明天上午10点，京A12348，换轮胎再做四轮定位"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "预约成功" in reply
    assert "→" in reply  # 提示需要跨工位作业

    order = WorkOrderService().db.work_orders.list_orders(limit=5)[0]
    assert order["item_codes"] == ["tire_change", "wheel_alignment"]
    assert len(order["bay_plan"]) == 2
    assert order["bay_plan"][0]["bay_type"] == "举升机工位"
    assert order["bay_plan"][1]["bay_type"] == "四轮定位工位"