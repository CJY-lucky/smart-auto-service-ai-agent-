"""RAG 咨询与知识库测试。"""

from __future__ import annotations

from agents.consultant_agent import ConsultantAgent
from services.knowledge_service import KnowledgeService


async def test_knowledge_service_seeds_and_searches():
    service = KnowledgeService()
    await service.initialize()

    assert service.get_documents_count() >= 10
    results = await service.search("机油多久换一次", top_k=3)

    assert results
    assert any("保养周期" in (item.get("category") or "") or "机油" in item["content"] for item in results)


async def test_consultant_answers_from_knowledge_base():
    agent = ConsultantAgent()

    chunks = []
    async for token in agent.consult_stream("换机油大概多少钱"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "380" in reply


async def test_safety_critical_question_gets_explicit_warning():
    agent = ConsultantAgent()

    chunks = []
    async for token in agent.consult_stream("仪表盘机油灯红灯亮了还能继续开吗"):
        chunks.append(token)
    reply = "".join(chunks)

    assert "靠边停车" in reply or "停车" in reply


async def test_consultation_records_behavior():
    from services.vehicle_behavior_service import VehicleBehaviorService

    agent = ConsultantAgent()
    async for _ in agent.consult_stream("刹车油多久换一次"):
        pass

    behaviors = VehicleBehaviorService().get_behaviors("default_owner", action_type="consultation")
    assert behaviors
    assert behaviors[0]["action_data"]["categories"]