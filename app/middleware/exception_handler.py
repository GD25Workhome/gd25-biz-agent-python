"""
异常处理中间件
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    Args:
        request: FastAPI 请求对象
        exc: 异常对象
        
    Returns:
        JSON 响应
    """
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "内部服务器错误",
            "detail": str(exc) if logger.level == logging.DEBUG else "请查看服务器日志"
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    请求验证异常处理器
    
    Args:
        request: FastAPI 请求对象
        exc: 验证异常对象
        
    Returns:
        JSON 响应
    """
    logger.warning(f"请求验证失败: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "请求验证失败",
            "detail": exc.errors()
        }
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    HTTP 异常处理器
    
    Args:
        request: FastAPI 请求对象
        exc: HTTP 异常对象
        
    Returns:
        JSON 响应
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail
        }
    )

