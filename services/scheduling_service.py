"""双资源排班内核——整个项目最关键的一段确定性逻辑。

约束模型：
1. 一名技师在整个时间窗内被占用（因为技师不可能同时出现在两个工位）；
2. 工位按项目分段占用：一个工单里的多个项目按物理依赖串行执行，
   需要变更工位时额外计入转移时间（挪车 + 交接）。

例如"换轮胎 + 四轮定位"：先在举升机工位换胎，再开到四轮定位工位做定位，
技师的整段时间被锁定，两个工位各自只在自己那一段被占用。

设计原则（README 的核心思想）：大模型只负责把口语需求翻译成结构化意图，
"能不能排出这个档期"完全由这里的确定性算法判定。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from config.constants import Certification
from config.service_catalog import SERVICE_ITEMS
from config.time_config import TimeWindow, time_config
from db.db_router import get_database_router
from services.bay_service import BayService
from services.technician_service import TechnicianService

logger = logging.getLogger(__name__)


class ConflictReason(str, Enum):
    """排期失败的原因，用于把冲突翻译成车主能听懂的话。"""

    NO_ITEMS = "no_items"
    NEED_SPLIT = "need_split"
    OUTSIDE_BUSINESS_HOURS = "outside_business_hours"
    OUTSIDE_SHIFT = "outside_shift"
    NO_QUALIFIED_TECHNICIAN = "no_qualified_technician"
    TECHNICIAN_NOT_FOUND = "technician_not_found"
    TECHNICIAN_NOT_QUALIFIED = "technician_not_qualified"
    TECHNICIAN_BUSY = "technician_busy"
    NO_SUITABLE_BAY = "no_suitable_bay"
    BAY_BUSY = "bay_busy"
    TIME_IN_PAST = "time_in_past"


REASON_TEXT = {
    ConflictReason.NO_ITEMS: "没有识别到要做哪些保养项目",
    ConflictReason.NEED_SPLIT: "这些项目缺少可承接的工位类型配置，需要拆单或补充工位",
    ConflictReason.OUTSIDE_BUSINESS_HOURS: "这个时间超出了门店营业时间（每天 9:00-20:00）",
    ConflictReason.OUTSIDE_SHIFT: "这个时间段没有技师在班",
    ConflictReason.NO_QUALIFIED_TECHNICIAN: "店内没有具备该项目资质的技师",
    ConflictReason.TECHNICIAN_NOT_FOUND: "没有找到指定的技师",
    ConflictReason.TECHNICIAN_NOT_QUALIFIED: "指定技师不具备该项目资质",
    ConflictReason.TECHNICIAN_BUSY: "该时间段技师已有其它工单",
    ConflictReason.NO_SUITABLE_BAY: "店内没有能承接该项目的工位",
    ConflictReason.BAY_BUSY: "该时间段匹配的工位已被占用",
    ConflictReason.TIME_IN_PAST: "预约时间已经过去了",
}


@dataclass
class WorkloadPlan:
    """一次预约的作业计划（含分段工序）。"""

    item_codes: List[str]
    items: List[Dict[str, Any]]
    segments: List[Dict[str, Any]]
    total_minutes: int
    amount: float
    required_certifications: List[str]
    bay_type_options: List[str]
    need_split: bool
    transfer_minutes: int = 0
    unsupported_codes: List[str] = field(default_factory=list)

    @property
    def item_names(self) -> List[str]:
        return [item["name"] for item in self.items]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_codes": list(self.item_codes),
            "items": list(self.items),
            "segments": list(self.segments),
            "total_minutes": self.total_minutes,
            "amount": self.amount,
            "required_certifications": list(self.required_certifications),
            "bay_type_options": list(self.bay_type_options),
            "need_split": self.need_split,
            "transfer_minutes": self.transfer_minutes,
            "unsupported_codes": list(self.unsupported_codes),
        }


@dataclass
class ScheduleSolution:
    """一个可行的排期方案。"""

    start_time: datetime
    end_time: datetime
    technician: Dict[str, Any]
    bay: Dict[str, Any]
    plan: WorkloadPlan
    segments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() // 60)

    @property
    def bay_names(self) -> List[str]:
        names: List[str] = []
        for segment in self.segments or []:
            name = (segment.get("bay") or {}).get("name")
            if name and name not in names:
                names.append(name)
        return names or [self.bay.get("name", "")]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "technician": self.technician,
            "bay": self.bay,
            "segments": [
                {
                    "item_code": segment["item_code"],
                    "item_name": segment["item_name"],
                    "bay_id": segment["bay"]["id"],
                    "bay_name": segment["bay"]["name"],
                    "bay_type": segment["bay"]["bay_type"],
                    "start": segment["start"],
                    "end": segment["end"],
                }
                for segment in (self.segments or [])
            ],
            "plan": self.plan.to_dict(),
            "duration_minutes": self.duration_minutes,
        }


@dataclass
class ScheduleResult:
    """排期结果：可行方案 + 失败原因 + 备选时段。"""

    feasible: bool
    plan: WorkloadPlan
    solution: Optional[ScheduleSolution] = None
    reasons: List[str] = field(default_factory=list)
    suggestions: List[ScheduleSolution] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def reason_texts(self) -> List[str]:
        texts = []
        for reason in self.reasons:
            try:
                texts.append(REASON_TEXT[ConflictReason(reason)])
            except ValueError:
                texts.append(reason)
        return texts


class SchedulingService:
    """技师 + 工位双资源排班。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)
        self.technician_service = TechnicianService(db_path)
        self.bay_service = BayService(db_path)

    # ================================================================ 作业计划
    def estimate_workload(self, item_codes: List[str]) -> WorkloadPlan:
        """把项目清单变成"工序顺序 + 总工时 + 资源需求"的作业计划。"""

        unique_codes: List[str] = []
        unsupported: List[str] = []
        for code in item_codes or []:
            if code in SERVICE_ITEMS:
                if code not in unique_codes:
                    unique_codes.append(code)
            elif code:
                unsupported.append(code)

        ordered_codes = self.order_items(unique_codes)

        items: List[Dict[str, Any]] = []
        segments: List[Dict[str, Any]] = []
        certifications: List[str] = []
        bay_types_union: List[str] = []
        offset = 0
        transfer_minutes = 0
        previous_bay_types: Optional[List[str]] = None

        for sequence, code in enumerate(ordered_codes):
            service_item = SERVICE_ITEMS[code]
            bay_types = list(service_item.bay_types)

            needs_transfer = False
            if previous_bay_types is not None and not set(bay_types) & set(previous_bay_types):
                # 相邻两个项目没有可共用的工位类型，必须先挪车
                needs_transfer = True
                offset += time_config.TRANSFER_MINUTES
                transfer_minutes += time_config.TRANSFER_MINUTES

            start_offset = offset
            offset += service_item.duration_minutes

            segments.append(
                {
                    "item_code": code,
                    "item_name": service_item.name,
                    "sequence": sequence,
                    "start_offset": start_offset,
                    "end_offset": offset,
                    "bay_types": bay_types,
                    "transfer_before": needs_transfer,
                }
            )
            items.append(
                {
                    "item_code": code,
                    "name": service_item.name,
                    "duration_minutes": service_item.duration_minutes,
                    "amount": service_item.amount,
                    "certification": service_item.certification,
                    "bay_types": bay_types,
                    "sequence": sequence,
                }
            )

            if service_item.certification and service_item.certification != Certification.NONE.value:
                if service_item.certification not in certifications:
                    certifications.append(service_item.certification)
            for bay_type in bay_types:
                if bay_type not in bay_types_union:
                    bay_types_union.append(bay_type)

            previous_bay_types = bay_types

        return WorkloadPlan(
            item_codes=ordered_codes,
            items=items,
            segments=segments,
            total_minutes=offset,
            amount=sum(item["amount"] for item in items),
            required_certifications=certifications,
            bay_type_options=bay_types_union,
            need_split=any(not segment["bay_types"] for segment in segments),
            transfer_minutes=transfer_minutes,
            unsupported_codes=unsupported,
        )

    @staticmethod
    def order_items(item_codes: List[str]) -> List[str]:
        """按项目之间的物理依赖排序（例如四轮定位要在换胎之后做）。"""

        remaining = list(item_codes)
        ordered: List[str] = []

        while remaining:
            progressed = False
            for code in list(remaining):
                dependencies = SERVICE_ITEMS[code].depends_on if code in SERVICE_ITEMS else []
                if any(dep in remaining for dep in dependencies):
                    continue
                ordered.append(code)
                remaining.remove(code)
                progressed = True
            if not progressed:
                logger.warning("项目依赖存在环：%s", remaining)
                ordered.extend(remaining)
                break

        return ordered

    # ================================================================ 排期求解
    def find_solution(
        self,
        item_codes: List[str],
        start_time: datetime,
        *,
        technician_id: Optional[int] = None,
        bay_id: Optional[int] = None,
        preference: Optional[str] = None,
        exclude_order_id: Optional[int] = None,
        with_suggestions: bool = True,
    ) -> ScheduleResult:
        """求解一个可行排期；不可行时给出原因与备选时段。"""

        plan = self.estimate_workload(item_codes)
        reasons: List[str] = []

        if not plan.items:
            return ScheduleResult(
                feasible=False,
                plan=plan,
                reasons=[ConflictReason.NO_ITEMS.value],
                detail={"unsupported_codes": plan.unsupported_codes},
            )
        if plan.need_split:
            return ScheduleResult(
                feasible=False,
                plan=plan,
                reasons=[ConflictReason.NEED_SPLIT.value],
                detail={"segments": plan.segments},
            )

        start_time = time_config.ceil_to_slot(start_time)
        end_time = start_time + timedelta(minutes=plan.total_minutes)
        window = TimeWindow(start_time, end_time)

        if start_time < time_config.now():
            reasons.append(ConflictReason.TIME_IN_PAST.value)
        if not time_config.is_within_business_hours(window):
            reasons.append(ConflictReason.OUTSIDE_BUSINESS_HOURS.value)

        # ---- 技师候选 ----
        all_technicians = self.technician_service.list_technicians()
        qualified = self.technician_service.filter_by_certifications(
            all_technicians, plan.required_certifications
        )

        target_technician: Optional[Dict[str, Any]] = None
        if technician_id is not None:
            target_technician = self.technician_service.get_technician(technician_id)
            if target_technician is None:
                reasons.append(ConflictReason.TECHNICIAN_NOT_FOUND.value)
            elif not self._is_qualified(target_technician, plan.required_certifications):
                reasons.append(ConflictReason.TECHNICIAN_NOT_QUALIFIED.value)
        elif not qualified:
            reasons.append(ConflictReason.NO_QUALIFIED_TECHNICIAN.value)

        # ---- 工位候选 ----
        all_bays = self.bay_service.list_bays()
        candidate_bays = [bay for bay in all_bays if bay["bay_type"] in plan.bay_type_options]
        if not candidate_bays:
            reasons.append(ConflictReason.NO_SUITABLE_BAY.value)

        # 指定工位只作为"第一道工序"的偏好约束：跨工位工单的后续工序仍需自由选工位
        pinned_bay: Optional[Dict[str, Any]] = None
        if bay_id is not None:
            target_bay = self.bay_service.get_bay(bay_id)
            if target_bay is None or target_bay["bay_type"] not in plan.bay_type_options:
                reasons.append(ConflictReason.NO_SUITABLE_BAY.value)
            elif plan.segments and target_bay["bay_type"] in plan.segments[0]["bay_types"]:
                pinned_bay = target_bay

        if reasons:
            return ScheduleResult(feasible=False, plan=plan, reasons=reasons)

        # ---- 候选技师排序 ----
        if target_technician is not None:
            candidate_technicians = [target_technician]
        else:
            candidate_technicians = list(qualified)
            if preference:
                candidate_technicians = self.technician_service.rank_by_specialty(
                    preference, candidate_technicians
                )

        shift_ok = [tech for tech in candidate_technicians if self._shift_covers(tech, window)]
        if not shift_ok:
            reasons.append(ConflictReason.OUTSIDE_SHIFT.value)
            return self._fail(plan, reasons, item_codes, start_time, technician_id, with_suggestions)

        # ---- 双资源联合匹配：技师占整段，工位按工序分段 ----
        technician_busy = False
        bay_busy = False
        for technician in shift_ok:
            if not self.technician_service.is_available(
                technician["id"], start_time, end_time, exclude_order_id=exclude_order_id
            ):
                technician_busy = True
                continue

            assignment = self._assign_bays(
                plan.segments,
                start_time,
                candidate_bays,
                pinned_bay=pinned_bay,
                exclude_order_id=exclude_order_id,
            )
            if assignment is None:
                bay_busy = True
                continue

            return ScheduleResult(
                feasible=True,
                plan=plan,
                solution=ScheduleSolution(
                    start_time=start_time,
                    end_time=end_time,
                    technician=technician,
                    bay=assignment[0]["bay"],
                    plan=plan,
                    segments=assignment,
                ),
            )

        if bay_busy:
            reasons.append(ConflictReason.BAY_BUSY.value)
        if technician_busy:
            reasons.append(ConflictReason.TECHNICIAN_BUSY.value)
        if not reasons:
            reasons.append(ConflictReason.BAY_BUSY.value)

        return self._fail(plan, reasons, item_codes, start_time, technician_id, with_suggestions)

    def _assign_bays(
        self,
        segments: List[Dict[str, Any]],
        start_time: datetime,
        candidate_bays: List[Dict[str, Any]],
        *,
        pinned_bay: Optional[Dict[str, Any]] = None,
        exclude_order_id: Optional[int] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """为每道工序分配一个空闲工位；任何一道分不到就返回 None。"""

        assignment: List[Dict[str, Any]] = []
        for index, segment in enumerate(segments):
            segment_start = start_time + timedelta(minutes=segment["start_offset"])
            segment_end = start_time + timedelta(minutes=segment["end_offset"])
            allowed = candidate_bays
            if index == 0 and pinned_bay is not None:
                allowed = [pinned_bay]
            chosen = None
            for bay in allowed:
                if bay["bay_type"] not in segment["bay_types"]:
                    continue
                if not self.bay_service.is_available(
                    bay["id"], segment_start, segment_end, exclude_order_id=exclude_order_id
                ):
                    continue
                chosen = bay
                break
            if chosen is None:
                return None
            assignment.append(
                {
                    "item_code": segment["item_code"],
                    "item_name": segment["item_name"],
                    "bay": chosen,
                    "start": segment_start,
                    "end": segment_end,
                }
            )
        return assignment

    def _fail(
        self,
        plan: WorkloadPlan,
        reasons: List[str],
        item_codes: List[str],
        start_time: datetime,
        technician_id: Optional[int],
        with_suggestions: bool,
    ) -> ScheduleResult:
        suggestions: List[ScheduleSolution] = []
        if with_suggestions:
            suggestions = self.suggest_slots(
                item_codes, start_time, technician_id=technician_id, limit=3
            )
        return ScheduleResult(
            feasible=False,
            plan=plan,
            reasons=reasons,
            suggestions=suggestions,
            detail={"requested_start": start_time},
        )

    # ================================================================ 备选时段
    def suggest_slots(
        self,
        item_codes: List[str],
        day: datetime,
        *,
        technician_id: Optional[int] = None,
        limit: int = 3,
        days_forward: int = 3,
    ) -> List[ScheduleSolution]:
        """从指定日期起向后找若干天，返回最早的若干个可行时段。"""

        plan = self.estimate_workload(item_codes)
        if not plan.items or plan.need_split:
            return []

        suggestions: List[ScheduleSolution] = []
        now = time_config.now()
        skipped = time_config.ceil_to_slot(day)

        for offset in range(days_forward):
            target_day = day + timedelta(days=offset)
            for slot_start in time_config.generate_slot_starts(target_day):
                if slot_start < now or slot_start == skipped:
                    continue
                result = self.find_solution(
                    item_codes,
                    slot_start,
                    technician_id=technician_id,
                    with_suggestions=False,
                )
                if result.feasible and result.solution:
                    suggestions.append(result.solution)
                    if len(suggestions) >= limit:
                        return suggestions
        return suggestions

    def next_slots_for_technician(
        self,
        technician_id: int,
        duration_minutes: int,
        *,
        day: Optional[datetime] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """某个技师在未来几天的可用时段（车主指定技师但当时没空时使用）。"""

        technician = self.technician_service.get_technician(technician_id)
        if technician is None:
            return []

        plan = self.estimate_workload([])
        results: List[Dict[str, Any]] = []
        base_day = day or time_config.now()
        now = time_config.now()

        for offset in range(7):
            target_day = base_day + timedelta(days=offset)
            for slot_start in time_config.generate_slot_starts(target_day):
                if slot_start < now:
                    continue
                end_time = slot_start + timedelta(minutes=duration_minutes)
                window = TimeWindow(slot_start, end_time)
                if not time_config.is_within_business_hours(window):
                    continue
                if not self._shift_covers(technician, window):
                    continue
                if not self.technician_service.is_available(technician["id"], slot_start, end_time):
                    continue
                results.append(
                    {
                        "start_time": slot_start,
                        "end_time": end_time,
                        "technician": technician,
                        "duration_minutes": duration_minutes,
                    }
                )
                if len(results) >= limit:
                    return results
        return results

    # ================================================================ 看板
    def day_board(self, day: Optional[datetime] = None) -> Dict[str, Any]:
        """车间排班看板数据：技师行、工位列、当日工单。"""

        day = day or time_config.now()
        technicians = self.technician_service.list_technicians()
        bays = self.bay_service.list_bays()
        orders = self.db.work_orders.list_orders_detail(day=day)

        technician_rows = []
        for technician in technicians:
            technician_rows.append(
                {
                    **technician,
                    "busy_periods": [
                        {
                            "start": item["start"].strftime("%H:%M"),
                            "end": item["end"].strftime("%H:%M"),
                            "order_no": item["order_no"],
                        }
                        for item in self.db.work_orders.busy_windows_for_technician(technician["id"], day)
                    ],
                }
            )

        bay_rows = []
        for bay in bays:
            bay_rows.append(
                {
                    **bay,
                    "busy_periods": [
                        {
                            "start": item["start"].strftime("%H:%M"),
                            "end": item["end"].strftime("%H:%M"),
                            "order_no": item["order_no"],
                        }
                        for item in self.db.work_orders.busy_windows_for_bay(bay["id"], day)
                    ],
                }
            )

        return {
            "day": day.strftime("%Y-%m-%d"),
            "business_hours": time_config.get_business_hours(),
            "technicians": technician_rows,
            "bays": bay_rows,
            "orders": orders,
        }

    # ================================================================ 工具
    @staticmethod
    def _is_qualified(technician: Dict[str, Any], required: List[str]) -> bool:
        requirements = {
            item for item in (required or []) if item and item != Certification.NONE.value
        }
        return requirements.issubset(set(technician.get("certifications") or []))

    @staticmethod
    def _shift_covers(technician: Dict[str, Any], window: TimeWindow) -> bool:
        shift_window = time_config.shift_window(window.start, technician.get("shift") or "全天班")
        return shift_window.start <= window.start and window.end <= shift_window.end

    @staticmethod
    def describe(result: ScheduleResult) -> str:
        """把结构化结果翻译成一句人话，供 Agent 直接使用。"""

        if result.feasible and result.solution:
            solution = result.solution
            bays = " → ".join(solution.bay_names)
            return (
                f"{time_config.friendly_datetime(solution.start_time)}-"
                f"{solution.end_time:%H:%M}，由 {solution.technician['name']} 技师在 {bays} 为您施工"
            )
        texts = result.reason_texts or ["暂时无法安排"]
        return "；".join(texts)