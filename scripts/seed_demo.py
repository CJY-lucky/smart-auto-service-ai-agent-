"""生成演示数据：车主、车辆档案、历史工单。

用法：
    python -m scripts.seed_demo
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.time_config import time_config  # noqa: E402
from services.bay_service import BayService  # noqa: E402
from services.technician_service import TechnicianService  # noqa: E402
from services.vehicle_service import VehicleService  # noqa: E402
from services.work_order_service import WorkOrderService  # noqa: E402


DEMO_VEHICLES = [
    {
        "owner_ref": "default_owner",
        "plate_no": "京A12345",
        "model": "卡罗拉",
        "brand": "丰田",
        "year": 2020,
        "mileage": 42000,
        "oil_spec": "0W-20 全合成",
        "last_service_mileage": 32000,
        "last_service_days_ago": 300,
        "purchase_date_days_ago": 1500,
    },
    {
        "owner_ref": "默认车主",
        "plate_no": "京B88888",
        "model": "Model 3",
        "brand": "特斯拉",
        "year": 2022,
        "mileage": 18000,
        "oil_spec": "不适用（纯电）",
        "last_service_mileage": 10000,
        "last_service_days_ago": 120,
        "purchase_date_days_ago": 700,
    },
]


def main() -> None:
    TechnicianService().initialize_default_technicians()
    BayService().initialize_default_bays()
    vehicle_service = VehicleService()

    now = time_config.now()
    for entry in DEMO_VEHICLES:
        owner_id = vehicle_service.ensure_owner(entry["owner_ref"])
        vehicle_id = vehicle_service.ensure_vehicle(
            owner_id,
            entry["plate_no"],
            model=entry["model"],
            brand=entry["brand"],
            year=entry["year"],
            mileage=entry["mileage"],
            oil_spec=entry["oil_spec"],
            last_service_date=now - timedelta(days=entry["last_service_days_ago"]),
            last_service_mileage=entry["last_service_mileage"],
            purchase_date=now - timedelta(days=entry["purchase_date_days_ago"]),
        )
        print(f"车辆档案已就绪：{entry['plate_no']} (id={vehicle_id})")

    print("演示数据生成完成。可以运行：python -m uvicorn app:app --reload")


if __name__ == "__main__":
    main()