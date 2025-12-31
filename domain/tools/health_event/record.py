"""
记录健康事件工具
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.health_event_repository import HealthEventRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info


@tool
async def record_health_event(
    token_id: str,
    event_type: str,
    event_name: str,
    event_date: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    记录健康事件数据
    
    Args:
        token_id: 令牌ID（自动注入）
        event_type: 事件类型（如：体检、检查、手术、疫苗接种等）
        event_name: 事件名称（如：年度体检、血常规检查等）
        event_date: 事件日期（ISO格式字符串，可选，默认为当前时间）
        location: 发生地点（可选，如：医院名称）
        description: 事件描述（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 数据转换：将 tokenId 转换为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 解析事件日期：未提供或格式错误时交由数据库默认时区时间处理
    event_datetime = None
    if event_date:
        try:
            event_datetime = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
        except ValueError:
            event_datetime = None
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        # 创建记录
        repo = HealthEventRepository(session)
        create_data = {
            "user_id": user_id,
            "event_type": event_type,
            "event_name": event_name,
            "location": location,
            "description": description,
            "notes": notes,
        }
        if event_datetime is not None:
            create_data["event_date"] = event_datetime
        
        record = await repo.create(**create_data)
        
        await session.commit()
    
    date_str = event_datetime.strftime('%Y-%m-%d') if event_datetime else "未指定"
    location_str = f"，地点：{location}" if location else ""
    return f"成功记录健康事件：{event_name}（{event_type}），日期：{date_str}{location_str}"
