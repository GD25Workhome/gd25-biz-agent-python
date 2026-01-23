#!/usr/bin/env python
"""
血压会话数据导入脚本

功能：从Excel文件导入血压会话原始记录数据到数据库

使用方法：
    python scripts/import_blood_pressure_session_data.py

说明：
    - 自动读取 static/rag_source/uat_data/ 目录下的两个Excel文件
    - 4.1 lsk_副本.xlsx：字段直接对应，message_id 从 ids 字段中提取
    - sh-1128_副本.xlsx：会话输入=新会话，供应商响应()=新会话响应，message_id 从 message_id 字段中提取
    - 数据插入前会根据"来源文件名"、"来源备注1"先清空数据，再重新插入
    - 空行判断："新会话"、"新会话响应"两个字段任意字段为空，即为空行，不导入
    - 字段值为"无"时，会被当做NULL处理
"""
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.config import settings
from backend.infrastructure.database.models.blood_pressure_session import BloodPressureSessionRecord
from backend.infrastructure.database.base import Base

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def ensure_psycopg3_sync_url(database_url: str) -> str:
    """
    确保数据库 URL 使用 psycopg3 驱动（同步模式）
    
    Args:
        database_url: 原始数据库 URL
        
    Returns:
        str: 确保使用 psycopg3 驱动的 URL
    """
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if "+" in database_url and "://" in database_url:
        scheme, rest = database_url.split("://", 1)
        if scheme.startswith("postgresql+"):
            return f"postgresql+psycopg://{rest}"
    return database_url


def create_table_if_not_exists(engine):
    """
    创建表（如果不存在）
    
    Args:
        engine: SQLAlchemy引擎
    """
    try:
        Base.metadata.create_all(engine, tables=[BloodPressureSessionRecord.__table__])
        logger.info("✓ 表创建成功或已存在")
    except Exception as e:
        logger.error(f"✗ 创建表失败: {e}")
        raise


def clean_data_by_source(session, source_filename: str, source_remark1: str):
    """
    根据来源文件名和备注清空数据
    
    Args:
        session: SQLAlchemy会话
        source_filename: 来源文件名
        source_remark1: 来源备注1
    """
    try:
        deleted_count = session.query(BloodPressureSessionRecord).filter(
            BloodPressureSessionRecord.source_filename == source_filename,
            BloodPressureSessionRecord.source_remark1 == source_remark1
        ).delete()
        session.commit()
        logger.info(f"  清空数据: {deleted_count} 条记录（来源: {source_filename}, {source_remark1}）")
    except Exception as e:
        session.rollback()
        logger.error(f"  清空数据失败: {e}")
        raise


def convert_to_int(value: Any) -> Optional[int]:
    """
    将值转换为整数
    
    Args:
        value: 待转换的值
        
    Returns:
        Optional[int]: 转换后的整数，如果无法转换则返回None
    """
    if pd.isna(value) or value is None or value == "":
        return None
    try:
        # 如果是字符串，先去除空格并检查是否为"无"
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value == "无":
                return None
            return int(float(value))  # 先转float再转int，处理"120.0"这种情况
        # 如果是浮点数，先转换为整数
        if isinstance(value, float):
            return int(value)
        return int(value)
    except (ValueError, TypeError):
        return None


def convert_to_string(value: Any, max_length: Optional[int] = None) -> Optional[str]:
    """
    将值转换为字符串
    
    Args:
        value: 待转换的值
        max_length: 最大长度限制
        
    Returns:
        Optional[str]: 转换后的字符串，如果为空或为"无"则返回None
    """
    if pd.isna(value) or value is None:
        return None
    result = str(value).strip()
    if result == "" or result == "无":
        return None
    if max_length and len(result) > max_length:
        result = result[:max_length]
    return result


def convert_to_text(value: Any) -> Optional[str]:
    """
    将值转换为文本（Text类型）
    
    Args:
        value: 待转换的值
        
    Returns:
        Optional[str]: 转换后的文本，如果为空或为"无"则返回None
    """
    if pd.isna(value) or value is None:
        return None
    result = str(value).strip()
    if result == "" or result == "无":
        return None
    return result


def extract_message_id(value: Any) -> Optional[str]:
    """
    提取 message_id
    
    规则：
    1. 如果 message_id 中没有换行以及中/英文冒号，就直接去除前后空格，存入
    2. 否则需要从以下格式中提取 message_id：
       messageId: 108fea3e-4c7c-41fd-b474-edb8f02171dd
       patientid: 1993595802664812567
       doctorid: 1922824398239559724
    
    Args:
        value: 待处理的值
        
    Returns:
        Optional[str]: 提取的 message_id，如果无法提取则返回None
    """
    if pd.isna(value) or value is None:
        return None
    
    value_str = str(value).strip()
    if value_str == "" or value_str == "无":
        return None
    
    # 检查是否包含换行符或冒号（中英文）
    has_newline = "\n" in value_str or "\r" in value_str
    has_colon = ":" in value_str or "：" in value_str
    
    # 如果没有换行和冒号，直接返回去除空格后的值
    if not has_newline and not has_colon:
        return value_str.strip()
    
    # 如果有换行或冒号，尝试从格式中提取 messageId
    import re
    
    # 尝试匹配 messageId: xxx 格式（不区分大小写）
    patterns = [
        r"messageId\s*[:：]\s*([^\s\n\r]+)",  # messageId: xxx
        r"message_id\s*[:：]\s*([^\s\n\r]+)",  # message_id: xxx
        r"messageId\s*=\s*([^\s\n\r]+)",  # messageId=xxx
        r"message_id\s*=\s*([^\s\n\r]+)",  # message_id=xxx
    ]
    
    for pattern in patterns:
        match = re.search(pattern, value_str, re.IGNORECASE)
        if match:
            message_id = match.group(1).strip()
            if message_id:
                return message_id
    
    # 如果无法提取，返回 None
    return None


def is_empty_row(row: pd.Series, new_session_col: str, new_session_response_col: str) -> bool:
    """
    判断是否为空行
    
    Args:
        row: 数据行
        new_session_col: 新会话列名
        new_session_response_col: 新会话响应列名
        
    Returns:
        bool: 如果为空行返回True
    """
    new_session = convert_to_text(row.get(new_session_col))
    new_session_response = convert_to_text(row.get(new_session_response_col))
    return new_session is None or new_session_response is None


def import_from_excel_lsk(
    session,
    excel_path: Path,
    source_filename: str
) -> Dict[str, int]:
    """
    从 4.1 lsk_副本.xlsx 导入数据
    
    Args:
        session: SQLAlchemy会话
        excel_path: Excel文件路径
        source_filename: 来源文件名
        
    Returns:
        Dict[str, int]: 导入统计信息
    """
    stats = {"success": 0, "fail": 0, "skipped": 0}
    
    try:
        # 读取所有sheet页
        excel_file = pd.ExcelFile(excel_path)
        sheet_names = excel_file.sheet_names
        
        logger.info(f"  发现 {len(sheet_names)} 个sheet页: {', '.join(sheet_names)}")
        
        for sheet_name in sheet_names:
            logger.info(f"  处理sheet页: {sheet_name}")
            
            # 读取sheet数据
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            
            if df.empty:
                logger.warning(f"    Sheet '{sheet_name}' 为空，跳过")
                continue
            
            # 清空该sheet对应的数据
            clean_data_by_source(session, source_filename, sheet_name)
            
            # 字段映射（Excel列名 -> 数据库字段名）
            field_mapping = {
                "年龄": "age",
                "疾病": "disease",
                "血压": "blood_pressure",
                "症状": "symptom",
                "用药": "medication",
                "用药情况": "medication_status",
                "习惯": "habit",
                "历史Action": "history_action",
                "历史会话": "history_session",
                "历史会话响应": "history_response",
                "新会话": "new_session",
                "新会话响应": "new_session_response",
                "ids": "ids",
                "ext": "ext",
            }
            
            # 处理每一行数据
            for idx, row in df.iterrows():
                try:
                    # 检查是否为空行
                    if is_empty_row(row, "新会话", "新会话响应"):
                        stats["skipped"] += 1
                        continue
                    
                    # 创建记录对象
                    record = BloodPressureSessionRecord()
                    record.source_filename = source_filename
                    record.source_remark1 = sheet_name
                    
                    # 映射字段
                    for excel_col, db_field in field_mapping.items():
                        if excel_col in df.columns:
                            value = row[excel_col]
                            if db_field == "age":
                                setattr(record, db_field, convert_to_int(value))
                            elif db_field in ["history_session", "history_response", "new_session", "new_session_response"]:
                                setattr(record, db_field, convert_to_text(value))
                            else:
                                setattr(record, db_field, convert_to_string(value, max_length=1000))
                    
                    # 处理 message_id 字段：从 ids 列中提取
                    if "ids" in df.columns:
                        record.message_id = extract_message_id(row["ids"])
                    
                    # 保存记录
                    session.add(record)
                    stats["success"] += 1
                    
                    # 每100条提交一次
                    if stats["success"] % 100 == 0:
                        session.commit()
                        logger.info(f"    已导入 {stats['success']} 条记录...")
                
                except Exception as e:
                    stats["fail"] += 1
                    logger.error(f"    第 {idx + 2} 行导入失败: {e}")
                    continue
            
            # 提交该sheet的数据
            session.commit()
            logger.info(f"  Sheet '{sheet_name}' 导入完成: 成功 {stats['success']}, 失败 {stats['fail']}, 跳过 {stats['skipped']}")
        
        return stats
    
    except Exception as e:
        session.rollback()
        logger.error(f"  导入文件失败: {e}")
        raise


def import_from_excel_sh1128(
    session,
    excel_path: Path,
    source_filename: str
) -> Dict[str, int]:
    """
    从 sh-1128_副本.xlsx 导入数据
    
    Args:
        session: SQLAlchemy会话
        excel_path: Excel文件路径
        source_filename: 来源文件名
        
    Returns:
        Dict[str, int]: 导入统计信息
    """
    stats = {"success": 0, "fail": 0, "skipped": 0}
    
    try:
        # 读取所有sheet页
        excel_file = pd.ExcelFile(excel_path)
        sheet_names = excel_file.sheet_names
        
        logger.info(f"  发现 {len(sheet_names)} 个sheet页: {', '.join(sheet_names)}")
        
        for sheet_name in sheet_names:
            logger.info(f"  处理sheet页: {sheet_name}")
            
            # 读取sheet数据
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            
            if df.empty:
                logger.warning(f"    Sheet '{sheet_name}' 为空，跳过")
                continue
            
            # 清空该sheet对应的数据
            clean_data_by_source(session, source_filename, sheet_name)
            
            # 字段映射（Excel列名 -> 数据库字段名）
            # 注意：会话输入=新会话，供应商响应()=新会话响应
            field_mapping = {
                "年龄": "age",
                "疾病": "disease",
                "血压": "blood_pressure",
                "症状": "symptom",
                "用药": "medication",
                "用药情况": "medication_status",
                "习惯": "habit",
                "历史Action": "history_action",
                "历史会话": "history_session",
                "历史会话响应": "history_response",
                "会话输入": "new_session",  # 特殊映射
                "供应商响应()": "new_session_response",  # 特殊映射
                "ids": "ids",
                "ext": "ext",
            }
            
            # 处理每一行数据
            for idx, row in df.iterrows():
                try:
                    # 检查是否为空行（使用映射后的列名）
                    if is_empty_row(row, "会话输入", "供应商响应()"):
                        stats["skipped"] += 1
                        continue
                    
                    # 创建记录对象
                    record = BloodPressureSessionRecord()
                    record.source_filename = source_filename
                    record.source_remark1 = sheet_name
                    
                    # 映射字段
                    for excel_col, db_field in field_mapping.items():
                        if excel_col in df.columns:
                            value = row[excel_col]
                            if db_field == "age":
                                setattr(record, db_field, convert_to_int(value))
                            elif db_field in ["history_session", "history_response", "new_session", "new_session_response"]:
                                setattr(record, db_field, convert_to_text(value))
                            else:
                                setattr(record, db_field, convert_to_string(value, max_length=1000))
                    
                    # 处理 message_id 字段：从 message_id 列中提取
                    if "message_id" in df.columns:
                        record.message_id = extract_message_id(row["message_id"])
                    
                    # 保存记录
                    session.add(record)
                    stats["success"] += 1
                    
                    # 每100条提交一次
                    if stats["success"] % 100 == 0:
                        session.commit()
                        logger.info(f"    已导入 {stats['success']} 条记录...")
                
                except Exception as e:
                    stats["fail"] += 1
                    logger.error(f"    第 {idx + 2} 行导入失败: {e}")
                    continue
            
            # 提交该sheet的数据
            session.commit()
            logger.info(f"  Sheet '{sheet_name}' 导入完成: 成功 {stats['success']}, 失败 {stats['fail']}, 跳过 {stats['skipped']}")
        
        return stats
    
    except Exception as e:
        session.rollback()
        logger.error(f"  导入文件失败: {e}")
        raise


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("血压会话数据导入工具")
    logger.info("=" * 60)
    
    # 获取数据库连接
    try:
        db_url = settings.DB_URI
        sync_db_url = ensure_psycopg3_sync_url(db_url)
        engine = create_engine(sync_db_url, echo=False)
        logger.info("✓ 数据库连接成功")
    except Exception as e:
        logger.error(f"✗ 数据库连接失败: {e}")
        sys.exit(1)
    
    # 创建表
    try:
        create_table_if_not_exists(engine)
    except Exception as e:
        logger.error(f"✗ 创建表失败: {e}")
        sys.exit(1)
    
    # 创建会话
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 定义Excel文件路径
        data_dir = project_root / "static" / "rag_source" / "uat_data"
        excel_lsk = data_dir / "4.1 lsk_副本.xlsx"
        excel_sh1128 = data_dir / "sh-1128_副本.xlsx"
        
        # 检查文件是否存在
        if not excel_lsk.exists():
            logger.error(f"✗ 文件不存在: {excel_lsk}")
            sys.exit(1)
        if not excel_sh1128.exists():
            logger.error(f"✗ 文件不存在: {excel_sh1128}")
            sys.exit(1)
        
        total_stats = {"success": 0, "fail": 0, "skipped": 0}
        
        # 导入第一个文件
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"导入文件: {excel_lsk.name}")
        logger.info("=" * 60)
        stats1 = import_from_excel_lsk(session, excel_lsk, excel_lsk.name)
        total_stats["success"] += stats1["success"]
        total_stats["fail"] += stats1["fail"]
        total_stats["skipped"] += stats1["skipped"]
        
        # 导入第二个文件
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"导入文件: {excel_sh1128.name}")
        logger.info("=" * 60)
        stats2 = import_from_excel_sh1128(session, excel_sh1128, excel_sh1128.name)
        total_stats["success"] += stats2["success"]
        total_stats["fail"] += stats2["fail"]
        total_stats["skipped"] += stats2["skipped"]
        
        # 打印总结果
        logger.info("")
        logger.info("=" * 60)
        logger.info("导入结果汇总")
        logger.info("=" * 60)
        logger.info(f"总计 - 成功: {total_stats['success']} 条")
        logger.info(f"总计 - 失败: {total_stats['fail']} 条")
        logger.info(f"总计 - 跳过: {total_stats['skipped']} 条（空行）")
        logger.info("=" * 60)
        
        if total_stats["fail"] > 0:
            logger.warning(f"⚠️  警告：有 {total_stats['fail']} 条数据导入失败")
            sys.exit(1)
        else:
            logger.info("✓ 数据导入完成")
            sys.exit(0)
    
    except KeyboardInterrupt:
        logger.warning("\n⚠️  用户中断操作")
        session.rollback()
        sys.exit(130)
    
    except Exception as e:
        logger.error(f"\n✗ 导入失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        session.rollback()
        sys.exit(1)
    
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
