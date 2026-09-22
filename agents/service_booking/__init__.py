"""预约工单 Agent 的组件。

- InputParser：口语 -> 结构化预约意图
- VehicleRecognizer：车牌/车型 -> 车辆档案
- BookingProcessor：流程状态机
- MessageBuilder：文案
- BookingDatabase：数据操作（经 Services 层）
"""

from .booking_database import BookingDatabase
from .booking_processor import BookingProcessor
from .input_parser import InputParser
from .message_builder import MessageBuilder
from .vehicle_recognizer import VehicleRecognizer

__all__ = [
    "BookingDatabase",
    "BookingProcessor",
    "InputParser",
    "MessageBuilder",
    "VehicleRecognizer",
]