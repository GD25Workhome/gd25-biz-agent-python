"""
查询血压工具
"""
from typing import Optional, List
from langchain_core.tools import tool

from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info


@tool
async def query_blood_pressure(
    token_id: str,
    limit: int = 10,
    offset: int = 0
) -> str:
    """
    查询用户的血压记录
    
    Args:
        token_id: 令牌ID（自动注入）
        limit: 返回记录数量限制（默认10）
        offset: 偏移量（默认0）
        
    Returns:
        血压记录列表的字符串表示
    """
    # 数据转换：将 tokenId 转换为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = BloodPressureRepository(session)
        records = await repo.get_by_user_id(user_id, limit=limit, offset=offset)
    
    if not records:
        return f"用户 {user_id} 暂无血压记录"
    
    result_lines = [f"用户 {user_id} 的血压记录（共 {len(records)} 条）："]
    for record in records:
        result_lines.append(
            f"- 时间：{record.record_time.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"收缩压：{record.systolic} mmHg，"
            f"舒张压：{record.diastolic} mmHg，"
            f"心率：{record.heart_rate or '未记录'} bpm"
        )
        if record.notes:
            result_lines.append(f"  备注：{record.notes}")
    
    return "\n".join(result_lines)

