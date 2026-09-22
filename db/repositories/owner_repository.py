"""车主数据访问。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from db.models import Owner


class OwnerRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _to_dict(owner: Owner) -> Dict[str, Any]:
        return {
            "id": owner.id,
            "name": owner.name,
            "phone": owner.phone or "",
            "remark": owner.remark or "",
            "created_at": owner.created_at,
        }

    def ensure_owner(self, owner_ref: str, name: Optional[str] = None) -> int:
        """按外部标识（手机号/名字/默认ID）确保车主存在，返回自增主键。"""

        owner_ref = (owner_ref or "default_owner").strip()
        with self._session_factory() as session:
            owner = None
            if owner_ref.isdigit():
                owner = session.query(Owner).filter(Owner.phone == owner_ref).one_or_none()
            if owner is None:
                owner = session.query(Owner).filter(Owner.name == owner_ref).one_or_none()
            if owner is None:
                owner = Owner(name=name or owner_ref, phone=owner_ref if owner_ref.isdigit() else None)
                session.add(owner)
                session.commit()
            return owner.id

    def get_by_id(self, owner_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            owner = session.get(Owner, owner_id)
            return self._to_dict(owner) if owner else None

    def get_by_ref(self, owner_ref: str) -> Optional[Dict[str, Any]]:
        owner_ref = (owner_ref or "").strip()
        with self._session_factory() as session:
            owner = session.query(Owner).filter(Owner.name == owner_ref).one_or_none()
            if owner is None and owner_ref.isdigit():
                owner = session.query(Owner).filter(Owner.phone == owner_ref).one_or_none()
            return self._to_dict(owner) if owner else None

    def list_owners(self) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            return [self._to_dict(item) for item in session.query(Owner).order_by(Owner.id).all()]

    def update_owner(self, owner_id: int, **updates) -> bool:
        with self._session_factory() as session:
            owner = session.get(Owner, owner_id)
            if not owner:
                return False
            for key in ("name", "phone", "remark"):
                if key in updates and updates[key] is not None:
                    setattr(owner, key, updates[key])
            session.commit()
            return True