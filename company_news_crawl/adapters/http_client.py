"""
HTTP 客户端适配器
"""
import httpx
import asyncio
import time
from typing import Optional, Tuple
from ..config import CrawlConfig


class HTTPClient:
    """HTTP 客户端封装"""
    
    def __init__(self, config: CrawlConfig):
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.last_request_time = 0.0
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.client = httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.client:
            await self.client.aclose()
    
    async def _respect_interval(self):
        """遵守请求间隔"""
        if self.config.request_interval > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.config.request_interval:
                await asyncio.sleep(self.config.request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def fetch(self, url: str) -> Tuple[Optional[str], int, Optional[str]]:
        """
        获取网页内容
        
        Returns:
            (html_content, status_code, error_message)
        """
        if not self.client:
            return None, 0, "Client not initialized"
        
        await self._respect_interval()
        
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.get(url)
                
                if response.status_code == 200:
                    try:
                        content = response.text
                        return content, response.status_code, None
                    except Exception as e:
                        return None, response.status_code, f"Decode error: {str(e)}"
                else:
                    return None, response.status_code, f"HTTP {response.status_code}"
                    
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                return None, 0, "Timeout"
            except httpx.ConnectError:
                return None, 0, "Connection error"
            except Exception as e:
                return None, 0, f"Error: {str(e)}"
        
        return None, 0, "Max retries exceeded"
    
    def fetch_sync(self, url: str) -> Tuple[Optional[str], int, Optional[str]]:
        """
        同步获取网页内容（用于同步上下文）
        
        Returns:
            (html_content, status_code, error_message)
        """
        for attempt in range(self.config.max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self.config.timeout,
                    follow_redirects=True,
                    headers={
                        "User-Agent": self.config.user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                ) as client:
                    if self.config.request_interval > 0 and attempt > 0:
                        time.sleep(self.config.request_interval)
                    
                    response = client.get(url)
                    
                    if response.status_code == 200:
                        try:
                            content = response.text
                            return content, response.status_code, None
                        except Exception as e:
                            return None, response.status_code, f"Decode error: {str(e)}"
                    else:
                        return None, response.status_code, f"HTTP {response.status_code}"
                        
            except httpx.TimeoutException:
                if attempt < self.config.max_retries:
                    time.sleep(1 * (attempt + 1))
                    continue
                return None, 0, "Timeout"
            except httpx.ConnectError:
                return None, 0, "Connection error"
            except Exception as e:
                return None, 0, f"Error: {str(e)}"
        
        return None, 0, "Max retries exceeded"
