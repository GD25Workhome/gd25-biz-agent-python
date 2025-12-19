"""
更新用药工具
"""
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.medication_repository import MedicationRepository
from infrastructure.database.connection import get_async_session_factory


@tool
async def update_medication(
    record_id: str,
    medication_name: Optional[str] = None,
    dosage: Optional[str] = None,
    frequency: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    doctor_name: Optional[str] = None,
    purpose: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    更新用药记录
    
    Args:
        record_id: 记录ID
        medication_name: 药物名称（可选）
        dosage: 剂量（可选）
        frequency: 用药频率（可选）
        start_date: 开始日期（ISO格式字符串，可选）
        end_date: 结束日期（ISO格式字符串，可选）
        doctor_name: 开药医生（可选）
        purpose: 用药目的（可选）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    from datetime import datetime
    
    # 构建更新字段
    update_fields = {}
    if medication_name is not None:
        update_fields["medication_name"] = medication_name
    if dosage is not None:
        update_fields["dosage"] = dosage
    if frequency is not None:
        update_fields["frequency"] = frequency
    if start_date is not None:
        try:
            update_fields["start_date"] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            pass
    if end_date is not None:
        try:
            update_fields["end_date"] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            pass
    if doctor_name is not None:
        update_fields["doctor_name"] = doctor_name
    if purpose is not None:
        update_fields["purpose"] = purpose
    if notes is not None:
        update_fields["notes"] = notes
    
    if not update_fields:
        return "没有提供要更新的字段"
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = MedicationRepository(session)
        
        # 更新记录
        record = await repo.update(record_id, **update_fields)
        
        if not record:
            return f"记录 {record_id} 不存在"
        
        await session.commit()
    
    return f"成功更新记录 {record_id} 的用药数据"
