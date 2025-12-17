"""
LLM 调用日志仓储
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from infrastructure.database.repository.base import BaseRepository
from infrastructure.database.models.llm_call_log import LlmCallLog, LlmCallMessage


class LlmCallLogRepository(BaseRepository[LlmCallLog]):
    """LLM 调用日志仓储类"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化 LLM 调用日志仓储
        
        Args:
            session: 数据库会话
        """
        super().__init__(session, LlmCallLog)
    
    async def get_by_call_id(self, call_id: str) -> Optional[LlmCallLog]:
        """
        根据调用唯一ID查询日志
        
        Args:
            call_id: 调用唯一ID
        
        Returns:
            LlmCallLog 或 None
        """
        result = await self.session.execute(
            select(LlmCallLog).where(LlmCallLog.call_id == call_id)
        )
        return result.scalar_one_or_none()
    
    async def create_call_log(
        self,
        call_id: str,
        model: str,
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
        prompt_snapshot: Optional[str],
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_key: Optional[str] = None,
        started_at: Optional[datetime] = None,
    ) -> LlmCallLog:
        """
        创建调用日志记录
        
        Args:
            call_id: 调用唯一ID
            model: 模型名称
            temperature: 温度参数
            top_p: 采样参数
            max_tokens: 最大输出 tokens
            prompt_snapshot: 提示词快照
            trace_id: 链路追踪ID
            session_id: 会话ID
            conversation_id: 对话ID
            user_id: 用户ID
            agent_key: 智能体标识
            started_at: 调用开始时间
        """
        started_time = started_at or datetime.utcnow()
        instance = LlmCallLog(
            call_id=call_id,
            trace_id=trace_id,
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            agent_key=agent_key,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            prompt_snapshot=prompt_snapshot,
            created_at=started_time,
        )
        self.session.add(instance)
        await self.session.flush()
        return instance
    
    async def mark_success(
        self,
        call_id: str,
        response_snapshot: Optional[str],
        latency_ms: Optional[int],
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        total_tokens: Optional[int],
        finished_at: Optional[datetime] = None,
    ) -> None:
        """
        标记调用成功
        
        Args:
            call_id: 调用唯一ID
            response_snapshot: 响应快照
            latency_ms: 耗时（毫秒）
            prompt_tokens: 提示 tokens
            completion_tokens: 生成 tokens
            total_tokens: 总 tokens
            finished_at: 完成时间
        """
        record = await self.get_by_call_id(call_id)
        if not record:
            return
        
        record.response_snapshot = response_snapshot
        record.latency_ms = latency_ms
        record.prompt_tokens = prompt_tokens
        record.completion_tokens = completion_tokens
        record.total_tokens = total_tokens
        record.success = True
        record.finished_at = finished_at or datetime.utcnow()
        await self.session.flush()
    
    async def mark_failure(
        self,
        call_id: str,
        error_code: Optional[str],
        error_message: Optional[str],
        latency_ms: Optional[int] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        """
        标记调用失败
        
        Args:
            call_id: 调用唯一ID
            error_code: 错误码
            error_message: 错误信息
            latency_ms: 耗时（毫秒）
            finished_at: 完成时间
        """
        record = await self.get_by_call_id(call_id)
        if not record:
            return
        
        record.success = False
        record.error_code = error_code
        record.error_message = error_message
        record.latency_ms = latency_ms
        record.finished_at = finished_at or datetime.utcnow()
        await self.session.flush()
    
    async def save_messages(
        self,
        call_id: str,
        messages: List[dict]
    ) -> None:
        """
        批量保存消息快照
        
        Args:
            call_id: 调用唯一ID
            messages: 消息列表，包含 role/content/token_estimate
        """
        if not messages:
            return
        
        for item in messages:
            message = LlmCallMessage(
                call_id=call_id,
                role=item.get("role") or "unknown",
                content=item.get("content") or "",
                token_estimate=item.get("token_estimate"),
            )
            self.session.add(message)
        await self.session.flush()
