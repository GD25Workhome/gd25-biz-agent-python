"""
查询血压工具
"""
from typing import Optional, List
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository


@tool
async def query_blood_pressure(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
    session: Optional[AsyncSession] = None
) -> str:
    """
    查询用户的血压记录
    
    Args:
        user_id: 用户ID
        limit: 返回记录数量限制（默认10）
        offset: 偏移量（默认0）
        session: 数据库会话（从上下文获取）
        
    Returns:
        血压记录列表的字符串表示
    """
    if not session:
        raise ValueError("数据库会话未提供")
    
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

