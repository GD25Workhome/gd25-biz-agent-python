"""
工具包装器：自动注入 tokenId
"""
import json
import logging
from typing import Any, Dict, Optional
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun

from backend.domain.tools.context import get_token_id

logger = logging.getLogger(__name__)


class TokenInjectedTool(BaseTool):
    """
    工具包装器：在工具调用时自动注入 tokenId
    
    工作原理：
    1. 包装原始工具，保持所有属性和行为
    2. 在 invoke/ainvoke 时，从上下文获取 tokenId
    3. 自动将 tokenId 注入到工具参数中
    4. 调用原始工具函数
    """
    
    def __init__(
        self,
        tool: BaseTool,
        token_id_param_name: str = "token_id",
        require_token: bool = True
    ):
        """
        初始化工具包装器
        
        Args:
            tool: 原始工具实例
            token_id_param_name: tokenId 参数名称（默认为 "token_id"）
            require_token: 是否要求 tokenId 必须存在（默认 True）
        """
        # 先调用 super().__init__，然后再设置属性，确保属性不会被覆盖
        super().__init__(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )
        
        # 在 super().__init__ 之后设置属性，确保它们不会被覆盖
        self._original_tool = tool
        self._token_id_param_name = token_id_param_name
        self._require_token = require_token
    
    @property
    def original_tool(self) -> BaseTool:
        """获取原始工具实例"""
        return self._original_tool
    
    def _inject_token_id(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        注入 tokenId 到工具参数中
        
        Args:
            tool_input: 工具输入参数字典
            
        Returns:
            注入 tokenId 后的参数字典
            
        Raises:
            ValueError: 如果 require_token=True 但 tokenId 不存在
        """
        # 从上下文获取 tokenId
        token_id = get_token_id()
        
        logger.debug(
            f"[TokenInjectedTool] 开始注入 tokenId - tool_name={self.name}, "
            f"token_id={token_id}, require_token={self._require_token}"
        )
        
        # 检查 tokenId 是否存在
        if token_id is None:
            if self._require_token:
                logger.error(
                    f"[TokenInjectedTool] tokenId 缺失 - tool_name={self.name}, "
                    f"require_token={self._require_token}"
                )
                raise ValueError(
                    f"工具 {self.name} 需要 tokenId，但上下文中未设置。"
                    f"请确保在调用工具前使用 TokenContext 设置 tokenId。"
                )
            else:
                # 如果不需要 tokenId，直接返回原参数
                logger.debug(
                    f"[TokenInjectedTool] tokenId 缺失但不需要，跳过注入 - tool_name={self.name}"
                )
                return tool_input
        
        # 检查参数中是否已经存在 token_id（避免重复注入）
        if self._token_id_param_name in tool_input:
            # 如果已存在，使用已有的值（LLM 可能已经传递）
            # 但记录警告，说明应该依赖自动注入
            logger.warning(
                f"[TokenInjectedTool] 工具 {self.name} 的参数中已存在 {self._token_id_param_name}，"
                f"将使用自动注入的值覆盖。原值={tool_input[self._token_id_param_name]}, 新值={token_id}"
            )
        
        # 注入 tokenId
        tool_input[self._token_id_param_name] = token_id
        logger.info(
            f"[TokenInjectedTool] tokenId 注入完成 - tool_name={self.name}, "
            f"token_id={token_id}"
        )
        
        return tool_input
    
    def _run(
        self,
        tool_input: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """
        同步运行工具（抽象方法实现）
        
        这是 BaseTool 要求的抽象方法，我们通过调用 invoke 来实现
        """
        # 将字符串输入转换为字典格式（如果需要）
        if isinstance(tool_input, str):
            # 尝试解析为 JSON，如果失败则作为普通字符串处理
            try:
                tool_input = json.loads(tool_input)
            except (json.JSONDecodeError, ValueError):
                # 如果不是 JSON，作为普通字符串处理
                tool_input = {"input": tool_input}
        
        # 调用 invoke 方法
        return self.invoke(tool_input, run_manager=run_manager, **kwargs)
    
    async def _arun(
        self,
        tool_input: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """
        异步运行工具（抽象方法实现）
        
        这是 BaseTool 要求的抽象方法，我们通过调用 ainvoke 来实现
        """
        # 将字符串输入转换为字典格式（如果需要）
        if isinstance(tool_input, str):
            # 尝试解析为 JSON，如果失败则作为普通字符串处理
            try:
                tool_input = json.loads(tool_input)
            except (json.JSONDecodeError, ValueError):
                # 如果不是 JSON，作为普通字符串处理
                tool_input = {"input": tool_input}
        
        # 调用 ainvoke 方法
        return await self.ainvoke(tool_input, run_manager=run_manager, **kwargs)
    
    def invoke(
        self,
        tool_input: Any,
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """
        同步调用工具（自动注入 tokenId）
        
        重写 invoke 方法，在调用原始工具之前注入 tokenId
        """
        # 如果 tool_input 是字典，直接注入 tokenId
        if isinstance(tool_input, dict):
            injected_input = self._inject_token_id(tool_input)
            return self._original_tool.invoke(injected_input, run_manager=run_manager, **kwargs)
        else:
            # 对于其他类型的输入，直接调用原始工具
            return self._original_tool.invoke(tool_input, run_manager=run_manager, **kwargs)
    
    async def ainvoke(
        self,
        tool_input: Any,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs: Any
    ) -> Any:
        """
        异步调用工具（自动注入 tokenId）
        
        重写 ainvoke 方法，在调用原始工具之前注入 tokenId
        """
        # 处理工具输入并注入 tokenId
        if isinstance(tool_input, dict):
            if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
                # LangChain 工具调用格式：提取 args
                args_dict = tool_input['args'].copy()
                injected_args = self._inject_token_id(args_dict)
                logger.debug(
                    f"[TokenInjectedTool] tokenId 注入完成（工具调用格式） - tool_name={self.name}"
                )
                # 更新 tool_input 中的 args
                tool_input = {**tool_input, 'args': injected_args}
            else:
                # 直接参数字典格式
                injected_input = self._inject_token_id(tool_input.copy())
                logger.debug(
                    f"[TokenInjectedTool] tokenId 注入完成（参数字典格式） - tool_name={self.name}"
                )
                tool_input = injected_input
        
        # 执行工具
        try:
            result = await self._original_tool.ainvoke(tool_input, run_manager=run_manager, **kwargs)
            logger.info(
                f"[TokenInjectedTool] 工具调用成功 - tool_name={self.name}"
            )
            return result
        except Exception as e:
            logger.error(
                f"[TokenInjectedTool] 工具调用失败 - tool_name={self.name}, "
                f"error_type={type(e).__name__}, error={str(e)}",
                exc_info=True
            )
            raise
    
    def __getattr__(self, name: str) -> Any:
        """
        代理原始工具的其他属性
        
        注意：避免访问已经在 __init__ 中设置的属性，防止递归
        """
        # 避免递归：使用 __dict__ 检查属性是否存在
        if name in self.__dict__:
            return self.__dict__[name]
        # 否则从原始工具获取
        try:
            return getattr(self._original_tool, name)
        except AttributeError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


def wrap_tools_with_token_context(
    tools: list[BaseTool],
    token_id_param_name: str = "token_id",
    require_token: bool = True
) -> list[BaseTool]:
    """
    批量包装工具，使其支持自动注入 tokenId
    
    Args:
        tools: 原始工具列表
        token_id_param_name: tokenId 参数名称（默认为 "token_id"）
        require_token: 是否要求 tokenId 必须存在（默认 True）
        
    Returns:
        包装后的工具列表
    """
    wrapped_tools = []
    for tool in tools:
        # 检查工具是否已经是包装后的工具
        if isinstance(tool, TokenInjectedTool):
            # 如果已经是包装后的工具，直接使用
            wrapped_tools.append(tool)
        else:
            # 包装工具
            wrapped_tool = TokenInjectedTool(
                tool=tool,
                token_id_param_name=token_id_param_name,
                require_token=require_token
            )
            wrapped_tools.append(wrapped_tool)
    
    return wrapped_tools

