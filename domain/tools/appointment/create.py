"""
创建预约工具
"""
from typing import Optional
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repository.appointment_repository import AppointmentRepository
from infrastructure.database.models.appointment import AppointmentStatus
from infrastructure.external.java_service import JavaServiceClient
from app.core.config import settings


@tool
async def create_appointment(
    user_id: int,
    department: str,
    appointment_time: str,
    doctor_name: Optional[str] = None,
    notes: Optional[str] = None,
    session: Optional[AsyncSession] = None
) -> str:
    """
    创建预约
    
    Args:
        user_id: 用户ID
        department: 科室
        appointment_time: 预约时间（ISO格式字符串）
        doctor_name: 医生姓名（可选）
        notes: 备注（可选）
        session: 数据库会话（从上下文获取）
        
    Returns:
        成功消息字符串
    """
    if not session:
        raise ValueError("数据库会话未提供")
    
    # 如果配置了 Java 微服务，优先使用微服务
    if settings.JAVA_SERVICE_BASE_URL:
        try:
            client = JavaServiceClient()
            result = await client.create_appointment(
                user_id=user_id,
                department=department,
                appointment_time=appointment_time,
                doctor_name=doctor_name,
                notes=notes
            )
            return f"成功创建预约：{result}"
        except Exception as e:
            # 如果微服务调用失败，降级到本地数据库
            pass
    
    # 使用本地数据库创建预约
    from datetime import datetime
    try:
        appointment_datetime = datetime.fromisoformat(appointment_time.replace('Z', '+00:00'))
    except ValueError:
        return f"预约时间格式错误：{appointment_time}"
    
    repo = AppointmentRepository(session)
    appointment = await repo.create(
        user_id=user_id,
        department=department,
        doctor_name=doctor_name,
        appointment_time=appointment_datetime,
        status=AppointmentStatus.PENDING,
        notes=notes
    )
    
    await session.commit()
    
    return f"成功创建预约：科室 {department}，时间 {appointment_time}，医生 {doctor_name or '未指定'}"

