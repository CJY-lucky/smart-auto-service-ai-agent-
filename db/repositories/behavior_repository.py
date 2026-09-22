"""车主行为、偏好与提醒的数据访问。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from db.models import OwnerBehavior, OwnerPreference, OwnerReminder


class BehaviorRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # -- 行为记录 -------------------------------------------------------
    def record_behavior(
        self,
        owner_id: str,
        action_type: str,
        action_data: Optional[Dict[str, Any]] = None,
        technician_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        with self._session_factory() as session:
            behavior = OwnerBehavior(
                owner_id=owner_id or "default_owner",
                action_type=action_type,
                action_data=action_data or {},
                technician_id=technician_id,
                vehicle_id=vehicle_id,
                session_id=session_id,
            )
            session.add(behavior)
            session.commit()
            return behavior.id

    def get_behaviors(
        self,
        owner_id: str = "default_owner",
        action_type: Optional[str] = None,
        days_back: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(OwnerBehavior).filter(OwnerBehavior.owner_id == owner_id)
            if action_type:
                query = query.filter(OwnerBehavior.action_type == action_type)
            if days_back:
                since = datetime.now() - timedelta(days=days_back)
                query = query.filter(OwnerBehavior.created_at >= since)
            query = query.order_by(OwnerBehavior.created_at.desc())
            if limit:
                query = query.limit(limit)
            return [
                {
                    "id": row.id,
                    "owner_id": row.owner_id,
                    "action_type": row.action_type,
                    "action_data": row.action_data or {},
                    "technician_id": row.technician_id,
                    "vehicle_id": row.vehicle_id,
                    "session_id": row.session_id,
                    "created_at": row.created_at,
                }
                for row in query.all()
            ]

    def count_behaviors(self, owner_id: str = "default_owner") -> int:
        with self._session_factory() as session:
            return (
                session.query(OwnerBehavior).filter(OwnerBehavior.owner_id == owner_id).count()
            )

    # -- 偏好 -----------------------------------------------------------
    def upsert_preference(
        self,
        owner_id: str,
        preference_type: str,
        preference_value: str,
        *,
        increment: int = 1,
    ) -> int:
        with self._session_factory() as session:
            row = (
                session.query(OwnerPreference)
                .filter(OwnerPreference.owner_id == owner_id)
                .filter(OwnerPreference.preference_type == preference_type)
                .filter(OwnerPreference.preference_value == preference_value)
                .one_or_none()
            )
            if row is None:
                row = OwnerPreference(
                    owner_id=owner_id,
                    preference_type=preference_type,
                    preference_value=preference_value,
                    confidence_score=max(increment, 1),
                )
                session.add(row)
            else:
                row.confidence_score = (row.confidence_score or 0) + increment
            session.commit()
            return row.id

    def get_preferences(
        self, owner_id: str = "default_owner", preference_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(OwnerPreference).filter(OwnerPreference.owner_id == owner_id)
            if preference_type:
                query = query.filter(OwnerPreference.preference_type == preference_type)
            query = query.order_by(OwnerPreference.confidence_score.desc())
            return [
                {
                    "preference_type": row.preference_type,
                    "preference_value": row.preference_value,
                    "confidence_score": row.confidence_score,
                    "last_updated": row.last_updated,
                }
                for row in query.all()
            ]

    # -- 提醒 -----------------------------------------------------------
    def create_reminder(
        self,
        owner_id: str,
        reminder_type: str,
        content: str,
        *,
        vehicle_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
    ) -> int:
        with self._session_factory() as session:
            reminder = OwnerReminder(
                owner_id=owner_id,
                reminder_type=reminder_type,
                content=content,
                vehicle_id=vehicle_id,
                due_date=due_date,
            )
            session.add(reminder)
            session.commit()
            return reminder.id

    def get_reminders(
        self,
        owner_id: str = "default_owner",
        *,
        pending_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(OwnerReminder).filter(OwnerReminder.owner_id == owner_id)
            if pending_only:
                query = query.filter(OwnerReminder.is_sent == 0)
            query = query.order_by(OwnerReminder.created_at.desc()).limit(limit)
            return [
                {
                    "id": row.id,
                    "owner_id": row.owner_id,
                    "vehicle_id": row.vehicle_id,
                    "reminder_type": row.reminder_type,
                    "content": row.content,
                    "due_date": row.due_date,
                    "is_sent": int(row.is_sent or 0),
                    "created_at": row.created_at,
                    "sent_at": row.sent_at,
                }
                for row in query.all()
            ]

    def mark_reminder_sent(self, reminder_id: int) -> bool:
        with self._session_factory() as session:
            reminder = session.get(OwnerReminder, reminder_id)
            if not reminder:
                return False
            reminder.is_sent = 1
            reminder.sent_at = datetime.now()
            session.commit()
            return True

    def has_recent_reminder(self, owner_id: str, reminder_type: str, days: int = 7) -> bool:
        since = datetime.now() - timedelta(days=days)
        with self._session_factory() as session:
            row = (
                session.query(OwnerReminder)
                .filter(OwnerReminder.owner_id == owner_id)
                .filter(OwnerReminder.reminder_type == reminder_type)
                .filter(OwnerReminder.created_at >= since)
                .first()
            )
            return row is not None