"""车辆档案数据访问。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from db.models import Vehicle


class VehicleRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _to_dict(vehicle: Vehicle) -> Dict[str, Any]:
        return {
            "id": vehicle.id,
            "owner_id": vehicle.owner_id,
            "plate_no": vehicle.plate_no,
            "model": vehicle.model or "",
            "brand": vehicle.brand or "",
            "year": vehicle.year,
            "mileage": vehicle.mileage,
            "oil_spec": vehicle.oil_spec or "",
            "last_service_date": vehicle.last_service_date,
            "last_service_mileage": vehicle.last_service_mileage,
            "purchase_date": vehicle.purchase_date,
            "created_at": vehicle.created_at,
            "updated_at": vehicle.updated_at,
        }

    def add_vehicle(
        self,
        owner_id: int,
        plate_no: str,
        *,
        model: Optional[str] = None,
        brand: Optional[str] = None,
        year: Optional[int] = None,
        mileage: Optional[int] = None,
        oil_spec: Optional[str] = None,
        last_service_date: Optional[datetime] = None,
        last_service_mileage: Optional[int] = None,
        purchase_date: Optional[datetime] = None,
    ) -> int:
        with self._session_factory() as session:
            vehicle = Vehicle(
                owner_id=owner_id,
                plate_no=plate_no.strip(),
                model=model,
                brand=brand,
                year=year,
                mileage=mileage,
                oil_spec=oil_spec,
                last_service_date=last_service_date,
                last_service_mileage=last_service_mileage,
                purchase_date=purchase_date,
            )
            session.add(vehicle)
            session.commit()
            return vehicle.id

    def get_by_id(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        with self._session_factory() as session:
            vehicle = session.get(Vehicle, vehicle_id)
            return self._to_dict(vehicle) if vehicle else None

    def get_by_plate(self, plate_no: str) -> Optional[Dict[str, Any]]:
        if not plate_no:
            return None
        with self._session_factory() as session:
            vehicle = (
                session.query(Vehicle)
                .filter(Vehicle.plate_no == plate_no.strip().upper())
                .one_or_none()
            )
            if vehicle is None:
                vehicle = (
                    session.query(Vehicle)
                    .filter(Vehicle.plate_no == plate_no.strip())
                    .one_or_none()
                )
            return self._to_dict(vehicle) if vehicle else None

    def list_by_owner(self, owner_id: int) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.query(Vehicle).filter(Vehicle.owner_id == owner_id).all()
            return [self._to_dict(item) for item in rows]

    def list_vehicles(self) -> List[Dict[str, Any]]:
        with self._session_factory() as session:
            return [self._to_dict(item) for item in session.query(Vehicle).order_by(Vehicle.id).all()]

    def update_vehicle(self, vehicle_id: int, **updates) -> bool:
        with self._session_factory() as session:
            vehicle = session.get(Vehicle, vehicle_id)
            if not vehicle:
                return False
            for key in (
                "plate_no",
                "model",
                "brand",
                "year",
                "mileage",
                "oil_spec",
                "last_service_date",
                "last_service_mileage",
                "purchase_date",
            ):
                if key in updates and updates[key] is not None:
                    setattr(vehicle, key, updates[key])
            session.commit()
            return True