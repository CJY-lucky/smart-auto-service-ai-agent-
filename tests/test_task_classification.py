"""任务分类 Agent 测试。"""

from __future__ import annotations

from agents.task_classification.task_classifier import TaskClassifier


def test_rule_classifier_distinguishes_intents():
    classifier = TaskClassifier(None)

    assert classifier.classify_rules("明天上午10点帮我预约换机油")["category"] == "booking"
    assert classifier.classify_rules("换一次机油多少钱")["category"] == "consult"
    assert classifier.classify_rules("帮我查一下我的车辆档案和保养记录")["category"] == "vehicle_profile"
    assert classifier.classify_rules("看看我平时的用车习惯和偏好")["category"] == "behavior"
    assert classifier.classify_rules("今天天气怎么样")["category"] == "other"


def test_classification_result_has_confidence_and_reason():
    classifier = TaskClassifier(None)
    result = classifier.classify_rules("刹车有异响是怎么回事")

    assert result["category"] == "consult"
    assert 0 < result["confidence"] <= 1
    assert result["reason"]


async def test_agent_routes_booking_request_end_to_end():
    from agents.consultant_agent import ConsultantAgent
    from agents.service_booking_agent import ServiceBookingAgent
    from agents.task_classification_agent import TaskClassificationAgent
    from agents.vehicle_behavior_agent import VehicleBehaviorAgent
    from services.work_order_service import WorkOrderService

    agent = TaskClassificationAgent(
        ServiceBookingAgent(), ConsultantAgent(), VehicleBehaviorAgent()
    )

    chunks = []
    async for token in agent.classify_task_stream("明天上午11点，京D20001，换机油"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "[REPLY]" in reply
    assert "预约成功" in reply
    assert WorkOrderService().db.work_orders.count_active() == 1


async def test_agent_routes_consultation_to_knowledge_answer():
    from agents.consultant_agent import ConsultantAgent
    from agents.service_booking_agent import ServiceBookingAgent
    from agents.task_classification_agent import TaskClassificationAgent
    from agents.vehicle_behavior_agent import VehicleBehaviorAgent

    agent = TaskClassificationAgent(
        ServiceBookingAgent(), ConsultantAgent(), VehicleBehaviorAgent()
    )

    chunks = []
    async for token in agent.classify_task_stream("换一次机油大概多少钱"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "380" in reply


async def test_unrelated_question_is_politely_refused():
    from agents.consultant_agent import ConsultantAgent
    from agents.service_booking_agent import ServiceBookingAgent
    from agents.task_classification_agent import TaskClassificationAgent
    from agents.vehicle_behavior_agent import VehicleBehaviorAgent

    agent = TaskClassificationAgent(
        ServiceBookingAgent(), ConsultantAgent(), VehicleBehaviorAgent()
    )

    chunks = []
    async for token in agent.classify_task_stream("给我讲讲今天的股票行情吧"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "保养" in reply
    assert "股票" not in reply.replace("股票行情", "")