"""
豆包 ChatOpenAI 包装类
支持在调用时自动传递 thinking 和 reasoning_effort 参数

重要说明：
- 直接继承 ChatOpenAI 而不是 BaseChatModel，避免 Pydantic 字段验证问题
- 直接接收所有参数，避免使用 model_dump() 的字段映射问题
- 使用私有属性（_thinking, _reasoning_effort）存储额外字段
- 通过重写 _generate 和 _agenerate 方法，在每次调用时自动添加 extra_body
"""
import logging
from typing import Dict, Any, Optional, List, Union
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


class DoubaoChatOpenAI(ChatOpenAI):
    """支持豆包 thinking 和 reasoning_effort 参数的 ChatOpenAI 包装类
    
    直接继承 ChatOpenAI，避免 Pydantic 字段验证问题。
    直接接收所有参数，避免使用 model_dump() 的字段映射问题。
    通过重写 _generate 和 _agenerate 方法，在每次调用时自动添加 extra_body。
    """
    
    def __init__(
        self,
        model: str,
        temperature: Optional[float] = None,
        openai_api_key: Optional[str] = None,
        openai_api_base: Optional[str] = None,
        timeout: Optional[int] = None,
        thinking: Optional[Dict[str, str]] = None,
        reasoning_effort: Optional[str] = None,
        **kwargs
    ):
        """
        初始化包装类
        
        Args:
            model: 模型名称
            temperature: 温度参数
            openai_api_key: API 密钥
            openai_api_base: API 基础 URL
            timeout: 超时时间（秒）
            thinking: 思考模式配置
            reasoning_effort: 推理努力程度
            **kwargs: 其他 ChatOpenAI 参数
        """
        # 直接调用父类初始化，传入所有参数
        super().__init__(
            model=model,
            temperature=temperature,
            openai_api_key=openai_api_key,
            openai_api_base=openai_api_base,
            timeout=timeout,
            **kwargs
        )
        
        # 使用 object.__setattr__ 设置私有属性，绕过 Pydantic 验证
        object.__setattr__(self, '_thinking', thinking)
        object.__setattr__(self, '_reasoning_effort', reasoning_effort)
    
    def _prepare_extra_body(self) -> Optional[Dict[str, Any]]:
        """准备 extra_body 参数"""
        extra_body = {}
        
        if self._thinking is not None:
            extra_body["thinking"] = self._thinking
        
        if self._reasoning_effort is not None:
            extra_body["reasoning_effort"] = self._reasoning_effort
        
        return extra_body if extra_body else None
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        """同步生成，自动添加 extra_body"""
        extra_body = self._prepare_extra_body()
        
        # 如果 kwargs 中已有 extra_body，合并它们
        if extra_body and "extra_body" in kwargs:
            existing_extra_body = kwargs.pop("extra_body")
            if isinstance(existing_extra_body, dict):
                extra_body.update(existing_extra_body)
        
        # 传递 extra_body 给底层 LLM
        if extra_body:
            kwargs["extra_body"] = extra_body
        
        logger.debug(
            f"调用 LLM (thinking={self._thinking}, reasoning_effort={self._reasoning_effort})"
        )
        
        # 调用父类的 _generate 方法
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ):
        """异步生成，自动添加 extra_body"""
        extra_body = self._prepare_extra_body()
        
        # 如果 kwargs 中已有 extra_body，合并它们
        if extra_body and "extra_body" in kwargs:
            existing_extra_body = kwargs.pop("extra_body")
            if isinstance(existing_extra_body, dict):
                extra_body.update(existing_extra_body)
        
        # 传递 extra_body 给底层 LLM
        if extra_body:
            kwargs["extra_body"] = extra_body
        
        logger.debug(
            f"异步调用 LLM (thinking={self._thinking}, reasoning_effort={self._reasoning_effort})"
        )
        
        # 调用父类的 _agenerate 方法
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
