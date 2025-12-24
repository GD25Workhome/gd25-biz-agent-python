"""
Java 微服务客户端
用于调用 Java 微服务的接口
"""
from typing import Optional, Dict, Any
import httpx
from app.core.config import settings


class JavaServiceClient:
    """Java 微服务客户端"""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30
    ):
        """
        初始化 Java 微服务客户端
        
        Args:
            base_url: 服务基础URL，如果不提供则使用配置中的URL
            timeout: 请求超时时间（秒）
        
        Raises:
            ValueError: 如果 base_url 和配置中的 URL 都为 None
        """
        if base_url is not None:
            self.base_url = base_url
        elif settings.JAVA_SERVICE_BASE_URL is not None:
            self.base_url = settings.JAVA_SERVICE_BASE_URL
        else:
            raise ValueError("Java 微服务 URL 未配置，请设置 JAVA_SERVICE_BASE_URL 或传入 base_url 参数")
        
        self.timeout = timeout if timeout else settings.JAVA_SERVICE_TIMEOUT

