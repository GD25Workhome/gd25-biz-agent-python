"""
insert_data_to_vector_db 节点实现
负责将 embedding 节点生成的向量值存储到数据库的 embedding_record 表中，并更新记录状态
"""
import logging
import traceback
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.models.embedding_record import EmbeddingRecord

logger = logging.getLogger(__name__)


class InsertDataToVectorDbNode(BaseFunctionNode):
    """insert_data_to_vector_db 节点"""
    
    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识key"""
        return "insert_data_to_vector_db"
    
    async def _get_embedding_record(
        self,
        session: AsyncSession,
        embedding_records_id: str,
    ) -> Optional[EmbeddingRecord]:
        """
        根据 ID 查询 embedding_record
        
        Args:
            session: 数据库会话
            embedding_records_id: embedding_record 的 ID
            
        Returns:
            Optional[EmbeddingRecord]: 查询结果，如果不存在返回 None
        """
        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.id == embedding_records_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def execute(self, state: FlowState) -> FlowState:
        """
        执行 insert_data_to_vector_db 节点逻辑
        
        Args:
            state: 流程状态对象
            
        Returns:
            FlowState: 更新后的状态对象
            
        Raises:
            ValueError: 如果必要字段缺失或记录不存在
            Exception: 如果数据库操作失败
        """
        try:
            # 1. 读取输入数据
            edges_var = state.get("edges_var", {})
            embedding_value = edges_var.get("embedding_value")
            
            prompt_vars = state.get("prompt_vars", {})
            embedding_records_id = prompt_vars.get("embedding_records_id")
            
            # 2. 验证数据完整性
            if embedding_value is None:
                raise ValueError("edges_var.embedding_value 缺失，无法继续执行")
            if not embedding_records_id:
                raise ValueError("prompt_vars.embedding_records_id 缺失，无法继续执行")
            
            # 3. 验证 embedding_value 格式
            if not isinstance(embedding_value, (list, tuple)):
                raise TypeError(
                    f"embedding_value 格式错误: 期望 list 或 tuple，实际类型: {type(embedding_value)}"
                )
            
            # 4. 获取数据库会话
            session_factory = get_session_factory()
            async with session_factory() as session:
                # 5. 查询记录
                embedding_record = await self._get_embedding_record(
                    session, embedding_records_id
                )
                if not embedding_record:
                    raise ValueError(
                        f"未找到 embedding_record: id={embedding_records_id}"
                    )
                
                # 6. 更新字段
                # 将列表转换为适合数据库存储的格式
                # 如果使用 pgvector，SQLAlchemy 会自动处理列表到 Vector 的转换
                embedding_record.embedding_value = list(embedding_value)
                embedding_record.generation_status = 1  # 成功
                embedding_record.failure_reason = None
                
                # 7. 提交事务
                await session.commit()
                
                logger.info(
                    f"成功更新 embedding_record: id={embedding_records_id}, "
                    f"generation_status=1, embedding_value维度={len(embedding_value)}"
                )
                
                # 8. 返回更新后的 state（不需要修改 state，直接返回）
                return state.copy()
                
        except Exception as e:
            # 异常处理：尝试更新状态为失败
            error_traceback = traceback.format_exc()
            logger.error(
                f"insert_data_to_vector_db 执行失败: {e}\n{error_traceback}",
                exc_info=True
            )
            
            # 如果能够获取到 embedding_records_id，尝试更新状态为失败
            try:
                prompt_vars = state.get("prompt_vars", {})
                embedding_records_id = prompt_vars.get("embedding_records_id")
                if embedding_records_id:
                    session_factory = get_session_factory()
                    async with session_factory() as session:
                        embedding_record = await self._get_embedding_record(
                            session, embedding_records_id
                        )
                        if embedding_record:
                            embedding_record.generation_status = -1  # 失败
                            embedding_record.failure_reason = error_traceback
                            await session.commit()
                            logger.warning(
                                f"已更新 embedding_record 状态为失败: id={embedding_records_id}"
                            )
            except Exception as update_error:
                logger.error(
                    f"更新失败状态时出错: {update_error}",
                    exc_info=True
                )
            
            # 抛出异常，中断流程
            raise
