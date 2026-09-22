"""接口层冒烟测试（含页面与确定性排班接口）。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import create_app
from config.time_config import time_config


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def tomorrow_str(hour: int = 10, minute: int = 0) -> str:
    moment = (time_config.now() + timedelta(days=1)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return time_config.format_datetime(moment)


def test_pages_are_served(client):
    for path in ["/", "/schedule", "/technician", "/bay", "/vehicle", "/behavior", "/knowledge"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "智保养" in response.text


def test_technician_and_bay_endpoints(client):
    technicians = client.get("/api/technicians").json()["data"]
    bays = client.get("/api/bays").json()["data"]

    assert any(item["name"] == "张伟" for item in technicians)
    assert any(item["bay_type"] == "举升机工位" for item in bays)
    assert any(item["bay_type"] == "四轮定位工位" for item in bays)


def test_quote_endpoint_returns_plan_and_solution(client):
    response = client.post(
        "/api/service-booking/quote",
        json={"item_codes": ["oil_change"], "start_time": tomorrow_str(10)},
    )
    payload = response.json()

    assert payload["success"] is True
    assert payload["data"]["feasible"] is True
    assert payload["data"]["plan"]["total_minutes"] == 40
    assert payload["data"]["solution"]["technician"]["name"]


def test_quote_plans_multi_bay_order(client):
    response = client.post(
        "/api/service-booking/quote",
        json={"item_codes": ["tire_change", "wheel_alignment"], "start_time": tomorrow_str(13)},
    )
    data = response.json()["data"]

    assert data["feasible"] is True
    assert data["plan"]["total_minutes"] == 125
    assert [segment["bay_type"] for segment in data["solution"]["segments"]] == ["举升机工位", "四轮定位工位"]


def test_create_and_list_order(client):
    created = client.post(
        "/api/service-booking/orders",
        json={
            "item_codes": ["oil_change"],
            "start_time": tomorrow_str(10),
            "plate_no": "京F60001",
            "owner_ref": "api_test_owner",
        },
    ).json()
    assert created["success"] is True
    order_no = created["data"]["order"]["order_no"]

    listed = client.get("/api/service-booking/orders?limit=20").json()["data"]
    assert any(item["order_no"] == order_no for item in listed)


def test_duplicate_booking_returns_alternatives(client):
    payload = {
        "item_codes": ["oil_change"],
        "start_time": tomorrow_str(10),
        "plate_no": "京F60002",
        "technician_id": 1,
        "bay_id": 1,
    }
    first = client.post("/api/service-booking/orders", json=payload).json()
    if not first["success"]:
        pytest.skip("技师 1 或工位 1 在目标时间不可用，跳过重复预约用例")

    second = client.post("/api/service-booking/orders", json=payload).json()
    assert second["success"] is False
    assert second["data"]["suggestions"]


def test_knowledge_endpoint(client):
    payload = client.get("/api/knowledge").json()["data"]
    assert payload["total_count"] >= 10
    assert payload["categories"]


def test_chat_stream_endpoint(client):
    response = client.post("/chat/stream", json={"message": "明天下午2点，京F60003，换机油"})
    assert response.status_code == 200
    assert "预约" in response.text


def test_behavior_dashboard_endpoint(client):
    data = client.get("/api/vehicle-behavior/dashboard_data").json()["data"]
    assert "total_appointments" in data
    assert "price_sensitivity" in data