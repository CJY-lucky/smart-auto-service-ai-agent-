"""数据访问层抽象接口。

定义 Repository 需要提供的能力边界，便于替换实现（例如未来换 PostgreSQL
或加缓存层）时保持上层代码不变。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


class BaseTechnicianRepository(ABC):
    @abstractmethod
    def add_technician(self, name: str, **fields) -> int: ...

    @abstractmethod
    def get_by_id(self, technician_id: int) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_technicians(self, active_only: bool = True) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def update_technician(self, technician_id: int, **updates) -> bool: ...

    @abstractmethod
    def delete_technician(self, technician_id: int) -> bool: ...


class BaseBayRepository(ABC):
    @abstractmethod
    def add_bay(self, name: str, bay_type: str, equipment: Optional[List[str]] = None) -> int: ...

    @abstractmethod
    def get_by_id(self, bay_id: int) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_bays(self, bay_type: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]: ...


class BaseWorkOrderRepository(ABC):
    @abstractmethod
    def create_order(self, **fields) -> int: ...

    @abstractmethod
    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def list_orders(self, **filters) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def is_technician_available(
        self, technician_id: int, start_time: datetime, end_time: datetime, exclude_order_id: Optional[int] = None
    ) -> bool: ...

    @abstractmethod
    def is_bay_available(
        self, bay_id: int, start_time: datetime, end_time: datetime, exclude_order_id: Optional[int] = None
    ) -> bool: ...