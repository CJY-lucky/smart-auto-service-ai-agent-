"""推荐与提醒调度服务。

按固定时间点扫描所有车辆档案，把"该保养了""电瓶该换了"这类主动触达
生成出来。避免重复打扰：同一类提醒在 7 天内只发一次。
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import schedule

from config.time_config import time_config
from db.db_router import get_database_router
from services.vehicle_behavior_service import VehicleBehaviorService, fetch_weather_note

logger = logging.getLogger(__name__)

SCHEDULE_TIMES = ["09:00", "14:00", "19:00"]
DEDUPE_DAYS = 7


class RecommendationService:
    """主动提醒的生成与调度。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db = get_database_router(db_path)
        self.behavior_service = VehicleBehaviorService(db_path)
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- 生成
    def generate_reminders(self, *, force: bool = False, include_weather: bool = False) -> List[Dict[str, Any]]:
        """扫描所有车主，生成待发送提醒。"""

        created: List[Dict[str, Any]] = []
        weather_note = fetch_weather_note() if include_weather else None

        for owner in self.db.owners.list_owners():
            owner_ref = owner.get("phone") or owner.get("name") or "default_owner"
            for reminder in self.behavior_service.build_reminders(owner_ref):
                if not force and self.db.behaviors.has_recent_reminder(
                    owner_ref, reminder["reminder_type"], days=DEDUPE_DAYS
                ):
                    continue
                content = reminder["content"]
                if weather_note and reminder["reminder_type"] in {"maintenance", "battery", "tire"}:
                    content = f"{content} {weather_note}"
                reminder_id = self.db.behaviors.create_reminder(
                    owner_ref,
                    reminder["reminder_type"],
                    content,
                    vehicle_id=reminder.get("vehicle_id"),
                    due_date=reminder.get("due_date"),
                )
                created.append({**reminder, "id": reminder_id, "owner_ref": owner_ref})

        logger.info("本次生成 %s 条提醒", len(created))
        return created

    def pending_reminders(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        return self.db.behaviors.get_reminders(owner_ref, pending_only=True)

    def send_reminders(self, owner_ref: str = "default_owner") -> List[Dict[str, Any]]:
        """标记提醒为已发送（真实项目里对接短信/微信即可）。"""

        sent = []
        for reminder in self.pending_reminders(owner_ref):
            self.db.behaviors.mark_reminder_sent(reminder["id"])
            sent.append(reminder)
        return sent

    # ---------------------------------------------------------------- 调度
    def start_scheduler(self) -> bool:
        if self.is_running:
            logger.warning("提醒调度器已在运行")
            return False

        for moment in SCHEDULE_TIMES:
            schedule.every().day.at(moment).do(self._safe_generate)
        schedule.every(2).hours.do(self._safe_generate)

        self.is_running = True

        def loop() -> None:
            logger.info("提醒调度器已启动，计划时间点：%s", ", ".join(SCHEDULE_TIMES))
            while self.is_running:
                try:
                    schedule.run_pending()
                except Exception as exc:  # pragma: no cover
                    logger.error("调度任务执行失败：%s", exc)
                time.sleep(30)
            logger.info("提醒调度器已停止")

        self._thread = threading.Thread(target=loop, daemon=True, name="reminder-scheduler")
        self._thread.start()
        return True

    def stop_scheduler(self) -> bool:
        self.is_running = False
        schedule.clear()
        return True

    def _safe_generate(self) -> None:
        try:
            self.generate_reminders(include_weather=True)
        except Exception as exc:  # pragma: no cover
            logger.error("生成提醒失败：%s", exc)

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "thread_alive": bool(self._thread and self._thread.is_alive()),
            "scheduled_times": list(SCHEDULE_TIMES),
            "next_run": str(schedule.next_run()) if schedule.jobs else None,
            "total_jobs": len(schedule.jobs),
            "checked_at": time_config.current_datetime_str(),
        }