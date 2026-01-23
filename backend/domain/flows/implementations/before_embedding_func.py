"""
before_embedding_func 节点实现
负责处理词干提取后的数据，插入到 embedding 表，并生成 embedding_str
"""
import json
import logging
import traceback
from typing import Any, Dict, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.models.blood_pressure_session import (
    BloodPressureSessionRecord,
)
from backend.infrastructure.database.models.embedding_record import EmbeddingRecord

logger = logging.getLogger(__name__)


class BeforeEmbeddingFuncNode(BaseFunctionNode):
    """before_embedding_func 节点"""
    
    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识key"""
        return "before_embedding_func"
    
    def _format_embedding_str(
        self,
        scene_summary: str,
        optimization_question: str,
        ai_response: str,
    ) -> str:
        """
        格式化 embedding_str
        
        Args:
            scene_summary: 场景摘要
            optimization_question: 优化后的问题
            ai_response: AI回复
            
        Returns:
            str: 格式化后的字符串
        """
        # 去除首尾空白
        scene_summary = (scene_summary or "").strip()
        optimization_question = (optimization_question or "").strip()
        ai_response = (ai_response or "").strip()
        
        # 按照格式拼接
        parts = []
        if scene_summary:
            parts.append(scene_summary)
        if optimization_question:
            parts.append(f"问题：{optimization_question}")
        if ai_response:
            parts.append(f"回复：{ai_response}")
        
        return "\n".join(parts)
    
    async def _get_blood_pressure_session_record(
        self,
        session: AsyncSession,
        source_id: str,
    ) -> Optional[BloodPressureSessionRecord]:
        """
        根据 source_id 查询 BloodPressureSessionRecord
        
        Args:
            session: 数据库会话
            source_id: 数据源记录ID
            
        Returns:
            Optional[BloodPressureSessionRecord]: 查询结果，如果不存在返回 None
        """
        stmt = select(BloodPressureSessionRecord).where(
            BloodPressureSessionRecord.id == source_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _calculate_next_version(
        self,
        session: AsyncSession,
        message_id: Optional[str],
    ) -> int:
        """
        计算下一个版本号
        
        Args:
            session: 数据库会话
            message_id: 消息ID
            
        Returns:
            int: 下一个版本号（从0开始）
        """
        if not message_id:
            # 如果 message_id 为空，返回 0
            return 0
        
        # 查询该 message_id 的最大版本号
        stmt = (
            select(func.max(EmbeddingRecord.version))
            .where(EmbeddingRecord.message_id == message_id)
        )
        result = await session.execute(stmt)
        max_version = result.scalar()
        
        # 如果不存在记录，返回 0；否则返回 max_version + 1
        if max_version is None:
            return 0
        return max_version + 1
    
    async def _create_embedding_record(
        self,
        session: AsyncSession,
        scene_summary: str,
        optimization_question: str,
        input_tags: list,
        response_tags: list,
        ai_response: str,
        message_id: Optional[str],
        version: int,
        source_table_name: str,
        source_record_id: str,
        trace_id: Optional[str] = None,
    ) -> EmbeddingRecord:
        """
        创建 embedding 记录
        
        Args:
            session: 数据库会话
            scene_summary: 场景摘要
            optimization_question: 优化后的问题
            input_tags: 输入标签列表
            response_tags: 响应标签列表
            ai_response: AI回复内容
            message_id: 消息ID
            version: 版本号
            source_table_name: 数据来源表名
            source_record_id: 数据来源记录ID
            trace_id: Trace ID（用于可观测性追踪）
            
        Returns:
            EmbeddingRecord: 创建的记录
        """
        record = EmbeddingRecord(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            ai_response=ai_response,
            message_id=message_id,
            trace_id=trace_id,
            version=version,
            is_published=False,
            source_table_name=source_table_name,
            source_record_id=source_record_id,
            generation_status=0,  # 进行中
            failure_reason=None,
        )
        
        # 设置标签（转换为 JSON 字符串）
        record.set_input_tags_list(input_tags)
        record.set_response_tags_list(response_tags)
        
        session.add(record)
        await session.flush()  # 刷新以获取 ID
        await session.refresh(record)  # 刷新以获取完整数据
        
        return record
    
    async def execute(self, state: FlowState) -> FlowState:
        """
        执行 before_embedding_func 节点逻辑
        
        Args:
            state: 流程状态对象
            
        Returns:
            FlowState: 更新后的状态对象
            
        Raises:
            ValueError: 如果必要字段缺失
            Exception: 如果数据库操作失败
        """
        try:
            # 1. 读取 edges_var 中的数据
            edges_var = state.get("edges_var", {})
            scene_summary = edges_var.get("scene_summary", "")
            optimization_question = edges_var.get("optimization_question", "")
            input_tags = edges_var.get("input_tags", [])
            response_tags = edges_var.get("response_tags", [])
            
            # 2. 读取 prompt_vars 中的数据源信息
            prompt_vars = state.get("prompt_vars", {})
            source_id = prompt_vars.get("source_id")
            source_table_name = prompt_vars.get("source_table_name")
            
            # 3. 验证必要字段
            if not source_id:
                raise ValueError("prompt_vars.source_id 缺失，无法继续执行")
            if not source_table_name:
                raise ValueError("prompt_vars.source_table_name 缺失，无法继续执行")
            
            # 4. 获取数据库会话
            session_factory = get_session_factory()
            async with session_factory() as session:
                # 5. 查询 BloodPressureSessionRecord
                bp_record = await self._get_blood_pressure_session_record(
                    session, source_id
                )
                if not bp_record:
                    raise ValueError(f"未找到 source_id={source_id} 的记录")
                
                message_id = bp_record.message_id
                ai_response = bp_record.new_session_response or ""
                
                # 6. 计算版本号
                version = await self._calculate_next_version(session, message_id)
                
                # 7. 从 state 中获取 trace_id
                trace_id = state.get("trace_id")
                
                # 8. 创建 embedding 记录
                embedding_record = await self._create_embedding_record(
                    session=session,
                    scene_summary=scene_summary,
                    optimization_question=optimization_question,
                    input_tags=input_tags,
                    response_tags=response_tags,
                    ai_response=ai_response,
                    message_id=message_id,
                    version=version,
                    source_table_name=source_table_name,
                    source_record_id=source_id,
                    trace_id=trace_id,
                )
                
                # 9. 提交事务
                await session.commit()
                
                logger.info(
                    f"成功创建 embedding 记录: id={embedding_record.id}, "
                    f"message_id={message_id}, trace_id={trace_id}, version={version}"
                )
                
                # 10. 生成 embedding_str
                embedding_str = self._format_embedding_str(
                    scene_summary=scene_summary,
                    optimization_question=optimization_question,
                    ai_response=ai_response,
                )
                
                # 11. 更新 state
                new_state = state.copy()
                if "edges_var" not in new_state:
                    new_state["edges_var"] = {}
                new_state["edges_var"]["embedding_str"] = embedding_str
                
                if "prompt_vars" not in new_state:
                    new_state["prompt_vars"] = {}
                new_state["prompt_vars"]["embedding_records_id"] = embedding_record.id
                
                logger.info(f"成功生成 embedding_str，长度={len(embedding_str)}")
                
                return new_state
                
        except Exception as e:
            # 记录完整的异常堆栈信息
            error_traceback = traceback.format_exc()
            logger.error(
                f"before_embedding_func 执行失败: {e}\n{error_traceback}",
                exc_info=True
            )
            
            # 抛出异常，中断流程
            raise
