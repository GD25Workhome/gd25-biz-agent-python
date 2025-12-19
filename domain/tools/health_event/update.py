"""
更新健康事件工具
"""
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.health_event_repository import HealthEventRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def update_health_event(
    record_id: str,
    event_type: Optional[str] = None,
    event_name: Optional[str] = None,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    更新健康事件记录
    
    Args:
        record_id: 记录ID
        event_type: 事件类型（可选）
        event_name: 事件名称（可选）
        event_date: 事件日期（ISO格式字符串，可选）
        location: 发生地点（可选）
        description: 事件描述（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    from datetime import datetime
    
    # 构建更新字段
    update_fields = {}
    if event_type is not None:
        update_fields["event_type"] = event_type
    if event_name is not None:
        update_fields["event_name"] = event_name
    if event_date is not None:
        try:
            update_fields["event_date"] = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
        except ValueError:
            pass
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
        repo = HealthEventRepository(session)
        
        # 更新记录
        record = await repo.update(record_id, **update_fields)
        
        if not record:
            return f"记录 {record_id} 不存在"
        
        await session.commit()
    
    return f"成功更新记录 {record_id} 的健康事件数据"
