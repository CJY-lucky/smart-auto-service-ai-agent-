"""FastAPI 应用入口。

启动时会：
1. 初始化知识库（必要时写入默认门店知识）与向量索引；
2. 初始化默认技师与工位；
3. 按需启动提醒调度器。

注意：必须在仓库根目录启动（SQLite 的相对路径依赖工作目录）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import api_routers
from api.core.exceptions import BusinessException, api_exception_handler, general_exception_handler
from config.settings import settings
from services.bay_service import BayService
from services.knowledge_service import KnowledgeService
from services.recommendation_service import RecommendationService
from services.technician_service import TechnicianService
from web import router as web_router

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_scheduler: RecommendationService | None = None


async def initialize_system() -> None:
    """初始化数据库种子数据与索引。"""

    global _scheduler

    logger.info("正在初始化智能保养预约系统……")

    knowledge_service = KnowledgeService()
    await knowledge_service.initialize()
    logger.info("知识库就绪，共 %s 条", knowledge_service.get_documents_count())

    TechnicianService().initialize_default_technicians()
    BayService().initialize_default_bays()
    logger.info("技师与工位数据就绪")

    if settings.enable_scheduler:
        _scheduler = RecommendationService()
        _scheduler.start_scheduler()
        logger.info("提醒调度器已启动")
    else:
        logger.info("提醒调度器未启用（ENABLE_SCHEDULER=false）")

    logger.info("系统初始化完成")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_system()
    yield
    if _scheduler is not None:
        _scheduler.stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="智保养 · 门店智能服务 Agent",
        description=(
            "面向汽车快修保养门店的智能预约与咨询系统：意图识别、RAG 知识问答、"
            "技师与工位双资源排班、工单管理、车辆档案与车主行为分析。"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(BusinessException, api_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)

    for router in api_routers:
        app.include_router(router)

    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)