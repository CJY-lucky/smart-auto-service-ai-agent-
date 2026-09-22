"""工位数据访问。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import ServiceBay


class BayRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _to_dict(bay: ServiceBay) -> Dict[str, Any]:
        return {
            "id": bay.id,
            "name": bay.name,
            "bay_type": bay.bay_type,
            "equipment": list(bay.equipment or []),
            "is_active": int(bay.is_active or 0),
        }

    def add_bay(self, name: str, bay_type: str, equipment: Optional[List[str]] = None) -> int:
        with self._session_factory() as session:
            existing = session.query(ServiceBay).filter(ServiceBay.name == name).one_or_none()
            if existing:
                return existing.id
            bay = ServiceBay(name=name, bay_type=bay_type, equipment=equipment or [], is_active=1)
            session.add(bay)
            session.commit()
            return bay.id

    def upsert_bay(self, name: str, bay_type: str, equipment: Optional[List[str]] = None) -> int:
        with self._session_factory() as session:
            bay = session.query(ServiceBay).filter(ServiceBay.name == name).one_or_none()
            if bay is None:
                bay = ServiceBay(name=name, is_active=1)
                session.add(bay)
            bay.bay_type = bay_type
            if equipment is not None:
                bay.equipment = equipment
            session.commit()
            return bay.id

    def update_bay(self, bay_id: int, **updates) -> bool:
        with self._session_factory() as session:
            bay = session.get(ServiceBay, bay_id)
            if not bay:
                return False
            for key in ("name", "bay_type", "equipment"):
                if key in updates and updates[key] is not None:
                    setattr(bay, key, updates[key])
            if "is_active" in updates and updates["is_active"] is not None:
                bay.is_active = 1 if updates["is_active"] else 0
            session.commit()
            return True

    def delete_bay(self, bay_id: int) -> bool:
        with self._session_factory() as session:
            bay = session.get(ServiceBay, bay_id)
            if not bay:
                return False
            bay.is_active = 0
            session.commit()
            return True

    def get_by_id(self, bay_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            bay = session.get(ServiceBay, bay_id)
            return self._to_dict(bay) if bay else None

    def list_bays(self, bay_type: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(ServiceBay).order_by(ServiceBay.id)
            if bay_type:
                query = query.filter(ServiceBay.bay_type == bay_type)
            if active_only:
                query = query.filter(ServiceBay.is_active == 1)
            return [self._to_dict(item) for item in query.all()]

    def count(self) -> int:
        with self._session_factory() as session:
            return session.query(ServiceBay).count()