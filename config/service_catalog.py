"""门店服务目录：保养项目、标准工时、所需资质与工位、项目依赖、保养周期。

这是排班与推荐共用的领域知识，统一放在配置层，保证 Services 层和 Agents 层
使用同一份口径（Agent 不允许自己编造工时和依赖关系）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .constants import BayType, Certification

LIFT = BayType.LIFT.value
ALIGNMENT = BayType.ALIGNMENT.value
PAINT = BayType.PAINT.value
WASH = BayType.WASH.value
QUICK = BayType.QUICK.value


@dataclass(frozen=True)
class ServiceItem:
    """一个可预约的保养项目。"""

    code: str
    name: str
    duration_minutes: int
    amount: float
    bay_types: List[str]
    certification: str = Certification.BASIC.value
    depends_on: List[str] = field(default_factory=list)
    interval_km: Optional[int] = None
    interval_months: Optional[int] = None
    keywords: List[str] = field(default_factory=list)
    category: str = "保养"

    def to_dict(self) -> Dict:
        return {
            "code": self.code,
            "name": self.name,
            "duration_minutes": self.duration_minutes,
            "amount": self.amount,
            "bay_types": list(self.bay_types),
            "certification": self.certification,
            "depends_on": list(self.depends_on),
            "interval_km": self.interval_km,
            "interval_months": self.interval_months,
            "keywords": list(self.keywords),
            "category": self.category,
        }


SERVICE_ITEMS: Dict[str, ServiceItem] = {
    item.code: item
    for item in [
        ServiceItem(
            code="oil_change",
            name="更换机油机滤",
            duration_minutes=40,
            amount=380,
            bay_types=[LIFT, QUICK],
            interval_km=10000,
            interval_months=12,
            keywords=["机油", "机滤", "小保养", "换油", "保养"],
        ),
        ServiceItem(
            code="air_filter",
            name="更换空气滤芯",
            duration_minutes=15,
            amount=120,
            bay_types=[QUICK, LIFT],
            interval_km=20000,
            interval_months=12,
            keywords=["空气滤芯", "空滤", "滤芯"],
        ),
        ServiceItem(
            code="ac_filter",
            name="更换空调滤芯",
            duration_minutes=15,
            amount=150,
            bay_types=[QUICK],
            interval_km=20000,
            interval_months=12,
            keywords=["空调滤芯", "空调滤", "空调"],
        ),
        ServiceItem(
            code="tire_rotation",
            name="四轮换位",
            duration_minutes=30,
            amount=80,
            bay_types=[LIFT],
            interval_km=10000,
            interval_months=12,
            keywords=["换位", "轮胎换位", "四轮换位"],
        ),
        ServiceItem(
            code="tire_change",
            name="更换轮胎",
            duration_minutes=60,
            amount=400,
            bay_types=[LIFT, QUICK],
            interval_km=60000,
            interval_months=60,
            keywords=["换胎", "轮胎", "爆胎", "补胎"],
        ),
        ServiceItem(
            code="wheel_alignment",
            name="四轮定位",
            duration_minutes=60,
            amount=300,
            bay_types=[ALIGNMENT],
            certification=Certification.ALIGNMENT.value,
            depends_on=["tire_change", "tire_rotation"],
            interval_km=20000,
            interval_months=24,
            keywords=["四轮定位", "定位", "跑偏", "方向盘偏"],
        ),
        ServiceItem(
            code="brake_pad",
            name="更换刹车片",
            duration_minutes=90,
            amount=680,
            bay_types=[LIFT],
            certification=Certification.BRAKE.value,
            depends_on=["tire_rotation"],
            interval_km=40000,
            interval_months=24,
            keywords=["刹车片", "刹车", "制动", "异响"],
        ),
        ServiceItem(
            code="brake_fluid",
            name="更换刹车油",
            duration_minutes=60,
            amount=260,
            bay_types=[LIFT],
            certification=Certification.BRAKE.value,
            interval_km=40000,
            interval_months=24,
            keywords=["刹车油", "制动液"],
        ),
        ServiceItem(
            code="coolant",
            name="更换防冻液",
            duration_minutes=60,
            amount=300,
            bay_types=[LIFT],
            certification=Certification.ENGINE.value,
            interval_km=60000,
            interval_months=24,
            keywords=["防冻液", "冷却液", "水箱"],
        ),
        ServiceItem(
            code="spark_plug",
            name="更换火花塞",
            duration_minutes=90,
            amount=480,
            bay_types=[QUICK],
            certification=Certification.ENGINE.value,
            interval_km=40000,
            interval_months=36,
            keywords=["火花塞", "点火", "抖动"],
        ),
        ServiceItem(
            code="transmission_oil",
            name="更换变速箱油",
            duration_minutes=90,
            amount=900,
            bay_types=[LIFT],
            certification=Certification.TRANSMISSION.value,
            interval_km=60000,
            interval_months=48,
            keywords=["变速箱油", "波箱油", "变速箱"],
        ),
        ServiceItem(
            code="battery",
            name="电瓶检测/更换",
            duration_minutes=30,
            amount=520,
            bay_types=[QUICK],
            certification=Certification.ELECTRICAL.value,
            interval_months=24,
            keywords=["电瓶", "蓄电池", "打不着火", "亏电"],
        ),
        ServiceItem(
            code="full_inspection",
            name="全车检查",
            duration_minutes=30,
            amount=0,
            bay_types=[QUICK, LIFT],
            keywords=["检查", "全车检查", "体检", "出长途"],
        ),
        ServiceItem(
            code="detailing",
            name="洗车",
            duration_minutes=30,
            amount=40,
            bay_types=[WASH],
            certification=Certification.NONE.value,
            keywords=["洗车", "清洗"],
            category="美容",
        ),
        ServiceItem(
            code="paint",
            name="钣金喷漆",
            duration_minutes=240,
            amount=1200,
            bay_types=[PAINT],
            certification=Certification.PAINT.value,
            keywords=["钣金", "喷漆", "划痕", "凹陷"],
            category="钣喷",
        ),
    ]
}

# 口语别名 -> 标准编码，用于无 LLM 时的规则兜底解析
ITEM_ALIASES: Dict[str, str] = {
    "小保养": "oil_change",
    "常规保养": "oil_change",
    "换机油": "oil_change",
    "机油": "oil_change",
    "机滤": "oil_change",
    "换胎": "tire_change",
    "补胎": "tire_change",
    "轮胎": "tire_change",
    "定位": "wheel_alignment",
    "跑偏": "wheel_alignment",
    "刹车": "brake_pad",
    "刹车片": "brake_pad",
    "防冻液": "coolant",
    "冷却液": "coolant",
    "火花塞": "spark_plug",
    "变速箱": "transmission_oil",
    "电瓶": "battery",
    "打不着火": "battery",
    "洗车": "detailing",
    "喷漆": "paint",
    "钣金": "paint",
    "检查": "full_inspection",
    "空调": "ac_filter",
    "空滤": "air_filter",
}


def get_service_item(code: str) -> Optional[ServiceItem]:
    """按编码取项目。"""

    return SERVICE_ITEMS.get(code)


def all_service_items() -> List[ServiceItem]:
    return list(SERVICE_ITEMS.values())


def resolve_item_code(text: str) -> Optional[str]:
    """把口语化项目名解析成标准编码，无法识别返回 None。"""

    if not text:
        return None
    normalized = str(text).strip()
    if normalized in SERVICE_ITEMS:
        return normalized
    for item in SERVICE_ITEMS.values():
        if normalized == item.name or normalized in item.keywords:
            return item.code
    best: Optional[str] = None
    best_length = 0
    for alias, code in ITEM_ALIASES.items():
        if alias in normalized and len(alias) > best_length:
            best = code
            best_length = len(alias)
    return best