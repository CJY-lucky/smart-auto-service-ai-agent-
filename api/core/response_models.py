"""API 请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.time_config import time_config


class BaseResponse(BaseModel):
    message: str = "ok"
    success: bool = True
    timestamp: datetime = Field(default_factory=time_config.now)


class DataResponse(BaseResponse):
    data: Any = None


class TaskClassificationRequest(BaseModel):
    text: str
    owner_ref: str = "default_owner"


class ChatRequest(BaseModel):
    message: str
    owner_ref: str = "default_owner"


class ConsultationRequest(BaseModel):
    question: str
    owner_ref: str = "default_owner"


class QuoteRequest(BaseModel):
    item_codes: List[str]
    start_time: str
    plate_no: Optional[str] = None
    technician_name: Optional[str] = None
    technician_id: Optional[int] = None
    preference: Optional[str] = None


class BookingRequest(BaseModel):
    item_codes: List[str]
    start_time: str
    owner_ref: str = "default_owner"
    plate_no: Optional[str] = None
    vehicle_model: Optional[str] = None
    mileage: Optional[int] = None
    oil_spec: Optional[str] = None
    technician_id: Optional[int] = None
    bay_id: Optional[int] = None
    preference: Optional[str] = None
    notes: Optional[str] = None
    session_id: Optional[str] = None


class RescheduleRequest(BaseModel):
    start_time: str
    technician_id: Optional[int] = None
    bay_id: Optional[int] = None


class CompleteRequest(BaseModel):
    mileage: Optional[int] = None
    amount: Optional[float] = None


class TechnicianRequest(BaseModel):
    name: str
    gender: Optional[str] = None
    level: Optional[str] = None
    certifications: Optional[List[str]] = None
    specialties: Optional[str] = None
    shift: Optional[str] = None
    is_active: Optional[bool] = None


class BayRequest(BaseModel):
    name: str
    bay_type: str
    equipment: Optional[List[str]] = None
    is_active: Optional[bool] = None


class VehicleRequest(BaseModel):
    owner_ref: str = "default_owner"
    owner_name: Optional[str] = None
    plate_no: str
    model: Optional[str] = None
    brand: Optional[str] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    oil_spec: Optional[str] = None
    last_service_date: Optional[str] = None
    last_service_mileage: Optional[int] = None
    purchase_date: Optional[str] = None


class KnowledgeRequest(BaseModel):
    content: str
    category: str
    keywords: Optional[List[str]] = None


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 3


class ReminderRequest(BaseModel):
    owner_ref: str = "default_owner"
    include_weather: bool = False