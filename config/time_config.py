"""门店时间基准。

三条规则写死在这里，其他模块不许自己造时间口径：
1. 全系统统一使用"北京时间 + naive datetime"，避免 naive/aware 混用报错。
2. 时间窗一律按半开区间 [start, end) 处理，首尾相接不算冲突。
3. 营业时间、班次、排期粒度只在本文件定义。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TimeWindow:
    """半开时间窗 [start, end)。"""

    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def clamp(self, other: "TimeWindow") -> "TimeWindow":
        return TimeWindow(max(self.start, other.start), min(self.end, other.end))

    def __str__(self) -> str:
        if self.start.date() == self.end.date():
            return f"{self.start:%Y-%m-%d %H:%M}-{self.end:%H:%M}"
        return f"{self.start:%Y-%m-%d %H:%M}-{self.end:%Y-%m-%d %H:%M}"


class TimeConfig:
    """门店时间配置。"""

    BEIJING_TZ = timezone(timedelta(hours=8))

    # 营业时间与排期粒度
    OPEN_HOUR = 9
    CLOSE_HOUR = 20
    SLOT_MINUTES = 30

    # 同一工单内需要更换工位时的转移耗时（挪车 + 交接）
    TRANSFER_MINUTES = 5

    # 班次定义：(开始小时, 结束小时)
    SHIFT_WINDOWS: Dict[str, tuple] = {
        "早班": (9, 18),
        "晚班": (11, 20),
        "全天班": (9, 20),
    }

    # ------------------------------------------------------------ 当前时间
    @classmethod
    def now(cls) -> datetime:
        """当前北京时间（naive）。"""

        return datetime.now(cls.BEIJING_TZ).replace(tzinfo=None, microsecond=0)

    @classmethod
    def today(cls) -> datetime:
        """今天的 00:00。"""

        return cls.now().replace(hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def current_date_str(cls, format_str: str = "%Y年%m月%d日") -> str:
        return cls.now().strftime(format_str)

    @classmethod
    def current_datetime_str(cls, format_str: str = "%Y-%m-%d %H:%M") -> str:
        return cls.now().strftime(format_str)

    @classmethod
    def current_weekday_str(cls) -> str:
        return "周" + "一二三四五六日"[cls.now().weekday()]

    # ------------------------------------------------------------ 解析与格式化
    @classmethod
    def parse_datetime(
        cls, value: str | datetime | None, format_str: str = "%Y-%m-%d %H:%M"
    ) -> Optional[datetime]:
        """把各种写法解析成北京时间 naive datetime，失败返回 None。"""

        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None, microsecond=0)

        text = str(value).strip().replace("/", "-").replace("T", " ")
        if len(text) == 16 and text[13] == ":":
            text += ":00"

        candidates = [format_str, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H", "%Y-%m-%d", "%m-%d %H:%M"]
        seen = set()
        for fmt in candidates:
            if fmt in seen:
                continue
            seen.add(fmt)
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            if fmt == "%m-%d %H:%M":
                parsed = parsed.replace(year=cls.now().year)
            return parsed.replace(tzinfo=None, microsecond=0)
        return None

    @classmethod
    def format_datetime(cls, dt: datetime, format_str: str = "%Y-%m-%d %H:%M") -> str:
        if dt.tzinfo is not None:
            dt = dt.astimezone(cls.BEIJING_TZ).replace(tzinfo=None)
        return dt.strftime(format_str)

    @classmethod
    def friendly_datetime(cls, dt: datetime) -> str:
        """给车主看的时间描述，例如"今天 15:00"。"""

        today = cls.today()
        delta_days = (dt.replace(hour=0, minute=0, second=0, microsecond=0) - today).days
        if delta_days == 0:
            day_text = "今天"
        elif delta_days == 1:
            day_text = "明天"
        elif delta_days == 2:
            day_text = "后天"
        else:
            day_text = f"{dt.month}月{dt.day}日"
        return f"{day_text} {dt:%H:%M}"

    # ------------------------------------------------------------ 营业时间与班次
    @classmethod
    def get_business_hours(cls) -> tuple:
        return (cls.OPEN_HOUR, cls.CLOSE_HOUR)

    @classmethod
    def is_business_time(cls, dt: Optional[datetime] = None) -> bool:
        dt = dt or cls.now()
        return cls.OPEN_HOUR <= dt.hour < cls.CLOSE_HOUR

    @classmethod
    def business_window(cls, day: date | datetime) -> TimeWindow:
        """某天的营业时间窗。"""

        if isinstance(day, datetime):
            day = day.date()
        return TimeWindow(
            datetime.combine(day, time(hour=cls.OPEN_HOUR)),
            datetime.combine(day, time(hour=cls.CLOSE_HOUR)),
        )

    @classmethod
    def shift_window(cls, day: date | datetime, shift: str) -> TimeWindow:
        """某天某班次的可工作时间窗（与营业时间取交集）。"""

        if isinstance(day, datetime):
            day = day.date()
        start_hour, end_hour = cls.SHIFT_WINDOWS.get(shift, cls.SHIFT_WINDOWS["全天班"])
        shift_window = TimeWindow(
            datetime.combine(day, time(hour=start_hour)),
            datetime.combine(day, time(hour=end_hour)),
        )
        return shift_window.clamp(cls.business_window(day))

    @classmethod
    def generate_slot_starts(
        cls, day: date | datetime, step_minutes: Optional[int] = None
    ) -> List[datetime]:
        """生成某天所有候选排期起始时刻。"""

        step = step_minutes or cls.SLOT_MINUTES
        window = cls.business_window(day)
        slots: List[datetime] = []
        cursor = window.start
        while cursor < window.end:
            slots.append(cursor)
            cursor += timedelta(minutes=step)
        return slots

    @classmethod
    def ceil_to_slot(cls, dt: datetime, step_minutes: Optional[int] = None) -> datetime:
        """把时间向上对齐到排期粒度。"""

        step = step_minutes or cls.SLOT_MINUTES
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = int((dt - midnight).total_seconds() // 60)
        remainder = elapsed % step
        if remainder == 0:
            return midnight + timedelta(minutes=elapsed)
        return midnight + timedelta(minutes=elapsed + step - remainder)

    @classmethod
    def is_within_business_hours(cls, window: TimeWindow) -> bool:
        if window.start.date() != window.end.date():
            return False
        business = cls.business_window(window.start)
        return window.start >= business.start and window.end <= business.end


time_config = TimeConfig()