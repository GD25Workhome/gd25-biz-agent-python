"""
药品记录工具
支持记录、查询药品服用信息
"""
import logging
import json
from typing import Optional
from datetime import datetime
from langchain_core.tools import tool

from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.medication_repository import MedicationRepository
from backend.domain.tools.context import get_token_id
from backend.domain.tools.decorator import register_tool
from backend.app.api.helpers import parse_datetime

logger = logging.getLogger(__name__)


@register_tool
async def record_medication(
    medication_name: str,
    dosage: int,
    dosage_unit: str,
    medication_time: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """
    记录药品服用信息
    
    Args:
        medication_name: 药品名称（必填）
        dosage: 每次服用剂量（必填，整数）
        dosage_unit: 剂量单位（必填，如：片、粒、ml、mg等）
        medication_time: 用药时间（可选，格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS，如果不提供则使用当前时间）
        notes: 备注（可选）
        
    Returns:
        记录结果的文本描述
        
    记录时间格式说明：
    - 支持格式：YYYY-MM-DD、YYYY-MM-DD HH:MM、YYYY-MM-DD HH:MM:SS
    - 例如：2024-03-15、2024-03-15 14:30、2024-03-15 14:30:00
    - 如果不提供medication_time参数，系统将使用当前时间作为用药时间
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        return "错误：无法获取用户ID，请确保在正确的上下文中调用此工具。"
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = MedicationRepository(session)
            
            # 解析用药时间
            parsed_medication_time = None
            if medication_time:
                parsed_medication_time = parse_datetime(medication_time)
                if parsed_medication_time is None:
                    return f"错误：用药时间格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM 格式（如：2024-03-15 或 2024-03-15 14:30）"
            else:
                # 如果没有提供用药时间，使用当前时间
                parsed_medication_time = datetime.now()
            
            # 构建记录数据
            record_data = {
                "user_id": token_id,
                "medication_name": medication_name,
                "dosage": dosage,
                "dosage_unit": dosage_unit,
                "medication_time": parsed_medication_time,
                "notes": notes
            }
            
            # 创建记录
            record = await repo.create(**record_data)
            await session.commit()
            
            logger.info(f"记录药品数据成功 (user_id={token_id}, record_id={record.id}): {json.dumps(record_data, ensure_ascii=False, default=str)}")
            
            # 生成回复
            result = f"已记录药品服用：{medication_name}，剂量 {dosage}{dosage_unit}"
            if medication_time:
                result += f"，用药时间：{parsed_medication_time.strftime('%Y-%m-%d %H:%M')}"
            if notes:
                result += f"。备注：{notes}"
            
            return result
            
        except Exception as e:
            await session.rollback()
            logger.error(f"记录药品数据失败 (user_id={token_id}): {e}", exc_info=True)
            return f"错误：记录药品数据失败 - {str(e)}"


@register_tool
async def query_medication(
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    查询药品记录
    
    Args:
        days: 查询天数（默认14天，最大14天）
        start_date: 开始日期（格式：YYYY-MM-DD，可选）
        end_date: 结束日期（格式：YYYY-MM-DD，可选，默认为当前日期）
        
    Returns:
        药品记录列表的文本描述（格式化输出）
        
    使用场景：
    - 用户询问"查看我的用药记录" → 查询最近14天
    - 用户询问"查看我最近7天的用药" → days=7
    - 用户询问"查看我3月1日到3月7日的用药" → start_date="2024-03-01", end_date="2024-03-07"
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        return "错误：无法获取用户ID，请确保在正确的上下文中调用此工具。"
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = MedicationRepository(session)
            
            # 解析日期参数（支持多种格式）
            parsed_start_date = None
            parsed_end_date = None
            
            if start_date:
                parsed_start_date = parse_datetime(start_date)
                if parsed_start_date is None:
                    return f"错误：开始日期格式不正确，请使用 YYYY-MM-DD 格式（如：2024-03-01）"
            
            if end_date:
                parsed_end_date = parse_datetime(end_date)
                if parsed_end_date is None:
                    return f"错误：结束日期格式不正确，请使用 YYYY-MM-DD 格式（如：2024-03-07）"
                # 如果只提供了日期（没有时间），设置为当天的结束时间（23:59:59）
                if parsed_end_date.hour == 0 and parsed_end_date.minute == 0 and parsed_end_date.second == 0:
                    parsed_end_date = parsed_end_date.replace(hour=23, minute=59, second=59)
            
            # 确定查询天数（默认14天，最大14天）
            query_days = min(days or 14, 14)
            
            # 查询记录
            records = await repo.get_recent_by_user_id(
                user_id=token_id,
                days=query_days,
                start_date=parsed_start_date,
                end_date=parsed_end_date
            )
            await session.commit()
            
            # 格式化输出
            if not records:
                return "您在此时间段内没有用药记录。"
            
            lines = [f"共找到 {len(records)} 条用药记录：\n"]
            for i, record in enumerate(records, 1):
                line = f"{i}. "
                if record.medication_time:
                    line += f"{record.medication_time.strftime('%Y-%m-%d %H:%M')} - "
                else:
                    line += f"{record.created_at.strftime('%Y-%m-%d %H:%M')} - "
                line += f"{record.medication_name}，剂量 {record.dosage}{record.dosage_unit}"
                if record.notes:
                    line += f"，备注：{record.notes}"
                lines.append(line)
            
            logger.info(f"查询药品记录成功 (user_id={token_id}, count={len(records)})")
            return "\n".join(lines)
            
        except Exception as e:
            await session.rollback()
            logger.error(f"查询药品记录失败 (user_id={token_id}): {e}", exc_info=True)
            return f"错误：查询药品记录失败 - {str(e)}"
