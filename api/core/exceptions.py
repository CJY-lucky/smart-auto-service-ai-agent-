"""API 异常与处理器。"""

from __future__ import annotations

import logging
import traceback

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class BusinessException(HTTPException):
    """业务异常。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=message)


class NotFoundException(BusinessException):
    """资源不存在。"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, status_code=404)


async def api_exception_handler(request: Request, exc: BusinessException):
    logger.warning("业务异常：%s", exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail, "success": False})


async def general_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常：%s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"error": "服务器内部错误", "success": False})