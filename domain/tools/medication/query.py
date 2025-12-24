"""
查询用药工具
"""
from typing import Optional, List
from langchain_core.tools import tool

from infrastructure.database.repository.medication_repository import MedicationRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def query_medication(
    user_id: str,
    limit: int = 10,
    offset: int = 0
) -> str:
    """
    查询用户的用药记录
    
    Args:
        user_id: 用户ID
        limit: 返回记录数量限制（默认10）
        offset: 偏移量（默认0）
        
    Returns:
        用药记录列表的字符串表示
    """
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = MedicationRepository(session)
        records = await repo.get_by_user_id(user_id, limit=limit, offset=offset)
    
    if not records:
        return f"用户 {user_id} 暂无用药记录"
    
    result_lines = [f"用户 {user_id} 的用药记录（共 {len(records)} 条）："]
    for record in records:
        start_str = record.start_date.strftime('%Y-%m-%d') if record.start_date else "未指定"
        end_str = f"至 {record.end_date.strftime('%Y-%m-%d')}" if record.end_date else ""
        doctor_str = f"，医生：{record.doctor_name}" if record.doctor_name else ""
        purpose_str = f"，目的：{record.purpose}" if record.purpose else ""
        result_lines.append(
            f"- {record.medication_name}，剂量：{record.dosage}，频率：{record.frequency}，"
            f"开始日期：{start_str}{end_str}{doctor_str}{purpose_str}"
        )
        if record.notes:
            result_lines.append(f"  备注：{record.notes}")
    
    return "\n".join(result_lines)
