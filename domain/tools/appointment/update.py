"""
更新预约工具
"""
from typing import Optional
from langchain_core.tools import tool
from datetime import datetime

from infrastructure.database.repository.appointment_repository import AppointmentRepository
from infrastructure.database.models.appointment import AppointmentStatus
from infrastructure.external.java_service import JavaServiceClient
from infrastructure.database.connection import get_async_session_factory
from app.core.config import settings


@tool
async def update_appointment(
    appointment_id: str,
    department: Optional[str] = None,
    appointment_time: Optional[str] = None,
    doctor_name: Optional[str] = None,
    status: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    更新预约
    
    Args:
        appointment_id: 预约ID
        department: 科室（可选）
        appointment_time: 预约时间（ISO格式字符串，可选）
        doctor_name: 医生姓名（可选）
        status: 预约状态（可选：pending, confirmed, completed, cancelled）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 如果配置了 Java 微服务，必须使用微服务
    if settings.JAVA_SERVICE_BASE_URL:
        client = JavaServiceClient()
        update_fields = {}
        if department:
            update_fields["department"] = department
        if appointment_time:
            update_fields["appointmentTime"] = appointment_time
        if doctor_name:
            update_fields["doctorName"] = doctor_name
        if status:
            update_fields["status"] = status
        if notes:
            update_fields["notes"] = notes
        
        result = await client.update_appointment(appointment_id, **update_fields)
        return f"成功更新预约：{result}"
    
    # 如果没有配置微服务，使用本地数据库更新预约
    # 构建更新字段
    update_fields = {}
    if department:
        update_fields["department"] = department
    if appointment_time:
        try:
            update_fields["appointment_time"] = datetime.fromisoformat(
                appointment_time.replace('Z', '+00:00')
            )
        except ValueError:
            return f"预约时间格式错误：{appointment_time}"
    if doctor_name:
        update_fields["doctor_name"] = doctor_name
    if status:
        try:
            update_fields["status"] = AppointmentStatus(status)
        except ValueError:
            return f"无效的预约状态：{status}"
    if notes:
        update_fields["notes"] = notes
    
    if not update_fields:
        return "没有提供要更新的字段"
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = AppointmentRepository(session)
        
        # 更新记录
        appointment = await repo.update(appointment_id, **update_fields)
        
        if not appointment:
            return f"预约 {appointment_id} 不存在"
        
        await session.commit()
    
    return f"成功更新预约 {appointment_id}"

