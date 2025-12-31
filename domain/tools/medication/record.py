"""
记录用药工具
"""
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool

from infrastructure.database.repository.medication_repository import MedicationRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info


@tool
async def record_medication(
    token_id: str,
    medication_name: str,
    dosage: str,
    frequency: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    doctor_name: Optional[str] = None,
    purpose: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    记录用药数据
    
    Args:
        token_id: 令牌ID（自动注入）
        medication_name: 药物名称
        dosage: 剂量（如：10mg、1片等）
        frequency: 用药频率（如：每日一次、每日三次等）
        start_date: 开始日期（ISO格式字符串，可选）
        end_date: 结束日期（ISO格式字符串，可选）
        doctor_name: 开药医生（可选）
        purpose: 用药目的（可选，如：降血压、治疗感冒等）
        notes: 备注（可选）
        
    Returns:
        成功消息字符串
    """
    # 数据转换：将 tokenId 转换为用户信息
    user_info = convert_token_to_user_info(token_id)
    user_id = user_info.user_id
    
    # 解析日期：未提供或格式错误时交由数据库默认时区时间处理
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            start_datetime = None
    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            end_datetime = None
    
    # 获取数据库会话
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        # 创建记录
        repo = MedicationRepository(session)
        create_data = {
            "user_id": user_id,
            "medication_name": medication_name,
            "dosage": dosage,
            "frequency": frequency,
            "doctor_name": doctor_name,
            "purpose": purpose,
            "notes": notes,
        }
        if start_datetime is not None:
            create_data["start_date"] = start_datetime
        if end_datetime is not None:
            create_data["end_date"] = end_datetime
        
        record = await repo.create(**create_data)
        
        await session.commit()
    
    start_str = start_datetime.strftime('%Y-%m-%d') if start_datetime else "未指定"
    doctor_str = f"，医生：{doctor_name}" if doctor_name else ""
    return f"成功记录用药：{medication_name}，剂量：{dosage}，频率：{frequency}，开始日期：{start_str}{doctor_str}"
