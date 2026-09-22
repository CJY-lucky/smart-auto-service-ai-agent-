"""预约需求解析：把车主的口语表达翻译成结构化意图。

两条路：
1. 有 API Key 时，让大模型输出 JSON（字段固定、可校验）；
2. 没有 Key 或模型失败时，用规则兜底解析。
两条路的结果会合并，规则结果负责填空，保证离线也能跑通完整流程。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.service_catalog import SERVICE_ITEMS, resolve_item_code
from config.time_config import time_config

TIME_OF_DAY = {"早上": 8, "上午": 9, "中午": 12, "下午": 14, "傍晚": 17, "晚上": 18, "今晚": 18}

DAY_OFFSET = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2, "大后天": 3}

WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

MILEAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(万)?\s*(公里|km|KM)")

CONFIRM_WORDS = ["可以", "好的", "好", "行", "是", "同意", "确定", "要", "预约吧", "yes", "ok"]
DENY_WORDS = ["不用", "不要", "不用了", "不", "先不", "算了", "no", "取消"]

PREFERENCE_KEYWORDS = ["老师傅", "技术好", "细心", "经验丰富", "快", "专业", "便宜", "熟悉", "原厂"]


class InputParser:
    """预约需求解析器。"""

    def __init__(self, llm=None):
        self.llm = llm

    async def parse(self, user_input: str, *, known: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """解析用户输入，返回结构化字段。"""

        rule_result = self.parse_rules(user_input)
        llm_result: Dict[str, Any] = {}
        if self.llm is not None:
            try:
                llm_result = await self._parse_with_llm(user_input, known or {})
            except Exception:
                llm_result = {}

        merged = dict(rule_result)
        for key, value in llm_result.items():
            if value in (None, "", [], "未知", "unknown"):
                continue
            merged[key] = value

        # 项目编码统一校正
        merged["item_codes"] = self._normalize_item_codes(
            llm_result.get("item_codes") or rule_result.get("item_codes") or []
        )
        merged["is_confirmation"] = self._detect_confirmation(user_input)
        merged["is_denial"] = self._detect_denial(user_input)
        merged["raw"] = user_input
        return merged

    # ---------------------------------------------------------------- 规则解析
    def parse_rules(self, text: str) -> Dict[str, Any]:
        from services.vehicle_service import VehicleService

        result: Dict[str, Any] = {}
        if not text:
            return result

        plate_no = VehicleService.extract_plate_no(text)
        if plate_no:
            result["plate_no"] = plate_no

        start_time = self._extract_time(text)
        if start_time:
            result["start_time"] = time_config.format_datetime(start_time)

        mileage = self._extract_mileage(text)
        if mileage is not None:
            result["mileage"] = mileage

        item_codes = self._extract_items(text)
        if item_codes:
            result["item_codes"] = item_codes

        for keyword in PREFERENCE_KEYWORDS:
            if keyword in text:
                result["preference"] = keyword
                break

        model = self._extract_vehicle_model(text)
        if model:
            result["vehicle_model"] = model

        technician_name = self._extract_technician_name(text)
        if technician_name:
            result["technician_name"] = technician_name

        return result

    @staticmethod
    def _extract_technician_name(text: str) -> Optional[str]:
        """把"找张伟技师""指定王强"这类表达识别成技师姓名。"""

        if not text:
            return None
        try:
            from services.technician_service import TechnicianService

            for technician in TechnicianService().list_technicians():
                if technician["name"] and technician["name"] in text:
                    return technician["name"]
        except Exception:  # pragma: no cover - 数据库不可用时忽略
            return None
        return None

    @staticmethod
    def _extract_time(text: str) -> Optional[datetime]:
        now = time_config.now()
        target_date = None

        for word, offset in DAY_OFFSET.items():
            if word in text:
                target_date = (now + timedelta(days=offset)).date()
                break

        if target_date is None:
            match = re.search(r"周([一二三四五六日天])", text)
            if match:
                weekday = WEEKDAY_MAP[match.group(1)]
                delta = (weekday - now.weekday()) % 7
                delta = 7 if delta == 0 else delta
                target_date = (now + timedelta(days=delta)).date()

        if target_date is None:
            match = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                try:
                    target_date = now.replace(month=month, day=day).date()
                except ValueError:
                    target_date = None

        hour: Optional[int] = None
        minute = 0
        match = re.search(r"(\d{1,2})[:：点](\d{1,2})?", text)
        if match:
            hour = int(match.group(1))
            if match.group(2):
                minute = int(match.group(2))
            if hour < 8 and ("下午" in text or "晚上" in text):
                hour += 12
        else:
            for word, default_hour in TIME_OF_DAY.items():
                if word in text:
                    hour = default_hour
                    break

        if hour is None:
            return None
        if hour >= 24:
            hour = hour % 24

        day = target_date or now.date()
        try:
            return datetime(day.year, day.month, day.day, hour, minute)
        except ValueError:
            return None

    @staticmethod
    def _extract_mileage(text: str) -> Optional[int]:
        match = MILEAGE_PATTERN.search(text)
        if not match:
            return None
        value = float(match.group(1))
        if match.group(2):
            value *= 10000
        return int(value)

    @staticmethod
    def _extract_items(text: str) -> List[str]:
        """按关键词匹配项目，长词优先，避免"四轮定位"被"轮胎"截走。"""

        candidates: List[tuple] = []
        for code, item in SERVICE_ITEMS.items():
            for keyword in list(item.keywords) + [item.name]:
                if keyword and keyword in text:
                    candidates.append((keyword, code))

        candidates.sort(key=lambda pair: len(pair[0]), reverse=True)
        codes: List[str] = []
        for _, code in candidates:
            if code not in codes:
                codes.append(code)

        if not codes:
            resolved = resolve_item_code(text)
            if resolved:
                codes.append(resolved)
        return codes

    @staticmethod
    def _extract_vehicle_model(text: str) -> Optional[str]:
        match = re.search(r"(卡罗拉|凯美瑞|朗逸|速腾|帕萨特|轩逸|思域|雅阁|宝来|model\s?3|Model\s?Y|汉EV|宋PLUS)", text)
        return match.group(0) if match else None

    # ---------------------------------------------------------------- LLM 解析
    async def _parse_with_llm(self, user_input: str, known: Dict[str, Any]) -> Dict[str, Any]:
        service_names = "、".join(item.name for item in SERVICE_ITEMS.values())
        system_prompt = (
            "你是汽车保养门店的预约信息抽取器。请把车主的话翻译成结构化 JSON。\n"
            f"当前北京时间：{time_config.current_datetime_str()}。\n"
            f"门店可承接的项目有：{service_names}。\n"
            "只输出 JSON，不要任何解释或代码块标记。字段如下：\n"
            "{\n"
            '  "plate_no": "车牌号，没有则为空字符串",\n'
            '  "vehicle_model": "车型，没有则为空",\n'
            '  "mileage": 当前里程数字，没有则为 null,\n'
            '  "start_time": "期望到店时间，格式 YYYY-MM-DD HH:MM，没有则为空",\n'
            '  "item_codes": ["识别到的项目中文名列表，用门店项目名称"],\n'
            '  "preference": "车主对技师的偏好，没有则为空",\n'
            '  "technician_name": "车主指定的技师姓名，没有则为空"\n'
            "}\n"
            "时间表达要结合当前时间换算（例如“明天下午三点”要换成具体日期 15:00）。"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"已知信息：{json.dumps(known, ensure_ascii=False)}\n车主说：{user_input}"},
        ]
        data = await self.llm.acomplete_json(messages, temperature=0)
        if not isinstance(data, dict):
            return {}
        return data

    @staticmethod
    def _normalize_item_codes(values: List[Any]) -> List[str]:
        codes: List[str] = []
        for value in values or []:
            if not value:
                continue
            code = value if value in SERVICE_ITEMS else resolve_item_code(str(value))
            if code and code not in codes:
                codes.append(code)
        return codes

    @staticmethod
    def _detect_confirmation(text: str) -> bool:
        if not text:
            return False
        stripped = text.strip().lower()
        if any(word in stripped for word in DENY_WORDS):
            return False
        return any(word in stripped for word in CONFIRM_WORDS)

    @staticmethod
    def _detect_denial(text: str) -> bool:
        if not text:
            return False
        stripped = text.strip().lower()
        return any(word in stripped for word in DENY_WORDS)