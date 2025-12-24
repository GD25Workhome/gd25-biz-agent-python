"""
查询健康事件工具
"""
from typing import Optional, List
from langchain_core.tools import tool

from infrastructure.database.repository.health_event_repository import HealthEventRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def query_health_event(
    user_id: str,
    limit: int = 10,
    offset: int = 0
) -> str:
    """
    查询用户的健康事件记录
    
    Args:
        user_id: 用户ID
        limit: 返回记录数量限制（默认10）
        offset: 偏移量（默认0）
        
    Returns:
        健康事件记录列表的字符串表示
    """
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = HealthEventRepository(session)
        records = await repo.get_by_user_id(user_id, limit=limit, offset=offset)
    
    if not records:
        return f"用户 {user_id} 暂无健康事件记录"
    
    result_lines = [f"用户 {user_id} 的健康事件记录（共 {len(records)} 条）："]
    for record in records:
        date_str = record.event_date.strftime('%Y-%m-%d') if record.event_date else "未指定日期"
        location_str = f"，地点：{record.location}" if record.location else ""
        result_lines.append(
            f"- {record.event_name}（{record.event_type}），日期：{date_str}{location_str}"
        )
        if record.description:
            result_lines.append(f"  描述：{record.description}")
        if record.notes:
            result_lines.append(f"  备注：{record.notes}")
    
    return "\n".join(result_lines)
