"""
日志中间件
"""
import logging
import time
import json
from typing import Dict, Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件"""
    
    async def dispatch(self, request: Request, call_next):
        """
        记录请求日志
        
        Args:
            request: FastAPI 请求对象
            call_next: 下一个中间件或路由处理函数
            
        Returns:
            响应对象
        """
        start_time = time.time()
        
        # 获取客户端信息
        client_host = request.client.host if request.client else 'unknown'
        client_port = request.client.port if request.client else None
        
        # 获取查询参数
        query_params = dict(request.query_params) if request.query_params else {}
        
        # 记录请求信息
        logger.info(
            f"[HTTP请求开始] {request.method} {request.url.path} - "
            f"客户端: {client_host}:{client_port if client_port else 'N/A'} - "
            f"查询参数: {query_params if query_params else '无'}"
        )
        
        # 对于 POST/PUT/PATCH 请求，尝试记录请求体（仅限 JSON）
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                # 读取请求体（注意：这会消耗请求体，需要保存以便后续使用）
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body.decode('utf-8'))
                        # 记录请求体（敏感信息可以脱敏）
                        logger.debug(f"[HTTP请求体] {request.method} {request.url.path} - body={body_json}")
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # 如果不是 JSON，记录为原始数据（截断）
                        body_preview = body[:200].decode('utf-8', errors='ignore')
                        logger.debug(f"[HTTP请求体] {request.method} {request.url.path} - body_preview={body_preview}")
                    
                    # 重新创建请求对象，因为 body 已被消耗
                    # 使用 Starlette 的标准方式重新设置请求体
                    async def receive():
                        return {"type": "http.request", "body": body}
                    
                    # 替换 request 的 _receive 方法
                    request._receive = receive
            except Exception as e:
                logger.warning(f"[HTTP请求体读取失败] {request.method} {request.url.path} - error={str(e)}")
        
        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 计算处理时间
            process_time = time.time() - start_time
            logger.error(
                f"[HTTP请求异常] {request.method} {request.url.path} - "
                f"异常: {str(e)} - "
                f"处理时间: {process_time:.3f}s",
                exc_info=True
            )
            raise
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 记录响应信息
        logger.info(
            f"[HTTP请求完成] {request.method} {request.url.path} - "
            f"状态码: {response.status_code} - "
            f"处理时间: {process_time:.3f}s"
        )
        
        return response

