"""技师数据访问。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import Technician


class TechnicianRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    # -- 内部工具 -------------------------------------------------------
    def _session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _to_dict(technician: Technician) -> Dict[str, Any]:
        return {
            "id": technician.id,
            "name": technician.name,
            "gender": technician.gender or "",
            "level": technician.level or "",
            "certifications": list(technician.certifications or []),
            "specialties": technician.specialties or "",
            "shift": technician.shift or "全天班",
            "is_active": int(technician.is_active or 0),
        }

    # -- 写操作 ---------------------------------------------------------
    def add_technician(self, name: str, **fields) -> int:
        with self._session_factory() as session:
            existing = session.query(Technician).filter(Technician.name == name).one_or_none()
            if existing:
                return existing.id
            technician = Technician(
                name=name,
                gender=fields.get("gender"),
                level=fields.get("level"),
                certifications=fields.get("certifications") or [],
                specialties=fields.get("specialties"),
                shift=fields.get("shift"),
                is_active=1 if fields.get("is_active", True) else 0,
            )
            session.add(technician)
            session.commit()
            return technician.id

    def update_technician(self, technician_id: int, **updates) -> bool:
        with self._session_factory() as session:
            technician = session.get(Technician, technician_id)
            if not technician:
                return False
            for key in ("name", "gender", "level", "certifications", "specialties", "shift"):
                if key in updates and updates[key] is not None:
                    setattr(technician, key, updates[key])
            if "is_active" in updates and updates["is_active"] is not None:
                technician.is_active = 1 if updates["is_active"] else 0
            session.commit()
            return True

    def upsert_technician(self, name: str, **fields) -> int:
        """按姓名存在即更新，不存在则新建。用于初始化默认技师。"""

        with self._session_factory() as session:
            technician = session.query(Technician).filter(Technician.name == name).one_or_none()
            if technician is None:
                technician = Technician(name=name, is_active=1)
                session.add(technician)
            for key in ("gender", "level", "certifications", "specialties", "shift"):
                if key in fields and fields[key] is not None:
                    setattr(technician, key, fields[key])
            session.commit()
            return technician.id

    def delete_technician(self, technician_id: int) -> bool:
        with self._session_factory() as session:
            technician = session.get(Technician, technician_id)
            if not technician:
                return False
            technician.is_active = 0
            session.commit()
            return True

    # -- 读操作 ---------------------------------------------------------
    def get_by_id(self, technician_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            technician = session.get(Technician, technician_id)
            return self._to_dict(technician) if technician else None

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        with self._session_factory() as session:
            technician = session.query(Technician).filter(Technician.name == name.strip()).one_or_none()
            return self._to_dict(technician) if technician else None

    def list_technicians(self, active_only: bool = True) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            query = session.query(Technician).order_by(Technician.id)
            if active_only:
                query = query.filter(Technician.is_active == 1)
            return [self._to_dict(item) for item in query.all()]

    def search_by_name(self, keyword: str) -> List[Dict[str, Any]]:
        if not keyword:
            return []
        with self._session_factory() as session:
            rows = (
                session.query(Technician)
                .filter(Technician.name.like(f"%{keyword.strip()}%"))
                .all()
            )
            return [self._to_dict(item) for item in rows]

    def count(self) -> int:
        with self._session_factory() as session:
            return session.query(Technician).count()