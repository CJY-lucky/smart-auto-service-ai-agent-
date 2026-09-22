"""SQLAlchemy 数据模型。

围绕五个核心对象组织：车主 Owner、车辆 Vehicle、工单 WorkOrder、
技师 Technician、工位 ServiceBay。工单同时引用技师与工位，这对"双资源占用"
是整个项目的业务约束基础。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Owner(Base):
    """车主。"""

    __tablename__ = "owners"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    phone = Column(String(32), nullable=True)
    remark = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")


class Vehicle(Base):
    """车辆档案。"""

    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)
    plate_no = Column(String(32), unique=True, nullable=False)
    model = Column(String(64), nullable=True)
    brand = Column(String(64), nullable=True)
    year = Column(Integer, nullable=True)
    mileage = Column(Integer, nullable=True)
    oil_spec = Column(String(64), nullable=True)
    last_service_date = Column(DateTime, nullable=True)
    last_service_mileage = Column(Integer, nullable=True)
    purchase_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    owner = relationship("Owner", back_populates="vehicles")


class Technician(Base):
    """技师。"""

    __tablename__ = "technicians"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    gender = Column(String(8), nullable=True)
    level = Column(String(16), nullable=True)  # 初级 / 中级 / 高级
    certifications = Column(JSON, nullable=True)  # 资质列表
    specialties = Column(String(255), nullable=True)  # 专长描述（用于相似度匹配）
    shift = Column(String(16), nullable=True)  # 班次
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class ServiceBay(Base):
    """工位。"""

    __tablename__ = "service_bays"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    bay_type = Column(String(32), nullable=False)
    equipment = Column(JSON, nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class WorkOrder(Base):
    """保养工单。

    时间窗为半开区间 [start_time, end_time)：在这段时间内，technician_id 与
    bay_id 两个资源同时被占用。
    """

    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True)
    order_no = Column(String(32), unique=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("owners.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    bay_id = Column(Integer, ForeignKey("service_bays.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(16), nullable=False, default="created")
    item_codes = Column(JSON, nullable=False, default=list)
    # 分段工位计划：[{item_code, bay_id, bay_name, bay_type, start, end}]
    # 一个工单内如果需要跨工位（例如换胎后做四轮定位），用这张计划记录每个项目占用的工位与时段
    bay_plan = Column(JSON, nullable=True)
    estimated_minutes = Column(Integer, nullable=False, default=0)
    amount = Column(Float, nullable=False, default=0.0)
    mileage = Column(Integer, nullable=True)
    notes = Column(String(255), nullable=True)
    session_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at = Column(DateTime, nullable=True)

    technician = relationship("Technician")
    bay = relationship("ServiceBay")
    vehicle = relationship("Vehicle")
    owner = relationship("Owner")


class WorkOrderItem(Base):
    """工单明细（记录实际执行的项目、工时与金额）。"""

    __tablename__ = "work_order_items"

    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=False)
    item_code = Column(String(32), nullable=False)
    item_name = Column(String(64), nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=0)
    amount = Column(Float, nullable=False, default=0.0)
    sequence = Column(Integer, nullable=False, default=0)


class KnowledgeDocument(Base):
    """知识库文档。"""

    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    category = Column(String(64), nullable=False)
    keywords = Column(JSON, nullable=True)
    embedding = Column(JSON, nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class EmbeddingCache(Base):
    """Embedding 缓存：同样的文本不重复调用向量接口。"""

    __tablename__ = "embedding_cache"
    __table_args__ = (UniqueConstraint("text_hash", "model", name="uq_embedding_text_model"),)

    id = Column(Integer, primary_key=True)
    text_hash = Column(String(64), nullable=False)
    model = Column(String(128), nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class OwnerBehavior(Base):
    """车主行为记录。"""

    __tablename__ = "owner_behaviors"

    id = Column(Integer, primary_key=True)
    owner_id = Column(String(64), nullable=False, default="default_owner")
    action_type = Column(String(32), nullable=False)
    action_data = Column(JSON, nullable=True)
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    session_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class OwnerPreference(Base):
    """车主偏好（技师、项目、时段、价格敏感度等）。"""

    __tablename__ = "owner_preferences"
    __table_args__ = (
        UniqueConstraint("owner_id", "preference_type", "preference_value", name="uq_owner_pref"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(String(64), nullable=False, default="default_owner")
    preference_type = Column(String(32), nullable=False)
    preference_value = Column(String(128), nullable=False)
    confidence_score = Column(Integer, default=1)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class OwnerReminder(Base):
    """主动提醒 / 推荐。"""

    __tablename__ = "owner_reminders"

    id = Column(Integer, primary_key=True)
    owner_id = Column(String(64), nullable=False, default="default_owner")
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    reminder_type = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    due_date = Column(DateTime, nullable=True)
    is_sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    sent_at = Column(DateTime, nullable=True)