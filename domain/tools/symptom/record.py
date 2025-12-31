"""
记录症状工具
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.symptom_repository import SymptomRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info


@tool
async def record_symptom(
    token_id: str,
    symptom_name: str,
    severity: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    duration: Optional[str] = None,
    location: Optional[str] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    记录症状数据
    
    Args:
        token_id: 令牌ID（自动注入）
        symptom_name: 症状名称（如：头痛、发热、咳嗽等）
        severity: 严重程度（可选，如：轻微、中等、严重）
        start_time: 开始时间（ISO格式字符串，可选）
        end_time: 结束时间（ISO格式字符串，可选）
        duration: 持续时间（可选，如：2小时、3天等）
        location: 症状部位（可选，如：头部、胸部等）
        description: 症状描述（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 数据转换：将 tokenId 转换为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 解析时间：未提供或格式错误时交由数据库默认时区时间处理
    start_datetime = None
    end_datetime = None
    if start_time:
        try:
            start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        except ValueError:
            start_datetime = None
    if end_time:
        try:
            end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            end_datetime = None
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        # 创建记录
        repo = SymptomRepository(session)
        create_data = {
            "user_id": user_id,
            "symptom_name": symptom_name,
            "severity": severity,
            "duration": duration,
            "location": location,
            "description": description,
            "notes": notes,
        }
        if start_datetime is not None:
            create_data["start_time"] = start_datetime
        if end_datetime is not None:
            create_data["end_time"] = end_datetime
        
        record = await repo.create(**create_data)
        
        await session.commit()
    
    severity_str = f"，严重程度：{severity}" if severity else ""
    location_str = f"，部位：{location}" if location else ""
    duration_str = f"，持续时间：{duration}" if duration else ""
    return f"成功记录症状：{symptom_name}{severity_str}{location_str}{duration_str}"
