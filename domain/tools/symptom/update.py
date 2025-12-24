"""
更新症状工具
"""
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.symptom_repository import SymptomRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def update_symptom(
    record_id: str,
    symptom_name: Optional[str] = None,
    severity: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    duration: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    更新症状记录
    
    Args:
        record_id: 记录ID
        symptom_name: 症状名称（可选）
        severity: 严重程度（可选）
        start_time: 开始时间（ISO格式字符串，可选）
        end_time: 结束时间（ISO格式字符串，可选）
        duration: 持续时间（可选）
        location: 症状部位（可选）
        description: 症状描述（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    from datetime import datetime
    
    # 构建更新字段
    update_fields = {}
    if symptom_name is not None:
        update_fields["symptom_name"] = symptom_name
    if severity is not None:
        update_fields["severity"] = severity
    if start_time is not None:
        try:
            update_fields["start_time"] = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            pass
    if end_time is not None:
        try:
            update_fields["end_time"] = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            pass
    if duration is not None:
        update_fields["duration"] = duration
    if location is not None:
        update_fields["location"] = location
    if description is not None:
        update_fields["description"] = description
    if notes is not None:
        update_fields["notes"] = notes
    
    if not update_fields:
        return "没有提供要更新的字段"
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = SymptomRepository(session)
        
        # 更新记录
        record = await repo.update(record_id, **update_fields)
        
        if not record:
            return f"记录 {record_id} 不存在"
        
        await session.commit()
    
    return f"成功更新记录 {record_id} 的症状数据"
