"""
记录血压工具
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def record_blood_pressure(
    user_id: str,
    systolic: int,
    diastolic: int,
    heart_rate: Optional[int] = None,
    record_time: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    记录血压数据
    
    Args:
        user_id: 用户ID
        systolic: 收缩压（高压）
        diastolic: 舒张压（低压）
        heart_rate: 心率（可选）
        record_time: 记录时间（ISO格式字符串，可选，默认为当前时间）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 解析记录时间
    if record_time:
        try:
            record_datetime = datetime.fromisoformat(record_time.replace('Z', '+00:00'))
        except ValueError:
            record_datetime = datetime.utcnow()
    else:
        record_datetime = datetime.utcnow()
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        # 创建记录
        repo = BloodPressureRepository(session)
        record = await repo.create(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            heart_rate=heart_rate,
            record_time=record_datetime,
            notes=notes
        )
        
        await session.commit()
    
    return f"成功记录血压：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg，心率 {heart_rate or '未记录'} bpm"

