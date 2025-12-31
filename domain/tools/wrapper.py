"""
工具包装器：自动注入 tokenId
"""
from typing import Any, Dict, Optional
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from langchain_core.messages import ToolMessage

from domain.tools.context import get_token_id
import logging

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
        
        # 保存工具名称，避免在 __getattr__ 中访问时触发递归
        self._tool_name = tool.name
    
    @property
    def original_tool(self) -> BaseTool:
        """获取原始工具实例"""
        # 从 __dict__ 直接获取，避免触发 __getattr__
        return self.__dict__.get('_original_tool')
    
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
        
        # 获取配置参数（直接从 __dict__ 获取，避免触发 __getattr__）
        token_id_param_name = self.__dict__.get('_token_id_param_name', 'token_id')
        require_token = self.__dict__.get('_require_token', True)
        tool_name = self.__dict__.get('_tool_name', 'unknown_tool')
        
        logger.info(
            f"[TokenInjectedTool] 开始注入 tokenId - tool_name={tool_name}, "
            f"token_id={token_id}, require_token={require_token}, tool_input={tool_input}"
        )
        
        # 检查 tokenId 是否存在
        if token_id is None:
            if require_token:
                logger.error(
                    f"[TokenInjectedTool] tokenId 缺失 - tool_name={tool_name}, "
                    f"require_token={require_token}"
                )
                raise ValueError(
                    f"工具 {tool_name} 需要 tokenId，但上下文中未设置。"
                    f"请确保在调用工具前使用 TokenContext 设置 tokenId。"
                )
            else:
                # 如果不需要 tokenId，直接返回原参数
                logger.debug(
                    f"[TokenInjectedTool] tokenId 缺失但不需要，跳过注入 - tool_name={tool_name}"
                )
                return tool_input
        
        # 检查参数中是否已经存在 token_id（避免重复注入）
        if token_id_param_name in tool_input:
            # 如果已存在，使用已有的值（LLM 可能已经传递）
            # 但记录警告，说明应该依赖自动注入
            logger.warning(
                f"[TokenInjectedTool] 工具 {tool_name} 的参数中已存在 {token_id_param_name}，"
                f"将使用自动注入的值覆盖。原值={tool_input[token_id_param_name]}, 新值={token_id}"
            )
        
        # 注入 tokenId
        tool_input[token_id_param_name] = token_id
        logger.info(
            f"[TokenInjectedTool] tokenId 注入完成 - tool_name={tool_name}, "
            f"token_id={token_id}, 注入后的参数={tool_input}"
        )
        
        return tool_input
    
    def _run(
        self,
        tool_input: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """
        同步运行工具（自动注入 tokenId）
        
        Args:
            tool_input: 工具输入（字符串格式）
            run_manager: 回调管理器
            
        Returns:
            工具输出（字符串格式）
        """
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        # 直接调用原始工具的 _run
        return original_tool._run(tool_input, run_manager=run_manager)
    
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
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        
        # 如果 tool_input 是字典，直接注入 tokenId
        if isinstance(tool_input, dict):
            injected_input = self._inject_token_id(tool_input)
            return original_tool.invoke(injected_input, run_manager=run_manager, **kwargs)
        else:
            # 对于其他类型的输入，先调用原始工具解析，然后再注入
            # 这里我们直接调用原始工具，让它处理输入解析
            # 但这样可能无法注入 tokenId，所以最好确保 tool_input 是字典
            return original_tool.invoke(tool_input, run_manager=run_manager, **kwargs)
    
    def _invoke(
        self,
        tool_input: Dict[str, Any],
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> Any:
        """
        同步调用工具（自动注入 tokenId）
        """
        # 注入 tokenId
        injected_input = self._inject_token_id(tool_input)
        
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        # 调用原始工具的 _invoke
        return original_tool._invoke(injected_input, run_manager=run_manager)
    
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
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        tool_name = self.__dict__.get('_tool_name', 'unknown_tool')
        
        # 记录工具调用开始
        logger.info(
            f"[TokenInjectedTool] 工具调用开始 - tool_name={tool_name}, "
            f"tool_input_type={type(tool_input).__name__}, tool_input={tool_input}"
        )
        
        try:
            # 如果 tool_input 是字典，需要处理不同的格式
            if isinstance(tool_input, dict):
                # 检查是否是 LangChain 工具调用格式（包含 'args' 字段）
                if 'args' in tool_input and isinstance(tool_input.get('args'), dict):
                    # LangChain 工具调用格式：{'name': '...', 'args': {...}, 'id': '...', 'type': '...'}
                    # 需要从 args 中提取参数，注入 tokenId
                    # 注意：LangChain 的工具期望直接接收参数字典，而不是包含 'args' 的字典
                    args_dict = tool_input['args'].copy()
                    logger.debug(
                        f"[TokenInjectedTool] 检测到工具调用格式 - tool_name={tool_name}, "
                        f"原始args={args_dict}"
                    )
                    injected_args = self._inject_token_id(args_dict)
                    
                    # 直接传递注入后的参数字典给原始工具
                    # LangChain 的工具会正确处理参数字典，并返回字符串
                    # LangGraph 的 tool_node 会自动将字符串包装成 ToolMessage
                    injected_input = injected_args
                    
                    logger.info(
                        f"[TokenInjectedTool] tokenId 注入完成（工具调用格式） - tool_name={tool_name}, "
                        f"原始args={tool_input['args']}, 注入后args={injected_args}"
                    )
                else:
                    # 直接参数字典格式：{'systolic': 120, 'diastolic': 75, ...}
                    injected_input = self._inject_token_id(tool_input.copy())
                    logger.debug(
                        f"[TokenInjectedTool] tokenId 注入完成（参数字典格式） - tool_name={tool_name}, "
                        f"injected_input={injected_input}"
                    )
                
                result = await original_tool.ainvoke(injected_input, run_manager=run_manager, **kwargs)
                logger.info(
                    f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
                    f"result_type={type(result).__name__}, result_length={len(str(result)) if isinstance(result, str) else 'N/A'}"
                )
                
                # 如果结果是字符串，且 tool_input 包含 'id' 字段（LangGraph 的 tool_node 调用格式）
                # 需要返回 ToolMessage 而不是字符串
                # 注意：LangGraph 的 tool_node 在某些情况下可能不会自动包装字符串
                if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
                    # LangGraph 的 tool_node 调用格式，需要返回 ToolMessage
                    tool_call_id = tool_input.get('id', '')
                    tool_message = ToolMessage(
                        content=result,
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    logger.debug(
                        f"[TokenInjectedTool] 将字符串结果包装成 ToolMessage - tool_name={tool_name}, "
                        f"tool_call_id={tool_call_id}"
                    )
                    return tool_message
                
                return result
            else:
                # 对于其他类型的输入，直接调用原始工具
                logger.warning(
                    f"[TokenInjectedTool] tool_input 不是字典类型，可能无法注入 tokenId - "
                    f"tool_name={tool_name}, tool_input_type={type(tool_input).__name__}"
                )
                result = await original_tool.ainvoke(tool_input, run_manager=run_manager, **kwargs)
                logger.info(
                    f"[TokenInjectedTool] 工具调用成功 - tool_name={tool_name}, "
                    f"result_type={type(result).__name__}"
                )
                
                # 如果结果是字符串，且 tool_input 包含 'id' 字段（LangGraph 的 tool_node 调用格式）
                if isinstance(result, str) and isinstance(tool_input, dict) and 'id' in tool_input:
                    tool_call_id = tool_input.get('id', '')
                    tool_message = ToolMessage(
                        content=result,
                        tool_call_id=tool_call_id,
                        name=tool_name
                    )
                    logger.debug(
                        f"[TokenInjectedTool] 将字符串结果包装成 ToolMessage - tool_name={tool_name}, "
                        f"tool_call_id={tool_call_id}"
                    )
                    return tool_message
                
                return result
        except Exception as e:
            logger.error(
                f"[TokenInjectedTool] 工具调用失败 - tool_name={tool_name}, "
                f"error_type={type(e).__name__}, error={str(e)}",
                exc_info=True
            )
            raise
    
    async def _ainvoke(
        self,
        tool_input: Dict[str, Any],
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> Any:
        """
        异步调用工具（自动注入 tokenId）
        """
        # 注入 tokenId
        injected_input = self._inject_token_id(tool_input)
        
        # 从 __dict__ 直接获取 _original_tool，避免触发 __getattr__
        original_tool = self.__dict__.get('_original_tool')
        # 调用原始工具的 _ainvoke
        return await original_tool._ainvoke(injected_input, run_manager=run_manager)
    
    def __getattr__(self, name: str) -> Any:
        """
        代理原始工具的其他属性
        
        注意：避免访问已经在 __init__ 中设置的属性，防止递归
        """
        # 避免递归：使用 __dict__ 检查属性是否存在，而不是 hasattr
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

