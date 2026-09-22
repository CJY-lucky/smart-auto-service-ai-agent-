"""技师服务：初始化默认技师、查询技师、判断技师在某时间窗是否可用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.constants import Certification, Shift
from db.db_router import get_database_router
from services.text_embedding import rank_by_similarity

logger = logging.getLogger(__name__)

DEFAULT_TECHNICIANS: List[Dict[str, Any]] = [
    {
        "name": "张伟",
        "gender": "男",
        "level": "高级",
        "certifications": [
            Certification.BASIC.value,
            Certification.BRAKE.value,
            Certification.ENGINE.value,
        ],
        "specialties": "发动机保养与制动系统检修经验丰富，擅长处理疑难故障",
        "shift": Shift.MORNING.value,
    },
    {
        "name": "王强",
        "gender": "男",
        "level": "中级",
        "certifications": [Certification.BASIC.value, Certification.BRAKE.value],
        "specialties": "底盘与制动系统维修，换刹车片手法熟练、效率高",
        "shift": Shift.FULL.value,
    },
    {
        "name": "李娜",
        "gender": "女",
        "level": "中级",
        "certifications": [Certification.BASIC.value, Certification.ELECTRICAL.value],
        "specialties": "电气系统诊断，擅长电瓶检测、电路排查与故障灯分析",
        "shift": Shift.MORNING.value,
    },
    {
        "name": "赵敏",
        "gender": "女",
        "level": "高级",
        "certifications": [Certification.BASIC.value, Certification.ALIGNMENT.value],
        "specialties": "四轮定位与轮胎动平衡专家，方向盘跑偏问题处理细致",
        "shift": Shift.FULL.value,
    },
    {
        "name": "刘洋",
        "gender": "男",
        "level": "中级",
        "certifications": [Certification.BASIC.value, Certification.TRANSMISSION.value],
        "specialties": "变速箱油更换与常规保养，熟悉各主流车型油品规格",
        "shift": Shift.EVENING.value,
    },
    {
        "name": "孙丽",
        "gender": "女",
        "level": "初级",
        "certifications": [Certification.BASIC.value],
        "specialties": "常规快修保养与洗车美容，服务细致耐心",
        "shift": Shift.MORNING.value,
    },
    {
        "name": "周杰",
        "gender": "男",
        "level": "高级",
        "certifications": [
            Certification.BASIC.value,
            Certification.BRAKE.value,
            Certification.ALIGNMENT.value,
        ],
        "specialties": "底盘与制动综合维修，擅长异响排查和四轮定位",
        "shift": Shift.FULL.value,
    },
    {
        "name": "吴婷",
        "gender": "女",
        "level": "初级",
        "certifications": [Certification.BASIC.value, Certification.ELECTRICAL.value],
        "specialties": "快修保养与电瓶更换，流程规范、讲解清楚",
        "shift": Shift.EVENING.value,
    },
    {
        "name": "郑斌",
        "gender": "男",
        "level": "高级",
        "certifications": [Certification.BASIC.value, Certification.PAINT.value],
        "specialties": "钣金喷漆与车身修复，处理划痕与凹陷经验丰富",
        "shift": Shift.FULL.value,
    },
    {
        "name": "何静",
        "gender": "女",
        "level": "初级",
        "certifications": [Certification.NONE.value],
        "specialties": "洗车与内饰清洁，擅长漆面养护",
        "shift": Shift.MORNING.value,
    },
]


class TechnicianService:
    """技师业务逻辑。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)

    # -- 初始化 ---------------------------------------------------------
    def initialize_default_technicians(self) -> bool:
        """数据库为空时写入默认技师（幂等）。"""

        try:
            existing = self.db.technicians.count()
            if existing:
                logger.info("已有 %s 位技师，跳过初始化", existing)
                return True
            for technician in DEFAULT_TECHNICIANS:
                self.db.technicians.upsert_technician(**technician)
            logger.info("默认技师初始化完成，共 %s 位", self.db.technicians.count())
            return True
        except Exception as exc:  # pragma: no cover
            logger.error("初始化默认技师失败：%s", exc)
            return False

    # -- 查询 -----------------------------------------------------------
    def list_technicians(self, active_only: bool = True) -> List[Dict[str, Any]]:
        return self.db.technicians.list_technicians(active_only=active_only)

    def get_technician(self, technician_id: int) -> Optional[Dict[str, Any]]:
        return self.db.technicians.get_by_id(technician_id)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self.db.technicians.get_by_name(name)

    def find_by_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        return self.db.technicians.search_by_name(keyword)

    def add_technician(self, name: str, **fields) -> int:
        return self.db.technicians.add_technician(name, **fields)

    def update_technician(self, technician_id: int, **updates) -> bool:
        return self.db.technicians.update_technician(technician_id, **updates)

    def remove_technician(self, technician_id: int) -> bool:
        return self.db.technicians.delete_technician(technician_id)

    # -- 资质与相似度 -----------------------------------------------------
    def filter_by_certifications(
        self, technicians: List[Dict[str, Any]], required: List[str]
    ) -> List[Dict[str, Any]]:
        """筛出具备全部所需资质的技师。空需求表示不限制。"""

        requirements = {item for item in (required or []) if item and item != Certification.NONE.value}
        if not requirements:
            return list(technicians)
        return [
            technician
            for technician in technicians
            if requirements.issubset(set(technician.get("certifications") or []))
        ]

    def rank_by_specialty(self, preference: str, technicians: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按车主偏好（如"擅长四轮定位"）对技师排序。"""

        if not preference or not technicians:
            return list(technicians)
        specialties = [technician.get("specialties", "") for technician in technicians]
        order = rank_by_similarity(preference, specialties)
        return [technicians[index] for index in order]

    # -- 可用性 -----------------------------------------------------------
    def is_available(
        self,
        technician_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_order_id: Optional[int] = None,
    ) -> bool:
        return self.db.work_orders.is_technician_available(
            technician_id, start_time, end_time, exclude_order_id=exclude_order_id
        )

    def busy_periods(self, technician_id: int, day: datetime) -> List[Dict[str, Any]]:
        return self.db.work_orders.busy_windows_for_technician(technician_id, day)