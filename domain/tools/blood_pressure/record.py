"""
记录血压工具
"""
import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
from infrastructure.database.connection import get_async_session_factory
from domain.tools.utils.token_converter import convert_token_to_user_info

# 创建日志记录器
logger = logging.getLogger(__name__)


class RecordBloodPressureInput(BaseModel):
    """记录血压工具的输入参数"""
    token_id: str = Field(
        default="",
        description="令牌ID（由系统自动注入，调用时不需要提供此参数）"
    )
    systolic: int = Field(
        description="收缩压（高压），必填，单位：mmHg",
        examples=[120, 130, 140]
    )
    diastolic: int = Field(
        description="舒张压（低压），必填，单位：mmHg",
        examples=[80, 85, 90]
    )
    heart_rate: Optional[int] = Field(
        default=None,
        description="心率，可选，单位：bpm（次/分）",
        examples=[72, 75, 80]
    )
    record_time: Optional[str] = Field(
        default=None,
        description="记录时间，可选，ISO格式字符串（如：2025-01-10T10:30:00），不提供则使用当前时间",
        examples=["2025-01-10T10:30:00"]
    )
    notes: Optional[str] = Field(
        default=None,
        description="备注信息，可选",
        examples=["晨起测量", "餐后测量"]
    )


@tool(args_schema=RecordBloodPressureInput)
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: Optional[int] = None,
    record_time: Optional[str] = None,
    notes: Optional[str] = None,
    token_id: str = ""  # 由系统自动注入，设置默认值以避免参数缺失错误
) -> str:
    """
    记录血压数据到数据库。
    
    重要说明：
    - token_id 参数由系统自动注入，调用时不需要提供此参数
    - 只需提供 systolic（收缩压）和 diastolic（舒张压）即可完成记录
    - heart_rate（心率）、record_time（记录时间）、notes（备注）为可选参数
    
    参数说明：
    - systolic: 收缩压（高压），必填，单位：mmHg
    - diastolic: 舒张压（低压），必填，单位：mmHg
    - heart_rate: 心率，可选，单位：bpm（次/分）
    - record_time: 记录时间，可选，ISO格式字符串（如：2025-01-10T10:30:00），不提供则使用当前时间
    - notes: 备注信息，可选
    
    返回：
        成功消息字符串，包含记录的血压数据
    
    示例：
        调用时只需提供：{"systolic": 120, "diastolic": 80, "heart_rate": 72}
        token_id 会自动注入，无需在参数中提供
    """
    # ========== 日志：函数入口 ==========
    logger.info(
        f"[record_blood_pressure] 工具调用开始 - "
        f"token_id={token_id}, systolic={systolic}, diastolic={diastolic}, "
        f"heart_rate={heart_rate}, record_time={record_time}, notes={notes}"
    )
    
    # ========== 验证 token_id ==========
    if not token_id or token_id == "":
        error_msg = "token_id 参数缺失或为空，无法记录血压数据"
        logger.error(f"[record_blood_pressure] {error_msg}")
        return f"错误：{error_msg}。请确保系统已正确注入 token_id。"
    
    try:
        # ========== 数据转换：将 tokenId 转换为用户信息 ==========
        logger.debug(f"[record_blood_pressure] 开始转换 token_id: {token_id}")
        user_info = convert_token_to_user_info(token_id)
        user_id = user_info.user_id
        logger.info(f"[record_blood_pressure] token_id 转换完成 - token_id={token_id}, user_id={user_id}")
        
        # ========== 解析记录时间：未提供或格式错误时交由数据库默认时区时间处理 ==========
        record_datetime = None
        if record_time:
            try:
                record_datetime = datetime.fromisoformat(record_time.replace('Z', '+00:00'))
                logger.debug(f"[record_blood_pressure] 时间解析成功 - record_time={record_time}, parsed={record_datetime}")
            except ValueError as e:
                logger.warning(f"[record_blood_pressure] 时间解析失败，将使用数据库默认时间 - record_time={record_time}, error={e}")
                record_datetime = None
        else:
            logger.debug(f"[record_blood_pressure] 未提供 record_time，将使用数据库默认时间")
        
        # ========== 获取数据库会话 ==========
        logger.debug(f"[record_blood_pressure] 开始获取数据库会话工厂")
        session_factory = get_async_session_factory()
        logger.debug(f"[record_blood_pressure] 数据库会话工厂获取成功，开始创建会话")
        session = session_factory()
        logger.info(f"[record_blood_pressure] 数据库会话创建成功 - session_id={id(session)}")
        
        try:
            # ========== 创建记录 ==========
            repo = BloodPressureRepository(session)
            create_data = {
                "user_id": user_id,
                "systolic": systolic,
                "diastolic": diastolic,
                "heart_rate": heart_rate,
                "notes": notes,
            }
            if record_datetime is not None:
                create_data["record_time"] = record_datetime
            
            logger.info(
                f"[record_blood_pressure] 准备创建血压记录 - "
                f"user_id={user_id}, systolic={systolic}, diastolic={diastolic}, "
                f"heart_rate={heart_rate}, record_time={record_datetime}, notes={notes}"
            )
            
            record = await repo.create(**create_data)
            logger.info(f"[record_blood_pressure] 血压记录创建成功 - record_id={record.id if hasattr(record, 'id') else 'N/A'}")
            
            # ========== 显式提交事务 ==========
            logger.debug(f"[record_blood_pressure] 开始提交事务")
            await session.commit()
            logger.info(f"[record_blood_pressure] 事务提交成功 - record_id={record.id if hasattr(record, 'id') else 'N/A'}")
            
            # ========== 返回成功消息 ==========
            result_message = f"成功记录血压：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg，心率 {heart_rate or '未记录'} bpm"
            logger.info(f"[record_blood_pressure] 工具调用成功完成 - result={result_message}")
            return result_message
            
        except Exception as e:
            # ========== 如果发生异常，回滚事务 ==========
            logger.error(
                f"[record_blood_pressure] 发生异常，开始回滚事务 - "
                f"error_type={type(e).__name__}, error={str(e)}",
                exc_info=True
            )
            await session.rollback()
            logger.error(f"[record_blood_pressure] 事务回滚完成")
            raise
        finally:
            # ========== 确保会话被正确关闭 ==========
            logger.debug(f"[record_blood_pressure] 开始关闭数据库会话")
            await session.close()
            logger.debug(f"[record_blood_pressure] 数据库会话已关闭")
            
    except Exception as e:
        # ========== 捕获所有异常（包括会话创建失败等） ==========
        logger.error(
            f"[record_blood_pressure] 工具调用失败 - "
            f"error_type={type(e).__name__}, error={str(e)}",
            exc_info=True
        )
        raise

