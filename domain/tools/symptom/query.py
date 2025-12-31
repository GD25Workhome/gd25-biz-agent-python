"""
查询症状工具
"""
from typing import Optional, List
from langchain_core.tools import tool

from infrastructure.database.repository.symptom_repository import SymptomRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info


@tool
async def query_symptom(
    token_id: str,
    limit: int = 10,
    offset: int = 0
) -> str:
    """
    查询用户的症状记录
    
    Args:
        token_id: 令牌ID（自动注入）
        limit: 返回记录数量限制（默认10）
        offset: 偏移量（默认0）
        
    Returns:
        症状记录列表的字符串表示
    """
    # 数据转换：将 tokenId 转换为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = SymptomRepository(session)
        records = await repo.get_by_user_id(user_id, limit=limit, offset=offset)
    
    if not records:
        return f"用户 {user_id} 暂无症状记录"
    
    result_lines = [f"用户 {user_id} 的症状记录（共 {len(records)} 条）："]
    for record in records:
        start_str = record.start_time.strftime('%Y-%m-%d %H:%M:%S') if record.start_time else "未指定"
        severity_str = f"，严重程度：{record.severity}" if record.severity else ""
        location_str = f"，部位：{record.location}" if record.location else ""
        duration_str = f"，持续时间：{record.duration}" if record.duration else ""
        result_lines.append(
            f"- {record.symptom_name}{severity_str}{location_str}，开始时间：{start_str}{duration_str}"
        )
        if record.description:
            result_lines.append(f"  描述：{record.description}")
        if record.notes:
            result_lines.append(f"  备注：{record.notes}")
    
    return "\n".join(result_lines)
