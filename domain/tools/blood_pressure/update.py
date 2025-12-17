"""
更新血压工具
"""
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def update_blood_pressure(
    record_id: int,
    systolic: Optional[int] = None,
    diastolic: Optional[int] = None,
    heart_rate: Optional[int] = None,
    notes: Optional[str] = None
) -> str:
    """
    更新血压记录
    
    Args:
        record_id: 记录ID
        systolic: 收缩压（可选）
        diastolic: 舒张压（可选）
        heart_rate: 心率（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 构建更新字段
    update_fields = {}
    if systolic is not None:
        update_fields["systolic"] = systolic
    if diastolic is not None:
        update_fields["diastolic"] = diastolic
    if heart_rate is not None:
        update_fields["heart_rate"] = heart_rate
    if notes is not None:
        update_fields["notes"] = notes
    
    if not update_fields:
        return "没有提供要更新的字段"
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = BloodPressureRepository(session)
        
        # 更新记录
        record = await repo.update(record_id, **update_fields)
        
        if not record:
            return f"记录 {record_id} 不存在"
        
        await session.commit()
    
    return f"成功更新记录 {record_id} 的血压数据"

