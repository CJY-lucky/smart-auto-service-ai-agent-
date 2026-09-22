"""测试环境准备。

关键点：在任何项目模块被导入之前，先把环境变量指向临时数据库，
并关闭大模型调用（没有 Key 时系统会自动走规则兜底），这样测试完全离线。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TEST_DIR = tempfile.mkdtemp(prefix="smart_auto_service_test_")
_TEST_DB = Path(_TEST_DIR) / "test.db"

os.environ["DATABASE_URL"] = "sqlite:///" + str(_TEST_DB).replace("\\", "/")
os.environ["MODEL_PROVIDER"] = "deepseek"
os.environ["LLM_API_KEY"] = ""
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["DEBUG"] = "false"

import pytest  # noqa: E402

from db.db_router import get_database_router  # noqa: E402
from services.bay_service import BayService  # noqa: E402
from services.technician_service import TechnicianService  # noqa: E402
from services.text_embedding import reset_embedder  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def prepare_environment():
    """初始化默认技师与工位。"""

    TechnicianService().initialize_default_technicians()
    BayService().initialize_default_bays()
    yield
    reset_embedder()


@pytest.fixture(autouse=True)
def clean_operational_data():
    """每个用例开始前清空工单与行为数据，保证排班结果可预期。"""

    router = get_database_router()
    router.work_orders.delete_all()
    with router.session_manager.session_scope() as session:
        from db.models import OwnerBehavior, OwnerPreference, OwnerReminder

        session.query(OwnerBehavior).delete()
        session.query(OwnerPreference).delete()
        session.query(OwnerReminder).delete()
    yield