"""
血压记录工具
简化版实现，仅记录数据，不持久化
"""
import logging
import json
from typing import Dict, Any
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: int = None,
    notes: str = None,
    token_id: str = ""  # 由TokenInjectedTool自动注入
) -> str:
    """
    记录血压数据
    
    Args:
        systolic: 收缩压（mmHg）
        diastolic: 舒张压（mmHg）
        heart_rate: 心率（次/分钟，可选）
        notes: 备注（可选）
        token_id: 用户ID（由系统自动注入，无需手动传递）
        
    Returns:
        记录结果的文本描述
    """
    try:
        # 数据验证
        if systolic < 50 or systolic > 250:
            return f"错误：收缩压 {systolic} mmHg 不在正常范围内（50-250 mmHg）"
        
        if diastolic < 30 or diastolic > 200:
            return f"错误：舒张压 {diastolic} mmHg 不在正常范围内（30-200 mmHg）"
        
        # 构建记录数据
        record = {
            "user_id": token_id,  # 使用自动注入的token_id
            "systolic": systolic,
            "diastolic": diastolic,
            "heart_rate": heart_rate,
            "notes": notes
        }
        
        # 本版本仅记录日志，不持久化
        logger.info(f"记录血压数据 (user_id={token_id}): {json.dumps(record, ensure_ascii=False)}")
        
        # 生成回复
        result = f"已记录血压数据：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg"
        if heart_rate:
            result += f"，心率 {heart_rate} 次/分钟"
        if notes:
            result += f"。备注：{notes}"
        
        return result
        
    except Exception as e:
        logger.error(f"记录血压数据失败: {e}")
        return f"错误：记录血压数据失败 - {str(e)}"

