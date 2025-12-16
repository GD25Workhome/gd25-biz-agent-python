"""
查询预约工具
"""
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.appointment_repository import AppointmentRepository
from infrastructure.external.java_service import JavaServiceClient
from infrastructure.database.connection import get_async_session_factory
from app.core.config import settings


@tool
async def query_appointment(
    user_id: int,
    appointment_id: Optional[int] = None
) -> str:
    """
    查询预约
    
    Args:
        user_id: 用户ID
        appointment_id: 预约ID（可选，如果不提供则查询用户所有预约）
        
    Returns:
        预约信息的字符串表示
    """
    # 如果配置了 Java 微服务，优先使用微服务
    if settings.JAVA_SERVICE_BASE_URL:
        try:
            client = JavaServiceClient()
            result = await client.query_appointment(
                user_id=user_id,
                appointment_id=appointment_id
            )
            return f"预约信息：{result}"
        except Exception as e:
            # 如果微服务调用失败，降级到本地数据库
            pass
    
    # 使用本地数据库查询预约
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = AppointmentRepository(session)
        
        if appointment_id:
            appointment = await repo.get_by_id(appointment_id)
            if not appointment or appointment.user_id != user_id:
                return f"预约 {appointment_id} 不存在或不属于用户 {user_id}"
            
            return (
                f"预约信息：\n"
                f"- ID: {appointment.id}\n"
                f"- 科室: {appointment.department}\n"
                f"- 医生: {appointment.doctor_name or '未指定'}\n"
                f"- 时间: {appointment.appointment_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- 状态: {appointment.status.value}\n"
                f"- 备注: {appointment.notes or '无'}"
            )
        else:
            appointments = await repo.get_by_user_id(user_id, limit=10)
            if not appointments:
                return f"用户 {user_id} 暂无预约记录"
            
            result_lines = [f"用户 {user_id} 的预约记录（共 {len(appointments)} 条）："]
            for apt in appointments:
                result_lines.append(
                    f"- ID: {apt.id}，科室: {apt.department}，"
                    f"时间: {apt.appointment_time.strftime('%Y-%m-%d %H:%M:%S')}，"
                    f"状态: {apt.status.value}"
                )
            
            return "\n".join(result_lines)

