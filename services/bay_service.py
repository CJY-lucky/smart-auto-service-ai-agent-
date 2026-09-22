"""工位服务：初始化默认工位、按类型筛选、判断工位占用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.constants import BayType
from db.db_router import get_database_router

logger = logging.getLogger(__name__)

DEFAULT_BAYS: List[Dict[str, Any]] = [
    {
        "name": "举升机工位A",
        "bay_type": BayType.LIFT.value,
        "equipment": ["双柱举升机", "废油回收机", "扭力扳手"],
    },
    {
        "name": "举升机工位B",
        "bay_type": BayType.LIFT.value,
        "equipment": ["双柱举升机", "轮胎拆装机", "动平衡机"],
    },
    {
        "name": "快修工位A",
        "bay_type": BayType.QUICK.value,
        "equipment": ["免举升作业台", "电瓶检测仪", "诊断电脑"],
    },
    {
        "name": "快修工位B",
        "bay_type": BayType.QUICK.value,
        "equipment": ["免举升作业台", "举升垫块", "快速保养台"],
    },
    {
        "name": "四轮定位工位",
        "bay_type": BayType.ALIGNMENT.value,
        "equipment": ["3D四轮定位仪", "专用转盘", "举升平台"],
    },
    {
        "name": "洗车工位",
        "bay_type": BayType.WASH.value,
        "equipment": ["高压清洗机", "泡沫机", "吸尘器"],
    },
    {
        "name": "钣喷房",
        "bay_type": BayType.PAINT.value,
        "equipment": ["烤漆房", "调漆间", "钣金台"],
    },
]


class BayService:
    """工位业务逻辑。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)

    def initialize_default_bays(self) -> bool:
        """写入默认工位（幂等）。"""

        try:
            existing = self.db.bays.count()
            if existing:
                logger.info("已有 %s 个工位，跳过初始化", existing)
                return True
            for bay in DEFAULT_BAYS:
                self.db.bays.upsert_bay(bay["name"], bay["bay_type"], bay["equipment"])
            logger.info("默认工位初始化完成，共 %s 个", self.db.bays.count())
            return True
        except Exception as exc:  # pragma: no cover
            logger.error("初始化默认工位失败：%s", exc)
            return False

    def list_bays(self, bay_type: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        return self.db.bays.list_bays(bay_type=bay_type, active_only=active_only)

    def get_bay(self, bay_id: int) -> Optional[Dict[str, Any]]:
        return self.db.bays.get_by_id(bay_id)

    def find_by_types(self, bay_types: List[str]) -> List[Dict[str, Any]]:
        """筛出类型匹配的工位。"""

        wanted = {item for item in (bay_types or []) if item}
        bays = self.list_bays()
        if not wanted:
            return bays
        return [bay for bay in bays if bay.get("bay_type") in wanted]

    def coverable_bay_types(self, item_bay_types: List[List[str]]) -> List[str]:
        """求多个项目所需工位类型的交集：交集为空说明必须拆单。"""

        if not item_bay_types:
            return []
        intersection = set(item_bay_types[0])
        for bay_types in item_bay_types[1:]:
            intersection &= set(bay_types)
        return sorted(intersection)

    def add_bay(self, name: str, bay_type: str, equipment: Optional[List[str]] = None) -> int:
        return self.db.bays.add_bay(name, bay_type, equipment)

    def update_bay(self, bay_id: int, **updates) -> bool:
        return self.db.bays.update_bay(bay_id, **updates)

    def remove_bay(self, bay_id: int) -> bool:
        return self.db.bays.delete_bay(bay_id)

    def is_available(
        self,
        bay_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> bool:
        return self.db.work_orders.is_bay_available(
            bay_id, start_time, end_time, exclude_order_id=exclude_order_id
        )

    def busy_periods(self, bay_id: int, day: datetime) -> List[Dict[str, Any]]:
        return self.db.work_orders.busy_windows_for_bay(bay_id, day)