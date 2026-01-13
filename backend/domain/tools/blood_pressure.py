"""
血压记录工具
支持记录、查询、更新血压数据
"""
import logging
import json
from typing import Optional
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from langchain_core.tools import tool

from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from backend.domain.tools.context import get_token_id

logger = logging.getLogger(__name__)


def parse_datetime(date_str: str) -> Optional[datetime]:
    """
    解析日期时间字符串，支持多种格式
    
    Args:
        date_str: 日期时间字符串
        
    Returns:
        datetime对象，如果解析失败则返回None
        
    支持的格式：
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DD HH:MM:SS
    - YYYY/MM/DD
    - YYYY/MM/DD HH:MM
    - 其他常见日期格式
    """
    if not date_str:
        return None
    
    try:
        # 使用dateutil.parser解析，支持多种格式
        return date_parser.parse(date_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"日期解析失败: {date_str}, 错误: {e}")
        return None


@tool
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: Optional[int] = None,
    notes: Optional[str] = None,
    record_time: Optional[str] = None
) -> str:
    """
    记录血压数据
    
    Args:
        systolic: 收缩压（mmHg）
        diastolic: 舒张压（mmHg）
        heart_rate: 心率（次/分钟，可选）
        notes: 备注（可选）
        record_time: 记录时间（可选，格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS，如果不提供则使用当前时间）
        
    Returns:
        记录结果的文本描述
        
    记录时间格式说明：
    - 支持格式：YYYY-MM-DD、YYYY-MM-DD HH:MM、YYYY-MM-DD HH:MM:SS
    - 例如：2024-03-15、2024-03-15 14:30、2024-03-15 14:30:00
    - 如果不提供record_time参数，系统将使用当前时间作为记录时间
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        return "错误：无法获取用户ID，请确保在正确的上下文中调用此工具。"
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = BloodPressureRepository(session)
            
            # 解析记录时间
            parsed_record_time = None
            if record_time:
                parsed_record_time = parse_datetime(record_time)
                if parsed_record_time is None:
                    return f"错误：记录时间格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM 格式（如：2024-03-15 或 2024-03-15 14:30）"
            else:
                # 如果没有提供记录时间，使用当前时间
                parsed_record_time = datetime.now()
            
            # 构建记录数据
            record_data = {
                "user_id": token_id,
                "systolic": systolic,
                "diastolic": diastolic,
                "heart_rate": heart_rate,
                "notes": notes,
                "record_time": parsed_record_time
            }
            
            # 创建记录
            record = await repo.create(**record_data)
            await session.commit()
            
            logger.info(f"记录血压数据成功 (user_id={token_id}, record_id={record.id}): {json.dumps(record_data, ensure_ascii=False, default=str)}")
            
            # 生成回复
            result = f"已记录血压数据：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg"
            if heart_rate:
                result += f"，心率 {heart_rate} 次/分钟"
            if record_time:
                result += f"，记录时间：{parsed_record_time.strftime('%Y-%m-%d %H:%M')}"
            if notes:
                result += f"。备注：{notes}"
            
            return result
            
        except Exception as e:
            await session.rollback()
            logger.error(f"记录血压数据失败 (user_id={token_id}): {e}", exc_info=True)
            return f"错误：记录血压数据失败 - {str(e)}"


@tool
async def query_blood_pressure(
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    """
    查询血压记录
    
    Args:
        days: 查询天数（默认14天，最大14天）
        start_date: 开始日期（格式：YYYY-MM-DD，可选）
        end_date: 结束日期（格式：YYYY-MM-DD，可选，默认为当前日期）
        
    Returns:
        血压记录列表的文本描述（格式化输出）
        
    使用场景：
    - 用户询问"查看我的血压记录" → 查询最近14天
    - 用户询问"查看我最近7天的血压" → days=7
    - 用户询问"查看我3月1日到3月7日的血压" → start_date="2024-03-01", end_date="2024-03-07"
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        return "错误：无法获取用户ID，请确保在正确的上下文中调用此工具。"
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = BloodPressureRepository(session)
            
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
                return "您在此时间段内没有血压记录。"
            
            lines = [f"共找到 {len(records)} 条血压记录：\n"]
            for i, record in enumerate(records, 1):
                line = f"{i}. "
                if record.record_time:
                    line += f"{record.record_time.strftime('%Y-%m-%d %H:%M')} - "
                else:
                    line += f"{record.created_at.strftime('%Y-%m-%d %H:%M')} - "
                line += f"收缩压 {record.systolic} mmHg，舒张压 {record.diastolic} mmHg"
                if record.heart_rate:
                    line += f"，心率 {record.heart_rate} 次/分钟"
                if record.notes:
                    line += f"，备注：{record.notes}"
                lines.append(line)
            
            logger.info(f"查询血压记录成功 (user_id={token_id}, count={len(records)})")
            return "\n".join(lines)
            
        except Exception as e:
            await session.rollback()
            logger.error(f"查询血压记录失败 (user_id={token_id}): {e}", exc_info=True)
            return f"错误：查询血压记录失败 - {str(e)}"


@tool
async def update_blood_pressure(
    systolic: Optional[int] = None,
    diastolic: Optional[int] = None,
    heart_rate: Optional[int] = None,
    notes: Optional[str] = None,
    record_time: Optional[str] = None
) -> str:
    """
    更新最新的血压记录
    
    Args:
        systolic: 收缩压（mmHg，可选）
        diastolic: 舒张压（mmHg，可选）
        heart_rate: 心率（次/分钟，可选）
        notes: 备注（可选）
        record_time: 记录时间（可选，格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM 或 YYYY-MM-DD HH:MM:SS）
        
    Returns:
        更新结果的文本描述
        
    使用场景：
    - 用户说"我刚才记录的血压有误，应该是120/80" → 更新最新记录
    - 用户说"修改一下刚才的备注" → 只更新备注字段
    - 用户说"修改记录时间为今天上午10点" → 更新记录时间
    
    限制：
    - 只能更新最新的血压记录
    - 如果用户没有血压记录，返回错误提示
    """
    # 从运行时上下文获取 token_id
    token_id = get_token_id()
    if not token_id:
        return "错误：无法获取用户ID，请确保在正确的上下文中调用此工具。"
    
    # 构建更新数据
    update_data = {}
    parsed_record_time = None
    
    if systolic is not None:
        update_data["systolic"] = systolic
    if diastolic is not None:
        update_data["diastolic"] = diastolic
    if heart_rate is not None:
        update_data["heart_rate"] = heart_rate
    if notes is not None:
        update_data["notes"] = notes
    if record_time is not None:
        parsed_record_time = parse_datetime(record_time)
        if parsed_record_time is None:
            return f"错误：记录时间格式不正确，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM 格式（如：2024-03-15 或 2024-03-15 14:30）"
        update_data["record_time"] = parsed_record_time
    
    # 获取数据库会话并执行操作
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            repo = BloodPressureRepository(session)
            
            # 获取最新记录
            latest_record = await repo.get_latest_by_user_id(user_id=token_id)
            
            if not latest_record:
                await session.commit()
                return "您还没有血压记录，无法更新。请先使用记录血压功能记录您的血压数据。"
            
            # 更新记录
            updated_record = await repo.update(latest_record.id, **update_data)
            await session.commit()
            
            if not updated_record:
                return "错误：更新血压记录失败"
            
            logger.info(f"更新血压记录成功 (user_id={token_id}, record_id={updated_record.id}): {json.dumps(update_data, ensure_ascii=False)}")
            
            # 生成回复
            result = "已更新血压记录："
            updates = []
            if systolic is not None:
                updates.append(f"收缩压 {systolic} mmHg")
            if diastolic is not None:
                updates.append(f"舒张压 {diastolic} mmHg")
            if heart_rate is not None:
                updates.append(f"心率 {heart_rate} 次/分钟")
            if notes is not None:
                updates.append(f"备注：{notes}")
            if record_time is not None:
                updates.append(f"记录时间：{parsed_record_time.strftime('%Y-%m-%d %H:%M')}")
            
            if updates:
                result += "，".join(updates)
            else:
                result = "未提供任何更新字段"
            
            return result
            
        except Exception as e:
            await session.rollback()
            logger.error(f"更新血压记录失败 (user_id={token_id}): {e}", exc_info=True)
            return f"错误：更新血压记录失败 - {str(e)}"

