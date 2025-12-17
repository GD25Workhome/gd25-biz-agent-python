"""
Java 微服务客户端
用于调用 Java 微服务的预约相关接口
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
            base_url: 服务基础URL，默认使用配置中的URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url or settings.JAVA_SERVICE_BASE_URL
        self.timeout = timeout or settings.JAVA_SERVICE_TIMEOUT
    
    async def create_appointment(
        self,
        user_id: str,
        department: str,
        appointment_time: str,
        doctor_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建预约（调用 Java 微服务）
        
        Args:
            user_id: 用户ID
            department: 科室
            appointment_time: 预约时间（ISO格式字符串）
            doctor_name: 医生姓名（可选）
            notes: 备注（可选）
            
        Returns:
            预约信息字典
            
        Raises:
            httpx.HTTPError: HTTP 请求错误
        """
        if not self.base_url:
            raise ValueError("Java 微服务 URL 未配置")
        
        url = f"{self.base_url}/api/appointments"
        payload = {
            "userId": user_id,
            "department": department,
            "appointmentTime": appointment_time,
            "doctorName": doctor_name,
            "notes": notes
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    
    async def query_appointment(
        self,
        user_id: str,
        appointment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询预约（调用 Java 微服务）
        
        Args:
            user_id: 用户ID
            appointment_id: 预约ID（可选，如果不提供则查询用户所有预约）
            
        Returns:
            预约信息字典或列表
            
        Raises:
            httpx.HTTPError: HTTP 请求错误
        """
        if not self.base_url:
            raise ValueError("Java 微服务 URL 未配置")
        
        if appointment_id:
            url = f"{self.base_url}/api/appointments/{appointment_id}"
        else:
            url = f"{self.base_url}/api/appointments?userId={user_id}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    
    async def update_appointment(
        self,
        appointment_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        更新预约（调用 Java 微服务）
        
        Args:
            appointment_id: 预约ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的预约信息字典
            
        Raises:
            httpx.HTTPError: HTTP 请求错误
        """
        if not self.base_url:
            raise ValueError("Java 微服务 URL 未配置")
        
        url = f"{self.base_url}/api/appointments/{appointment_id}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(url, json=kwargs)
            response.raise_for_status()
            return response.json()

